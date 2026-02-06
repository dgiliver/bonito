"""Secure credential models for broker API keys."""

import re

from pydantic import BaseModel, Field, SecretStr, field_serializer, field_validator


class AlpacaCredentials(BaseModel):
    """Alpaca API credentials with validation."""

    api_key: SecretStr = Field(..., description="Alpaca API Key")
    secret_key: SecretStr = Field(..., description="Alpaca Secret Key")
    is_paper: bool = Field(default=True, description="Paper trading mode")

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: SecretStr) -> SecretStr:
        """Validate Alpaca API key format."""
        key = v.get_secret_value()
        # Paper keys start with PK, live with AK
        # Keys are typically 20-30 characters (Alpaca has changed formats over time)
        if not re.match(r"^(PK|AK)[A-Z0-9]{18,28}$", key):
            raise ValueError(
                "Invalid Alpaca API key format. "
                "Should start with PK (paper) or AK (live) followed by alphanumeric characters"
            )
        return v

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: SecretStr) -> SecretStr:
        """Validate Alpaca secret key format."""
        secret = v.get_secret_value()
        # Secret keys are typically 40-48 characters
        if len(secret) < 32 or len(secret) > 64:
            raise ValueError("Invalid Alpaca secret key length (expected 32-64 chars)")
        return v

    def get_redacted_display(self) -> str:
        """Return redacted version for logging/display."""
        key = self.api_key.get_secret_value()
        return f"{key[:4]}...{key[-4:]}"

    @field_serializer("api_key", "secret_key")
    def serialize_secret(self, value: SecretStr) -> str:
        """Serialize SecretStr fields as masked strings."""
        return "********"


class CredentialTestResult(BaseModel):
    """Result of testing credentials against Alpaca API."""

    valid: bool
    account_id: str | None = None
    account_type: str | None = None  # "paper" or "live"
    buying_power: float | None = None
    error: str | None = None
