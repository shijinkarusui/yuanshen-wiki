"""人工校验共享逻辑（M06E 后端）。

只有 owner 可以设置/清除校验；agent 调用 → 403。
verified_revision 记录校验时的实体 revision，用于过期提示。
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy.orm import Session

from app.core.errors import ApiError


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def set_verification(db: Session, entity, actor_id: uuid.UUID) -> None:
    entity.is_verified = True
    entity.verified_by = actor_id
    entity.verified_at = _now()
    entity.verified_revision = getattr(entity, "revision", None)
    db.commit()


def clear_verification(db: Session, entity) -> None:
    entity.is_verified = False
    entity.verified_by = None
    entity.verified_at = None
    entity.verified_revision = None
    db.commit()


def verification_info(entity) -> dict:
    return {
        "is_verified": bool(getattr(entity, "is_verified", False)),
        "verified_by": str(getattr(entity, "verified_by")) if getattr(entity, "verified_by", None) else None,
        "verified_at": getattr(entity, "verified_at").isoformat() if getattr(entity, "verified_at", None) else None,
        "verified_revision": getattr(entity, "verified_revision", None),
        "revision": getattr(entity, "revision", None),
        # 校验后实体又被修改 → 视为过期
        "verification_stale": bool(getattr(entity, "is_verified", False))
        and getattr(entity, "verified_revision", None) != getattr(entity, "revision", None),
    }
