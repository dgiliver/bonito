"""Validate Alpaca credentials before storage."""

import os

from .credentials import AlpacaCredentials, CredentialTestResult


class CredentialValidator:
    """Validate Alpaca credentials before storage."""

    def __init__(self, use_real_api: bool | None = None):
        """Initialize validator.

        Args:
            use_real_api: Whether to use real Alpaca API. If None, auto-detect based on
                environment variable. Set BONITO_USE_MOCK_ALPACA_API=true to use mock mode.
        """
        if use_real_api is None:
            # Default to TRUE (use real API), unless explicitly set to use mock
            use_real_api = os.environ.get("BONITO_USE_MOCK_ALPACA_API", "").lower() != "true"
        self.use_real_api = use_real_api

    async def validate_and_test(self, credentials: AlpacaCredentials) -> CredentialTestResult:
        """Validate format and test against Alpaca API."""
        if self.use_real_api:
            return await self._validate_with_real_api(credentials)
        else:
            return await self._validate_mock(credentials)

    async def _validate_with_real_api(self, credentials: AlpacaCredentials) -> CredentialTestResult:
        """Validate credentials against real Alpaca API."""
        try:
            from alpaca.trading.client import TradingClient

            client = TradingClient(
                api_key=credentials.api_key.get_secret_value(),
                secret_key=credentials.secret_key.get_secret_value(),
                paper=credentials.is_paper,
            )

            account = client.get_account()

            # Determine if account is paper based on account number prefix
            is_actually_paper = str(account.account_number).startswith("PA")

            if is_actually_paper != credentials.is_paper:
                return CredentialTestResult(
                    valid=False,
                    error=f"Credential type mismatch: account is {'paper' if is_actually_paper else 'live'}, "
                    f"but is_paper={credentials.is_paper}",
                )

            return CredentialTestResult(
                valid=True,
                account_id=str(account.account_number),
                account_type="paper" if is_actually_paper else "live",
                buying_power=float(account.buying_power),
            )

        except Exception as e:
            return CredentialTestResult(valid=False, error=f"Failed to connect to Alpaca: {str(e)}")

    async def _validate_mock(self, credentials: AlpacaCredentials) -> CredentialTestResult:
        """Mock validation for testing (doesn't hit real API)."""
        try:
            # Format validation is done by Pydantic validators
            api_key = credentials.api_key.get_secret_value()
            is_paper = api_key.startswith("PK")

            if is_paper != credentials.is_paper:
                return CredentialTestResult(
                    valid=False,
                    error=f"Credential type mismatch: key is {'paper' if is_paper else 'live'}, "
                    f"but is_paper={credentials.is_paper}",
                )

            # Mock successful validation
            return CredentialTestResult(
                valid=True,
                account_id=f"{'PA' if is_paper else 'A'}1234567890",
                account_type="paper" if is_paper else "live",
                buying_power=100000.0 if is_paper else 50000.0,
            )

        except Exception as e:
            return CredentialTestResult(valid=False, error=f"Validation failed: {str(e)}")
