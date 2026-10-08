"""M08B: 撤销协调器（spec §8.3-8.6）。

聚焦 paragraph_edits 变更的撤销/重做（spec 核心必须用例）：
- 合并撤销恢复 1-9 与旧 2-5
- 后续段落编辑冲突
- 新锚点逆映射
- 撤销 insert 使仅引用它的锚点失效
- 撤销之撤销（单根线性 toggle 链）

逆映射复用 anchor_mapping：把 lineage 步骤取逆后正向跑映射算法。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.core.ids import parse_uuid
from app.features.discourses.anchor_mapping import AnchorInput, map_anchors
from app.features.discourses.models import Anchor, Discourse, Paragraph
from app.features.discourses.simulation import LineageStep
from app.features.history_write.models import (
    AnchorAdjustment,
    ChangeEffectState,
    ChangeItem,
    ChangeSet,
    ParagraphLineage,
)
from app.features.identity.models import IdempotencyRecord

REVERT_TOKEN_TTL_HINT = "token 绑定快照，不设过期但任何不一致即 409"


def _hmac_key() -> bytes:
    return (settings.secret_key or "changeme").encode()


def _sign(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    sig = hmac.new(_hmac_key(), raw, hashlib.sha256).digest()
    return (
        base64.urlsafe_b64encode(raw).decode().rstrip("=")
        + "."
        + base64.urlsafe_b64encode(sig).decode().rstrip("=")
    )


def _verify(token: str) -> dict:
    try:
        raw_b64, sig_b64 = token.split(".")
        raw = base64.urlsafe_b64decode(raw_b64 + "==")
        sig = base64.urlsafe_b64decode(sig_b64 + "==")
        if not hmac.compare_digest(sig, hmac.new(_hmac_key(), raw, hashlib.sha256).digest()):
            raise ValueError("bad signature")
        return json.loads(raw)
    except Exception:
        raise ApiError("invalid_revert_token", 400, "撤销 token 非法或已损坏")


def _resolve_root(db: Session, change_set_id: uuid.UUID, for_update: bool = True) -> Tuple[ChangeSet, ChangeSet, ChangeEffectState]:
    """返回 (请求的 change_set, 根 change_set, effect_state)。"""
    cs = db.get(ChangeSet, change_set_id)
    if cs is None:
        raise ApiError("not_found", 404, "变更不存在")
    root = db.get(ChangeSet, cs.root_effect_change_set_id)
    if root is None:
        raise ApiError("not_found", 404, "变更根不存在")
    q = select(ChangeEffectState).where(ChangeEffectState.root_effect_change_set_id == root.id)
    if for_update:
        q = q.with_for_update()
    state = db.execute(q).scalar_one_or_none()
    if state is None:
        raise ApiError("not_found", 404, "变更 effect 状态不存在")
    # 必须传入根或当前 last_toggle；传入旧 toggle 拒绝（§8.6#2）
    if cs.id != root.id and cs.id != state.last_toggle_change_set_id:
        raise ApiError("change_not_current", 409, "只能撤销根变更或当前最新的 toggle，不猜测意图")
    return cs, root, state


def _last_toggle_cs(db: Session, state: ChangeEffectState) -> ChangeSet:
    t = db.get(ChangeSet, state.last_toggle_change_set_id)
    if t is None:
        raise ApiError("not_found", 404, "toggle 变更不存在")
    return t


def _discourse_item(db: Session, csid: uuid.UUID) -> Optional[ChangeItem]:
    return db.execute(
        select(ChangeItem).where(
            ChangeItem.change_set_id == csid, ChangeItem.entity_kind == "discourse"
        )
    ).scalars().first()


def _net_forward_map(
    lineage: List[ParagraphLineage], before_ids: List[str]
) -> Dict[str, List[str]]:
    """从 forward lineage 计算净 ID 映射（before_id -> [after_ids]）。"""
    net: Dict[str, List[str]] = {bid: [bid] for bid in before_ids}
    for l in sorted(lineage, key=lambda x: x.step_index):
        srcs = [str(x) for x in l.source_ids]
        tgts = [str(x) for x in l.target_ids]
        if l.command_type == "update_text":
            step_map = {srcs[0]: [srcs[0]]} if srcs else {}
        elif l.command_type == "insert":
            step_map = {}
        elif l.command_type == "split":
            step_map = {srcs[0]: list(tgts)} if srcs else {}
        elif l.command_type == "merge":
            step_map = {s: list(tgts) for s in srcs}
        elif l.command_type == "delete":
            step_map = {s: [] for s in srcs}
        else:
            step_map = {}
        net = {
            bid: [n for cid in cur for n in step_map.get(cid, [cid])]
            for bid, cur in net.items()
        }
    return net


def _forward_synthetic_step(
    lineage: List[ParagraphLineage],
    before_order: List[str],
    after_order: List[str],
) -> LineageStep:
    """为重做构造单步净映射（供 map_anchors 复用）。"""
    step = LineageStep(step_index=0, command_type="reapply")
    step.before_order = list(before_order)
    step.after_order = list(after_order)
    step.id_map = _net_forward_map(lineage, before_order)
    # 重做时文本变化：原 lineage 中所有 update_text 的 target
    changed: list[str] = []
    for l in lineage:
        if l.command_type == "update_text":
            changed.extend(str(x) for x in l.target_ids)
    step.text_changed_ids = changed
    return step


def _reverse_steps(
    lineage: List[ParagraphLineage], current_order: List[str]
) -> List[LineageStep]:
    """把 lineage 步骤取逆（逆序），并用 source/target_orders 重建每步 before/after 顺序。

    反向语义：
    - update_text → update_text（顺序不变）
    - insert → delete（移除 target_orders 位置）
    - split → merge（target 位置合并回 source）
    - merge → split（target 位置展开为 sources）
    - delete → insert（按 source_orders 恢复）
    """
    rev: List[LineageStep] = []
    order = list(current_order)  # 反向第一步的 before = 当前顺序
    for l in sorted(lineage, key=lambda x: -x.step_index):
        step = LineageStep(step_index=l.step_index, command_type=l.command_type)
        srcs = [str(x) for x in l.source_ids]
        tgts = [str(x) for x in l.target_ids]
        step.before_order = list(order)
        if l.command_type == "update_text":
            step.id_map = {tgts[0]: [srcs[0]]} if tgts and srcs else {}
            step.text_changed_ids = list(tgts) if tgts else []
            step.after_order = list(order)
        elif l.command_type == "insert":
            # 反向删除：移除插入的段
            step.id_map = {t: [] for t in tgts}
            step.after_order = [x for x in order if x not in set(tgts)]
        elif l.command_type == "split":
            # 反向合并：子段位置收拢为源段
            step.id_map = {t: list(srcs) for t in tgts}
            pos = (l.target_orders[0] - 1) if l.target_orders else order.index(tgts[0])
            rest = [x for x in order if x not in set(tgts)]
            pos = min(pos, len(rest))
            step.after_order = rest[:pos] + srcs + rest[pos:]
        elif l.command_type == "merge":
            # 反向拆分：合并段位置展开为源段
            step.id_map = {tgts[0]: list(srcs)} if tgts else {}
            pos = (l.target_orders[0] - 1) if l.target_orders else order.index(tgts[0])
            rest = [x for x in order if x not in set(tgts)]
            pos = min(pos, len(rest))
            step.after_order = rest[:pos] + srcs + rest[pos:]
        elif l.command_type == "delete":
            # 反向插入：按源段号恢复
            step.id_map = {}
            restored = list(order)
            for sid, sord in sorted(zip(srcs, l.source_orders), key=lambda x: x[1]):
                pos = min(sord - 1, len(restored))
                restored.insert(pos, sid)
            step.after_order = restored
        else:
            step.id_map = {}
            step.after_order = list(order)
        rev.append(step)
        order = step.after_order
    return rev


def _current_order(db: Session, discourse_id: uuid.UUID) -> List[str]:
    return [
        str(pid) for pid in db.execute(
            select(Paragraph.id)
            .where(Paragraph.discourse_id == discourse_id, Paragraph.archived_at.is_(None))
            .order_by(Paragraph.current_order)
        ).scalars()
    ]


def revert_preview(
    db: Session, change_set_id: str, actor_id: uuid.UUID
) -> Dict[str, Any]:
    try:
        csid = uuid.UUID(change_set_id)
    except ValueError:
        raise ApiError("not_found", 404, "变更不存在")
    _, root, state = _resolve_root(db, csid, for_update=False)
    toggle = _last_toggle_cs(db, state)

    if toggle.operation not in ("paragraph_edits", "revert"):
        raise ApiError("revert_unsupported", 422, f"暂不支持撤销 operation={toggle.operation}")

    d_item = _discourse_item(db, toggle.id)
    if d_item is None or not d_item.before or not d_item.after:
        raise ApiError("revert_unsupported", 422, "该变更缺少段落快照，无法撤销")
    discourse_id = d_item.entity_id
    before_paras: List[dict] = d_item.before.get("paragraphs", [])
    after_paras: List[dict] = d_item.after.get("paragraphs", [])

    # 方向：已应用 → inverse（撤销）；未应用 → forward（重做）
    direction = "inverse" if state.is_applied else "forward"
    # 求逆目标：undo 和 redo 都是恢复 toggle.before
    # （undo：toggle 是 forward 变更，before 是原始状态；redo：toggle 是 revert，before 是 revert 前的状态即原始 after）
    target_paras = before_paras
    current_ids = _current_order(db, discourse_id)
    # 当前状态必须等于 toggle.after（toggle 创建的状态），否则说明之后又有变更
    other_paras = after_paras
    other_ids = [p["id"] for p in other_paras]

    conflicts: List[Dict[str, Any]] = []
    # §8.3#2：当前段落必须与另一端快照一致（ID/顺序/文本摘要），否则后续段落编辑冲突
    cur_texts = {
        str(pid): txt for pid, txt in db.execute(
            select(Paragraph.id, Paragraph.text).where(
                Paragraph.discourse_id == discourse_id, Paragraph.archived_at.is_(None))
        )
    }
    other_map = {p["id"]: p for p in other_paras}
    state_ok = (
        current_ids == other_ids
        and all(cur_texts.get(pid) == other_map[pid]["text"] for pid in other_ids)
    )
    if not state_ok:
        conflicts.append({
            "code": "paragraph_changed_since",
            "message": "目标变更之后段落又被编辑过，撤销会冲突",
        })

    # §8.3#3：自动调整过的锚点，当前 revision 必须等于 after_revision
    adj_items = list(db.execute(
        select(ChangeItem).where(
            ChangeItem.change_set_id == toggle.id, ChangeItem.entity_kind == "anchor")
    ).scalars())
    anchor_conflicts = []
    for ai in adj_items:
        a = db.get(Anchor, ai.entity_id)
        if a is None:
            continue
        if a.revision != ai.after_revision:
            anchor_conflicts.append(str(a.id))
    if anchor_conflicts:
        conflicts.append({
            "code": "anchor_revision_changed",
            "message": f"{len(anchor_conflicts)} 个锚点在之后被修改过",
            "anchor_ids": anchor_conflicts,
        })

    # 逆映射：构造反向 lineage，用当前锚点状态跑 map_anchors
    # 逆映射：撤销时逆转 toggle lineage；重做时正向重放 root lineage
    if direction == "inverse":
        lineage = list(db.execute(
            select(ParagraphLineage).where(ParagraphLineage.change_set_id == toggle.id)
            .order_by(ParagraphLineage.step_index)
        ).scalars())
        steps = _reverse_steps(lineage, list(current_ids))
    else:
        lineage = list(db.execute(
            select(ParagraphLineage).where(ParagraphLineage.change_set_id == root.id)
            .order_by(ParagraphLineage.step_index)
        ).scalars())
        # 重做：从当前（B）正向重放到目标（A）
        target_ids = [p["id"] for p in target_paras]
        steps = [_forward_synthetic_step(lineage, list(current_ids), target_ids)]

    anchors = list(db.execute(
        select(Anchor).where(Anchor.discourse_id == discourse_id,
                             Anchor.archived_at.is_(None))).scalars())
    anchor_inputs = [
        AnchorInput(id=str(a.id),
                    start_id=str(a.start_paragraph_id) if a.start_paragraph_id else None,
                    end_id=str(a.end_paragraph_id) if a.end_paragraph_id else None,
                    is_valid=a.is_valid, revision=a.revision)
        for a in anchors
    ]
    impacts = map_anchors(anchor_inputs, steps, list(current_ids))
    anchor_map = {str(a.id): a for a in anchors}
    will_invalid = [
        i.anchor_id for i in impacts
        if i.will_be_invalid and anchor_map.get(i.anchor_id) and anchor_map[i.anchor_id].is_valid
    ]
    # 新锚点逆映射预测（§8.3#4）：impacts 已包含所有当前锚点
    new_mappings = [
        {"anchor_id": i.anchor_id,
         "new_start": i.new_range.start_order, "new_end": i.new_range.end_order,
         "will_be_invalid": i.will_be_invalid}
        for i in impacts
    ]

    # 全局最新 sequence_no
    max_seq = db.execute(select(func.max(ChangeSet.sequence_no))).scalar() or 0

    token_payload = {
        "target_change_set_id": str(root.id),
        "root_effect_change_set_id": str(root.id),
        "actor_id": str(actor_id),
        "direction": direction,
        "last_toggle_change_set_id": str(state.last_toggle_change_set_id),
        "observed_max_sequence_no": max_seq,
        "discourse_id": str(discourse_id),
        "discourse_revision": db.get(Discourse, discourse_id).revision,
        "target_paragraph_ids": [p["id"] for p in target_paras],
        "inverse_summary": f"{direction} paragraph_edits ({len(lineage)} steps)",
    }
    # rollback 前取出返回值需要的字段（rollback 后 ORM 对象过期）
    ret_root_id = str(root.id)
    ret_root_op = root.operation
    ret_root_summary = root.summary
    ret_lineage = [{"step_index": l.step_index, "command_type": l.command_type} for l in lineage]
    db.rollback()  # 预览只读
    return {
        "target_change_set": {"id": ret_root_id, "operation": ret_root_op,
                              "summary": ret_root_summary},
        "direction": direction,
        "inverse_operations": [
            {"step_index": l["step_index"], "command_type": l["command_type"],
             "inverse_of": f"撤销 {l['command_type']}"} for l in ret_lineage
        ],
        "affected_entities": [{"kind": "discourse", "id": str(discourse_id)}] +
            [{"kind": "anchor", "id": i.anchor_id} for i in impacts if i.needs_revision_bump],
        "new_anchor_mappings": new_mappings,
        "will_invalidate_anchors": will_invalid,
        "conflicts": conflicts,
        "revert_preview_token": _sign(token_payload),
    }


def revert_commit(
    db: Session,
    change_set_id: str,
    actor_id: uuid.UUID,
    token: str,
    idempotency_key: str,
) -> Dict[str, Any]:
    payload = _verify(token)
    if payload.get("actor_id") != str(actor_id):
        raise ApiError("invalid_revert_token", 400, "token 与当前用户不匹配")
    csid = parse_uuid(change_set_id, "change_set_id")
    if not idempotency_key:
        raise ApiError("missing_idempotency_key", 400, "撤销提交需要 Idempotency-Key")

    # 幂等
    req_digest = hashlib.sha256(
        json.dumps({"change_set_id": change_set_id, "token": token},
                   sort_keys=True).encode()
    ).hexdigest()
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

    _, root, state = _resolve_root(db, csid)
    # token 绑定校验
    if payload.get("root_effect_change_set_id") != str(root.id):
        raise ApiError("history_stale", 409, "token 根变更不一致")
    if payload.get("last_toggle_change_set_id") != str(state.last_toggle_change_set_id):
        raise ApiError("history_stale", 409, "已有新的撤销/重做，请重新预览")
    max_seq = db.execute(select(func.max(ChangeSet.sequence_no))).scalar() or 0
    if max_seq != payload.get("observed_max_sequence_no"):
        raise ApiError("history_stale", 409, "有新的变更写入，请重新预览")

    toggle = _last_toggle_cs(db, state)
    direction = payload["direction"]  # inverse=撤销，forward=重做
    if (direction == "inverse") != state.is_applied:
        raise ApiError("history_stale", 409, "撤销/重做方向与当前状态不一致")

    d_item = _discourse_item(db, toggle.id)
    discourse_id = uuid.UUID(payload["discourse_id"])
    discourse = db.execute(
        select(Discourse).where(Discourse.id == discourse_id).with_for_update()
    ).scalar_one_or_none()
    if discourse is None:
        raise ApiError("not_found", 404, "论述不存在")
    if discourse.revision != payload.get("discourse_revision"):
        raise ApiError("history_stale", 409, "论述版本已变化，请重新预览")

    target_paras: List[dict] = d_item.before.get("paragraphs", [])
    target_ids = [p["id"] for p in target_paras]
    if target_ids != payload.get("target_paragraph_ids"):
        raise ApiError("history_stale", 409, "目标段落快照不一致")

    # 重新做冲突检查（与 preview 相同逻辑，简化为状态一致性）
    current_ids = _current_order(db, discourse_id)
    other_paras = d_item.after.get("paragraphs", [])
    other_ids = [p["id"] for p in other_paras]
    cur_texts = {
        str(pid): txt for pid, txt in db.execute(
            select(Paragraph.id, Paragraph.text).where(
                Paragraph.discourse_id == discourse_id, Paragraph.archived_at.is_(None))
        )
    }
    other_map = {p["id"]: p for p in other_paras}
    if not (current_ids == other_ids and all(
            cur_texts.get(pid) == other_map[pid]["text"] for pid in other_ids)):
        raise ApiError("history_stale", 409, "段落状态已变化，请重新预览")

    # ---- 应用逆操作：恢复段落快照（先增改 → 锚点 → 后删除，避免外键冲突） ----
    old_paras = list(db.execute(
        select(Paragraph).where(Paragraph.discourse_id == discourse_id,
                                Paragraph.archived_at.is_(None))).scalars())
    old_by_id = {str(p.id): p for p in old_paras}
    target_id_set = set(target_ids)
    for i, tp in enumerate(target_paras):
        if tp["id"] in old_by_id:
            p = old_by_id[tp["id"]]
            if p.text != tp["text"]:
                p.revision += 1
            p.text = tp["text"]
            p.current_order = i + 1
            p.updated_by = actor_id
        else:
            db.add(Paragraph(
                id=uuid.UUID(tp["id"]), discourse_id=discourse_id,
                text=tp["text"], current_order=i + 1,
                created_by=actor_id, updated_by=actor_id,
            ))
    db.flush()

    # ---- 锚点映射（撤销逆转 / 重做正向重放） ----
    if direction == "inverse":
        c_lineage = list(db.execute(
            select(ParagraphLineage).where(ParagraphLineage.change_set_id == toggle.id)
            .order_by(ParagraphLineage.step_index)).scalars())
        c_steps = _reverse_steps(c_lineage, current_ids)
    else:
        c_lineage = list(db.execute(
            select(ParagraphLineage).where(ParagraphLineage.change_set_id == root.id)
            .order_by(ParagraphLineage.step_index)).scalars())
        c_steps = [_forward_synthetic_step(
            c_lineage, current_ids, [p["id"] for p in target_paras])]
    anchors = list(db.execute(
        select(Anchor).where(Anchor.discourse_id == discourse_id,
                             Anchor.archived_at.is_(None))).scalars())
    anchor_inputs = [
        AnchorInput(id=str(a.id),
                    start_id=str(a.start_paragraph_id) if a.start_paragraph_id else None,
                    end_id=str(a.end_paragraph_id) if a.end_paragraph_id else None,
                    is_valid=a.is_valid, revision=a.revision)
        for a in anchors
    ]
    impacts = map_anchors(anchor_inputs, c_steps, current_ids)
    anchor_by_id = {str(a.id): a for a in anchors}
    adj_count = 0
    for imp in impacts:
        if not imp.needs_revision_bump:
            continue
        a = anchor_by_id[imp.anchor_id]
        old_start_o = imp.old_range.start_order
        old_end_o = imp.old_range.end_order
        if imp.will_be_invalid:
            a.last_known_range = {
                "start_order": old_start_o, "end_order": old_end_o,
                "paragraph_ids": imp.old_range.paragraph_ids,
            }
            a.start_paragraph_id = None
            a.end_paragraph_id = None
            a.is_valid = False
            a.invalid_reason = "revert_invalidated"
        else:
            if imp.new_range.paragraph_ids:
                a.start_paragraph_id = uuid.UUID(imp.new_range.paragraph_ids[0])
                a.end_paragraph_id = uuid.UUID(imp.new_range.paragraph_ids[-1])
                a.is_valid = True
                a.invalid_reason = None
        a.revision += 1
        a.updated_by = actor_id
        adj_count += 1
    db.flush()

    # 删除不再存在的段落（锚点已调整，不再引用它们）
    for p in old_paras:
        if str(p.id) not in target_id_set:
            db.delete(p)
    db.flush()

    discourse.paragraph_revision += 1
    discourse.revision += 1
    discourse.updated_by = actor_id

    # ---- toggle change_set（§8.6）：绝不回退 revision，单调递增 ----
    new_direction = "inverse" if direction == "inverse" else "forward"
    rcs_seq = db.execute(select(func.nextval("change_set_seq"))).scalar()
    rcs = ChangeSet(
        sequence_no=rcs_seq,
        actor_id=actor_id,
        operation="revert",
        summary=f"{'撤销' if direction == 'inverse' else '重做'} paragraph_edits（{toggle.id}）",
        request_id=idempotency_key,
        reverts_change_set_id=state.last_toggle_change_set_id,
        root_effect_change_set_id=root.id,
        effect_direction=new_direction,
    )
    db.add(rcs)
    db.flush()
    if rcs.reverts_change_set_id != state.last_toggle_change_set_id:
        raise ApiError("history_stale", 409, "toggle 前驱已变化")
    state.is_applied = (direction == "forward")
    state.last_toggle_change_set_id = rcs.id
    db.add(ChangeItem(
        change_set_id=rcs.id, entity_kind="discourse", entity_id=discourse.id,
        before_revision=discourse.revision - 1, after_revision=discourse.revision,
        before={
            "paragraph_revision": discourse.paragraph_revision - 1,
            "paragraphs": [
                {"id": p["id"], "order": i + 1, "text": p["text"]}
                for i, p in enumerate(other_paras)
            ],
        },
        after={
            "paragraph_revision": discourse.paragraph_revision,
            "paragraphs": [
                {"id": p["id"], "order": i + 1, "text": p["text"]}
                for i, p in enumerate(target_paras)
            ],
            "revert_direction": direction,
        },
        changed_fields=["paragraph_revision", "paragraphs"],
    ))
    # toggle lineage：记录本次实际的前后状态（供未来的撤销/重做取逆）
    # undo：source=after快照 → target=before快照；redo：反之
    for l in c_lineage:
        ctype = l.command_type
        if ctype.startswith("revert_"):
            ctype = ctype[7:]
        if direction == "inverse":
            s_ids, s_orders = [str(x) for x in l.target_ids], list(l.target_orders)
            t_ids, t_orders = [str(x) for x in l.source_ids], list(l.source_orders)
        else:
            s_ids, s_orders = [str(x) for x in l.source_ids], list(l.source_orders)
            t_ids, t_orders = [str(x) for x in l.target_ids], list(l.target_orders)
        db.add(ParagraphLineage(
            change_set_id=rcs.id, step_index=l.step_index,
            command_type=ctype,
            discourse_id=discourse_id,
            source_ids=s_ids, source_orders=s_orders,
            target_ids=t_ids, target_orders=t_orders,
        ))

    response = {
        "change_set_id": str(rcs.id),
        "root_effect_change_set_id": str(root.id),
        "direction": direction,
        "discourse_revision": discourse.revision,
        "paragraph_revision": discourse.paragraph_revision,
        "anchors_adjusted": adj_count,
    }
    db.add(IdempotencyRecord(
        actor_id=actor_id, key=idempotency_key, request_digest=req_digest,
        status="succeeded", response_body=response, change_set_id=rcs.id,
    ))
    db.commit()
    return response
