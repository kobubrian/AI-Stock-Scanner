import httpx

from app.config import get_settings

DEFAULT_TIMEOUT = 30.0


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True)


def has_polygon() -> bool:
    return bool(get_settings().polygon_api_key)


def has_alpaca() -> bool:
    s = get_settings()
    return bool(s.alpaca_api_key and s.alpaca_api_secret)


def has_finnhub() -> bool:
    return bool(get_settings().finnhub_api_key)


def has_fmp() -> bool:
    return bool(get_settings().fmp_api_key)


def has_benzinga() -> bool:
    return bool(get_settings().benzinga_api_key)


def has_openai() -> bool:
    return bool(get_settings().openai_api_key)
