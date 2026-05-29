"""Short-lived in-memory quote cache — avoids re-fetching on every tab switch."""

from __future__ import annotations

import time
from typing import Any

_TTL_SEC = 120.0
_cache: dict[str, tuple[dict[str, Any], float]] = {}


def get(symbol: str) -> dict[str, Any] | None:
    sym = symbol.upper()
    ent = _cache.get(sym)
    if not ent:
        return None
    data, at = ent
    if time.monotonic() - at > _TTL_SEC:
        _cache.pop(sym, None)
        return None
    return data


def set(symbol: str, data: dict[str, Any]) -> None:
    _cache[symbol.upper()] = (data, time.monotonic())


def get_many(symbols: list[str]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    hits: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for sym in symbols:
        key = sym.upper()
        row = get(key)
        if row:
            hits[key] = row
        else:
            missing.append(key)
    return hits, missing


def clear() -> None:
    _cache.clear()
