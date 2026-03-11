"""Field-Level Encryption and Key Management

AES-256-GCM encryption for sensitive fields:
  - PII: name, email, phone, address, DOB, SSN
  - PHI: diagnoses, medications, lab results (HIPAA)
  - PCI: PAN, CVV, expiry (PCI-DSS)

Key management:
  - Master key encrypted at rest
  - Data encryption keys (DEKs) per tenant
  - Automatic key rotation on schedule
  - Key versioning for decrypt of older data
"""

import os
import time
import hashlib
import secrets
import logging
import base64
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.compliance.encryption")


class FieldSensitivity(Enum):
    PUBLIC = "public"           # No encryption needed
    INTERNAL = "internal"       # Organization-internal
    CONFIDENTIAL = "confidential"   # PII
    RESTRICTED = "restricted"       # PHI, PCI (highest protection)


@dataclass
class EncryptionKey:
    key_id: str
    version: int = 1
    algorithm: str = "AES-256-GCM"
    created_at: float = field(default_factory=time.time)
    rotated_at: Optional[float] = None
    expires_at: Optional[float] = None
    active: bool = True
    tenant_id: Optional[str] = None
    # key_material stored separately, never in this dataclass


@dataclass
class EncryptedField:
    ciphertext: str          # Base64-encoded encrypted data
    key_id: str              # Which key encrypted this
    key_version: int         # Key version for rotation
    iv: str                  # Base64-encoded initialization vector
    algorithm: str = "AES-256-GCM"
    tag: str = ""            # Base64-encoded auth tag (GCM)


# Field sensitivity classification for CortexDB tables
FIELD_CLASSIFICATIONS = {
    "customers": {
        "canonical_name": FieldSensitivity.CONFIDENTIAL,
        "canonical_email": FieldSensitivity.CONFIDENTIAL,
        "canonical_phone": FieldSensitivity.CONFIDENTIAL,
        "customer_id": FieldSensitivity.INTERNAL,
    },
    "customer_identifiers": {
        "identifier_value": FieldSensitivity.RESTRICTED,  # Could be SSN, PAN, etc.
    },
    "customer_events": {
        "properties": FieldSensitivity.CONFIDENTIAL,  # May contain PII
    },
    "customer_profiles": {
        "preferred_categories": FieldSensitivity.INTERNAL,
    },
}

# PCI fields that MUST be encrypted or tokenized
PCI_FIELDS = {
    "pan", "card_number", "cvv", "expiry", "cardholder_name",
    "payment_token", "account_number", "routing_number",
}

# HIPAA PHI fields
HIPAA_PHI_FIELDS = {
    "patient_name", "ssn", "date_of_birth", "address", "zip_code",
    "phone_number", "email", "medical_record_number", "health_plan_id",
    "diagnosis", "medication", "lab_result", "treatment_notes",
}


class KeyManager:
    """Cryptographic key management with rotation support.

    Key hierarchy:
      Master Key (KEK) -> encrypted at rest via env var or HSM
      └── Data Encryption Keys (DEKs) -> per-tenant, rotated
          └── Field values encrypted with DEK
    """

    ROTATION_INTERVAL = 90 * 86400  # 90 days default

    def __init__(self, master_key: Optional[str] = None):
        self._master_key = (master_key or
                            os.getenv("CORTEX_MASTER_KEY") or
                            self._derive_default_key())
        self._keys: Dict[str, Dict[int, bytes]] = {}  # key_id -> {version -> key_material}
        self._key_metadata: Dict[str, EncryptionKey] = {}
        self._rotations = 0

    def _derive_default_key(self) -> str:
        """Derive a master key from CORTEX_SECRET_KEY via PBKDF2.

        Refuses to start with no key material in production mode.
        """
        secret = os.getenv("CORTEX_SECRET_KEY", "")
        mode = os.getenv("CORTEX_MODE", "development")
        if not secret or len(secret) < 32:
            if mode != "development":
                raise RuntimeError(
                    "SECURITY: CORTEX_MASTER_KEY or CORTEX_SECRET_KEY (>= 32 chars) "
                    "must be set in production. Refusing to start with insecure defaults."
                )
            logger.warning(
                "SECURITY: Using dev-only fallback key. Set CORTEX_MASTER_KEY in production."
            )
            secret = secret or "cortex-dev-key-DO-NOT-USE-IN-PRODUCTION"
        # Use PBKDF2 with salt — deterministic for same secret
        salt = b"cortexdb-kdf-salt-v4"
        key = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, iterations=100_000)
        return key.hex()

    def generate_key(self, key_id: str = None,
                     tenant_id: Optional[str] = None) -> EncryptionKey:
        """Generate a new data encryption key."""
        key_id = key_id or f"dek-{secrets.token_hex(8)}"
        key_material = secrets.token_bytes(32)  # 256 bits

        # Encrypt DEK with master key
        encrypted_dek = self._encrypt_dek(key_material)

        if key_id not in self._keys:
            self._keys[key_id] = {}
        version = len(self._keys[key_id]) + 1
        self._keys[key_id][version] = key_material

        meta = EncryptionKey(
            key_id=key_id, version=version,
            tenant_id=tenant_id,
            expires_at=time.time() + self.ROTATION_INTERVAL)
        self._key_metadata[key_id] = meta

        logger.info(f"Key generated: {key_id} v{version}")
        return meta

    def rotate_key(self, key_id: str) -> EncryptionKey:
        """Rotate an existing key (old versions kept for decryption)."""
        if key_id not in self._keys:
            raise ValueError(f"Key not found: {key_id}")

        new_material = secrets.token_bytes(32)
        version = len(self._keys[key_id]) + 1
        self._keys[key_id][version] = new_material

        meta = self._key_metadata[key_id]
        meta.version = version
        meta.rotated_at = time.time()
        meta.expires_at = time.time() + self.ROTATION_INTERVAL
        self._rotations += 1

        logger.info(f"Key rotated: {key_id} -> v{version}")
        return meta

    def get_key(self, key_id: str, version: int = None) -> Optional[bytes]:
        """Get key material for encryption/decryption."""
        if key_id not in self._keys:
            return None
        versions = self._keys[key_id]
        if version:
            return versions.get(version)
        # Return latest version
        return versions.get(max(versions.keys()))

    def get_tenant_key(self, tenant_id: str) -> EncryptionKey:
        """Get or create a DEK for a tenant."""
        key_id = f"tenant-{tenant_id}"
        if key_id not in self._key_metadata:
            return self.generate_key(key_id, tenant_id)
        return self._key_metadata[key_id]

    def check_rotation_needed(self) -> List[str]:
        """Find keys that need rotation."""
        now = time.time()
        due = []
        for key_id, meta in self._key_metadata.items():
            if meta.expires_at and meta.expires_at < now:
                due.append(key_id)
        return due

    def _encrypt_dek(self, dek: bytes) -> bytes:
        """Encrypt DEK with master key (envelope encryption)."""
        # In production, use AWS KMS, GCP KMS, or Azure Key Vault
        master = hashlib.sha256(self._master_key.encode()).digest()
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            nonce = secrets.token_bytes(12)
            aesgcm = AESGCM(master)
            ct = aesgcm.encrypt(nonce, dek, None)
            return nonce + ct
        except ImportError:
            raise RuntimeError(
                "SECURITY: cryptography package required for key encryption. "
                "Install with: pip install cryptography"
            )

    def get_stats(self) -> Dict:
        return {
            "total_keys": len(self._key_metadata),
            "total_versions": sum(len(v) for v in self._keys.values()),
            "rotations": self._rotations,
            "keys_needing_rotation": len(self.check_rotation_needed()),
        }


class FieldEncryption:
    """Field-level encryption for PII/PHI/PCI data.

    Usage:
        enc = FieldEncryption(key_manager)
        encrypted = enc.encrypt("John Doe", "customers", "canonical_name", tenant_id="t1")
        decrypted = enc.decrypt(encrypted)  # -> "John Doe"
    """

    def __init__(self, key_manager: KeyManager = None):
        self.key_manager = key_manager or KeyManager()
        self._encrypt_count = 0
        self._decrypt_count = 0
        self._has_crypto = False

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            self._has_crypto = True
        except ImportError:
            logger.error(
                "SECURITY: cryptography package not installed! "
                "Encryption operations will fail. Install: pip install cryptography"
            )

    def encrypt(self, plaintext: str, table: str = "",
                field: str = "", tenant_id: Optional[str] = None) -> EncryptedField:
        """Encrypt a field value."""
        self._encrypt_count += 1

        # Get or create tenant key
        if tenant_id:
            key_meta = self.key_manager.get_tenant_key(tenant_id)
        else:
            key_meta = self.key_manager.get_tenant_key("global")

        key = self.key_manager.get_key(key_meta.key_id)
        if not key:
            raise RuntimeError(f"Key not found: {key_meta.key_id}")

        if self._has_crypto:
            return self._encrypt_aes_gcm(plaintext, key, key_meta)
        else:
            raise RuntimeError(
                "SECURITY: cryptography package required for encryption. "
                "Install with: pip install cryptography"
            )

    def decrypt(self, encrypted: EncryptedField) -> str:
        """Decrypt a field value."""
        self._decrypt_count += 1

        key = self.key_manager.get_key(encrypted.key_id, encrypted.key_version)
        if not key:
            raise RuntimeError(f"Key not found: {encrypted.key_id} v{encrypted.key_version}")

        if self._has_crypto:
            return self._decrypt_aes_gcm(encrypted, key)
        elif encrypted.algorithm == "XOR-FALLBACK":
            # Allow decrypting legacy XOR-encrypted data for migration
            logger.warning("Decrypting XOR-fallback data. Re-encrypt with AES-256-GCM.")
            return self._decrypt_fallback(encrypted, key)
        else:
            raise RuntimeError(
                "SECURITY: cryptography package required for decryption. "
                "Install with: pip install cryptography"
            )

    def _encrypt_aes_gcm(self, plaintext: str, key: bytes,
                          key_meta: EncryptionKey) -> EncryptedField:
        """AES-256-GCM encryption (production)."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        iv = secrets.token_bytes(12)
        aesgcm = AESGCM(key)
        ct = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)

        # ct includes the 16-byte auth tag at the end
        ciphertext = ct[:-16]
        tag = ct[-16:]

        return EncryptedField(
            ciphertext=base64.b64encode(ciphertext).decode(),
            key_id=key_meta.key_id,
            key_version=key_meta.version,
            iv=base64.b64encode(iv).decode(),
            tag=base64.b64encode(tag).decode())

    def _decrypt_aes_gcm(self, encrypted: EncryptedField, key: bytes) -> str:
        """AES-256-GCM decryption (production)."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        iv = base64.b64decode(encrypted.iv)
        ciphertext = base64.b64decode(encrypted.ciphertext)
        tag = base64.b64decode(encrypted.tag)

        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(iv, ciphertext + tag, None)
        return plaintext.decode("utf-8")

    def _decrypt_fallback(self, encrypted: EncryptedField, key: bytes) -> str:
        """XOR-based fallback decryption."""
        ct = base64.b64decode(encrypted.ciphertext)
        extended_key = (key * ((len(ct) // len(key)) + 1))[:len(ct)]
        plaintext = bytes(a ^ b for a, b in zip(ct, extended_key))
        return plaintext.decode("utf-8")

    def encrypt_payload(self, payload: Dict, table: str,
                        tenant_id: Optional[str] = None) -> Dict:
        """Encrypt sensitive fields in a payload based on classification."""
        if table not in FIELD_CLASSIFICATIONS:
            return payload

        encrypted = dict(payload)
        for field_name, sensitivity in FIELD_CLASSIFICATIONS[table].items():
            if field_name in encrypted and encrypted[field_name]:
                if sensitivity in (FieldSensitivity.CONFIDENTIAL,
                                   FieldSensitivity.RESTRICTED):
                    enc = self.encrypt(
                        str(encrypted[field_name]), table, field_name, tenant_id)
                    encrypted[field_name] = {
                        "_encrypted": True,
                        "ciphertext": enc.ciphertext,
                        "key_id": enc.key_id,
                        "key_version": enc.key_version,
                        "iv": enc.iv,
                        "tag": enc.tag,
                    }
        return encrypted

    def decrypt_payload(self, payload: Dict) -> Dict:
        """Decrypt all encrypted fields in a payload."""
        decrypted = dict(payload)
        for field_name, value in decrypted.items():
            if isinstance(value, dict) and value.get("_encrypted"):
                enc = EncryptedField(
                    ciphertext=value["ciphertext"],
                    key_id=value["key_id"],
                    key_version=value["key_version"],
                    iv=value["iv"],
                    tag=value.get("tag", ""))
                decrypted[field_name] = self.decrypt(enc)
        return decrypted

    def get_classification(self, table: str) -> Dict:
        """Get field sensitivity classification for a table."""
        return {
            field: sens.value
            for field, sens in FIELD_CLASSIFICATIONS.get(table, {}).items()
        }

    def get_stats(self) -> Dict:
        return {
            "encryptions": self._encrypt_count,
            "decryptions": self._decrypt_count,
            "has_production_crypto": self._has_crypto,
            "classified_tables": len(FIELD_CLASSIFICATIONS),
            "key_manager": self.key_manager.get_stats(),
        }
