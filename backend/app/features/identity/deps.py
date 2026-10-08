from __future__ import annotations

import datetime
import hashlib
import hmac

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_db
from app.features.identity.security import token_digest


def _resolve_models():
    candidates = [
        "app.features.identity.models",
        "app.features.identity.model",
        "app.db.models",
        "app.models",
        "app.db.model",
    ]
    for mod in candidates:
        try:
            m = __import__(mod, fromlist=["Actor", "ApiToken", "Session"])
            a = getattr(m, "Actor", None)
            t = getattr(m, "ApiToken", None)
            s = getattr(m, "Session", None)
            if a is not None and t is not None and s is not None:
                return a, t, s
        except Exception:
            continue
    try:
        from app.db.base import Base

        def _all_subs(cls):
            for sub in cls.__subclasses__():
                yield sub
                yield from _all_subs(sub)

        mapping = {getattr(c, "__tablename__", None): c for c in _all_subs(Base)}
        if "actors" in mapping and "api_tokens" in mapping and "sessions" in mapping:
            return mapping["actors"], mapping["api_tokens"], mapping["sessions"]
    except Exception:
        pass
    raise ImportError("identity models not found")


Actor, ApiToken, SessionRow = _resolve_models()


def get_current_actor(request: Request, db: Session = Depends(get_db)):
    now = datetime.datetime.now(datetime.timezone.utc)
    token = request.cookies.get("ldw_session")
    if token:
        try:
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            stmt = select(SessionRow).where(SessionRow.session_digest == digest)
            row = db.execute(stmt).scalars().first()
            if row is not None and getattr(row, "revoked_at", None) is None:
                exp = getattr(row, "expires_at", None)
                if exp is not None:
                    if exp.tzinfo is None:
                        exp = exp.replace(tzinfo=datetime.timezone.utc)
                    if exp > now:
                        actor = db.get(Actor, getattr(row, "actor_id"))
                        if actor is not None and getattr(actor, "active", True):
                            return actor
        except ApiError:
            raise
        except Exception:
            pass
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth and auth.startswith("Bearer "):
        raw = auth[len("Bearer ") :].strip()
        if raw.startswith("ldw_"):
            rest = raw[len("ldw_") :]
            if "_" in rest:
                public_id, secret = rest.split("_", 1)
                if public_id and secret:
                    try:
                        stmt = select(ApiToken).where(ApiToken.public_id == public_id)
                        tok = db.execute(stmt).scalars().first()
                        if tok is not None and getattr(tok, "revoked_at", None) is None:
                            expected = str(getattr(tok, "secret_digest", ""))
                            actual = token_digest(secret)
                            if expected and hmac.compare_digest(expected, actual):
                                actor = db.get(Actor, getattr(tok, "actor_id"))
                                if actor is not None and getattr(actor, "active", True):
                                    try:
                                        tok.last_used_at = now  # type: ignore[attr-defined]
                                        db.commit()
                                    except Exception:
                                        try:
                                            db.rollback()
                                        except Exception:
                                            pass
                                    return actor
                    except ApiError:
                        raise
                    except Exception:
                        pass
    raise ApiError("unauthenticated", 401, "unauthenticated")


def require_owner(actor=Depends(get_current_actor)):
    if getattr(actor, "kind", None) != "owner":
        raise ApiError("forbidden", 403, "forbidden")
    return actor


def get_public_or_actor(request: Request, db: Session = Depends(get_db)):
    """读操作公开（未登录返回 None），写操作必须登录。"""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        try:
            return get_current_actor(request, db)
        except ApiError:
            return None
    return get_current_actor(request, db)
