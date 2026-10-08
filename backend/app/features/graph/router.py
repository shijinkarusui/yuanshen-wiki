"""M07A: 图谱查询（spec §10.2）。

节点是锚点，边是关系。
- 节点标题优先 anchor.title；否则"第一责任者-年份-当前段落范围"
- 单次最多 200 节点 / 500 边；超限返回截断结果 + truncated=true；
  只有请求参数显式超过硬上限才 422 graph_limit_exceeded
- 失效/归档节点保留状态徽标
- 无孤立边（边的两端都必须在返回节点集合中）
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.ids import parse_uuid
from app.db.session import get_db
from app.features.bibliography.models import (
    BibliographicContributor,
    BibliographicRecord,
    Person,
)
from app.features.discourses.models import Anchor, Discourse, IssueDiscourse, Paragraph
from app.features.identity.deps import get_current_actor, get_public_or_actor
from app.features.relations.models import Relation

router_graph = APIRouter(prefix="/graph", dependencies=[Depends(get_public_or_actor)])

MAX_NODES = 200
MAX_EDGES = 500


def _sid(v):
    return str(v) if isinstance(v, uuid.UUID) else v


@router_graph.get("")
def get_graph(
    issue_id: Optional[str] = Query(default=None),
    discourse_id: Optional[str] = Query(default=None),
    limit_nodes: int = Query(default=MAX_NODES, ge=1),
    limit_edges: int = Query(default=MAX_EDGES, ge=1),
    db: Session = Depends(get_db),
):
    if limit_nodes > MAX_NODES or limit_edges > MAX_EDGES:
        raise ApiError(
            "graph_limit_exceeded", 422,
            f"图谱上限为 {MAX_NODES} 节点 / {MAX_EDGES} 边，请缩小范围后重试",
        )

    # ---- 确定论述范围 ----
    discourse_ids: List[uuid.UUID] = []
    if discourse_id:
        discourse_ids = [parse_uuid(discourse_id, "discourse_id")]
    elif issue_id:
        iid = parse_uuid(issue_id, "issue_id")
        discourse_ids = list(
            db.execute(
                select(IssueDiscourse.discourse_id).where(
                    IssueDiscourse.issue_id == iid,
                    IssueDiscourse.archived_at.is_(None),
                )
            ).scalars()
        )
    else:
        raise ApiError("missing_scope", 400, "需要 issue_id 或 discourse_id")

    if not discourse_ids:
        return {"data": {"nodes": [], "edges": [],
                         "total_nodes": 0, "total_edges": 0, "truncated": False}}

    # ---- 节点：锚点（含失效；归档锚点带徽标） ----
    anchors = list(
        db.execute(
            select(Anchor)
            .where(Anchor.discourse_id.in_(discourse_ids))
            .order_by(Anchor.created_at)
        ).scalars()
    )
    total_nodes = len(anchors)
    truncated = False
    shown_anchors = anchors[:limit_nodes]
    if total_nodes > limit_nodes:
        truncated = True
    shown_anchor_ids = {a.id for a in shown_anchors}

    # 段落段号映射（用于标题回退与范围显示）
    para_orders: Dict[uuid.UUID, int] = {}
    for did in discourse_ids:
        for pid, ord_ in db.execute(
            select(Paragraph.id, Paragraph.current_order).where(
                Paragraph.discourse_id == did,
                Paragraph.archived_at.is_(None),
            )
        ):
            para_orders[pid] = ord_

    # 文献信息（标题回退：第一责任者-年份）
    bib_info: Dict[uuid.UUID, Dict[str, Any]] = {}
    for did in discourse_ids:
        d = db.get(Discourse, did)
        if d is None or d.bibliographic_record_id is None:
            continue
        rec = db.get(BibliographicRecord, d.bibliographic_record_id)
        if rec is None:
            continue
        contrib = db.execute(
            select(BibliographicContributor, Person)
            .outerjoin(Person, Person.id == BibliographicContributor.person_id)
            .where(
                BibliographicContributor.record_id == rec.id,
                BibliographicContributor.archived_at.is_(None),
            )
            .order_by(BibliographicContributor.ordinal)
            .limit(1)
        ).first()
        name = None
        if contrib:
            bc, person = contrib
            name = (person.primary_name if person else None) or bc.literal_name
        bib_info[did] = {"author": name, "year": rec.year}

    nodes = []
    for a in shown_anchors:
        start_o = para_orders.get(a.start_paragraph_id) if a.start_paragraph_id else None
        end_o = para_orders.get(a.end_paragraph_id) if a.end_paragraph_id else None
        rng = f"{start_o}-{end_o}" if start_o and end_o else "?"
        title = a.title
        if not title:
            bi = bib_info.get(a.discourse_id, {})
            author = bi.get("author") or "佚名"
            year = bi.get("year") or "?"
            title = f"{author}-{year} §{rng}"
        nodes.append({
            "id": _sid(a.id),
            "title": title,
            "discourse_id": _sid(a.discourse_id),
            "is_valid": a.is_valid,
            "archived": a.archived_at is not None,
            "is_verified": a.is_verified,
            "range": {"start": start_o, "end": end_o},
            "revision": a.revision,
        })

    # ---- 边：关系（两端都必须在返回节点中，无孤立边） ----
    relations = list(
        db.execute(
            select(Relation).where(
                or_(
                    Relation.source_anchor_id.in_(shown_anchor_ids),
                    Relation.target_anchor_id.in_(shown_anchor_ids),
                ),
                Relation.archived_at.is_(None),
            )
        ).scalars()
    )
    # 过滤孤立边
    relations = [
        r for r in relations
        if r.source_anchor_id in shown_anchor_ids and r.target_anchor_id in shown_anchor_ids
    ]
    total_edges = len(relations)
    shown_relations = relations[:limit_edges]
    if total_edges > limit_edges:
        truncated = True

    edges = [
        {
            "id": _sid(r.id),
            "source_anchor_id": _sid(r.source_anchor_id),
            "target_anchor_id": _sid(r.target_anchor_id),
            "basis": r.basis,
            "reason": r.reason,
            "is_verified": r.is_verified,
            "archived": False,
            "revision": r.revision,
        }
        for r in shown_relations
    ]

    return {"data": {
        "nodes": nodes,
        "edges": edges,
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "truncated": truncated,
    }}
