from __future__ import annotations

import datetime
import hashlib
import secrets
import uuid

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_db
from app.features.identity.deps import get_current_actor, require_owner
from app.features.identity.security import (
    gen_session_token,
    hash_password,
    make_agent_token,
    token_digest,
    verify_password,
)


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

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_COOKIE = "ldw_session"
SESSION_DAYS = 30


class BootstrapOwnerIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=256)


class SessionIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=256)


class TokenCreateIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _actor_out(actor) -> dict:
    return {"id": str(getattr(actor, "id")), "display_name": getattr(actor, "display_name"), "kind": getattr(actor, "kind")}


def _sha256hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@router.post("/bootstrap-owner")
def bootstrap_owner(payload: BootstrapOwnerIn, db: Session = Depends(get_db)):
    existing = db.execute(select(Actor).where(Actor.kind == "owner", Actor.active.is_(True))).scalars().first()
    if existing is not None:
        raise ApiError("forbidden", 403, "owner already bootstrapped")
    actor = Actor(
        id=uuid.uuid4(),
        kind="owner",
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
        active=True,
    )
    db.add(actor)
    db.commit()
    db.refresh(actor)
    return _actor_out(actor)


@router.post("/session")
def create_session(payload: SessionIn, response: Response, db: Session = Depends(get_db)):
    stmt = select(Actor).where(Actor.display_name == payload.display_name.strip(), Actor.kind == "owner")
    actor = db.execute(stmt).scalars().first()
    if actor is None or not getattr(actor, "active", False):
        raise ApiError("unauthenticated", 401, "invalid credentials")
    ph = getattr(actor, "password_hash", None)
    if not ph or not verify_password(str(ph), payload.password):
        raise ApiError("unauthenticated", 401, "invalid credentials")
    now = _now()
    token = gen_session_token()
    session_digest = _sha256hex(token)
    csrf_raw = secrets.token_hex(32)
    csrf_digest = _sha256hex(csrf_raw)
    expires_at = now + datetime.timedelta(days=SESSION_DAYS)
    row = SessionRow(
        id=uuid.uuid4(),
        session_digest=session_digest,
        actor_id=getattr(actor, "id"),
        csrf_digest=csrf_digest,
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="strict",
        path="/",
        max_age=SESSION_DAYS * 24 * 60 * 60,
    )
    return _actor_out(actor)


@router.delete("/session")
def delete_session(request: Request, response: Response, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    now = _now()
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        try:
            digest = _sha256hex(token)
            row = db.execute(select(SessionRow).where(SessionRow.session_digest == digest)).scalars().first()
            if row is not None and getattr(row, "revoked_at", None) is None:
                row.revoked_at = now  # type: ignore[attr-defined]
                db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def get_me(actor=Depends(get_current_actor)):
    return _actor_out(actor)


@router.post("/tokens")
def create_token(payload: TokenCreateIn, db: Session = Depends(get_db), owner=Depends(require_owner)):
    now = _now()
    agent = Actor(
        id=uuid.uuid4(),
        kind="agent",
        display_name=payload.display_name.strip(),
        password_hash=None,
        active=True,
    )
    db.add(agent)
    db.flush()
    public_id, secret, plaintext = make_agent_token()
    digest = token_digest(secret)
    rec = ApiToken(
        id=uuid.uuid4(),
        actor_id=getattr(agent, "id"),
        public_id=public_id,
        secret_digest=digest,
        scopes=[],
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return {"token_id": str(getattr(rec, "id")), "public_id": public_id, "token_plaintext": plaintext}


@router.get("/tokens")
def list_tokens(db: Session = Depends(get_db), owner=Depends(require_owner)):
    rows = db.execute(select(ApiToken).order_by(ApiToken.created_at.desc())).scalars().all()
    out: list[dict] = []
    for t in rows:
        actor = db.get(Actor, getattr(t, "actor_id"))
        out.append(
            {
                "id": str(getattr(t, "id")),
                "public_id": getattr(t, "public_id"),
                "actor_id": str(getattr(t, "actor_id")),
                "display_name": getattr(actor, "display_name", None) if actor is not None else None,
                "scopes": getattr(t, "scopes", []),
                "last_used_at": getattr(t, "last_used_at").isoformat() if getattr(t, "last_used_at", None) else None,
                "revoked_at": getattr(t, "revoked_at").isoformat() if getattr(t, "revoked_at", None) else None,
                "created_at": getattr(t, "created_at").isoformat() if getattr(t, "created_at", None) else None,
            }
        )
    return out


@router.post("/tokens/{token_id}/revoke")
def revoke_token(token_id: uuid.UUID, db: Session = Depends(get_db), owner=Depends(require_owner)):
    tok = db.get(ApiToken, token_id)
    if tok is None:
        raise ApiError("not_found", 404, "token not found")
    now = _now()
    if getattr(tok, "revoked_at", None) is None:
        tok.revoked_at = now  # type: ignore[attr-defined]
        db.commit()
        db.refresh(tok)
    revoked = getattr(tok, "revoked_at", None)
    return {"id": str(getattr(tok, "id")), "revoked_at": revoked.isoformat() if revoked else None}
