from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEYS = re.compile(
    r"(^|[_-])(api[_-]?key|authorization|cookie|password|passwd|secret|token|private[_-]?key)($|[_-])",
    re.IGNORECASE,
)

SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
)


def redact_text(value: str, max_chars: int) -> str:
    result = value
    for pattern in SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    if len(result) > max_chars:
        return result[:max_chars] + "\n[TRUNCATED]"
    return result


def sanitize(value: Any, max_chars: int = 8_000, key: str = "") -> Any:
    if key and SENSITIVE_KEYS.search(key):
        return "[REDACTED]"
    if isinstance(value, str):
        return redact_text(value, max_chars)
    if isinstance(value, dict):
        return {
            str(item_key): sanitize(item_value, max_chars, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(item, max_chars) for item in value[:100]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_text(str(value), max_chars)
