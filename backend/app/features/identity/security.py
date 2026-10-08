from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Tuple

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _ph.verify(password_hash, password)
        return True
    except (VerifyMismatchError, InvalidHash, AttributeError, ValueError):
        return False


def gen_session_token() -> str:
    return secrets.token_hex(32)


def make_agent_token() -> Tuple[str, str, str]:
    public_id = secrets.token_hex(6)
    secret = secrets.token_hex(16)
    plaintext = f"ldw_{public_id}_{secret}"
    return public_id, secret, plaintext


def _resolve_pepper(pepper: str | None = None) -> str:
    if pepper is not None:
        return pepper
    try:
        from app.core.config import settings

        for key in ("secret_key", "SECRET_KEY", "pepper", "PEPPER"):
            try:
                val = getattr(settings, key, None)
            except Exception:
                val = None
            if val:
                return str(val)
        try:
            dump = settings.model_dump()  # type: ignore[attr-defined]
            for key in ("secret_key", "SECRET_KEY"):
                if dump.get(key):
                    return str(dump[key])
        except Exception:
            pass
    except Exception:
        pass
    return ""


def token_digest(secret: str, pepper: str | None = None) -> str:
    p = _resolve_pepper(pepper)
    return hmac.new(p.encode("utf-8"), secret.encode("utf-8"), hashlib.sha256).hexdigest()
