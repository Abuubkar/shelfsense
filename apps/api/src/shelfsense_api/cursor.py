"""Opaque, signed pagination cursors: a position plus the query it was issued for.

Signing stops clients from forging positions; binding the query stops a cursor from one query being reused with
another, which would silently skip or repeat rows (docs/adr/0005).
"""

import base64
import hashlib
import hmac
import json
from typing import Any


class InvalidCursor(ValueError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _scope_key(scope: dict[str, Any]) -> str:
    """A short digest of the query: enough to tell queries apart, without carrying them in the cursor."""
    canonical = json.dumps(scope, sort_keys=True, separators=(",", ":"), default=str)
    return _b64(hashlib.sha256(canonical.encode()).digest()[:12])


def _sign(payload: bytes, secret: str) -> bytes:
    return hmac.new(secret.encode(), payload, hashlib.sha256).digest()[:16]


def encode(position: dict[str, Any], scope: dict[str, Any], secret: str) -> str:
    payload = json.dumps({"p": position, "s": _scope_key(scope)}, separators=(",", ":")).encode()
    return f"{_b64(payload)}.{_b64(_sign(payload, secret))}"


def decode(cursor: str, scope: dict[str, Any], secret: str) -> dict[str, Any]:
    try:
        payload_part, signature_part = cursor.split(".")
        payload, signature = _unb64(payload_part), _unb64(signature_part)
    except ValueError:
        raise InvalidCursor("malformed cursor") from None
    if not hmac.compare_digest(signature, _sign(payload, secret)):
        raise InvalidCursor("cursor signature does not match")
    data = json.loads(payload)
    if data["s"] != _scope_key(scope):
        raise InvalidCursor("cursor was issued for a different query")
    position: dict[str, Any] = data["p"]
    return position
