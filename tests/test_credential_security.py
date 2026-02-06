"""Security tests for credential handling."""

import logging
import tempfile
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from bonito.trading.credential_store import CredentialStore
from bonito.trading.credential_validator import CredentialValidator
from bonito.trading.credentials import AlpacaCredentials

# Test credentials (format valid but fake)
# Alpaca keys vary in length: API key is typically 20-30 chars, secret is 40-48 chars
VALID_PAPER_KEY = "PKABCDEFGHIJ12345678ABCD"  # PK + 22 alphanumeric = 24 total
VALID_LIVE_KEY = "AKABCDEFGHIJ12345678ABCD"  # AK + 22 alphanumeric = 24 total
VALID_SECRET = "A" * 44  # 44 characters (common Alpaca secret length)


class TestAlpacaCredentials:
    def test_valid_paper_credentials(self):
        creds = AlpacaCredentials(api_key=VALID_PAPER_KEY, secret_key=VALID_SECRET, is_paper=True)
        assert creds.is_paper is True
        assert isinstance(creds.api_key, SecretStr)

    def test_valid_live_credentials(self):
        creds = AlpacaCredentials(api_key=VALID_LIVE_KEY, secret_key=VALID_SECRET, is_paper=False)
        assert creds.is_paper is False

    def test_invalid_api_key_format(self):
        with pytest.raises(ValidationError) as exc_info:
            AlpacaCredentials(
                api_key="invalid_key",
                secret_key=VALID_SECRET,
            )
        assert "Invalid Alpaca API key format" in str(exc_info.value)

    def test_invalid_secret_key_length(self):
        with pytest.raises(ValidationError) as exc_info:
            AlpacaCredentials(
                api_key=VALID_PAPER_KEY,
                secret_key="tooshort",
            )
        assert "Invalid Alpaca secret key length" in str(exc_info.value)

    def test_redacted_display(self):
        creds = AlpacaCredentials(
            api_key=VALID_PAPER_KEY,
            secret_key=VALID_SECRET,
        )
        redacted = creds.get_redacted_display()
        assert "PKAB" in redacted  # First 4 chars visible
        assert "ABCD" in redacted  # Last 4 chars visible
        assert "CDEFGHIJ1234" not in redacted  # Middle hidden

    def test_secrets_not_in_json(self):
        creds = AlpacaCredentials(
            api_key=VALID_PAPER_KEY,
            secret_key=VALID_SECRET,
        )
        json_str = creds.model_dump_json()
        assert VALID_PAPER_KEY not in json_str
        assert VALID_SECRET not in json_str

    def test_secrets_not_in_repr(self):
        creds = AlpacaCredentials(
            api_key=VALID_PAPER_KEY,
            secret_key=VALID_SECRET,
        )
        repr_str = repr(creds)
        assert VALID_PAPER_KEY not in repr_str
        assert VALID_SECRET not in repr_str


class TestCredentialStore:
    def test_store_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CredentialStore(Path(tmpdir))
            creds = AlpacaCredentials(
                api_key=VALID_PAPER_KEY,
                secret_key=VALID_SECRET,
            )

            store.store_credentials(creds, "testpassword")
            loaded = store.load_credentials("testpassword")

            assert loaded is not None
            assert loaded.api_key.get_secret_value() == VALID_PAPER_KEY
            assert loaded.secret_key.get_secret_value() == VALID_SECRET

    def test_wrong_password_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CredentialStore(Path(tmpdir))
            creds = AlpacaCredentials(
                api_key=VALID_PAPER_KEY,
                secret_key=VALID_SECRET,
            )

            store.store_credentials(creds, "correctpassword")
            loaded = store.load_credentials("wrongpassword")

            assert loaded is None

    def test_delete_credentials(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CredentialStore(Path(tmpdir))
            creds = AlpacaCredentials(
                api_key=VALID_PAPER_KEY,
                secret_key=VALID_SECRET,
            )

            store.store_credentials(creds, "password")
            assert store.has_credentials() is True

            store.delete_credentials()
            assert store.has_credentials() is False

    def test_credentials_encrypted_on_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CredentialStore(Path(tmpdir))
            creds = AlpacaCredentials(
                api_key=VALID_PAPER_KEY,
                secret_key=VALID_SECRET,
            )

            store.store_credentials(creds, "password")

            # Read raw file contents
            raw_content = (Path(tmpdir) / "credentials.enc").read_bytes()

            # Secrets should NOT be readable in raw file
            assert VALID_PAPER_KEY.encode() not in raw_content
            assert VALID_SECRET.encode() not in raw_content


class TestCredentialValidator:
    @pytest.mark.asyncio
    async def test_validate_paper_credentials(self):
        validator = CredentialValidator(use_real_api=False)
        creds = AlpacaCredentials(api_key=VALID_PAPER_KEY, secret_key=VALID_SECRET, is_paper=True)

        result = await validator.validate_and_test(creds)

        assert result.valid is True
        assert result.account_type == "paper"

    @pytest.mark.asyncio
    async def test_validate_live_credentials(self):
        validator = CredentialValidator(use_real_api=False)
        creds = AlpacaCredentials(api_key=VALID_LIVE_KEY, secret_key=VALID_SECRET, is_paper=False)

        result = await validator.validate_and_test(creds)

        assert result.valid is True
        assert result.account_type == "live"

    @pytest.mark.asyncio
    async def test_type_mismatch_detection(self):
        validator = CredentialValidator(use_real_api=False)
        # Paper key with is_paper=False
        creds = AlpacaCredentials(
            api_key=VALID_PAPER_KEY,
            secret_key=VALID_SECRET,
            is_paper=False,  # Mismatch!
        )

        result = await validator.validate_and_test(creds)

        assert result.valid is False
        assert "mismatch" in result.error.lower()


# CRITICAL SECURITY TESTS
class TestSecurityRequirements:
    """Tests to ensure credentials are never exposed."""

    def test_credentials_not_in_logs(self, caplog):
        """Verify credentials are not logged."""
        logger = logging.getLogger("test")

        creds = AlpacaCredentials(
            api_key=VALID_PAPER_KEY,
            secret_key=VALID_SECRET,
        )

        # Log the credential object
        logger.info(f"Credential info: {creds}")
        logger.info(f"Redacted: {creds.get_redacted_display()}")

        # Check logs don't contain secrets
        for record in caplog.records:
            assert VALID_PAPER_KEY not in record.message
            assert VALID_SECRET not in record.message

    def test_credentials_not_serialized(self):
        """Verify SecretStr fields are masked in serialization."""
        creds = AlpacaCredentials(
            api_key=VALID_PAPER_KEY,
            secret_key=VALID_SECRET,
        )

        # Test various serialization methods
        json_output = creds.model_dump_json()
        dict_output = str(creds.model_dump())

        assert VALID_PAPER_KEY not in json_output
        assert VALID_SECRET not in json_output
        assert VALID_PAPER_KEY not in dict_output
        assert VALID_SECRET not in dict_output
