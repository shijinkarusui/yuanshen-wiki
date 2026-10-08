"""M04A 模拟器单元测试（纯函数，无 DB）。"""
import uuid

import pytest

from app.features.discourses.simulation import (
    SimulationError,
    SimParagraph,
    simulate_paragraph_edits,
)


def mkstate(n=9):
    return [SimParagraph(str(uuid.uuid4()), f"段落{i}正文") for i in range(1, n + 1)]


def ids(res):
    return [p.id for p in res.paragraphs]


def test_update_text():
    st = mkstate(3)
    target = st[1].id
    res = simulate_paragraph_edits(st, [
        {"command": "update_text", "paragraph_id": target, "text": "新正文"},
    ])
    assert res.paragraphs[1].text == "新正文"
    assert res.paragraphs[1].id == target
    assert res.lineage[0].id_map == {target: [target]}


def test_insert_before_after_append():
    st = mkstate(3)
    n1, n2, n3 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    res = simulate_paragraph_edits(st, [
        {"command": "insert", "paragraph_id": n1, "text": "首", "placement": "before",
         "target_paragraph_id": st[0].id},
        {"command": "insert", "paragraph_id": n2,
         "text": "中", "placement": "after", "target_paragraph_id": st[1].id},
        {"command": "insert", "paragraph_id": n3, "text": "尾", "placement": "append",
         "target_paragraph_id": None},
    ])
    texts = [p.text for p in res.paragraphs]
    # "首"插到最前；"中"插到 st[1]（段落2正文）之后；"尾"追加到最后
    assert texts == ["首", "段落1正文", "段落2正文", "中", "段落3正文", "尾"]


def test_insert_sequential_uuid_reference():
    """后续命令引用前面命令创建的 UUID。"""
    st = mkstate(2)
    n1, n2 = str(uuid.uuid4()), str(uuid.uuid4())
    res = simulate_paragraph_edits(st, [
        {"command": "insert", "paragraph_id": n1, "text": "A", "placement": "append",
         "target_paragraph_id": None},
        {"command": "insert", "paragraph_id": n2, "text": "B", "placement": "after",
         "target_paragraph_id": n1},
        {"command": "update_text", "paragraph_id": n2, "text": "B2"},
    ])
    assert [p.text for p in res.paragraphs][-2:] == ["A", "B2"]


def test_split_basic():
    st = [SimParagraph(str(uuid.uuid4()), "abcdefghij")]
    a, b, c = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    res = simulate_paragraph_edits(st, [
        {"command": "split", "source_paragraph_id": st[0].id,
         "split_offsets": [3, 7], "new_paragraph_ids": [a, b, c]},
    ])
    assert [p.text for p in res.paragraphs] == ["abc", "defg", "hij"]
    assert res.lineage[0].id_map == {st[0].id: [a, b, c]}


def test_split_grapheme_boundary_rejected():
    # "é" 用 e + 组合重音表示（2 码点 1 字素）；offset=1 落在字素内部
    st = [SimParagraph(str(uuid.uuid4()), "ae\u0301b")]
    with pytest.raises(SimulationError) as ei:
        simulate_paragraph_edits(st, [
            {"command": "split", "source_paragraph_id": st[0].id,
             "split_offsets": [2], "new_paragraph_ids": [str(uuid.uuid4()), str(uuid.uuid4())]},
        ])
    assert ei.value.code == "invalid_split_offset"


def test_split_emoji_zwj_rejected():
    # ZWJ emoji 👨‍👩‍👧：多个码点一个字素，中间切分应拒绝
    fam = "👨\u200d👩\u200d👧"
    st = [SimParagraph(str(uuid.uuid4()), "x" + fam + "y")]
    with pytest.raises(SimulationError) as ei:
        simulate_paragraph_edits(st, [
            {"command": "split", "source_paragraph_id": st[0].id,
             "split_offsets": [2], "new_paragraph_ids": [str(uuid.uuid4()), str(uuid.uuid4())]},
        ])
    assert ei.value.code == "invalid_split_offset"


def test_split_emoji_boundary_ok():
    fam = "👨\u200d👩\u200d👧"  # 5 码点
    st = [SimParagraph(str(uuid.uuid4()), "x" + fam + "y")]
    res = simulate_paragraph_edits(st, [
        {"command": "split", "source_paragraph_id": st[0].id,
         "split_offsets": [1, 6], "new_paragraph_ids": [str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())]},
    ])
    assert [p.text for p in res.paragraphs] == ["x", fam, "y"]


def test_split_newline_inside():
    st = [SimParagraph(str(uuid.uuid4()), "第一行\n第二行\n第三行")]
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    # "第一行\n第二行\n第三行" 码点：3+1+3+1+3=11；offset 4 在 "\n" 之后
    res = simulate_paragraph_edits(st, [
        {"command": "split", "source_paragraph_id": st[0].id,
         "split_offsets": [4], "new_paragraph_ids": [a, b]},
    ])
    assert [p.text for p in res.paragraphs] == ["第一行\n", "第二行\n第三行"]


def test_merge_5_6():
    """spec 边界：旧 1-9，合并旧 5、6 → 新 1-8。"""
    st = mkstate(9)
    p5, p6 = st[4].id, st[5].id
    nid = str(uuid.uuid4())
    res = simulate_paragraph_edits(st, [
        {"command": "merge", "source_paragraph_ids": [p5, p6],
         "paragraph_id": nid, "text": "合并后的五六段"},
    ])
    assert len(res.paragraphs) == 8
    assert res.paragraphs[4].id == nid
    assert res.paragraphs[4].text == "合并后的五六段"
    assert res.lineage[0].id_map == {p5: [nid], p6: [nid]}


def test_merge_must_be_adjacent_and_ordered():
    st = mkstate(5)
    nid = str(uuid.uuid4())
    # 不相邻
    with pytest.raises(SimulationError) as ei:
        simulate_paragraph_edits(st, [
            {"command": "merge", "source_paragraph_ids": [st[0].id, st[2].id],
             "paragraph_id": nid, "text": "x"},
        ])
    assert ei.value.code == "invalid_merge"
    # 逆序
    with pytest.raises(SimulationError):
        simulate_paragraph_edits(st, [
            {"command": "merge", "source_paragraph_ids": [st[2].id, st[1].id],
             "paragraph_id": str(uuid.uuid4()), "text": "x"},
        ])


def test_delete_partial_and_all_rejected():
    st = mkstate(3)
    res = simulate_paragraph_edits(st, [
        {"command": "delete", "paragraph_ids": [st[0].id, st[2].id]},
    ])
    assert len(res.paragraphs) == 1
    assert res.lineage[0].id_map == {st[0].id: [], st[2].id: []}
    # 全删拒绝
    st2 = mkstate(2)
    with pytest.raises(SimulationError) as ei:
        simulate_paragraph_edits(st2, [
            {"command": "delete", "paragraph_ids": [p.id for p in st2]},
        ])
    assert ei.value.code == "delete_all"


def test_failure_has_no_partial_result():
    st = mkstate(3)
    before = [(p.id, p.text) for p in st]
    with pytest.raises(SimulationError):
        simulate_paragraph_edits(st, [
            {"command": "update_text", "paragraph_id": st[0].id, "text": "已改"},
            {"command": "delete", "paragraph_ids": ["00000000-0000-4000-8000-000000000000"]},
        ])
    # 输入 state 未被修改（纯函数不 mutate 输入）
    assert [(p.id, p.text) for p in st] == before


def test_new_uuid_conflict_in_batch():
    st = mkstate(2)
    nid = str(uuid.uuid4())
    with pytest.raises(SimulationError) as ei:
        simulate_paragraph_edits(st, [
            {"command": "insert", "paragraph_id": nid, "text": "A",
             "placement": "append", "target_paragraph_id": None},
            {"command": "insert", "paragraph_id": nid, "text": "B",
             "placement": "append", "target_paragraph_id": None},
        ])
    assert ei.value.code == "paragraph_id_conflict"


def test_empty_text_rejected():
    st = mkstate(2)
    with pytest.raises(SimulationError) as ei:
        simulate_paragraph_edits(st, [
            {"command": "update_text", "paragraph_id": st[0].id, "text": "   "},
        ])
    assert ei.value.code == "empty_text"
