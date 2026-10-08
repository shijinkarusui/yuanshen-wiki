"""M04C: 段落编辑预览与提交服务（spec §7.3）。

- preview: 纯计算，零写入（不写正文、历史、幂等记录、序列，不预留 UUID）
- commit: 写锁 + 重新模拟 + fingerprint 校验，任一不一致返回 409 preview_stale
"""
from __future__ import annotations

import base64
import hashlib
import json
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.features.discourses.anchor_mapping import AnchorInput, map_anchors
from app.features.discourses.models import Anchor, Discourse, Paragraph
from app.features.discourses.simulation import (
    ALGORITHM_VERSION,
    SimParagraph,
    SimulationError,
    simulate_paragraph_edits,
)
from app.features.history_write.models import (
    AnchorAdjustment,
    AnchorAdjustmentRelation,
    ChangeItem,
    ChangeSet,
    ParagraphLineage,
)
from app.features.identity.models import IdempotencyRecord
from app.features.relations.models import Relation


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_fingerprint(
    *,
    discourse_id: str,
    base_discourse_revision: int,
    base_paragraph_revision: int,
    paragraphs: List[SimParagraph],
    commands: List[dict],
    anchors: List[dict],
    relations: List[dict],
) -> str:
    """preview_fingerprint = 规范化内容的 SHA-256（base64url）。不是授权凭据。"""
    norm = {
        "algorithm": ALGORITHM_VERSION,
        "discourse_id": discourse_id,
        "base_discourse_revision": base_discourse_revision,
        "base_paragraph_revision": base_paragraph_revision,
        "paragraphs": [
            {"id": p.id, "sha256": _sha_text(p.text)} for p in paragraphs
        ],
        "commands": json.loads(json.dumps(commands, sort_keys=True, ensure_ascii=False)),
        "anchors": sorted(
            [
                {
                    "id": a["id"],
                    "revision": a["revision"],
                    "start": a["start_paragraph_id"],
                    "end": a["end_paragraph_id"],
                    "is_valid": a["is_valid"],
                }
                for a in anchors
            ],
            key=lambda x: x["id"],
        ),
        "relations": sorted(
            [
                {
                    "id": r["id"],
                    "revision": r["revision"],
                    "archived": r["archived"],
                }
                for r in relations
            ],
            key=lambda x: x["id"],
        ),
    }
    raw = json.dumps(norm, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _parse_if_match(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    v = value.strip().strip('"')
    if v.startswith("rev-"):
        try:
            return int(v[4:])
        except ValueError:
            pass
    raise ApiError("invalid_if_match", 400, f"非法 If-Match: {value!r}")


def _load_discourse_for_update(db: Session, discourse_id: str, if_match: Optional[str], for_update: bool = True) -> Discourse:
    try:
        did = uuid.UUID(discourse_id)
    except ValueError:
        raise ApiError("not_found", 404, "论述不存在")
    q = select(Discourse).where(Discourse.id == did)
    if for_update:
        q = q.with_for_update()
    d = db.execute(q).scalar_one_or_none()
    if d is None or d.archived_at is not None:
        raise ApiError("not_found", 404, "论述不存在")
    want = _parse_if_match(if_match)
    if want is not None and d.revision != want:
        raise ApiError(
            "precondition_failed", 412,
            f"论述 revision 已变化（期望 rev-{want}，当前 rev-{d.revision}）",
        )
    return d


def _active_paragraphs(db: Session, discourse_id: uuid.UUID) -> List[Paragraph]:
    return list(
        db.execute(
            select(Paragraph)
            .where(Paragraph.discourse_id == discourse_id, Paragraph.archived_at.is_(None))
            .order_by(Paragraph.current_order)
        ).scalars()
    )


def _anchors_of(db: Session, discourse_id: uuid.UUID) -> List[Anchor]:
    return list(
        db.execute(
            select(Anchor)
            .where(Anchor.discourse_id == discourse_id, Anchor.archived_at.is_(None))
            .order_by(Anchor.created_at)
        ).scalars()
    )


def _relations_of_anchors(db: Session, anchor_ids: List[uuid.UUID]) -> List[Relation]:
    if not anchor_ids:
        return []
    return list(
        db.execute(
            select(Relation).where(
                or_(
                    Relation.source_anchor_id.in_(anchor_ids),
                    Relation.target_anchor_id.in_(anchor_ids),
                ),
                Relation.archived_at.is_(None),
            )
        ).scalars()
    )


def _simulate(
    db: Session,
    discourse: Discourse,
    base_paragraph_revision: int,
    commands: List[dict],
):
    if discourse.paragraph_revision != base_paragraph_revision:
        raise ApiError(
            "stale_paragraph_revision", 409,
            f"段落版本已变化（期望 {base_paragraph_revision}，当前 {discourse.paragraph_revision}）",
        )
    paras = _active_paragraphs(db, discourse.id)
    state = [SimParagraph(str(p.id), p.text) for p in paras]
    try:
        result = simulate_paragraph_edits(state, commands)
    except SimulationError as e:
        raise ApiError(e.code, 422, e.message)
    anchors = _anchors_of(db, discourse.id)
    anchor_inputs = [
        AnchorInput(
            id=str(a.id),
            start_id=str(a.start_paragraph_id) if a.start_paragraph_id else None,
            end_id=str(a.end_paragraph_id) if a.end_paragraph_id else None,
            is_valid=a.is_valid,
            revision=a.revision,
        )
        for a in anchors
    ]
    anchor_ids = [a.id for a in anchors]
    relations = _relations_of_anchors(db, anchor_ids)
    rels_by_anchor: Dict[str, List[str]] = {}
    for r in relations:
        for aid in (r.source_anchor_id, r.target_anchor_id):
            if aid in anchor_ids:
                rels_by_anchor.setdefault(str(aid), []).append(str(r.id))
    impacts = map_anchors(
        anchor_inputs,
        result.lineage,
        [str(p.id) for p in paras],  # 命令执行前的初始顺序
        rels_by_anchor,
    )
    return result, paras, anchors, relations, impacts


def _impact_dict(imp) -> Dict[str, Any]:
    return {
        "anchor_id": imp.anchor_id,
        "old_range": {
            "start": imp.old_range.start_order,
            "end": imp.old_range.end_order,
            "paragraph_ids": imp.old_range.paragraph_ids,
        },
        "new_range": {
            "start": imp.new_range.start_order,
            "end": imp.new_range.end_order,
            "paragraph_ids": imp.new_range.paragraph_ids,
        },
        "content_changed": imp.content_changed,
        "display_range_changed": imp.display_range_changed,
        "will_be_invalid": imp.will_be_invalid,
        "validity_changed": imp.validity_changed,
        "relation_ids": imp.relation_ids,
    }


def preview_paragraph_edits(
    db: Session,
    discourse_id: str,
    if_match: Optional[str],
    base_paragraph_revision: int,
    commands: List[dict],
) -> Dict[str, Any]:
    """零写入预览（只读，不加写锁）。"""
    discourse = _load_discourse_for_update(db, discourse_id, if_match, for_update=False)
    result, paras, anchors, relations, impacts = _simulate(
        db, discourse, base_paragraph_revision, commands
    )
    fingerprint = compute_fingerprint(
        discourse_id=str(discourse.id),
        base_discourse_revision=discourse.revision,
        base_paragraph_revision=discourse.paragraph_revision,
        paragraphs=[SimParagraph(str(p.id), p.text) for p in paras],
        commands=commands,
        anchors=[
            {
                "id": str(a.id),
                "revision": a.revision,
                "start_paragraph_id": str(a.start_paragraph_id) if a.start_paragraph_id else None,
                "end_paragraph_id": str(a.end_paragraph_id) if a.end_paragraph_id else None,
                "is_valid": a.is_valid,
            }
            for a in anchors
        ],
        relations=[
            {"id": str(r.id), "revision": r.revision, "archived": r.archived_at is not None}
            for r in relations
        ],
    )
    # 预览返回值中用到的版本号提前取出（rollback 后 ORM 对象过期）
    base_rev = discourse.revision
    base_para_rev = discourse.paragraph_revision
    db.rollback()  # 防御性：确保预览无任何写入残留
    return {
        "base_discourse_revision": base_rev,
        "base_paragraph_revision": base_para_rev,
        "preview_fingerprint": fingerprint,
        "paragraphs": [
            {"id": p.id, "order": i + 1, "text": p.text}
            for i, p in enumerate(result.paragraphs)
        ],
        "anchor_impacts": [_impact_dict(i) for i in impacts],
    }


def commit_paragraph_edits(
    db: Session,
    discourse_id: str,
    actor_id: uuid.UUID,
    if_match: Optional[str],
    idempotency_key: Optional[str],
    base_paragraph_revision: int,
    commands: List[dict],
    preview_fingerprint: str,
) -> Dict[str, Any]:
    """提交段落编辑：写锁 + 重模拟 + 指纹校验 + 持久化。"""
    if not idempotency_key:
        raise ApiError("missing_idempotency_key", 400, "提交需要 Idempotency-Key")

    # 幂等：同 key 同摘要直接返回
    req_digest = _sha_text(json.dumps(
        {"discourse_id": discourse_id, "commands": commands,
         "fingerprint": preview_fingerprint, "base_paragraph_revision": base_paragraph_revision},
        sort_keys=True, ensure_ascii=False,
    ))
    existing = db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == actor_id,
            IdempotencyRecord.key == idempotency_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.request_digest != req_digest:
            raise ApiError("idempotency_key_conflict", 409, "幂等键已被用于不同请求")
        if existing.status == "succeeded" and existing.response_body:
            return dict(existing.response_body)
        raise ApiError("idempotency_in_progress", 409, "相同幂等键的请求正在处理中")

    discourse = _load_discourse_for_update(db, discourse_id, if_match)
    result, paras, anchors, relations, impacts = _simulate(
        db, discourse, base_paragraph_revision, commands
    )

    # 指纹校验：用当前 DB 状态重新计算，必须与提交携带的一致
    fresh_fp = compute_fingerprint(
        discourse_id=str(discourse.id),
        base_discourse_revision=discourse.revision,
        base_paragraph_revision=discourse.paragraph_revision,
        paragraphs=[SimParagraph(str(p.id), p.text) for p in paras],
        commands=commands,
        anchors=[
            {
                "id": str(a.id),
                "revision": a.revision,
                "start_paragraph_id": str(a.start_paragraph_id) if a.start_paragraph_id else None,
                "end_paragraph_id": str(a.end_paragraph_id) if a.end_paragraph_id else None,
                "is_valid": a.is_valid,
            }
            for a in anchors
        ],
        relations=[
            {"id": str(r.id), "revision": r.revision, "archived": r.archived_at is not None}
            for r in relations
        ],
    )
    if fresh_fp != preview_fingerprint:
        raise ApiError(
            "preview_stale", 409,
            "预览已过期：论述/段落/锚点/关系状态发生变化，请重新预览",
        )

    # 新 UUID 并发占用检查
    new_ids = [uuid.UUID(p.id) for p in result.paragraphs if p.id not in {str(x.id) for x in paras}]
    if new_ids:
        clash = db.execute(
            select(Paragraph.id).where(Paragraph.id.in_(new_ids))
        ).scalars().first()
        if clash is not None:
            raise ApiError("paragraph_id_conflict", 409, f"段落 ID 已被并发占用: {clash}")

    # ---- 持久化（顺序：先增改段落 → 调整锚点 → 最后删除旧段落，避免外键冲突） ----
    # 注意：先抓取 before 快照，因为下面的 ORM 更新会原地变异 paras 对象
    before_snapshot = [
        {"id": str(p.id), "order": p.current_order, "text": p.text} for p in paras
    ]
    before_para_rev = discourse.paragraph_revision
    old_para_by_id = {str(p.id): p for p in paras}
    final_ids = {p.id for p in result.paragraphs}
    # 更新/插入段落（新段落先入库，锚点才能指向它们）
    for i, sp in enumerate(result.paragraphs):
        if sp.id in old_para_by_id:
            p = old_para_by_id[sp.id]
            if p.text != sp.text:
                p.revision += 1
            p.text = sp.text
            p.current_order = i + 1
            p.updated_by = actor_id
        else:
            db.add(Paragraph(
                id=uuid.UUID(sp.id),
                discourse_id=discourse.id,
                text=sp.text,
                current_order=i + 1,
                created_by=actor_id,
                updated_by=actor_id,
            ))
    db.flush()

    # 锚点调整（每锚点每事务最多 bump 一次）
    anchor_by_id = {str(a.id): a for a in anchors}
    adjustments = []
    for imp in impacts:
        if not imp.needs_revision_bump:
            continue
        a = anchor_by_id[imp.anchor_id]
        old_start_o = imp.old_range.start_order
        old_end_o = imp.old_range.end_order
        if imp.will_be_invalid:
            a.last_known_range = {
                "start_order": old_start_o,
                "end_order": old_end_o,
                "paragraph_ids": imp.old_range.paragraph_ids,
            }
            a.start_paragraph_id = None
            a.end_paragraph_id = None
            a.is_valid = False
            a.invalid_reason = "paragraphs_deleted"
        else:
            if imp.new_range.paragraph_ids:
                a.start_paragraph_id = uuid.UUID(imp.new_range.paragraph_ids[0])
                a.end_paragraph_id = uuid.UUID(imp.new_range.paragraph_ids[-1])
        a.revision += 1
        a.updated_by = actor_id
        adjustments.append((a, imp, old_start_o, old_end_o))
    db.flush()

    # 删除不再存在的段落（锚点已不再引用它们）
    for p in paras:
        if str(p.id) not in final_ids:
            db.delete(p)
    db.flush()

    # 版本递增
    discourse.paragraph_revision += 1
    discourse.revision += 1
    discourse.updated_by = actor_id

    # 历史：change_set + change_items + lineage + adjustments
    seq_no = db.execute(select(func.nextval("change_set_seq"))).scalar()
    cs_id = uuid.uuid4()
    cs = ChangeSet(
        id=cs_id,
        sequence_no=seq_no,
        actor_id=actor_id,
        operation="paragraph_edits",
        summary=f"段落编辑：{len(commands)} 条命令，{len(adjustments)} 个锚点受影响",
        request_id=idempotency_key,
        effect_direction="forward",
        root_effect_change_set_id=cs_id,  # 根变更指向自己
    )
    db.add(cs)
    db.flush()
    # effect state
    from app.features.history_write.models import ChangeEffectState
    db.add(ChangeEffectState(
        root_effect_change_set_id=cs.id,
        is_applied=True,
        last_toggle_change_set_id=cs.id,
    ))
    # discourse change item（含段落快照，供撤销时恢复）
    db.add(ChangeItem(
        change_set_id=cs.id,
        entity_kind="discourse",
        entity_id=discourse.id,
        before_revision=discourse.revision - 1,
        after_revision=discourse.revision,
        before={
            "paragraph_revision": before_para_rev,
            "paragraphs": before_snapshot,
        },
        after={
            "paragraph_revision": discourse.paragraph_revision,
            "paragraphs": [
                {"id": p.id, "order": i + 1, "text": p.text}
                for i, p in enumerate(result.paragraphs)
            ],
        },
        changed_fields=["paragraph_revision", "paragraphs"],
    ))
    # lineage（每个命令都写，无锚点也写）
    for step in result.lineage:
        db.add(ParagraphLineage(
            change_set_id=cs.id,
            step_index=step.step_index,
            command_type=step.command_type,
            discourse_id=discourse.id,
            source_ids=step.source_ids,
            source_orders=step.source_orders,
            target_ids=step.target_ids,
            target_orders=step.target_orders,
        ))
    # anchor adjustments
    for a, imp, old_start_o, old_end_o in adjustments:
        adj = AnchorAdjustment(
            change_set_id=cs.id,
            anchor_id=a.id,
            old_start_order=old_start_o,
            old_end_order=old_end_o,
            new_start_order=imp.new_range.start_order,
            new_end_order=imp.new_range.end_order,
            content_changed=imp.content_changed,
            display_range_changed=imp.display_range_changed,
            validity_changed=imp.validity_changed,
        )
        db.add(adj)
        db.flush()
        for rid in imp.relation_ids:
            db.add(AnchorAdjustmentRelation(
                adjustment_id=adj.id,
                relation_id=uuid.UUID(rid),
            ))
        db.add(ChangeItem(
            change_set_id=cs.id,
            entity_kind="anchor",
            entity_id=a.id,
            before_revision=a.revision - 1,
            after_revision=a.revision,
            before={
                "start_order": old_start_o, "end_order": old_end_o,
                "is_valid": imp.old_range.start_order is not None,
            },
            after={
                "start_order": imp.new_range.start_order,
                "end_order": imp.new_range.end_order,
                "is_valid": not imp.will_be_invalid,
            },
            changed_fields=["range", "is_valid", "revision"],
        ))

    response = {
        "base_discourse_revision": discourse.revision - 1,
        "base_paragraph_revision": discourse.paragraph_revision - 1,
        "preview_fingerprint": preview_fingerprint,
        "paragraphs": [
            {"id": p.id, "order": i + 1, "text": p.text}
            for i, p in enumerate(result.paragraphs)
        ],
        "anchor_impacts": [_impact_dict(i) for i in impacts],
        "change_set_id": str(cs.id),
        "discourse_revision": discourse.revision,
        "paragraph_revision": discourse.paragraph_revision,
    }
    db.add(IdempotencyRecord(
        actor_id=actor_id,
        key=idempotency_key,
        request_digest=req_digest,
        status="succeeded",
        response_body=response,
        change_set_id=cs.id,
    ))
    db.commit()
    return response
