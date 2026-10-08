"""通用更新/归档/恢复助手。"""
from __future__ import annotations

import datetime
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.ids import parse_uuid


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def get_or_404(db: Session, model, id_str: str, name: str):
    obj = db.get(model, parse_uuid(id_str, name))
    if obj is None or getattr(obj, "archived_at", None) is not None:
        raise ApiError("not_found", 404, f"{name} 不存在")
    return obj


def archive_entity(db: Session, obj) -> None:
    if getattr(obj, "archived_at", None) is not None:
        raise ApiError("not_found", 404, "已归档")
    obj.archived_at = _now()
    db.commit()


def restore_entity(db: Session, model, obj, unique_fields: list[str] | None = None) -> None:
    """恢复归档；如有唯一字段冲突则 409。"""
    if getattr(obj, "archived_at", None) is None:
        raise ApiError("not_found", 404, "未归档")
    if unique_fields:
        from sqlalchemy import select, func
        for f in unique_fields:
            val = getattr(obj, f, None)
            if val is None:
                continue
            exists = db.scalar(
                select(func.count()).select_from(model).where(
                    getattr(model, f) == val,
                    model.archived_at.is_(None),
                    model.id != obj.id,
                )
            )
            if exists:
                raise ApiError("conflict", 409, f"恢复冲突：{f} 已存在")
    obj.archived_at = None
    db.commit()


def apply_update(db: Session, obj, data: dict[str, Any], allowed: list[str], actor_id: uuid.UUID) -> None:
    for k in allowed:
        if k in data and data[k] is not None:
            setattr(obj, k, data[k])
    if hasattr(obj, "updated_by"):
        obj.updated_by = actor_id
    if hasattr(obj, "revision"):
        obj.revision = (obj.revision or 1) + 1
    db.commit()
