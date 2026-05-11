"""PRADY TRADER — Market intelligence surface."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QHBoxLayout, QScrollArea, QTextEdit, QVBoxLayout, QWidget

from desktop.widgets import MetricCard, colored_item, make_table, page_title, section_label


def _format_money(value: float | int | None) -> str:
    return f"${float(value or 0.0):,.2f}"


def _status_color(status: str) -> str:
    return {
        "healthy": "#00d4aa",
        "ok": "#00d4aa",
        "degraded": "#ff9800",
        "warning": "#ffcc00",
        "error": "#ff4444",
        "disabled": "#6e7681",
    }.get(str(status or "unknown").lower(), "#8b949e")


class MarketsPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        container = QWidget()
        self.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 8, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(page_title("Markets"))

        self._banner = QLabel("Waiting for market telemetry…")
        self._banner.setWordWrap(True)
        self._banner.setStyleSheet(
            "background: #121b25; border: 1px solid #223142; border-radius: 12px; "
            "padding: 10px 12px; color: #d6e3ef; font-size: 12px;"
        )
        layout.addWidget(self._banner)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self._btc = MetricCard("BTC")
        self._eth = MetricCard("ETH")
        self._market_cap = MetricCard("Market Cap")
        self._dominance = MetricCard("BTC Dom")
        self._sentiment = MetricCard("Fear & Greed")
        self._news_count = MetricCard("News Flow")
        for card in (
            self._btc,
            self._eth,
            self._market_cap,
            self._dominance,
            self._sentiment,
            self._news_count,
        ):
            metrics.addWidget(card)
        layout.addLayout(metrics)

        layout.addWidget(section_label("Live Prices"))
        self._prices_table = make_table(["Symbol", "Price"], max_h=280)
        layout.addWidget(self._prices_table)

        layout.addWidget(section_label("Trending Coins"))
        self._trending_table = make_table(["Symbol", "Rank", "Name"], max_h=220)
        layout.addWidget(self._trending_table)

        layout.addWidget(section_label("Provider Telemetry"))
        self._provider_table = make_table(["Provider", "Status", "Failures", "Rate"], max_h=240)
        layout.addWidget(self._provider_table)

        layout.addWidget(section_label("News Flow"))
        self._news_feed = QTextEdit()
        self._news_feed.setReadOnly(True)
        self._news_feed.setMinimumHeight(260)
        layout.addWidget(self._news_feed)
        layout.addStretch()

    def update_data(self, data: dict):
        market = data.get("market_overview", {}) or {}
        prices = data.get("prices", {}) or {}
        fng = data.get("fear_greed", {}) or {}
        news = list(data.get("news", []) or [])

        btc_price = prices.get("BTCUSDT") or market.get("btc_price")
        eth_price = prices.get("ETHUSDT") or market.get("eth_price")
        market_cap = float(market.get("total_market_cap", 0.0) or 0.0)
        change_24h = float(market.get("market_cap_change_24h", 0.0) or 0.0)
        dominance = float(market.get("btc_dominance", 0.0) or 0.0)
        sentiment_value = int(fng.get("value", 0) or 0)
        sentiment_label = str(fng.get("classification", "Unknown") or "Unknown")

        self._btc.set(_format_money(btc_price) if btc_price else "—")
        self._eth.set(_format_money(eth_price) if eth_price else "—")
        self._market_cap.set(f"${market_cap / 1_000_000_000_000:.2f}T" if market_cap else "—", f"{change_24h:+.1f}%", change_24h >= 0)
        self._dominance.set(f"{dominance:.1f}%" if dominance else "—")
        self._sentiment.set(f"{sentiment_value}", sentiment_label, sentiment_value >= 50)
        self._news_count.set(str(len(news)))

        summary = [
            f"Market cap change {change_24h:+.1f}%" if market_cap else "Market overview warming up",
            f"{len(prices)} live symbol(s)",
            f"{len(news)} article(s)",
            f"{len(data.get('provider_statuses', {}) or {})} provider(s) tracked",
        ]
        self._banner.setText("  |  ".join(summary))

        price_items = sorted(prices.items())
        self._prices_table.setRowCount(len(price_items))
        for row, (symbol, price) in enumerate(price_items):
            self._prices_table.setCellWidget(row, 0, QLabel(symbol))
            self._prices_table.setCellWidget(row, 1, QLabel(_format_money(price)))

        trending = list(data.get("trending", []) or [])[:12]
        self._trending_table.setRowCount(len(trending))
        for row, coin in enumerate(trending):
            symbol = str(coin.get("symbol") or coin.get("item", {}).get("symbol") or "—")
            rank = str(coin.get("market_cap_rank") or coin.get("item", {}).get("market_cap_rank") or "—")
            name = str(coin.get("name") or coin.get("item", {}).get("name") or symbol)
            self._trending_table.setCellWidget(row, 0, QLabel(symbol))
            self._trending_table.setCellWidget(row, 1, QLabel(rank))
            self._trending_table.setCellWidget(row, 2, QLabel(name))

        statuses = data.get("provider_statuses", {}) or {}
        rate_stats = data.get("rate_limiter_stats", {}) or {}
        providers = sorted(set(statuses.keys()) | {name for name in rate_stats.keys() if name != "default"})
        self._provider_table.setRowCount(len(providers))
        for row, provider in enumerate(providers):
            info = statuses.get(provider, {}) if isinstance(statuses.get(provider), dict) else {}
            rate = rate_stats.get(provider, {}) if isinstance(rate_stats.get(provider), dict) else {}
            status = str(info.get("status", "unknown") or "unknown")
            failures = int(info.get("consecutive_failures", 0) or 0)
            limit = rate.get("daily_limit")
            rate_text = "—"
            if rate:
                daily_limit = str(limit) if limit not in (None, 0) else "∞"
                rate_text = f"{int(rate.get('daily_used', 0) or 0)}/{daily_limit}"
            label = QLabel(str(info.get("display_name", provider.replace("_", " ").title())))
            self._provider_table.setCellWidget(row, 0, label)
            self._provider_table.setItem(row, 1, colored_item(status.upper(), _status_color(status)))
            self._provider_table.setCellWidget(row, 2, QLabel(str(failures)))
            self._provider_table.setCellWidget(row, 3, QLabel(rate_text))

        news_lines = []
        for article in news[:12]:
            title = str(article.get("title", "Untitled") or "Untitled")
            source = str(article.get("source") or article.get("_provider") or "feed")
            sentiment = str(article.get("sentiment", "neutral") or "neutral").lower()
            accent = "#00d4aa" if sentiment in {"positive", "bullish"} else "#ff4444" if sentiment in {"negative", "bearish"} else "#8ea2b6"
            news_lines.append(
                f"<span style='color:{accent}'>•</span> <span style='color:#f4f8fc'>{title}</span><br>"
                f"<span style='color:#8ea2b6'>{source}</span>"
            )
        self._news_feed.setHtml("<br><br>".join(news_lines) or "<span style='color:#8b949e'>No market headlines yet.</span>")