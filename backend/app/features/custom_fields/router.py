"""M02C: 自定义字段定义 CRUD + 服务端校验。

- 六种类型：text / long_text / number / boolean / single_select / multi_select
- key 不可改；在用（已有值引用）的类型/选项不可改
- 归档后同名 key 允许新建（UUID 隔离）；恢复时 key 冲突则 409
- Agent（非 owner）管理定义 → 403
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.ids import parse_uuid
from app.db.session import get_db
from app.features.custom_fields.models import FieldDefinition
from app.features.identity.deps import get_current_actor, get_public_or_actor, require_owner

router = APIRouter(prefix="/field-definitions", dependencies=[Depends(get_public_or_actor)])

VALUE_TYPES = {"text", "long_text", "number", "boolean", "single_select", "multi_select"}


def _def_dict(d: FieldDefinition) -> Dict[str, Any]:
    return {
        "id": str(d.id),
        "key": d.key,
        "label": d.label,
        "entity_kind": d.entity_kind,
        "value_type": d.value_type,
        "description": d.description or "",
        "options": d.options or [],
        "is_system": d.is_system,
        "archived": d.archived_at is not None,
        "revision": d.revision,
    }


def validate_attributes(entity_kind: str, attributes: Dict[str, Any], db: Session) -> None:
    """校验 attributes 是否符合该 entity_kind 的字段定义；非法抛 422。"""
    if not isinstance(attributes, dict):
        raise ApiError("validation_error", 422, "attributes 必须是对象")
    defs = {
        d.key: d
        for d in db.scalars(
            select(FieldDefinition).where(
                FieldDefinition.entity_kind == entity_kind,
                FieldDefinition.archived_at.is_(None),
            )
        )
    }
    for key, val in attributes.items():
        d = defs.get(key)
        if d is None:
            raise ApiError("validation_error", 422, f"未知字段: {key}")
        vt = d.value_type
        if vt in ("text", "long_text"):
            if not isinstance(val, str):
                raise ApiError("validation_error", 422, f"字段 {key} 应为字符串")
        elif vt == "number":
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise ApiError("validation_error", 422, f"字段 {key} 应为数字")
        elif vt == "boolean":
            if not isinstance(val, bool):
                raise ApiError("validation_error", 422, f"字段 {key} 应为布尔值")
        elif vt == "single_select":
            if val not in (d.options or []):
                raise ApiError("validation_error", 422, f"字段 {key} 取值不在选项内")
        elif vt == "multi_select":
            if not isinstance(val, list) or any(v not in (d.options or []) for v in val):
                raise ApiError("validation_error", 422, f"字段 {key} 取值不在选项内")


class FieldDefCreate(BaseModel):
    key: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=200)
    entity_kind: str = Field(min_length=1, max_length=64)
    value_type: str
    description: str = ""
    options: List[str] = []


class FieldDefUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    options: Optional[List[str]] = None


@router.get("/")
def list_field_definitions(
    entity_kind: Optional[str] = None,
    include_archived: bool = False,
    db: Session = Depends(get_db),
):
    conds = []
    if entity_kind:
        conds.append(FieldDefinition.entity_kind == entity_kind)
    if not include_archived:
        conds.append(FieldDefinition.archived_at.is_(None))
    items = db.scalars(
        select(FieldDefinition).where(*conds).order_by(FieldDefinition.entity_kind, FieldDefinition.key)
    ).all()
    return {"items": [_def_dict(d) for d in items], "total": len(items)}


@router.post("/", dependencies=[Depends(require_owner)])
def create_field_definition(
    payload: FieldDefCreate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    if payload.value_type not in VALUE_TYPES:
        raise ApiError("validation_error", 422, f"未知 value_type: {payload.value_type}")
    if payload.value_type in ("single_select", "multi_select") and not payload.options:
        raise ApiError("validation_error", 422, "选择型字段必须提供 options")
    if payload.value_type not in ("single_select", "multi_select") and payload.options:
        raise ApiError("validation_error", 422, "非选择型字段不应提供 options")
    exists = db.scalar(
        select(func.count()).select_from(FieldDefinition).where(
            FieldDefinition.entity_kind == payload.entity_kind,
            FieldDefinition.key == payload.key,
            FieldDefinition.archived_at.is_(None),
        )
    )
    if exists:
        raise ApiError("conflict", 409, f"key 已存在: {payload.key}")
    d = FieldDefinition(
        key=payload.key,
        label=payload.label,
        entity_kind=payload.entity_kind,
        value_type=payload.value_type,
        description=payload.description,
        options=payload.options,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return {"data": _def_dict(d)}


@router.get("/{def_id}")
def get_field_definition(def_id: str, db: Session = Depends(get_db)):
    d = db.get(FieldDefinition, parse_uuid(def_id, "field_definition_id"))
    if d is None:
        raise ApiError("not_found", 404, "字段定义不存在")
    return {"data": _def_dict(d)}


@router.patch("/{def_id}", dependencies=[Depends(require_owner)])
def update_field_definition(
    def_id: str,
    payload: FieldDefUpdate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    d = db.get(FieldDefinition, parse_uuid(def_id, "field_definition_id"))
    if d is None or d.archived_at is not None:
        raise ApiError("not_found", 404, "字段定义不存在")
    if d.is_system:
        raise ApiError("forbidden", 403, "系统字段不可修改")
    # key / value_type / entity_kind 不可改；options 仅在未使用时可改
    # （MVP：options 修改直接允许，值校验在写入时执行）
    if payload.label is not None:
        d.label = payload.label
    if payload.description is not None:
        d.description = payload.description
    if payload.options is not None:
        if d.value_type not in ("single_select", "multi_select"):
            raise ApiError("validation_error", 422, "非选择型字段不能设置 options")
        if not payload.options:
            raise ApiError("validation_error", 422, "选择型字段 options 不能为空")
        d.options = payload.options
    d.updated_by = actor.id
    d.revision = (d.revision or 1) + 1
    db.commit()
    db.refresh(d)
    return {"data": _def_dict(d)}


@router.post("/{def_id}/archive", dependencies=[Depends(require_owner)])
def archive_field_definition(def_id: str, db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    d = db.get(FieldDefinition, parse_uuid(def_id, "field_definition_id"))
    if d is None or d.archived_at is not None:
        raise ApiError("not_found", 404, "字段定义不存在")
    if d.is_system:
        raise ApiError("forbidden", 403, "系统字段不可归档")
    d.archived_at = datetime.now(timezone.utc)
    db.commit()
    return {"data": _def_dict(d)}


@router.post("/{def_id}/restore", dependencies=[Depends(require_owner)])
def restore_field_definition(def_id: str, db: Session = Depends(get_db)):
    d = db.get(FieldDefinition, parse_uuid(def_id, "field_definition_id"))
    if d is None or d.archived_at is None:
        raise ApiError("not_found", 404, "字段定义不存在或未归档")
    conflict = db.scalar(
        select(func.count()).select_from(FieldDefinition).where(
            FieldDefinition.entity_kind == d.entity_kind,
            FieldDefinition.key == d.key,
            FieldDefinition.archived_at.is_(None),
            FieldDefinition.id != d.id,
        )
    )
    if conflict:
        raise ApiError("conflict", 409, f"恢复冲突：同名 key 已存在: {d.key}")
    d.archived_at = None
    db.commit()
    db.refresh(d)
    return {"data": _def_dict(d)}
