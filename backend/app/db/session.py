from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _resolve_database_url() -> str:
    for key in (
        "DATABASE_URL",
        "database_url",
        "SQLALCHEMY_DATABASE_URI",
        "sqlalchemy_database_uri",
        "database_uri",
        "postgres_dsn",
        "db_url",
    ):
        try:
            val = getattr(settings, key, None)
        except Exception:
            val = None
        if val:
            return str(val)
    try:
        dump = settings.model_dump()  # type: ignore[attr-defined]
        for key in (
            "DATABASE_URL",
            "database_url",
            "SQLALCHEMY_DATABASE_URI",
            "sqlalchemy_database_uri",
        ):
            if dump.get(key):
                return str(dump[key])
        for _, v in dump.items():
            if isinstance(v, str) and v.startswith(
                ("postgresql://", "postgres://", "postgresql+psycopg://")
            ):
                return v
    except Exception:
        pass
    env_val = os.getenv("DATABASE_URL") or os.getenv("database_url")
    if env_val:
        return env_val
    raise RuntimeError("database url not configured in settings")


def _to_psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


DATABASE_URL = _to_psycopg_url(_resolve_database_url())

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
