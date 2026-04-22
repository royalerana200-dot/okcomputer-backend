"""
OKComputer — Core Configuration
Loads all environment variables with validation
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    # Application
    app_name: str = "OKComputer"
    app_version: str = "1.0.0"
    app_env: str = "development"
    debug: bool = True
    secret_key: str
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Database
    database_url: str
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Anthropic
    anthropic_api_key: str
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_max_tokens: int = 1500

    # Binance
    binance_api_key: str = ""
    binance_secret_key: str = ""
    binance_testnet: bool = True
    binance_testnet_url: str = "https://testnet.binance.vision"

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter: str = ""
    stripe_price_growth: str = ""
    stripe_price_enterprise: str = ""

    # Trading Risk Limits — The Constitution Article A1
    max_position_size_pct: float = 0.02
    max_daily_drawdown_pct: float = 0.03
    max_total_drawdown_pct: float = 0.10
    min_confidence_threshold: float = 0.70
    paper_trading_mode: bool = True

    # Email
    resend_api_key: str = ""
    from_email: str = "noreply@okcomputer.ai"
    admin_email: str = ""

    # CORS
    allowed_origins: str = "http://localhost:3000"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
