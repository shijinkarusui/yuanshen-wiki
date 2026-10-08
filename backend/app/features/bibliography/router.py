"""Persons and bibliographic records API."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.ids import parse_uuid
from app.core.crud import get_or_404, archive_entity, restore_entity, apply_update
from app.db.session import get_db
from app.features.bibliography.models import (
    BibliographicContributor,
    BibliographicRecord,
    Person,
)
from app.features.identity.deps import get_current_actor, get_public_or_actor

router_person = APIRouter(prefix="/persons", dependencies=[Depends(get_public_or_actor)])
router_ref = APIRouter(prefix="/references", dependencies=[Depends(get_public_or_actor)])


def _sid(v):
    return str(v) if isinstance(v, uuid.UUID) else v


def _person_dict(p) -> Dict[str, Any]:
    return {
        "id": _sid(p.id),
        "primary_name": p.primary_name,
        "aliases": p.aliases or [],
        "note": p.note or "",
        "revision": p.revision,
    }


def _record_dict(r, contributors=None) -> Dict[str, Any]:
    d = {
        "id": _sid(r.id),
        "record_type": r.record_type,
        "title": r.title,
        "year": r.year,
        "language": r.language,
        "doi_normalized": r.doi_normalized,
        "publication": r.publication or {},
        "revision": r.revision,
    }
    if contributors is not None:
        d["contributors"] = contributors
    return d


def _contrib_dict(c) -> Dict[str, Any]:
    return {
        "id": _sid(c.id),
        "person_id": _sid(c.person_id),
        "literal_name": c.literal_name,
        "role": c.role,
        "ordinal": c.ordinal,
    }


class PersonCreate(BaseModel):
    primary_name: str = Field(min_length=1, max_length=300)
    aliases: List[str] = []
    note: str = ""


@router_person.get("/")
def list_persons(
    q: Optional[str] = None,
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 100))
    from sqlalchemy import func

    conds = [Person.archived_at.is_(None)]
    if q:
        conds.append(Person.primary_name.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(Person).where(*conds))
    items = db.scalars(
        select(Person).where(*conds).order_by(Person.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "items": [_person_dict(p) for p in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router_person.post("/")
def create_person(
    payload: PersonCreate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    p = Person(
        primary_name=payload.primary_name,
        aliases=payload.aliases,
        note=payload.note,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"data": _person_dict(p)}


@router_person.get("/{person_id}")
def get_person(person_id: str, db: Session = Depends(get_db)):
    p = db.get(Person, parse_uuid(person_id, "person_id"))
    if p is None or p.archived_at is not None:
        raise ApiError("not_found", 404, "person not found")
    return {"data": _person_dict(p)}


class PersonUpdate(BaseModel):
    primary_name: Optional[str] = None
    aliases: Optional[List[str]] = None
    note: Optional[str] = None


@router_person.patch("/{person_id}")
def update_person(
    person_id: str,
    payload: PersonUpdate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    p = get_or_404(db, Person, person_id, "person")
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    apply_update(db, p, data, ["primary_name", "aliases", "note"], actor.id)
    db.refresh(p)
    return {"data": _person_dict(p)}


@router_person.post("/{person_id}/archive")
def archive_person(person_id: str, db: Session = Depends(get_db)):
    p = get_or_404(db, Person, person_id, "person")
    archive_entity(db, p)
    return {"ok": True}


@router_person.post("/{person_id}/restore")
def restore_person(person_id: str, db: Session = Depends(get_db)):
    p = db.get(Person, parse_uuid(person_id, "person_id"))
    if p is None:
        raise ApiError("not_found", 404, "person 不存在")
    restore_entity(db, Person, p)
    return {"ok": True}


class ContributorIn(BaseModel):
    person_id: Optional[str] = None
    literal_name: Optional[str] = None
    role: str = "author"
    ordinal: int = 0


class RecordCreate(BaseModel):
    record_type: str
    title: str
    year: Optional[int] = None
    language: Optional[str] = None
    doi_normalized: Optional[str] = None
    publication: Dict[str, Any] = {}
    contributors: List[ContributorIn] = []


def _normalize_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    d = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
            break
    return d or None


@router_ref.get("/")
def list_records(
    q: Optional[str] = None,
    record_type: Optional[str] = None,
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    from sqlalchemy import func

    limit = max(1, min(limit, 100))
    conds = [BibliographicRecord.archived_at.is_(None)]
    if q:
        conds.append(BibliographicRecord.title.ilike(f"%{q}%"))
    if record_type:
        conds.append(BibliographicRecord.record_type == record_type)
    total = db.scalar(select(func.count()).select_from(BibliographicRecord).where(*conds))
    items = db.scalars(
        select(BibliographicRecord)
        .where(*conds)
        .order_by(BibliographicRecord.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [_record_dict(r) for r in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router_ref.post("/")
def create_record(
    payload: RecordCreate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    if payload.record_type not in ("journal", "book", "chapter", "thesis"):
        raise ApiError("validation_error", 422, f"未知 record_type: {payload.record_type}")
    doi = _normalize_doi(payload.doi_normalized)
    if doi:
        exists = db.scalar(
            select(BibliographicRecord.id).where(
                BibliographicRecord.doi_normalized == doi,
                BibliographicRecord.archived_at.is_(None),
            )
        )
        if exists:
            raise ApiError("unique_conflict", 409, "doi already exists")
    r = BibliographicRecord(
        record_type=payload.record_type,
        title=payload.title,
        year=payload.year,
        language=payload.language,
        doi_normalized=doi,
        publication=payload.publication,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(r)
    db.flush()
    contribs = []
    for c in payload.contributors:
        pid = parse_uuid(c.person_id, "contributors.person_id", optional=True)
        if pid is not None and db.get(Person, pid) is None:
            raise ApiError("not_found", 404, f"person 不存在: {c.person_id}")
        bc = BibliographicContributor(
            record_id=r.id,
            person_id=pid,
            literal_name=c.literal_name,
            role=c.role,
            ordinal=c.ordinal,
            created_by=actor.id,
            updated_by=actor.id,
        )
        db.add(bc)
        db.flush()
        contribs.append(_contrib_dict(bc))
    # contributor changes bump record revision (spec 6.2)
    r.revision = (r.revision or 1) + 1
    db.commit()
    db.refresh(r)
    return {"data": _record_dict(r, contribs)}


@router_ref.get("/{record_id}")
def get_record(record_id: str, db: Session = Depends(get_db)):
    r = db.get(BibliographicRecord, parse_uuid(record_id, "record_id"))
    if r is None or r.archived_at is not None:
        raise ApiError("not_found", 404, "record not found")
    contribs = db.scalars(
        select(BibliographicContributor)
        .where(
            BibliographicContributor.record_id == r.id,
            BibliographicContributor.archived_at.is_(None),
        )
        .order_by(BibliographicContributor.ordinal)
    ).all()
    return {"data": _record_dict(r, [_contrib_dict(c) for c in contribs])}


class RecordUpdate(BaseModel):
    title: Optional[str] = None
    year: Optional[int] = None
    language: Optional[str] = None
    publication: Optional[str] = None


@router_ref.patch("/{record_id}")
def update_record(
    record_id: str,
    payload: RecordUpdate,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    r = get_or_404(db, BibliographicRecord, record_id, "record")
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    apply_update(db, r, data, ["title", "year", "language", "publication"], actor.id)
    db.refresh(r)
    return {"data": _record_dict(r)}


@router_ref.post("/{record_id}/archive")
def archive_record(record_id: str, db: Session = Depends(get_db)):
    r = get_or_404(db, BibliographicRecord, record_id, "record")
    archive_entity(db, r)
    return {"ok": True}


@router_ref.post("/{record_id}/restore")
def restore_record(record_id: str, db: Session = Depends(get_db)):
    r = db.get(BibliographicRecord, parse_uuid(record_id, "record_id"))
    if r is None:
        raise ApiError("not_found", 404, "record 不存在")
    restore_entity(db, BibliographicRecord, r)
    return {"ok": True}
