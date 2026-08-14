\
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


SECRET_FIELD_NAMES = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
}

_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
_BEARER_PATTERN = re.compile(
    r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+\b"
)
_KEY_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|token|password|secret)\s*[:=]\s*([^\s,;]+)"
)


def redact_text(value: str) -> str:
    redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", value)
    redacted = _SSN_PATTERN.sub("[SSN_REDACTED]", redacted)
    redacted = _EMAIL_PATTERN.sub("[EMAIL_REDACTED]", redacted)
    redacted = _KEY_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        redacted,
    )
    return redacted


def redact(value: Any) -> Any:
    """Return a recursively redacted copy suitable for persisted evidence."""

    if isinstance(value, str):
        return redact_text(value)

    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in SECRET_FIELD_NAMES:
                output[key_text] = "[REDACTED]"
            else:
                output[key_text] = redact(item)
        return output

    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [redact(item) for item in value]

    return value
