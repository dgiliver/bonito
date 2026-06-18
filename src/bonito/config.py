"""Application configuration."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Paths
    data_dir: Path = Field(default=Path("data"), description="Directory for data storage")

    # LLM Configuration
    anthropic_api_key: str | None = Field(default=None, description="Anthropic API key")
    openai_api_key: str | None = Field(default=None, description="OpenAI API key")
    default_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Default LLM model to use",
    )

    # Agent Configuration
    max_iterations: int = Field(default=10, description="Max agent iterations per request")
    max_tokens: int = Field(default=4096, description="Max tokens per LLM response")

    # Backtest Configuration
    default_initial_capital: float = Field(
        default=100_000.0, description="Default starting capital"
    )
    default_commission: float = Field(default=0.001, description="Default commission rate (0.1%)")

    # Live trading safety (Alpaca bot-deploy path)
    alpaca_live_trading_enabled: bool = Field(
        default=False,
        description="Human-only master switch for real-money Alpaca bot deployment "
        "(mode='live'). Off by default - application code must never set this; only "
        "an operator setting ALPACA_LIVE_TRADING_ENABLED=true in the environment can "
        "enable it. No BONITO_ prefix - this Settings class has none configured "
        "(matches ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.).",
    )


settings = Settings()
