from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path


class SafeJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal, numpy scalars, arrays, and paths."""

    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, Path):
            return str(o)
        if isinstance(o, set):
            return list(o)
        if hasattr(o, "isoformat") and callable(o.isoformat):
            try:
                return o.isoformat()
            except Exception:
                pass
        if hasattr(o, "item") and callable(o.item):
            try:
                return o.item()
            except Exception:
                pass
        if hasattr(o, "tolist") and callable(o.tolist):
            try:
                return o.tolist()
            except Exception:
                pass
        return super().default(o)