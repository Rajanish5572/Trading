"""
Central settings. Everything is loaded from environment variables / .env so that
credentials never live in source code. See backend/.env.example for the full list.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    arrow_app_id: str = ""
    arrow_app_secret: str = ""
    arrow_user_id: str = ""
    arrow_password: str = ""
    arrow_totp_secret: str = ""

    # Master safety switch. True = every order is simulated locally against
    # live market data instead of being sent to the broker. Flip to false only
    # after you've exercised every tab (chart, option chain, strategy builder,
    # positions) in paper mode and you trust the flow end to end.
    paper_mode: bool = True
    paper_starting_cash: float = 1_000_000.0

    host: str = "127.0.0.1"
    port: int = 8000

    token_cache_path: str = ".arrow_token.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
