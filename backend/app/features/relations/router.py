"""Relations, annotations and dictionaries API (read slice)."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.ids import parse_uuid
from app.core.crud import get_or_404, archive_entity, restore_entity, apply_update
from app.db.session import get_db
from app.features.identity.deps import get_current_actor, get_public_or_actor, require_owner
from app.features.discourses.models import Anchor
from app.features.relations.models import (
    Annotation,
    DimensionKind,
    Relation,
    RelationDimension,
    RelationKind,
)
from app.features.taxonomy.models import Issue

router_rel = APIRouter(prefix="/relations", dependencies=[Depends(get_public_or_actor)])
router_kind = APIRouter(prefix="/relation-kinds", dependencies=[Depends(get_public_or_actor)])
router_dim = APIRouter(prefix="/dimension-kinds", dependencies=[Depends(get_public_or_actor)])
router_ann = APIRouter(prefix="/annotations", dependencies=[Depends(get_public_or_actor)])


def _sid(v):
    return str(v) if isinstance(v, uuid.UUID) else v


def _rel_dict(r) -> Dict[str, Any]:
    return {
        "id": _sid(r.id),
        "issue_id": _sid(r.issue_id),
        "source_anchor_id": _sid(r.source_anchor_id),
        "target_anchor_id": _sid(r.target_anchor_id),
        "relation_kind_id": _sid(r.relation_kind_id),
        "basis": r.basis,
        "reason": r.reason,
        "revision": r.revision,
        "is_verified": r.is_verified,
    }


class RelationCreate(BaseModel):
    issue_id: str
    source_anchor_id: str
    target_anchor_id: str
    relation_kind_code: str
    basis: str
    reason: str
    dimension_codes: List[str] = []


@router_rel.get("/")
def list_relations(
    issue_id: Optional[str] = None,
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 100))
    conds = [Relation.archived_at.is_(None)]
    if issue_id:
        conds.append(Relation.issue_id == parse_uuid(issue_id, "issue_id"))
    total = db.scalar(select(func.count()).select_from(Relation).where(*conds))
    items = db.scalars(
        select(Relation).where(*conds).order_by(Relation.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return {"items": [_rel_dict(r) for r in items], "total": total, "limit": limit, "offset": offset}


@router_rel.post("/")
def create_relation(
    payload: RelationCreate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    if payload.basis not in ("author_explicit", "analyst_inferred"):
        raise ApiError("validation_error", 422, "invalid basis")
    kind = db.scalar(select(RelationKind).where(RelationKind.code == payload.relation_kind_code))
    if kind is None:
        raise ApiError("validation_error", 422, "unknown relation kind")
    src = db.get(Anchor, parse_uuid(payload.source_anchor_id, "source_anchor_id"))
    tgt = db.get(Anchor, parse_uuid(payload.target_anchor_id, "target_anchor_id"))
    if src is None or tgt is None or not src.is_valid or not tgt.is_valid:
        raise ApiError("anchor_invalid", 422, "anchors must exist and be valid")
    issue_id = parse_uuid(payload.issue_id, "issue_id")
    if db.get(Issue, issue_id) is None:
        raise ApiError("not_found", 404, "issue 不存在")
    r = Relation(
        issue_id=issue_id,
        source_anchor_id=src.id,
        target_anchor_id=tgt.id,
        relation_kind_id=kind.id,
        basis=payload.basis,
        reason=payload.reason,
        source_anchor_revision_at_creation=src.revision,
        target_anchor_revision_at_creation=tgt.revision,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(r)
    db.flush()
    for code in payload.dimension_codes:
        dk = db.scalar(select(DimensionKind).where(DimensionKind.code == code))
        if dk is None:
            raise ApiError("validation_error", 422, f"unknown dimension kind: {code}")
        db.add(
            RelationDimension(
                relation_id=r.id,
                dimension_kind_id=dk.id,
                created_by=actor.id,
                updated_by=actor.id,
            )
        )
    db.commit()
    db.refresh(r)
    return {"data": _rel_dict(r)}


@router_rel.get("/{relation_id}")
def get_relation(relation_id: str, db: Session = Depends(get_db)):
    r = db.get(Relation, parse_uuid(relation_id, "relation_id"))
    if r is None or r.archived_at is not None:
        raise ApiError("not_found", 404, "relation not found")
    out = _rel_dict(r)
    from app.features.relations.verification import verification_info
    out["verification"] = verification_info(r)
    return {"data": out}


@router_rel.post("/{relation_id}/verify", dependencies=[Depends(require_owner)])
def verify_relation(relation_id: str, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    from app.features.relations.verification import set_verification, verification_info
    r = db.get(Relation, parse_uuid(relation_id, "relation_id"))
    if r is None or r.archived_at is not None:
        raise ApiError("not_found", 404, "relation not found")
    set_verification(db, r, actor.id)
    out = _rel_dict(r)
    out["verification"] = verification_info(r)
    return {"data": out}


@router_rel.post("/{relation_id}/unverify", dependencies=[Depends(require_owner)])
def unverify_relation(relation_id: str, db: Session = Depends(get_db)):
    from app.features.relations.verification import clear_verification, verification_info
    r = db.get(Relation, parse_uuid(relation_id, "relation_id"))
    if r is None or r.archived_at is not None:
        raise ApiError("not_found", 404, "relation not found")
    clear_verification(db, r)
    out = _rel_dict(r)
    out["verification"] = verification_info(r)
    return {"data": out}


class RelationUpdate(BaseModel):
    reason: Optional[str] = None
    basis: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None


@router_rel.patch("/{relation_id}")
def update_relation(
    relation_id: str,
    payload: RelationUpdate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    r = get_or_404(db, Relation, relation_id, "relation")
    data = {}
    if payload.reason is not None:
        data["reason"] = payload.reason
    if payload.basis is not None:
        if payload.basis not in ("author_explicit", "analyst_inferred"):
            raise ApiError("validation_error", 422, "invalid basis")
        data["basis"] = payload.basis
    if payload.attributes is not None:
        from app.features.custom_fields.router import validate_attributes
        validate_attributes("relation", payload.attributes, db)
        data["attributes"] = payload.attributes
    # 修改后校验过期
    if data:
        from app.features.relations.verification import clear_verification
        clear_verification(db, r)
    apply_update(db, r, data, ["reason", "basis", "attributes"], actor.id)
    db.refresh(r)
    return {"data": _rel_dict(r)}


@router_rel.post("/{relation_id}/archive")
def archive_relation(relation_id: str, db: Session = Depends(get_db)):
    r = get_or_404(db, Relation, relation_id, "relation")
    archive_entity(db, r)
    return {"data": _rel_dict(r)}


@router_rel.post("/{relation_id}/restore")
def restore_relation(relation_id: str, db: Session = Depends(get_db)):
    r = db.get(Relation, parse_uuid(relation_id, "relation_id"))
    if r is None:
        raise ApiError("not_found", 404, "relation 不存在")
    restore_entity(db, Relation, r)
    db.refresh(r)
    return {"data": _rel_dict(r)}


@router_kind.get("/")
def list_relation_kinds(db: Session = Depends(get_db)):
    kinds = db.scalars(
        select(RelationKind).where(RelationKind.archived_at.is_(None)).order_by(RelationKind.sort_order)
    ).all()
    return {"data": [{"id": _sid(k.id), "code": k.code, "name_cn": k.name_cn} for k in kinds]}


@router_dim.get("/")
def list_dimension_kinds(db: Session = Depends(get_db)):
    kinds = db.scalars(
        select(DimensionKind).where(DimensionKind.archived_at.is_(None)).order_by(DimensionKind.sort_order)
    ).all()
    return {"data": [{"id": _sid(k.id), "code": k.code, "name_cn": k.name_cn} for k in kinds]}


class AnnotationCreate(BaseModel):
    anchor_id: Optional[str] = None
    relation_id: Optional[str] = None
    body: str = ""


@router_ann.get("/")
def list_annotations(
    anchor_id: Optional[str] = None,
    relation_id: Optional[str] = None,
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 100))
    conds = [Annotation.archived_at.is_(None)]
    if anchor_id:
        conds.append(Annotation.anchor_id == parse_uuid(anchor_id, "anchor_id"))
    if relation_id:
        conds.append(Annotation.relation_id == parse_uuid(relation_id, "relation_id"))
    total = db.scalar(select(func.count()).select_from(Annotation).where(*conds))
    items = db.scalars(
        select(Annotation).where(*conds).order_by(Annotation.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "items": [
            {
                "id": _sid(a.id),
                "anchor_id": _sid(a.anchor_id),
                "relation_id": _sid(a.relation_id),
                "body": a.body,
            }
            for a in items
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router_ann.post("/")
def create_annotation(
    payload: AnnotationCreate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    if bool(payload.anchor_id) == bool(payload.relation_id):
        raise ApiError("validation_error", 422, "exactly one of anchor_id/relation_id required")
    anchor_id = parse_uuid(payload.anchor_id, "anchor_id", optional=True)
    relation_id = parse_uuid(payload.relation_id, "relation_id", optional=True)
    if anchor_id is not None and db.get(Anchor, anchor_id) is None:
        raise ApiError("not_found", 404, "anchor 不存在")
    if relation_id is not None and db.get(Relation, relation_id) is None:
        raise ApiError("not_found", 404, "relation 不存在")
    a = Annotation(
        anchor_id=anchor_id,
        relation_id=relation_id,
        body=payload.body,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"data": {"id": _sid(a.id), "body": a.body}}


class AnnotationUpdate(BaseModel):
    body: Optional[str] = None


@router_ann.patch("/{annotation_id}")
def update_annotation(
    annotation_id: str,
    payload: AnnotationUpdate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    a = get_or_404(db, Annotation, annotation_id, "annotation")
    apply_update(db, a, {"body": payload.body} if payload.body is not None else {}, ["body"], actor.id)
    db.refresh(a)
    return {"data": {"id": _sid(a.id), "body": a.body}}


@router_ann.post("/{annotation_id}/archive")
def archive_annotation(annotation_id: str, db: Session = Depends(get_db)):
    a = get_or_404(db, Annotation, annotation_id, "annotation")
    archive_entity(db, a)
    return {"ok": True}


@router_ann.post("/{annotation_id}/restore")
def restore_annotation(annotation_id: str, db: Session = Depends(get_db)):
    a = db.get(Annotation, parse_uuid(annotation_id, "annotation_id"))
    if a is None:
        raise ApiError("not_found", 404, "annotation 不存在")
    restore_entity(db, Annotation, a)
    return {"ok": True}
