"""Standard JSON response helpers."""

from __future__ import annotations

from typing import Any, Mapping


def json_success(data: Mapping[str, Any], status_code: int = 200) -> tuple[dict[str, Any], int]:
    """Wrap a successful payload for Flask jsonify consistency."""
    payload = dict(data)
    return payload, status_code


def json_error(message: str, status_code: int = 500, extra: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], int]:
    """Build an error payload."""
    body: dict[str, Any] = {"error": message, "ok": False}
    if extra:
        body.update(dict(extra))
    return body, status_code
