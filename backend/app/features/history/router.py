"""M08A: 历史查询和差异（spec §8.1/8.2）。

- GET /api/v1/history/change-sets — 全局/对象历史（entity_kind/entity_id 过滤）
- GET /api/v1/history/change-sets/{id} — 变更详情（含 change_items、lineage、anchor 调整）
- 关系对象历史聚合其两端锚点的 anchor_adjustments（§8.1）
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.ids import parse_uuid
from app.db.session import get_db
from app.features.history_write.models import (
    AnchorAdjustment,
    AnchorAdjustmentRelation,
    ChangeEffectState,
    ChangeItem,
    ChangeSet,
    ParagraphLineage,
)
from app.features.identity.deps import get_current_actor, get_public_or_actor
from app.features.relations.models import Relation

router_history = APIRouter(prefix="/history", dependencies=[Depends(get_public_or_actor)])


def _sid(v):
    return str(v) if isinstance(v, uuid.UUID) else v


def _cs_dict(cs: ChangeSet) -> Dict[str, Any]:
    return {
        "id": _sid(cs.id),
        "sequence_no": cs.sequence_no,
        "actor_id": _sid(cs.actor_id),
        "operation": cs.operation,
        "summary": cs.summary,
        "effect_direction": cs.effect_direction,
        "reverts_change_set_id": _sid(cs.reverts_change_set_id) if cs.reverts_change_set_id else None,
        "root_effect_change_set_id": _sid(cs.root_effect_change_set_id),
        "created_at": cs.created_at.isoformat() if cs.created_at else None,
    }


@router_history.get("/change-sets")
def list_change_sets(
    entity_kind: Optional[str] = Query(default=None),
    entity_id: Optional[str] = Query(default=None),
    operation: Optional[str] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    q = select(ChangeSet)
    if entity_kind or entity_id:
        sub = select(ChangeItem.change_set_id).where(
            *([ChangeItem.entity_kind == entity_kind] if entity_kind else []),
            *([ChangeItem.entity_id == parse_uuid(entity_id, "entity_id")] if entity_id else []),
        ).distinct()
        q = q.where(ChangeSet.id.in_(sub))
    if operation:
        q = q.where(ChangeSet.operation == operation)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar()
    items = list(db.execute(q.order_by(desc(ChangeSet.sequence_no)).limit(limit).offset(offset)).scalars())
    return {"items": [_cs_dict(cs) for cs in items], "total": total, "limit": limit, "offset": offset}


@router_history.get("/change-sets/{change_set_id}")
def get_change_set(change_set_id: str, db: Session = Depends(get_db)):
    csid = parse_uuid(change_set_id, "change_set_id")
    cs = db.get(ChangeSet, csid)
    if cs is None:
        raise ApiError("not_found", 404, "变更不存在")

    items = list(
        db.execute(
            select(ChangeItem).where(ChangeItem.change_set_id == csid).order_by(ChangeItem.id)
        ).scalars()
    )
    lineage = list(
        db.execute(
            select(ParagraphLineage)
            .where(ParagraphLineage.change_set_id == csid)
            .order_by(ParagraphLineage.step_index)
        ).scalars()
    )
    adjustments = list(
        db.execute(
            select(AnchorAdjustment).where(AnchorAdjustment.change_set_id == csid)
        ).scalars()
    )

    # 关系对象历史聚合两端锚点的 adjustments（§8.1）
    relation_anchor_adjustments: List[Dict[str, Any]] = []
    for item in items:
        if item.entity_kind != "relation":
            continue
        rel = db.get(Relation, item.entity_id)
        if rel is None:
            continue
        for aid in (rel.source_anchor_id, rel.target_anchor_id):
            adj = db.execute(
                select(AnchorAdjustment).where(
                    AnchorAdjustment.change_set_id == csid,
                    AnchorAdjustment.anchor_id == aid,
                )
            ).scalars().first()
            if adj:
                relation_anchor_adjustments.append({
                    "anchor_id": _sid(aid),
                    "old_start_order": adj.old_start_order,
                    "old_end_order": adj.old_end_order,
                    "new_start_order": adj.new_start_order,
                    "new_end_order": adj.new_end_order,
                    "content_changed": adj.content_changed,
                    "display_range_changed": adj.display_range_changed,
                    "validity_changed": adj.validity_changed,
                })

    state = db.get(ChangeEffectState, cs.root_effect_change_set_id)

    return {"data": {
        **_cs_dict(cs),
        "is_applied": state.is_applied if state else True,
        "last_toggle_change_set_id": _sid(state.last_toggle_change_set_id) if state else _sid(cs.id),
        "items": [
            {
                "id": _sid(i.id),
                "entity_kind": i.entity_kind,
                "entity_id": _sid(i.entity_id),
                "before_revision": i.before_revision,
                "after_revision": i.after_revision,
                "before": i.before,
                "after": i.after,
                "changed_fields": i.changed_fields,
            }
            for i in items
        ],
        "paragraph_lineage": [
            {
                "step_index": l.step_index,
                "command_type": l.command_type,
                "source_ids": [_sid(x) for x in l.source_ids],
                "source_orders": l.source_orders,
                "target_ids": [_sid(x) for x in l.target_ids],
                "target_orders": l.target_orders,
            }
            for l in lineage
        ],
        "anchor_adjustments": [
            {
                "anchor_id": _sid(a.anchor_id),
                "old_start_order": a.old_start_order,
                "old_end_order": a.old_end_order,
                "new_start_order": a.new_start_order,
                "new_end_order": a.new_end_order,
                "content_changed": a.content_changed,
                "display_range_changed": a.display_range_changed,
                "validity_changed": a.validity_changed,
            }
            for a in adjustments
        ],
        "relation_anchor_adjustments": relation_anchor_adjustments,
    }}


# ---- M08B: 撤销预览与提交 ----

class RevertCommitRequest(BaseModel):
    revert_preview_token: str
    idempotency_key: str


@router_history.post("/change-sets/{change_set_id}/revert-preview")
def post_revert_preview(
    change_set_id: str,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    from app.features.history.revert import revert_preview as _preview

    return {"data": _preview(db, change_set_id, actor.id)}


@router_history.post("/change-sets/{change_set_id}/revert")
def post_revert(
    change_set_id: str,
    body: RevertCommitRequest,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    from app.features.history.revert import revert_commit as _commit

    return {"data": _commit(db, change_set_id, actor.id,
                            body.revert_preview_token, body.idempotency_key)}
