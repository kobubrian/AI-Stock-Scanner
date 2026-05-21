from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000,http://localhost:3001"

    database_url: str = "sqlite+aiosqlite:///./data/trading_scanner.db"

    # MVP: Alpaca + Finnhub (Polygon/FMP/Benzinga optional)
    polygon_api_key: str = ""
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    # Market data feed for snapshot: "" (Alpaca default), "sip" (full tape — needs data subscription),
    # "iex" (limited). Using "sip" when your account includes it improves premarket/after-hours prints.
    alpaca_market_data_feed: str = ""
    finnhub_api_key: str = ""
    # Free tier: avoid /stock/metric (often 403). Alpaca already has VWAP/volume.
    finnhub_fetch_metrics: bool = False
    finnhub_fetch_company_news: bool = True
    # Seconds between Finnhub calls (e.g. 1.05 ≈ 60/min). 0 = no delay.
    finnhub_min_request_interval_sec: float = 0.0
    fmp_api_key: str = ""
    benzinga_api_key: str = ""

    sec_user_agent: str = "TradingResearchScanner contact@example.com"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    scan_premarket: str = "04:00"
    scan_open_confirm: str = "06:30"
    scan_midday: str = "10:00"
    scan_overnight: str = "12:00"

    # Max symbols per manual scan (API limit). Large scans are slow; news skipped above threshold.
    scan_max_symbols: int = 2000
    scan_news_max_symbols: int = 100

    account_balance: str = ""
    account_pdt_restricted: bool = False
    max_risk_per_trade: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
