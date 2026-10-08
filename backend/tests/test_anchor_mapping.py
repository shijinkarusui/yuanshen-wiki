"""M04B 锚点映射测试（纯函数，无 DB），覆盖 spec §7.4 边界表。"""
import uuid

from app.features.discourses.anchor_mapping import AnchorInput, map_anchors
from app.features.discourses.simulation import SimParagraph, simulate_paragraph_edits


def mkstate(n):
    return [SimParagraph(str(uuid.uuid4()), f"段{i}") for i in range(1, n + 1)]


def run(st, commands, anchors, rels=None):
    res = simulate_paragraph_edits(st, commands)
    initial_order = [p.id for p in st]
    impacts = map_anchors(anchors, res.lineage, initial_order, rels)
    return res, {i.anchor_id: i for i in impacts}


def test_merge_5_6_anchor_2_5():
    """旧 1-9，锚点 2-5，合并旧 5、6 → 新 1-8，锚点新 2-5。"""
    st = mkstate(9)
    a = AnchorInput(id=str(uuid.uuid4()), start_id=st[1].id, end_id=st[4].id,
                    is_valid=True, revision=3)
    nid = str(uuid.uuid4())
    res, mp = run(st, [
        {"command": "merge", "source_paragraph_ids": [st[4].id, st[5].id],
         "paragraph_id": nid, "text": "五六合并"},
    ], [a], rels={a.id: ["rel-1"]})
    imp = mp[a.id]
    assert len(res.paragraphs) == 8
    assert (imp.new_range.start_order, imp.new_range.end_order) == (2, 5)
    assert nid in imp.new_range.paragraph_ids  # 包含旧 6 内容
    assert imp.display_range_changed is True
    assert imp.needs_revision_bump is True
    assert imp.will_be_invalid is False
    assert imp.relation_ids == ["rel-1"]


def test_split_anchor_includes_all_children():
    st = [SimParagraph(str(uuid.uuid4()), f"第{i}段正文内容") for i in range(1, 4)]
    a = AnchorInput(id=str(uuid.uuid4()), start_id=st[1].id, end_id=st[1].id,
                    is_valid=True, revision=1)
    n1, n2 = str(uuid.uuid4()), str(uuid.uuid4())
    res, mp = run(st, [
        {"command": "split", "source_paragraph_id": st[1].id,
         "split_offsets": [3], "new_paragraph_ids": [n1, n2]},
    ], [a])
    imp = mp[a.id]
    assert imp.new_range.paragraph_ids == [n1, n2]
    assert (imp.new_range.start_order, imp.new_range.end_order) == (2, 3)
    assert imp.needs_revision_bump is True


def test_insert_between_start_end_included():
    st = mkstate(5)
    a = AnchorInput(id=str(uuid.uuid4()), start_id=st[1].id, end_id=st[3].id,
                    is_valid=True, revision=1)
    nid = str(uuid.uuid4())
    res, mp = run(st, [
        {"command": "insert", "paragraph_id": nid, "text": "X",
         "placement": "after", "target_paragraph_id": st[2].id},
    ], [a])
    imp = mp[a.id]
    assert nid in imp.new_range.paragraph_ids  # 之间插入 → 纳入
    assert (imp.new_range.start_order, imp.new_range.end_order) == (2, 5)
    assert imp.needs_revision_bump is True


def test_insert_before_start_not_included_but_bump():
    st = mkstate(5)
    a = AnchorInput(id=str(uuid.uuid4()), start_id=st[1].id, end_id=st[3].id,
                    is_valid=True, revision=1)
    nid = str(uuid.uuid4())
    res, mp = run(st, [
        {"command": "insert", "paragraph_id": nid, "text": "X",
         "placement": "before", "target_paragraph_id": st[0].id},
    ], [a])
    imp = mp[a.id]
    assert nid not in imp.new_range.paragraph_ids  # 边界外不纳入
    assert (imp.new_range.start_order, imp.new_range.end_order) == (3, 5)  # 段号后移
    assert imp.display_range_changed is True
    assert imp.needs_revision_bump is True


def test_single_para_anchor_insert_before_and_after():
    st = mkstate(3)
    a = AnchorInput(id=str(uuid.uuid4()), start_id=st[1].id, end_id=st[1].id,
                    is_valid=True, revision=1)
    n1, n2 = str(uuid.uuid4()), str(uuid.uuid4())
    res, mp = run(st, [
        {"command": "insert", "paragraph_id": n1, "text": "前",
         "placement": "before", "target_paragraph_id": st[1].id},
        {"command": "insert", "paragraph_id": n2, "text": "后",
         "placement": "after", "target_paragraph_id": st[1].id},
    ], [a])
    imp = mp[a.id]
    # 单段锚点之前/之后插入都是边界外，不纳入
    assert n1 not in imp.new_range.paragraph_ids
    assert n2 not in imp.new_range.paragraph_ids
    assert imp.new_range.paragraph_ids == [st[1].id]
    assert (imp.new_range.start_order, imp.new_range.end_order) == (3, 3)


def test_delete_partial_shrinks():
    st = mkstate(6)
    a = AnchorInput(id=str(uuid.uuid4()), start_id=st[1].id, end_id=st[4].id,
                    is_valid=True, revision=1)
    res, mp = run(st, [
        {"command": "delete", "paragraph_ids": [st[1].id, st[4].id]},
    ], [a])
    imp = mp[a.id]
    # 收缩到存活成员的最小/最大范围：段3-4（新段号 2-3）
    assert imp.new_range.paragraph_ids == [st[2].id, st[3].id]
    assert (imp.new_range.start_order, imp.new_range.end_order) == (2, 3)
    assert imp.will_be_invalid is False
    assert imp.needs_revision_bump is True


def test_delete_all_members_invalidates():
    st = mkstate(4)
    a = AnchorInput(id=str(uuid.uuid4()), start_id=st[1].id, end_id=st[2].id,
                    is_valid=True, revision=2)
    res, mp = run(st, [
        {"command": "delete", "paragraph_ids": [st[1].id, st[2].id]},
    ], [a], rels={a.id: ["rel-9"]})
    imp = mp[a.id]
    assert imp.will_be_invalid is True
    assert imp.validity_changed is True
    assert imp.new_range.paragraph_ids == []
    assert imp.relation_ids == ["rel-9"]  # 关系保留
    assert imp.needs_revision_bump is True


def test_update_text_content_changed():
    st = mkstate(4)
    a = AnchorInput(id=str(uuid.uuid4()), start_id=st[1].id, end_id=st[2].id,
                    is_valid=True, revision=5)
    res, mp = run(st, [
        {"command": "update_text", "paragraph_id": st[1].id, "text": "改过"},
    ], [a])
    imp = mp[a.id]
    assert imp.new_range.paragraph_ids == [st[1].id, st[2].id]  # 范围 ID 不变
    assert imp.content_changed is True
    assert imp.display_range_changed is False
    assert imp.needs_revision_bump is True


def test_edit_after_anchor_end_no_change():
    st = mkstate(5)
    a = AnchorInput(id=str(uuid.uuid4()), start_id=st[0].id, end_id=st[1].id,
                    is_valid=True, revision=5)
    res, mp = run(st, [
        {"command": "update_text", "paragraph_id": st[4].id, "text": "改最后一段"},
    ], [a])
    imp = mp[a.id]
    assert imp.content_changed is False
    assert imp.display_range_changed is False
    assert imp.needs_revision_bump is False  # 锚点无变化，不递增


def test_already_invalid_anchor_stays():
    st = mkstate(3)
    a = AnchorInput(id=str(uuid.uuid4()), start_id=None, end_id=None,
                    is_valid=False, revision=7)
    res, mp = run(st, [
        {"command": "update_text", "paragraph_id": st[0].id, "text": "改"},
    ], [a])
    imp = mp[a.id]
    assert imp.will_be_invalid is True
    assert imp.needs_revision_bump is False  # 已失效的不再 bump
