"""
SuperAdmin Authentication — Passphrase-based authentication with session tokens.
Only the superadmin has access. Sessions expire after 24 hours.
"""

import os
import time
import secrets
import hashlib
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Passphrase from env var — fail-fast in production if not set
_passphrase = os.environ.get("CORTEXDB_MASTER_SECRET", "")
if not _passphrase:
    _mode = os.environ.get("CORTEX_MODE", "development")
    if _mode in ("staging", "production"):
        raise RuntimeError("CORTEXDB_MASTER_SECRET must be set in staging/production")
    _passphrase = "thisismydatabasebaby"
    logger.warning("Using default superadmin passphrase — set CORTEXDB_MASTER_SECRET for production")
PASSPHRASE_HASH = hashlib.sha256(_passphrase.encode()).hexdigest()
del _passphrase  # Don't keep plaintext in memory

SESSION_TTL = 86400  # 24 hours


class SuperAdminAuth:
    """Manages superadmin authentication and session tokens."""

    def __init__(self):
        self._sessions: Dict[str, float] = {}  # token -> expiry
        self._failed_attempts: Dict[str, int] = {}  # ip -> count
        self._lockout_until: Dict[str, float] = {}  # ip -> timestamp

    def authenticate(self, passphrase: str, ip: str = "unknown") -> Optional[str]:
        """Verify passphrase and return session token, or None."""
        now = time.time()

        # Check lockout
        if ip in self._lockout_until and now < self._lockout_until[ip]:
            remaining = int(self._lockout_until[ip] - now)
            logger.warning("SuperAdmin login locked out for IP %s (%ds remaining)", ip, remaining)
            return None

        # Verify passphrase (constant-time comparison to prevent timing attacks)
        attempt_hash = hashlib.sha256(passphrase.encode()).hexdigest()
        if not secrets.compare_digest(attempt_hash, PASSPHRASE_HASH):
            self._failed_attempts[ip] = self._failed_attempts.get(ip, 0) + 1
            logger.warning("SuperAdmin login failed from %s (attempt %d)", ip, self._failed_attempts[ip])

            # Lockout after 5 failures
            if self._failed_attempts[ip] >= 5:
                self._lockout_until[ip] = now + 300  # 5 min lockout
                self._failed_attempts[ip] = 0
                logger.warning("SuperAdmin IP %s locked out for 5 minutes", ip)
            return None

        # Success — clear failures, create session
        self._failed_attempts.pop(ip, None)
        token = secrets.token_urlsafe(48)
        self._sessions[token] = now + SESSION_TTL
        self._cleanup_sessions()
        logger.info("SuperAdmin authenticated from %s", ip)
        return token

    def validate_session(self, token: str) -> bool:
        """Check if session token is valid and not expired."""
        if not token or token not in self._sessions:
            return False
        if time.time() > self._sessions[token]:
            del self._sessions[token]
            return False
        return True

    def revoke_session(self, token: str):
        """Logout — revoke session token."""
        self._sessions.pop(token, None)

    def _cleanup_sessions(self):
        now = time.time()
        expired = [t for t, exp in self._sessions.items() if now > exp]
        for t in expired:
            del self._sessions[t]

    def get_session_info(self, token: str) -> Optional[dict]:
        if not self.validate_session(token):
            return None
        return {
            "valid": True,
            "expires_at": self._sessions[token],
            "remaining_seconds": int(self._sessions[token] - time.time()),
            "active_sessions": len(self._sessions),
        }
