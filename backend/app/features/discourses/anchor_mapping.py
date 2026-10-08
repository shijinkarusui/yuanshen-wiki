"""M04B: 锚点映射算法（纯函数，spec §7.4）。

输入：锚点当前状态 + 模拟器产生的 lineage 步骤（含每步 before/after 顺序与 id_map）。
输出：每个锚点的最终影响（新范围/失效/内容变化/显示变化）。

规则摘要：
- 每步在上一步的中间状态上执行
- 未改变身份的段落映射到自己；split 一对多；merge 多对一；
  delete 一对零；insert 零对一
- 有存活成员 → 新顺序最小/最大位置形成连续范围（之间新插入的自然纳入）
- 无存活成员 → 锚点失效，起止 ID 清空，写 last_known_range
- 已失效锚点不自动恢复
- 文字/成员/显示范围/有效性变化的锚点在整个事务中各 bump revision 一次
- 关系 ID/类型/revision/is_verified 不因自动映射改变
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.features.discourses.simulation import LineageStep


@dataclass
class AnchorInput:
    id: str
    start_id: str | None
    end_id: str | None
    is_valid: bool
    revision: int


@dataclass
class RangeInfo:
    start_order: int | None  # 显示段号（1-based），失效时为 None
    end_order: int | None
    paragraph_ids: list[str] = field(default_factory=list)


@dataclass
class AnchorImpact:
    anchor_id: str
    old_range: RangeInfo
    new_range: RangeInfo
    content_changed: bool = False
    display_range_changed: bool = False
    validity_changed: bool = False
    will_be_invalid: bool = False
    needs_revision_bump: bool = False
    relation_ids: list[str] = field(default_factory=list)


@dataclass
class _WorkAnchor:
    inp: AnchorInput
    start_id: str | None
    end_id: str | None
    is_valid: bool
    content_changed: bool = False
    display_changed: bool = False
    validity_changed: bool = False


def _members_in_order(start_id: str, end_id: str, order: list[str]) -> list[str]:
    """展开起止 ID 之间的完整成员 ID 集合（按顺序）。"""
    try:
        si = order.index(start_id)
        ei = order.index(end_id)
    except ValueError:
        return []
    if si > ei:
        si, ei = ei, si
    return order[si : ei + 1]


def map_anchors(
    anchors: list[AnchorInput],
    steps: list[LineageStep],
    initial_order: list[str],
    relations_by_anchor: dict[str, list[str]] | None = None,
) -> list[AnchorImpact]:
    """对 lineage 的每一步依次做锚点映射，返回每个锚点的最终影响。"""
    relations_by_anchor = relations_by_anchor or {}
    work = [
        _WorkAnchor(inp=a, start_id=a.start_id, end_id=a.end_id, is_valid=a.is_valid)
        for a in anchors
    ]
    # 记录初始范围
    old_ranges: dict[str, RangeInfo] = {}
    for w in work:
        old_ranges[w.inp.id] = _range_info(w.start_id, w.end_id, initial_order, w.is_valid)

    for step in steps:
        before, after = step.before_order, step.after_order
        id_map = step.id_map
        for w in work:
            if not w.is_valid or w.start_id is None or w.end_id is None:
                continue
            members = _members_in_order(w.start_id, w.end_id, before)
            # 旧显示范围（本步之前）
            old_start_o = before.index(w.start_id) + 1 if w.start_id in before else None
            old_end_o = before.index(w.end_id) + 1 if w.end_id in before else None

            # 映射到存活 ID（保持 after 顺序）
            mapped: list[str] = []
            for m in members:
                targets = id_map.get(m, [m])  # 未在 id_map 中 → 映射到自己
                mapped.extend(t for t in targets if t in after)
            # 去重保序
            seen: set[str] = set()
            survived = [x for x in after if x in set(mapped) and not (x in seen or seen.add(x))]

            # 内容变化：本步直接改写文本且命中成员
            changed = set(step.text_changed_ids) or (
                {step.target_ids[0]} if step.command_type == "update_text" and step.target_ids else set()
            )
            if changed & set(members):
                w.content_changed = True

            if not survived:
                w.is_valid = False
                w.validity_changed = True
                w.start_id = None
                w.end_id = None
                continue

            new_start, new_end = survived[0], survived[-1]
            # 连续范围：两端之间新插入的段落自然纳入（§7.4#4）
            si, ei = after.index(new_start), after.index(new_end)
            full_members = after[si : ei + 1]
            new_start_o = si + 1
            new_end_o = ei + 1
            # 成员集合变化（ID 集合不同）→ 标记显示变化
            if set(members) != set(full_members):
                w.display_changed = True
            if old_start_o != new_start_o or old_end_o != new_end_o:
                w.display_changed = True
            w.start_id, w.end_id = new_start, new_end

    impacts: list[AnchorImpact] = []
    final_order = steps[-1].after_order if steps else initial_order
    for w in work:
        new_range = _range_info(w.start_id, w.end_id, final_order, w.is_valid)
        old_range = old_ranges[w.inp.id]
        # 显示范围变化也要比较事务首尾（跨步累积）
        display_changed = w.display_changed or (
            (old_range.start_order, old_range.end_order)
            != (new_range.start_order, new_range.end_order)
        )
        will_be_invalid = not w.is_valid
        needs_bump = (
            w.content_changed or display_changed or w.validity_changed
        ) and w.inp.is_valid  # 仅对原本有效的锚点 bump
        impacts.append(
            AnchorImpact(
                anchor_id=w.inp.id,
                old_range=old_range,
                new_range=new_range,
                content_changed=w.content_changed,
                display_range_changed=display_changed,
                validity_changed=w.validity_changed,
                will_be_invalid=will_be_invalid,
                needs_revision_bump=needs_bump,
                relation_ids=relations_by_anchor.get(w.inp.id, []),
            )
        )
    return impacts


def _range_info(
    start_id: str | None, end_id: str | None, order: list[str], is_valid: bool
) -> RangeInfo:
    if not is_valid or start_id is None or end_id is None:
        return RangeInfo(start_order=None, end_order=None, paragraph_ids=[])
    members = _members_in_order(start_id, end_id, order)
    if not members:
        return RangeInfo(start_order=None, end_order=None, paragraph_ids=[])
    return RangeInfo(
        start_order=order.index(members[0]) + 1,
        end_order=order.index(members[-1]) + 1,
        paragraph_ids=members,
    )
