"""Discourses, paragraphs and anchors API (read slice)."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.ids import parse_uuid
from app.core.crud import get_or_404, archive_entity, restore_entity, apply_update
from app.db.session import get_db
from app.features.discourses.models import Anchor, Discourse, IssueDiscourse, Paragraph
from app.features.identity.deps import get_current_actor, get_public_or_actor, require_owner
from app.features.taxonomy.models import Issue
from app.features.bibliography.models import BibliographicRecord

router_disc = APIRouter(prefix="/discourses", dependencies=[Depends(get_public_or_actor)])
router_anchor = APIRouter(prefix="/anchors", dependencies=[Depends(get_public_or_actor)])


def _sid(v):
    return str(v) if isinstance(v, uuid.UUID) else v


def _disc_dict(d) -> Dict[str, Any]:
    return {
        "id": _sid(d.id),
        "title": d.title,
        "bibliographic_record_id": _sid(d.bibliographic_record_id),
        "source_locator": d.source_locator or {},
        "attribution_note": d.attribution_note or "",
        "revision": d.revision,
        "paragraph_revision": d.paragraph_revision,
        "is_verified": d.is_verified,
    }


def _para_dict(p) -> Dict[str, Any]:
    return {
        "id": _sid(p.id),
        "order": p.current_order,
        "text": p.text,
        "revision": p.revision,
    }


def _anchor_dict(a) -> Dict[str, Any]:
    return {
        "id": _sid(a.id),
        "discourse_id": _sid(a.discourse_id),
        "start_paragraph_id": _sid(a.start_paragraph_id),
        "end_paragraph_id": _sid(a.end_paragraph_id),
        "title": a.title,
        "note": a.note or "",
        "is_valid": a.is_valid,
        "invalid_reason": a.invalid_reason,
        "last_known_range": a.last_known_range,
        "revision": a.revision,
        "is_verified": a.is_verified,
    }


class DiscourseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    bibliographic_record_id: Optional[str] = None
    source_locator: Dict[str, Any] = {}
    attribution_note: str = ""
    paragraphs: List[str] = []
    issue_ids: List[str] = []


@router_disc.get("/")
def list_discourses(
    q: Optional[str] = None,
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 100))
    conds = [Discourse.archived_at.is_(None)]
    if q:
        conds.append(Discourse.title.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(Discourse).where(*conds))
    items = db.scalars(
        select(Discourse).where(*conds).order_by(Discourse.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return {"items": [_disc_dict(d) for d in items], "total": total, "limit": limit, "offset": offset}


@router_disc.post("/")
def create_discourse(
    payload: DiscourseCreate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    bib_id = parse_uuid(payload.bibliographic_record_id, "bibliographic_record_id", optional=True)
    if bib_id is not None and db.get(BibliographicRecord, bib_id) is None:
        raise ApiError("not_found", 404, "bibliographic_record 不存在")
    issue_ids: list[uuid.UUID] = []
    for iid in payload.issue_ids:
        uid = parse_uuid(iid, "issue_ids")
        if db.get(Issue, uid) is None:
            raise ApiError("not_found", 404, f"issue 不存在: {iid}")
        issue_ids.append(uid)
    d = Discourse(
        title=payload.title,
        bibliographic_record_id=bib_id,
        source_locator=payload.source_locator,
        attribution_note=payload.attribution_note,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(d)
    db.flush()
    order = 0
    for text in payload.paragraphs:
        if not text.strip():
            continue
        order += 1  # 跳过空段落后序号连续
        db.add(
            Paragraph(
                discourse_id=d.id,
                text=text,
                current_order=order,
                created_by=actor.id,
                updated_by=actor.id,
            )
        )
    for issue_id in issue_ids:
        db.add(
            IssueDiscourse(
                issue_id=issue_id,
                discourse_id=d.id,
                created_by=actor.id,
                updated_by=actor.id,
            )
        )
    db.commit()
    db.refresh(d)
    return {"data": _disc_dict(d)}


@router_disc.get("/{discourse_id}")
def get_discourse(discourse_id: str, db: Session = Depends(get_db)):
    d = db.get(Discourse, parse_uuid(discourse_id, "discourse_id"))
    if d is None or d.archived_at is not None:
        raise ApiError("not_found", 404, "discourse not found")
    paras = db.scalars(
        select(Paragraph)
        .where(Paragraph.discourse_id == d.id, Paragraph.archived_at.is_(None))
        .order_by(Paragraph.current_order)
    ).all()
    out = _disc_dict(d)
    out["paragraphs"] = [_para_dict(p) for p in paras]
    return {"data": out}


class DiscourseUpdate(BaseModel):
    title: Optional[str] = None
    attribution_note: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None


@router_disc.patch("/{discourse_id}")
def update_discourse(
    discourse_id: str,
    payload: DiscourseUpdate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    d = get_or_404(db, Discourse, discourse_id, "discourse")
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "attributes" in data:
        from app.features.custom_fields.router import validate_attributes
        validate_attributes("discourse", data["attributes"], db)
    apply_update(db, d, data, ["title", "attribution_note", "attributes"], actor.id)
    db.refresh(d)
    return {"data": _disc_dict(d)}


@router_disc.post("/{discourse_id}/archive")
def archive_discourse(discourse_id: str, db: Session = Depends(get_db)):
    d = get_or_404(db, Discourse, discourse_id, "discourse")
    archive_entity(db, d)
    return {"ok": True}


@router_disc.post("/{discourse_id}/restore")
def restore_discourse(discourse_id: str, db: Session = Depends(get_db)):
    d = db.get(Discourse, parse_uuid(discourse_id, "discourse_id"))
    if d is None:
        raise ApiError("not_found", 404, "discourse 不存在")
    restore_entity(db, Discourse, d)
    return {"ok": True}


class AnchorCreate(BaseModel):
    discourse_id: str
    start_paragraph_id: Optional[str] = None
    end_paragraph_id: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=300)
    note: str = ""


@router_anchor.get("/")
def list_anchors(
    discourse_id: Optional[str] = None,
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 100))
    conds = [Anchor.archived_at.is_(None)]
    if discourse_id:
        conds.append(Anchor.discourse_id == parse_uuid(discourse_id, "discourse_id"))
    total = db.scalar(select(func.count()).select_from(Anchor).where(*conds))
    items = db.scalars(
        select(Anchor).where(*conds).order_by(Anchor.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return {"items": [_anchor_dict(a) for a in items], "total": total, "limit": limit, "offset": offset}


@router_anchor.post("/")
def create_anchor(
    payload: AnchorCreate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    did = parse_uuid(payload.discourse_id, "discourse_id")
    if db.get(Discourse, did) is None:
        raise ApiError("not_found", 404, "discourse 不存在")
    start_id = parse_uuid(payload.start_paragraph_id, "start_paragraph_id", optional=True)
    end_id = parse_uuid(payload.end_paragraph_id, "end_paragraph_id", optional=True)
    # 锚点段落必须存在且属于该论述
    para_map: dict[str, Any] = {}
    for pid, fname in ((start_id, "start_paragraph_id"), (end_id, "end_paragraph_id")):
        if pid is None:
            continue
        p = db.get(Paragraph, pid)
        if p is None or p.archived_at is not None or p.discourse_id != did:
            raise ApiError("validation_error", 422, f"{fname} 不是该论述的有效段落")
        para_map[fname] = p
    if start_id is not None and end_id is not None:
        if para_map["start_paragraph_id"].current_order > para_map["end_paragraph_id"].current_order:
            raise ApiError("validation_error", 422, "start_paragraph 必须在 end_paragraph 之前")
    a = Anchor(
        discourse_id=did,
        start_paragraph_id=start_id,
        end_paragraph_id=end_id,
        title=payload.title,
        note=payload.note,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"data": _anchor_dict(a)}


@router_anchor.get("/{anchor_id}")
def get_anchor(anchor_id: str, db: Session = Depends(get_db)):
    a = db.get(Anchor, parse_uuid(anchor_id, "anchor_id"))
    if a is None or a.archived_at is not None:
        raise ApiError("not_found", 404, "anchor not found")
    out = _anchor_dict(a)
    from app.features.relations.verification import verification_info
    out["verification"] = verification_info(a)
    return {"data": out}


@router_anchor.post("/{anchor_id}/verify", dependencies=[Depends(require_owner)])
def verify_anchor(anchor_id: str, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    from app.features.relations.verification import set_verification, verification_info
    a = db.get(Anchor, parse_uuid(anchor_id, "anchor_id"))
    if a is None or a.archived_at is not None:
        raise ApiError("not_found", 404, "anchor not found")
    set_verification(db, a, actor.id)
    out = _anchor_dict(a)
    out["verification"] = verification_info(a)
    return {"data": out}


@router_anchor.post("/{anchor_id}/unverify", dependencies=[Depends(require_owner)])
def unverify_anchor(anchor_id: str, db: Session = Depends(get_db)):
    from app.features.relations.verification import clear_verification, verification_info
    a = db.get(Anchor, parse_uuid(anchor_id, "anchor_id"))
    if a is None or a.archived_at is not None:
        raise ApiError("not_found", 404, "anchor not found")
    clear_verification(db, a)
    out = _anchor_dict(a)
    out["verification"] = verification_info(a)
    return {"data": out}


class AnchorUpdate(BaseModel):
    title: Optional[str] = None
    note: Optional[str] = None


@router_anchor.patch("/{anchor_id}")
def update_anchor(
    anchor_id: str,
    payload: AnchorUpdate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    a = get_or_404(db, Anchor, anchor_id, "anchor")
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    apply_update(db, a, data, ["title", "note"], actor.id)
    db.refresh(a)
    return {"data": _anchor_dict(a)}


@router_anchor.post("/{anchor_id}/archive")
def archive_anchor(anchor_id: str, db: Session = Depends(get_db)):
    a = get_or_404(db, Anchor, anchor_id, "anchor")
    archive_entity(db, a)
    return {"ok": True}


@router_anchor.post("/{anchor_id}/restore")
def restore_anchor(anchor_id: str, db: Session = Depends(get_db)):
    a = db.get(Anchor, parse_uuid(anchor_id, "anchor_id"))
    if a is None:
        raise ApiError("not_found", 404, "anchor 不存在")
    restore_entity(db, Anchor, a)
    return {"ok": True}


# ---- M04C: 段落编辑预览与提交 ----

class ParagraphEditsPreviewRequest(BaseModel):
    base_paragraph_revision: int
    commands: List[Dict[str, Any]]


class ParagraphEditsCommitRequest(BaseModel):
    base_paragraph_revision: int
    commands: List[Dict[str, Any]]
    preview_fingerprint: str


@router_disc.post("/{discourse_id}/paragraph-edits/preview")
def preview_paragraph_edits(
    discourse_id: str,
    body: ParagraphEditsPreviewRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    from app.features.discourses.edit_service import preview_paragraph_edits as _preview

    return {
        "data": _preview(
            db,
            discourse_id,
            request.headers.get("If-Match"),
            body.base_paragraph_revision,
            body.commands,
        )
    }


@router_disc.post("/{discourse_id}/paragraph-edits")
def commit_paragraph_edits(
    discourse_id: str,
    body: ParagraphEditsCommitRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    from app.features.discourses.edit_service import commit_paragraph_edits as _commit

    return {
        "data": _commit(
            db,
            discourse_id,
            actor.id,
            request.headers.get("If-Match"),
            request.headers.get("Idempotency-Key"),
            body.base_paragraph_revision,
            body.commands,
            body.preview_fingerprint,
        )
    }
