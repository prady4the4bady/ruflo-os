"""
PRADY TRADER — Trade journal.
SQLAlchemy-based persistent trade history.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from urllib.parse import urlparse

from sqlalchemy import (
    Column, DateTime, Float, Integer, String, Boolean,
    create_engine, text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import get_settings
from utils.time_utils import utc_now, utc_now_naive

logger = logging.getLogger("prady.execution.trade_journal")


def _is_local_database_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    return host in {"localhost", "127.0.0.1", "::1"}


class Base(DeclarativeBase):
    pass


class TradeRecord(Base):
    __tablename__ = "trade_journal"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    direction = Column(String(10), nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=False)
    leverage = Column(Integer, default=5)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    pnl = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    council_score = Column(Float, nullable=True)
    council_confidence = Column(Float, nullable=True)
    paper = Column(Boolean, default=True)
    entry_time = Column(DateTime, default=utc_now_naive)
    exit_time = Column(DateTime, nullable=True)
    exit_reason = Column(String(50), nullable=True)
    notes = Column(String(500), nullable=True)


class TradeJournal:
    """Persistent trade journal backed by PostgreSQL."""

    def __init__(self):
        settings = get_settings()
        try:
            db_url = settings.database_url
            engine_kwargs: dict = {"pool_pre_ping": True}
            # SQLite doesn't support pool_size / max_overflow
            if not db_url.startswith("sqlite"):
                engine_kwargs["pool_size"] = 5
                engine_kwargs["max_overflow"] = 10
            self._engine = create_engine(db_url, **engine_kwargs)
            Base.metadata.create_all(self._engine)
            self._session_factory = sessionmaker(bind=self._engine)
            self._available = True
            logger.info("Trade journal connected to database (%s)", db_url.split("@")[-1] if "@" in db_url else db_url)
        except Exception as exc:
            if _is_local_database_url(settings.database_url):
                logger.info("Local database unavailable, journal in memory-only mode: %s", exc)
            else:
                logger.warning("Database unavailable, journal in memory-only mode: %s", exc)
            self._available = False
            self._memory_journal: List[Dict] = []

    def record_entry(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        quantity: float,
        leverage: int = 5,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        council_score: Optional[float] = None,
        council_confidence: Optional[float] = None,
        paper: bool = True,
    ) -> int:
        """Record a trade entry. Returns the trade ID."""
        if not self._available:
            record = {
                "id": len(self._memory_journal) + 1,
                "symbol": symbol,
                "direction": direction,
                "entry_price": entry_price,
                "quantity": quantity,
                "leverage": leverage,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "council_score": council_score,
                "council_confidence": council_confidence,
                "paper": paper,
                "entry_time": utc_now().isoformat(),
            }
            self._memory_journal.append(record)
            trade_id: int = len(self._memory_journal)
            return trade_id

        with self._session_factory() as session:
            trade = TradeRecord(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                quantity=quantity,
                leverage=leverage,
                stop_loss=stop_loss,
                take_profit=take_profit,
                council_score=council_score,
                council_confidence=council_confidence,
                paper=paper,
            )
            session.add(trade)
            session.commit()
            db_trade_id: int = int(trade.id)  # type: ignore[arg-type]
            logger.info("Recorded entry #%d: %s %s @ %.2f", db_trade_id, direction, symbol, entry_price)
            return db_trade_id

    def record_exit(
        self,
        trade_id: int,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        exit_reason: str = "signal",
    ):
        """Record trade exit with PnL."""
        if not self._available:
            for rec in self._memory_journal:
                if rec.get("id") == trade_id:
                    rec["exit_price"] = exit_price
                    rec["pnl"] = pnl
                    rec["pnl_pct"] = pnl_pct
                    rec["exit_reason"] = exit_reason
                    rec["exit_time"] = utc_now().isoformat()
                    break
            return

        with self._session_factory() as session:
            trade = session.get(TradeRecord, trade_id)
            if trade:
                trade.exit_price = exit_price
                trade.pnl = pnl
                trade.pnl_pct = pnl_pct
                trade.exit_reason = exit_reason
                trade.exit_time = utc_now_naive()
                session.commit()
                logger.info("Recorded exit #%d: PnL=$%.2f (%.2f%%)", trade_id, pnl, pnl_pct)

    def get_recent_trades(self, n: int = 50, paper: Optional[bool] = None) -> List[Dict]:
        """Get the last N trades, optionally filtered by paper/live execution mode."""
        if not self._available:
            trades = self._memory_journal
            if paper is not None:
                trades = [trade for trade in trades if bool(trade.get("paper", True)) is paper]
            return trades[-n:]

        with self._session_factory() as session:
            query = session.query(TradeRecord)
            if paper is not None:
                query = query.filter(TradeRecord.paper.is_(paper))

            trades = query.order_by(TradeRecord.entry_time.desc()).limit(n).all()
            return [
                {
                    "id": t.id,
                    "symbol": t.symbol,
                    "direction": t.direction,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "quantity": t.quantity,
                    "pnl": t.pnl,
                    "pnl_pct": t.pnl_pct,
                    "paper": t.paper,
                    "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                    "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                    "exit_reason": t.exit_reason,
                }
                for t in reversed(trades)
            ]

    def get_stats(self, paper: Optional[bool] = None) -> Dict:
        """Aggregate trading statistics, optionally filtered by paper/live execution mode."""
        if not self._available:
            closed = [t for t in self._memory_journal if t.get("pnl") is not None]
            if paper is not None:
                closed = [trade for trade in closed if bool(trade.get("paper", True)) is paper]
            if not closed:
                return {"total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0}
            pnls = [t["pnl"] for t in closed]
            wins = sum(1 for p in pnls if p > 0)
            return {
                "total_trades": len(closed),
                "win_rate": wins / len(closed) if closed else 0.0,
                "total_pnl": sum(pnls),
                "avg_pnl": sum(pnls) / len(pnls),
                "best_trade": max(pnls),
                "worst_trade": min(pnls),
            }

        with self._session_factory() as session:
            total_query = session.query(TradeRecord).filter(TradeRecord.pnl.isnot(None))
            wins_query = session.query(TradeRecord).filter(TradeRecord.pnl > 0)
            if paper is not None:
                total_query = total_query.filter(TradeRecord.paper.is_(paper))
                wins_query = wins_query.filter(TradeRecord.paper.is_(paper))

            total = total_query.count()
            if total == 0:
                return {"total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0}

            wins = wins_query.count()

            stats_sql = "SELECT SUM(pnl), AVG(pnl), MAX(pnl), MIN(pnl) FROM trade_journal WHERE pnl IS NOT NULL"
            params: Dict[str, bool] = {}
            if paper is not None:
                stats_sql += " AND paper = :paper"
                params["paper"] = paper

            result = session.execute(text(stats_sql), params).fetchone()

            return {
                "total_trades": total,
                "win_rate": wins / total,
                "total_pnl": float(result[0] or 0),
                "avg_pnl": float(result[1] or 0),
                "best_trade": float(result[2] or 0),
                "worst_trade": float(result[3] or 0),
            }
