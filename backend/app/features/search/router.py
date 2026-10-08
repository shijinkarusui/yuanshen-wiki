"""M05C: 全局检索。

GET /search?q=...&types=issue,discourse,paragraph,anchor,person,record&limit=&offset=

- 中文短词：用 ilike 做子串匹配（不宣称语义检索）
- 归档过滤：只返回未归档
- 类型化筛选：types 参数限定实体类型
- 稳定分页：按 (type, created_at, id) 排序，limit/offset
- 返回统一结构：{type, id, title, snippet, extra}
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_db
from app.features.bibliography.models import BibliographicRecord, Person
from app.features.discourses.models import Anchor, Discourse, Paragraph
from app.features.identity.deps import get_current_actor, get_public_or_actor
from app.features.taxonomy.models import Issue

router = APIRouter(prefix="/search", dependencies=[Depends(get_public_or_actor)])

VALID_TYPES = {"issue", "discourse", "paragraph", "anchor", "person", "record"}

TYPE_LABEL = {
    "issue": "争议问题",
    "discourse": "论述",
    "paragraph": "段落",
    "anchor": "锚点",
    "person": "人物",
    "record": "文献",
}


def _snippet(text: str, q: str, radius: int = 30) -> str:
    """以关键词为中心截取片段。"""
    if not text:
        return ""
    low = text.lower()
    idx = low.find(q.lower())
    if idx < 0:
        return text[: radius * 2]
    start = max(0, idx - radius)
    end = min(len(text), idx + len(q) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end] + suffix


@router.get("")
def search_all(
    q: str = Query(min_length=1, max_length=200),
    types: Optional[str] = Query(default=None, description="逗号分隔，如 issue,discourse"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    wanted = VALID_TYPES
    if types:
        req = {t.strip() for t in types.split(",") if t.strip()}
        bad = req - VALID_TYPES
        if bad:
            raise ApiError("validation_error", 422, f"未知检索类型: {','.join(sorted(bad))}")
        wanted = req

    pattern = f"%{q}%"
    results: List[Dict[str, Any]] = []

    if "issue" in wanted:
        for o in db.scalars(
            select(Issue).where(Issue.archived_at.is_(None), Issue.title.ilike(pattern))
        ):
            results.append({
                "type": "issue", "id": str(o.id), "title": o.title,
                "snippet": _snippet(o.summary or "", q),
                "created_at": o.created_at.isoformat() if o.created_at else "",
            })
    if "discourse" in wanted:
        for o in db.scalars(
            select(Discourse).where(Discourse.archived_at.is_(None), Discourse.title.ilike(pattern))
        ):
            results.append({
                "type": "discourse", "id": str(o.id), "title": o.title,
                "snippet": _snippet(o.attribution_note or "", q),
                "created_at": o.created_at.isoformat() if o.created_at else "",
            })
    if "paragraph" in wanted:
        for o in db.scalars(
            select(Paragraph).where(Paragraph.archived_at.is_(None), Paragraph.text.ilike(pattern))
        ):
            results.append({
                "type": "paragraph", "id": str(o.id),
                "title": f"段落 #{o.current_order}",
                "snippet": _snippet(o.text, q),
                "extra": {"discourse_id": str(o.discourse_id)},
                "created_at": o.created_at.isoformat() if o.created_at else "",
            })
    if "anchor" in wanted:
        for o in db.scalars(
            select(Anchor).where(
                Anchor.archived_at.is_(None),
                or_(Anchor.title.ilike(pattern), Anchor.note.ilike(pattern)),
            )
        ):
            results.append({
                "type": "anchor", "id": str(o.id),
                "title": o.title or "未命名锚点",
                "snippet": _snippet(o.note or "", q),
                "extra": {"discourse_id": str(o.discourse_id)},
                "created_at": o.created_at.isoformat() if o.created_at else "",
            })
    if "person" in wanted:
        for o in db.scalars(
            select(Person).where(Person.archived_at.is_(None), Person.primary_name.ilike(pattern))
        ):
            results.append({
                "type": "person", "id": str(o.id), "title": o.primary_name,
                "snippet": _snippet(o.note or "", q),
                "created_at": o.created_at.isoformat() if o.created_at else "",
            })
    if "record" in wanted:
        for o in db.scalars(
            select(BibliographicRecord).where(
                BibliographicRecord.archived_at.is_(None),
                BibliographicRecord.title.ilike(pattern),
            )
        ):
            results.append({
                "type": "record", "id": str(o.id), "title": o.title,
                "snippet": str(o.year) if o.year else "",
                "created_at": o.created_at.isoformat() if o.created_at else "",
            })

    # 稳定排序：类型 → 创建时间 → id
    results.sort(key=lambda r: (r["type"], r["created_at"], r["id"]))
    total = len(results)
    page = results[offset: offset + limit]
    for r in page:
        r["type_label"] = TYPE_LABEL[r["type"]]
    return {"items": page, "total": total, "limit": limit, "offset": offset, "q": q}
