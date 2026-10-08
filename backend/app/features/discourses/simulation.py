"""M04A: 纯段落编辑模拟器。

simulate_paragraph_edits(state, commands) 是纯函数：
- 无数据库访问、无时间/随机副作用
- 任一步失败则整体失败，不返回部分结果

命令契约见 spec §7.2。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import regex

ALGORITHM_VERSION = "para-sim-v1"


class SimulationError(Exception):
    """code 为机器可读错误码，message 为人类可读说明。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class SimParagraph:
    id: str
    text: str


@dataclass
class LineageStep:
    step_index: int
    command_type: str
    source_ids: list[str] = field(default_factory=list)
    source_orders: list[int] = field(default_factory=list)
    target_ids: list[str] = field(default_factory=list)
    target_orders: list[int] = field(default_factory=list)
    # 该步骤的 ID 映射（旧ID -> 新ID列表），供锚点映射使用：
    # update: {id:[id]}；insert: {}；split: {src:[n1,n2..]}；
    # merge: {s1:[n],s2:[n]..}；delete: {d:[]}
    id_map: dict[str, list[str]] = field(default_factory=dict)
    before_order: list[str] = field(default_factory=list)
    after_order: list[str] = field(default_factory=list)
    # 本步直接改写文本的段落 ID（update_text 的 target），用于内容变化检测
    text_changed_ids: list[str] = field(default_factory=list)


@dataclass
class SimulationResult:
    paragraphs: list[SimParagraph]
    lineage: list[LineageStep]


def _as_uuid(value: str, field_name: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise SimulationError("invalid_uuid", f"{field_name} 不是合法 UUID: {value!r}")


def _require_nonempty_text(text: object, command: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise SimulationError("empty_text", f"{command}: 文本不能为空（text.strip() 为空）")
    return text


def _grapheme_boundaries(text: str) -> set[int]:
    """返回所有扩展字素簇边界的码点偏移集合（含 0 和 len）。"""
    bounds = {0}
    for m in regex.finditer(r"\X", text):
        bounds.add(m.end())
    return bounds


def _check_new_id(pid: str, seen: set[str], command: str) -> str:
    pid = _as_uuid(pid, f"{command}.paragraph_id")
    if pid in seen:
        raise SimulationError(
            "paragraph_id_conflict",
            f"{command}: 新段落 ID 已被占用: {pid}",
        )
    return pid


class _State:
    def __init__(self, paragraphs: list[SimParagraph]):
        self.paras: list[SimParagraph] = [SimParagraph(p.id, p.text) for p in paragraphs]
        self.ids: set[str] = {p.id for p in self.paras}

    def order_of(self, pid: str) -> int:
        for i, p in enumerate(self.paras):
            if p.id == pid:
                return i + 1
        raise SimulationError("unknown_paragraph", f"段落不存在于当前步骤: {pid}")

    def get(self, pid: str) -> SimParagraph:
        for p in self.paras:
            if p.id == pid:
                return p
        raise SimulationError("unknown_paragraph", f"段落不存在于当前步骤: {pid}")

    def order_list(self) -> list[str]:
        return [p.id for p in self.paras]


def _cmd_update(st: _State, cmd: dict, step: LineageStep) -> None:
    pid = _as_uuid(cmd.get("paragraph_id"), "update_text.paragraph_id")
    para = st.get(pid)  # 不存在则抛 unknown_paragraph
    text = _require_nonempty_text(cmd.get("text"), "update_text")
    order = st.order_of(pid)
    para.text = text
    step.source_ids = [pid]
    step.source_orders = [order]
    step.target_ids = [pid]
    step.target_orders = [order]
    step.id_map = {pid: [pid]}
    step.text_changed_ids = [pid]


def _cmd_insert(st: _State, cmd: dict, step: LineageStep) -> None:
    new_id = _check_new_id(cmd.get("paragraph_id"), st.ids, "insert")
    text = _require_nonempty_text(cmd.get("text"), "insert")
    placement = cmd.get("placement")
    target = cmd.get("target_paragraph_id")
    if placement == "append":
        if target is not None:
            raise SimulationError("invalid_placement", "insert: placement=append 时 target 必须为 null")
        idx = len(st.paras)
        src_ids, src_orders = [], []
    elif placement in ("before", "after"):
        if target is None:
            raise SimulationError("invalid_placement", f"insert: placement={placement} 时必须给出 target_paragraph_id")
        tid = _as_uuid(target, "insert.target_paragraph_id")
        torder = st.order_of(tid)
        idx = torder - 1 if placement == "before" else torder
        src_ids, src_orders = [tid], [torder]
    else:
        raise SimulationError("invalid_placement", f"insert: 非法 placement: {placement!r}，应为 before|after|append")
    st.paras.insert(idx, SimParagraph(new_id, text))
    st.ids.add(new_id)
    step.source_ids = src_ids
    step.source_orders = src_orders
    step.target_ids = [new_id]
    step.target_orders = [idx + 1]
    step.id_map = {}


def _cmd_split(st: _State, cmd: dict, step: LineageStep) -> None:
    src_id = _as_uuid(cmd.get("source_paragraph_id"), "split.source_paragraph_id")
    src = st.get(src_id)
    src_order = st.order_of(src_id)
    offsets = cmd.get("split_offsets")
    new_ids_raw = cmd.get("new_paragraph_ids")
    if not isinstance(offsets, list) or not offsets or not all(
        isinstance(o, int) and not isinstance(o, bool) for o in offsets
    ):
        raise SimulationError("invalid_split_offset", "split: split_offsets 必须是非空整数数组")
    if offsets != sorted(offsets) or len(set(offsets)) != len(offsets):
        raise SimulationError("invalid_split_offset", "split: split_offsets 必须严格递增")
    n_cp = len(src.text)
    if any(o < 1 or o > n_cp - 1 for o in offsets):
        raise SimulationError(
            "invalid_split_offset",
            f"split: offset 必须在 1..{n_cp - 1} 范围内",
        )
    bounds = _grapheme_boundaries(src.text)
    bad = [o for o in offsets if o not in bounds]
    if bad:
        raise SimulationError(
            "invalid_split_offset",
            f"split: offset {bad} 落在扩展字素簇内部，禁止切分",
        )
    if not isinstance(new_ids_raw, list) or len(new_ids_raw) != len(offsets) + 1:
        raise SimulationError(
            "invalid_split_offset",
            f"split: new_paragraph_ids 数量必须为 offsets 数量 + 1（{len(offsets) + 1}）",
        )
    new_ids: list[str] = []
    seen_new: set[str] = set()
    for v in new_ids_raw:
        nid = _as_uuid(v, "split.new_paragraph_ids")
        if nid in st.ids or nid in seen_new:
            raise SimulationError("paragraph_id_conflict", f"split: 新段落 ID 已被占用: {nid}")
        seen_new.add(nid)
        new_ids.append(nid)
    cuts = [0] + offsets + [n_cp]
    parts = [src.text[cuts[i] : cuts[i + 1]] for i in range(len(cuts) - 1)]
    for part in parts:
        if not part.strip():
            raise SimulationError("invalid_split_offset", "split: 切分产生了空段落")
    idx = src_order - 1
    st.paras[idx : idx + 1] = [SimParagraph(nid, part) for nid, part in zip(new_ids, parts)]
    st.ids.discard(src_id)
    st.ids.update(new_ids)
    step.source_ids = [src_id]
    step.source_orders = [src_order]
    step.target_ids = new_ids
    step.target_orders = list(range(src_order, src_order + len(new_ids)))
    step.id_map = {src_id: list(new_ids)}


def _cmd_merge(st: _State, cmd: dict, step: LineageStep) -> None:
    raw_sources = cmd.get("source_paragraph_ids")
    if not isinstance(raw_sources, list) or len(raw_sources) < 2:
        raise SimulationError("invalid_merge", "merge: source_paragraph_ids 至少需要两个")
    sources = [_as_uuid(v, "merge.source_paragraph_ids") for v in raw_sources]
    if len(set(sources)) != len(sources):
        raise SimulationError("invalid_merge", "merge: source_paragraph_ids 有重复")
    orders = [st.order_of(s) for s in sources]  # 不存在则抛 unknown_paragraph
    if orders != sorted(orders) or any(b - a != 1 for a, b in zip(orders, orders[1:])):
        raise SimulationError("invalid_merge", "merge: 源段落必须在当前步骤中相邻且顺序一致")
    new_id = _check_new_id(cmd.get("paragraph_id"), st.ids, "merge")
    text = _require_nonempty_text(cmd.get("text"), "merge")
    first_idx = orders[0] - 1
    del st.paras[first_idx : first_idx + len(sources)]
    st.paras.insert(first_idx, SimParagraph(new_id, text))
    for s in sources:
        st.ids.discard(s)
    st.ids.add(new_id)
    step.source_ids = sources
    step.source_orders = orders
    step.target_ids = [new_id]
    step.target_orders = [orders[0]]
    step.id_map = {s: [new_id] for s in sources}


def _cmd_delete(st: _State, cmd: dict, step: LineageStep) -> None:
    raw_ids = cmd.get("paragraph_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise SimulationError("invalid_delete", "delete: paragraph_ids 必须是非空数组")
    targets = [_as_uuid(v, "delete.paragraph_ids") for v in raw_ids]
    if len(set(targets)) != len(targets):
        raise SimulationError("invalid_delete", "delete: paragraph_ids 有重复")
    orders = [st.order_of(t) for t in targets]
    del_set = set(targets)
    st.paras = [p for p in st.paras if p.id not in del_set]
    for t in targets:
        st.ids.discard(t)
    # source_ids 与 source_orders 必须一一对应（按输入顺序，不另行排序）
    step.source_ids = targets
    step.source_orders = orders
    step.target_ids = []
    step.target_orders = []
    step.id_map = {t: [] for t in targets}


_HANDLERS = {
    "update_text": _cmd_update,
    "insert": _cmd_insert,
    "split": _cmd_split,
    "merge": _cmd_merge,
    "delete": _cmd_delete,
}


def simulate_paragraph_edits(
    state: list[SimParagraph] | list[dict],
    commands: list[dict],
) -> SimulationResult:
    """纯模拟段落编辑命令序列。

    state: 当前活动段落有序列表，每项 {id, text}（dict 或 SimParagraph）。
    commands: 按 §7.2 契约的命令数组。
    任一步失败抛 SimulationError，且不返回部分结果。
    """
    paras: list[SimParagraph] = []
    for p in state:
        if isinstance(p, SimParagraph):
            paras.append(SimParagraph(p.id, p.text))
        else:
            paras.append(SimParagraph(_as_uuid(p.get("id"), "state.id"), str(p.get("text", ""))))
    if not isinstance(commands, list) or not commands:
        raise SimulationError("empty_commands", "commands 必须是非空数组")

    st = _State(paras)
    lineage: list[LineageStep] = []
    for i, cmd in enumerate(commands):
        if not isinstance(cmd, dict):
            raise SimulationError("invalid_command", f"第 {i} 步不是合法命令对象")
        ctype = cmd.get("command")
        handler = _HANDLERS.get(ctype)
        if handler is None:
            raise SimulationError("unknown_command", f"第 {i} 步未知命令: {ctype!r}")
        step = LineageStep(step_index=i, command_type=ctype)
        step.before_order = st.order_list()
        handler(st, cmd, step)
        step.after_order = st.order_list()
        lineage.append(step)

    # 批次结束后必须至少有一个非空活动段落
    if not any(p.text.strip() for p in st.paras):
        raise SimulationError("delete_all", "批次结束后论述必须至少保留一个非空活动段落")

    return SimulationResult(paragraphs=st.paras, lineage=lineage)
