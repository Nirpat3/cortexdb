"""
Input Validation — Sanitize and validate API inputs for SuperAdmin endpoints.
"""

import re
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Max lengths for common fields
MAX_LENGTHS = {
    "agent_id": 64,
    "task_id": 64,
    "name": 200,
    "title": 500,
    "description": 5000,
    "content": 50000,
    "prompt": 20000,
    "command": 2000,
    "query": 5000,
    "passphrase": 200,
    "path": 1000,
}

# Pattern for valid IDs (alphanumeric, hyphens, underscores, dots)
ID_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.]+$')


class ValidationError(Exception):
    """Raised when input validation fails."""
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"Validation error on '{field}': {message}")


def validate_id(value: str, field: str = "id") -> str:
    """Validate an identifier string."""
    if not value or not value.strip():
        raise ValidationError(field, "cannot be empty")
    value = value.strip()
    max_len = MAX_LENGTHS.get(field, 64)
    if len(value) > max_len:
        raise ValidationError(field, f"exceeds max length of {max_len}")
    if not ID_PATTERN.match(value):
        raise ValidationError(field, "contains invalid characters (only alphanumeric, hyphens, underscores, dots allowed)")
    return value


def validate_string(value: Any, field: str, required: bool = True,
                     max_length: int = None, min_length: int = 0) -> str:
    """Validate a string field."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValidationError(field, "is required")
        return ""
    if not isinstance(value, str):
        raise ValidationError(field, "must be a string")
    value = value.strip()
    max_len = max_length or MAX_LENGTHS.get(field, 5000)
    if len(value) > max_len:
        raise ValidationError(field, f"exceeds max length of {max_len}")
    if len(value) < min_length:
        raise ValidationError(field, f"must be at least {min_length} characters")
    return value


def validate_number(value: Any, field: str, min_val: float = None,
                     max_val: float = None, required: bool = True) -> Optional[float]:
    """Validate a numeric field."""
    if value is None:
        if required:
            raise ValidationError(field, "is required")
        return None
    try:
        num = float(value)
    except (ValueError, TypeError):
        raise ValidationError(field, "must be a number")
    if min_val is not None and num < min_val:
        raise ValidationError(field, f"must be >= {min_val}")
    if max_val is not None and num > max_val:
        raise ValidationError(field, f"must be <= {max_val}")
    return num


def validate_enum(value: Any, field: str, allowed: List[str],
                   required: bool = True) -> Optional[str]:
    """Validate a value is one of allowed options."""
    if value is None or value == "":
        if required:
            raise ValidationError(field, "is required")
        return None
    if value not in allowed:
        raise ValidationError(field, f"must be one of: {', '.join(allowed)}")
    return value


def validate_list(value: Any, field: str, max_items: int = 100,
                   required: bool = True) -> list:
    """Validate a list field."""
    if value is None:
        if required:
            raise ValidationError(field, "is required")
        return []
    if not isinstance(value, list):
        raise ValidationError(field, "must be a list")
    if len(value) > max_items:
        raise ValidationError(field, f"exceeds max items of {max_items}")
    return value


def validate_dict(value: Any, field: str, required: bool = True) -> dict:
    """Validate a dict field."""
    if value is None:
        if required:
            raise ValidationError(field, "is required")
        return {}
    if not isinstance(value, dict):
        raise ValidationError(field, "must be an object")
    return value


def sanitize_for_log(value: str, max_len: int = 200) -> str:
    """Sanitize a string for safe logging (remove control chars, truncate)."""
    clean = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', str(value))
    if len(clean) > max_len:
        clean = clean[:max_len] + "..."
    return clean


def validate_command(command: str) -> str:
    """Validate a CLI command for the run_command tool."""
    command = validate_string(command, "command", max_length=2000)

    # Check for dangerous patterns
    dangerous = [
        (r';\s*rm\s+-rf\s+/', "recursive root delete"),
        (r'\|\s*(ba)?sh', "pipe to shell"),
        (r'>\s*/dev/sd', "write to disk device"),
        (r'mkfs', "filesystem format"),
        (r'dd\s+if=', "disk dump"),
        (r':()\s*\{', "fork bomb"),
        (r'shutdown|reboot|halt|poweroff', "system control"),
        (r'chmod\s+-R\s+777\s+/', "recursive chmod root"),
        (r'curl\s+.*\|\s*(ba)?sh', "curl pipe to shell"),
    ]

    for pattern, desc in dangerous:
        if re.search(pattern, command, re.IGNORECASE):
            raise ValidationError("command", f"blocked: {desc}")

    return command


def validate_path(path: str, allow_absolute: bool = True) -> str:
    """Validate a file path."""
    path = validate_string(path, "path", max_length=1000)

    # Block path traversal
    if ".." in path:
        raise ValidationError("path", "path traversal (..) not allowed")

    # Block access to sensitive paths
    sensitive = ["/etc/shadow", "/etc/passwd", "~/.ssh", ".env", "id_rsa"]
    for s in sensitive:
        if s in path.lower():
            raise ValidationError("path", f"access to {s} is restricted")

    if not allow_absolute and path.startswith("/"):
        raise ValidationError("path", "absolute paths not allowed")

    return path
