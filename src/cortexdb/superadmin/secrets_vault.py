"""
Secrets Vault — Encrypts API keys and sensitive config at rest.

Uses AES-256-GCM via the cryptography library.
Master key is derived from CORTEXDB_MASTER_SECRET env var (or auto-generated
and stored in the data directory). API keys are encrypted before being written
to SQLite persistence.
"""

import os
import base64
import json
import logging
import secrets
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# cryptography is already a dependency in pyproject.toml
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

VAULT_KEY_FILE = ".vault_key"
NONCE_BYTES = 12
KEY_BYTES = 32  # AES-256


class SecretsVault:
    """Encrypt/decrypt secrets using AES-256-GCM."""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._key: Optional[bytes] = None

    def initialize(self):
        """Derive or load the encryption key."""
        master_secret = os.environ.get("CORTEXDB_MASTER_SECRET")

        if master_secret:
            # Derive key from master secret + salt
            salt = self._load_or_create_salt()
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=KEY_BYTES,
                salt=salt,
                iterations=600_000,
            )
            self._key = kdf.derive(master_secret.encode("utf-8"))
            logger.info("Vault key derived from CORTEXDB_MASTER_SECRET")
        else:
            # Auto-generate and store key (dev/single-server mode)
            key_path = self._data_dir / VAULT_KEY_FILE
            if key_path.exists():
                self._key = base64.b64decode(key_path.read_text("utf-8").strip())
                logger.info("Vault key loaded from %s", key_path)
            else:
                self._key = AESGCM.generate_key(bit_length=256)
                key_path.write_text(base64.b64encode(self._key).decode("utf-8"), "utf-8")
                # Restrict permissions (best effort on Windows)
                try:
                    os.chmod(str(key_path), 0o600)
                except OSError:
                    pass
                logger.info("Vault key generated and stored at %s", key_path)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string. Returns base64-encoded (nonce + ciphertext)."""
        if not self._key:
            raise RuntimeError("Vault not initialized")
        nonce = secrets.token_bytes(NONCE_BYTES)
        aesgcm = AESGCM(self._key)
        ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ct).decode("utf-8")

    def decrypt(self, token: str) -> str:
        """Decrypt a base64-encoded (nonce + ciphertext) string."""
        if not self._key:
            raise RuntimeError("Vault not initialized")
        raw = base64.b64decode(token)
        nonce = raw[:NONCE_BYTES]
        ct = raw[NONCE_BYTES:]
        aesgcm = AESGCM(self._key)
        return aesgcm.decrypt(nonce, ct, None).decode("utf-8")

    def encrypt_dict(self, data: dict, sensitive_keys: list) -> dict:
        """Encrypt specified keys in a dict, leaving others as-is."""
        result = dict(data)
        for key in sensitive_keys:
            if key in result and result[key] and not self._is_encrypted(result[key]):
                result[key] = f"vault:{self.encrypt(str(result[key]))}"
        return result

    def decrypt_dict(self, data: dict, sensitive_keys: list) -> dict:
        """Decrypt specified keys in a dict."""
        result = dict(data)
        for key in sensitive_keys:
            if key in result and isinstance(result[key], str) and result[key].startswith("vault:"):
                try:
                    result[key] = self.decrypt(result[key][6:])
                except Exception:
                    logger.warning("Failed to decrypt key '%s' — may be corrupted", key)
        return result

    @staticmethod
    def _is_encrypted(value) -> bool:
        return isinstance(value, str) and value.startswith("vault:")

    def _load_or_create_salt(self) -> bytes:
        salt_path = self._data_dir / ".vault_salt"
        if salt_path.exists():
            return base64.b64decode(salt_path.read_text("utf-8").strip())
        salt = secrets.token_bytes(16)
        salt_path.write_text(base64.b64encode(salt).decode("utf-8"), "utf-8")
        try:
            os.chmod(str(salt_path), 0o600)
        except OSError:
            pass
        return salt

    @property
    def is_initialized(self) -> bool:
        return self._key is not None
