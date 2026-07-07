import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Database & Cache
    DATABASE_URL: str = Field(default="postgresql+asyncpg://postgres:postgres@db:5432/mbm_radar")
    REDIS_URL: str = Field(default="redis://redis:6379/0")

    # Telegram Bot Config
    TELEGRAM_BOT_TOKEN: str = Field(default="mock_token")
    TELEGRAM_CHANNEL_ID: int = Field(default=-1001234567890)
    WEBHOOK_URL: str = Field(default="")

    # Stock API Keys
    FMP_API_KEY: str = Field(default="")
    POLYGON_API_KEY: str = Field(default="")
    FINNHUB_API_KEY: str = Field(default="")
    ALPACA_API_KEY: str = Field(default="")
    ALPACA_API_SECRET: str = Field(default="")
    IEX_CLOUD_API_KEY: str = Field(default="")
    ALPHA_VANTAGE_API_KEY: str = Field(default="")

    ACTIVE_DATA_PROVIDER: str = Field(default="FMP")  # FMP, POLYGON, etc.

    # Security
    JWT_SECRET: str = Field(default="super_secret_jwt_key_change_me_in_production_123456789")
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440)
    ADMIN_PASSWORD: str = Field(default="admin_pass_123")
    ADMIN_TELEGRAM_ID: int = Field(default=123456789)

    # Scanner thresholds
    SCANNER_MAX_PRICE: float = Field(default=30.0)
    SCANNER_MAX_FLOAT: float = Field(default=20000000.0)
    SCANNER_MAX_MARKET_CAP: float = Field(default=3000000000.0)
    SCANNER_MIN_RVOL: float = Field(default=1.5)
    SCANNER_MIN_VOLUME: int = Field(default=50000)
    SCANNER_MIN_GAP_PCT: float = Field(default=2.0)
    SCANNER_MIN_CHANGE_PCT: float = Field(default=1.0)
    SCANNER_LIMIT: int = Field(default=200)
    SCANNER_CACHE_MINUTES: int = Field(default=30)
    SCANNER_POLL_INTERVAL_SECONDS: int = Field(default=60)

    # Batch Ranking & Concurrency Config
    SCANNER_TOP_K: int = Field(default=50)
    SCANNER_CONCURRENCY_LIMIT: int = Field(default=5)
    SCANNER_MAX_SIGNALS: int = Field(default=20)

    COOLDOWN_PERIOD_MINUTES: int = Field(default=15)
    MIN_SCORE_THRESHOLD: float = Field(default=5.0)

    # Test Mode parameters
    TEST_MODE: bool = Field(default=False)
    STAGE2_MIN_RVOL: float = Field(default=1.0)

    # Simulation Mode — generates synthetic market signals through the real pipeline
    SIMULATION_MODE: bool = Field(default=False)
    SIMULATION_INTERVAL_SECONDS: int = Field(default=3)  # Interval between simulated signals

    # Payments Gateway
    PAYMENT_PROVIDER: str = Field(default="MOCK")
    STRIPE_SECRET_KEY: str = Field(default="")

settings = Settings()
