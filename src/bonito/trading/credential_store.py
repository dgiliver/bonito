"""Encrypted credential storage for local development."""

import base64
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .credentials import AlpacaCredentials


class CredentialStore:
    """Encrypted local credential storage."""

    def __init__(self, store_dir: Path | None = None):
        """Initialize credential store.

        Args:
            store_dir: Directory for credential files. Defaults to ~/.bonito/
        """
        self.store_dir = store_dir or Path.home() / ".bonito"
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._credentials_file = self.store_dir / "credentials.enc"
        self._salt_file = self.store_dir / "salt"

    def _get_or_create_salt(self) -> bytes:
        """Get or create salt for key derivation."""
        if self._salt_file.exists():
            return self._salt_file.read_bytes()
        salt = os.urandom(16)
        self._salt_file.write_bytes(salt)
        return salt

    def _derive_key(self, password: str) -> bytes:
        """Derive encryption key from password using PBKDF2."""
        salt = self._get_or_create_salt()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,  # OWASP recommended
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    def store_credentials(self, credentials: AlpacaCredentials, password: str) -> None:
        """Encrypt and store credentials."""
        key = self._derive_key(password)
        f = Fernet(key)

        # Serialize credentials (excluding SecretStr display)
        data = {
            "api_key": credentials.api_key.get_secret_value(),
            "secret_key": credentials.secret_key.get_secret_value(),
            "is_paper": credentials.is_paper,
        }
        encrypted = f.encrypt(json.dumps(data).encode())
        self._credentials_file.write_bytes(encrypted)

    def load_credentials(self, password: str) -> AlpacaCredentials | None:
        """Load and decrypt credentials."""
        if not self._credentials_file.exists():
            return None

        key = self._derive_key(password)
        f = Fernet(key)

        try:
            encrypted = self._credentials_file.read_bytes()
            decrypted = f.decrypt(encrypted)
            data = json.loads(decrypted.decode())
            return AlpacaCredentials(**data)
        except Exception:
            return None

    def delete_credentials(self) -> bool:
        """Delete stored credentials."""
        if self._credentials_file.exists():
            self._credentials_file.unlink()
            return True
        return False

    def has_credentials(self) -> bool:
        """Check if credentials are stored."""
        return self._credentials_file.exists()
