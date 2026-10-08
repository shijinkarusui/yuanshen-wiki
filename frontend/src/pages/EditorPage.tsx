import { useRef, useState } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  selectionToCodePoints,
} from "../utils/unicode";

interface Paragraph {
  id: string;
  order: number;
  text: string;
}

interface Discourse {
  id: string;
  title: string;
  revision: number;
  paragraph_revision: number;
  paragraphs: Paragraph[];
}

type Command =
  | { command: "update_text"; paragraph_id: string; text: string }
  | {
      command: "insert";
      paragraph_id: string;
      text: string;
      placement: "before" | "after" | "append";
      target_paragraph_id: string | null;
    }
  | {
      command: "split";
      source_paragraph_id: string;
      split_offsets: number[];
      new_paragraph_ids: string[];
    }
  | {
      command: "merge";
      source_paragraph_ids: string[];
      paragraph_id: string;
      text: string;
    }
  | { command: "delete"; paragraph_ids: string[] };

function cmdLabel(c: Command): string {
  switch (c.command) {
    case "update_text":
      return `改写段落 ${c.paragraph_id.slice(0, 8)}…`;
    case "insert":
      return `插入（${c.placement === "append" ? "末尾" : c.placement}）`;
    case "split":
      return `拆分段落 ${c.source_paragraph_id.slice(0, 8)}… 为 ${c.new_paragraph_ids.length} 段`;
    case "merge":
      return `合并 ${c.source_paragraph_ids.length} 个段落`;
    case "delete":
      return `删除 ${c.paragraph_ids.length} 个段落`;
  }
}

export default function EditorPage() {
  const { issueId } = useParams();
  const [sp] = useSearchParams();
  const discourseId = sp.get("discourse") || "";
  const qc = useQueryClient();

  const [commands, setCommands] = useState<Command[]>([]);
  const [preview, setPreview] = useState<any>(null);
  const [error, setError] = useState("");
  const [okMsg, setOkMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [mergeSel, setMergeSel] = useState<string[]>([]);
  const [mergeText, setMergeText] = useState("");
  const [editText, setEditText] = useState<Record<string, string>>({});
  const [splitFor, setSplitFor] = useState<string | null>(null);
  const [splitCuts, setSplitCuts] = useState<number[]>([]);
  const splitRef = useRef<HTMLTextAreaElement>(null);

  const discQ = useQuery({
    queryKey: ["discourse", discourseId],
    queryFn: () => api.get(`/discourses/${discourseId}`).then((r) => r.data as Discourse),
    enabled: !!discourseId,
  });
  const disc = discQ.data;

  const ifMatch = disc ? `"rev-${disc.revision}"` : "";

  function pushCmd(c: Command) {
    setCommands((cs) => [...cs, c]);
    setPreview(null); // 命令变化 → 预览失效
    setOkMsg("");
  }

  function removeCmd(i: number) {
    setCommands((cs) => cs.filter((_, j) => j !== i));
    setPreview(null);
  }

  async function doPreview() {
    if (!disc || commands.length === 0) return;
    setBusy(true);
    setError("");
    setOkMsg("");
    try {
      const r = await api.previewParagraphEdits(
        disc.id,
        disc.paragraph_revision,
        commands,
        ifMatch,
      );
      setPreview(r.data);
    } catch (e: any) {
      setError(e.message || "预览失败");
    } finally {
      setBusy(false);
    }
  }

  async function doCommit() {
    if (!disc || !preview) return;
    setBusy(true);
    setError("");
    try {
      const r = await api.commitParagraphEdits(
        disc.id,
        disc.paragraph_revision,
        commands,
        preview.preview_fingerprint,
        ifMatch,
        crypto.randomUUID(),
      );
      setOkMsg(
        `提交成功：论述 rev-${r.data.discourse_revision}，段落版本 ${r.data.paragraph_revision}`,
      );
      setCommands([]);
      setPreview(null);
      qc.invalidateQueries({ queryKey: ["discourse", discourseId] });
    } catch (e: any) {
      // 409 preview_stale → 保留本地草稿，仅提示重新预览
      setError(e.message || "提交失败");
    } finally {
      setBusy(false);
    }
  }

  function addSplitPoint(text: string) {
    const ta = splitRef.current;
    if (!ta) return;
    try {
      const cps = selectionToCodePoints(text, ta.selectionStart, ta.selectionEnd);
      setSplitCuts((cuts) => [...new Set([...cuts, ...cps])].sort((a, b) => a - b));
      setError("");
    } catch (e: any) {
      setError(e.message);
    }
  }

  function confirmSplit(paraId: string) {
    if (splitCuts.length === 0) {
      setError("请先用鼠标在文本中选择切分位置");
      return;
    }
    pushCmd({
      command: "split",
      source_paragraph_id: paraId,
      split_offsets: splitCuts,
      new_paragraph_ids: splitCuts.map(() => crypto.randomUUID()),
    });
    setSplitFor(null);
    setSplitCuts([]);
  }

  function confirmMerge() {
    if (mergeSel.length < 2) {
      setError("合并至少需要选择两个段落");
      return;
    }
    if (!mergeText.trim()) {
      setError("请填写合并后的段落正文（可同时校对）");
      return;
    }
    // 客户端预校验相邻性（后端也会校验）
    if (disc) {
      const orderById = new Map(disc.paragraphs.map((p) => [p.id, p.order]));
      const orders = mergeSel.map((id) => orderById.get(id) ?? -1).sort((a, b) => a - b);
      const adjacent = orders.every((o, i) => i === 0 || o === orders[i - 1] + 1);
      if (!adjacent || orders.includes(-1)) {
        setError("所选段落必须相邻且连续，请重新选择");
        return;
      }
      // 按段落顺序排列
      mergeSel.sort((a, b) => (orderById.get(a) ?? 0) - (orderById.get(b) ?? 0));
    }
    pushCmd({
      command: "merge",
      source_paragraph_ids: mergeSel,
      paragraph_id: crypto.randomUUID(),
      text: mergeText,
    });
    setMergeSel([]);
    setMergeText("");
  }

  if (!discourseId) return <p>缺少 discourse 参数</p>;
  if (discQ.isLoading) return <p>加载中…</p>;
  if (!disc) return <p>论述不存在</p>;

  return (
    <div className="editor-wrap">
      <header className="topbar">
        <Link to={`/issues/${issueId}?discourse=${discourseId}`}>← 返回阅读</Link>
        <h1>段落编辑：{disc.title}</h1>
        <span className="badge">
          rev-{disc.revision} / 段落版本 {disc.paragraph_revision}
        </span>
      </header>

      {error && <div className="alert error">{error}</div>}
      {okMsg && <div className="alert ok">{okMsg}</div>}

      <div className="editor-cols">
        <div className="editor-main">
          {mergeSel.length > 0 && (
            <div className="card merge-bar">
              <p>已选 {mergeSel.length} 段用于合并（须相邻且有序）</p>
              <textarea
                rows={3}
                placeholder="合并后的段落正文（用户确认，可同时校对）"
                value={mergeText}
                onChange={(e) => setMergeText(e.target.value)}
              />
              <div>
                <button onClick={confirmMerge}>确认合并</button>
                <button onClick={() => setMergeSel([])}>取消选择</button>
              </div>
            </div>
          )}

          {disc.paragraphs.map((p) => (
            <div key={p.id} className="card para-edit">
              <div className="para-head">
                <span className="pno">{p.order}</span>
                <label>
                  <input
                    type="checkbox"
                    checked={mergeSel.includes(p.id)}
                    onChange={(e) =>
                      setMergeSel((s) =>
                        e.target.checked ? [...s, p.id] : s.filter((x) => x !== p.id),
                      )
                    }
                  />{" "}
                  合并
                </label>
              </div>
              {editText[p.id] !== undefined ? (
                <>
                  <textarea
                    rows={4}
                    value={editText[p.id]}
                    onChange={(e) =>
                      setEditText((m) => ({ ...m, [p.id]: e.target.value }))
                    }
                  />
                  <div>
                    <button
                      onClick={() => {
                        pushCmd({
                          command: "update_text",
                          paragraph_id: p.id,
                          text: editText[p.id],
                        });
                        setEditText((m) => {
                          const n = { ...m };
                          delete n[p.id];
                          return n;
                        });
                      }}
                    >
                      加入改写
                    </button>
                    <button
                      onClick={() =>
                        setEditText((m) => {
                          const n = { ...m };
                          delete n[p.id];
                          return n;
                        })
                      }
                    >
                      取消
                    </button>
                  </div>
                </>
              ) : splitFor === p.id ? (
                <>
                  <textarea
                    ref={splitRef}
                    rows={4}
                    readOnly
                    value={p.text}
                    style={{ userSelect: "text", cursor: "text" }}
                  />
                  <p className="hint">
                    用鼠标在文本中拖选出切分点位置（可多次），已选码点：
                    {splitCuts.join(", ") || "无"}
                  </p>
                  <div>
                    <button onClick={() => addSplitPoint(p.text)}>添加切分点</button>
                    <button onClick={() => confirmSplit(p.id)}>确认拆分</button>
                    <button
                      onClick={() => {
                        setSplitFor(null);
                        setSplitCuts([]);
                      }}
                    >
                      取消
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <p className="serif">{p.text}</p>
                  <div className="para-actions">
                    <button onClick={() => setEditText((m) => ({ ...m, [p.id]: p.text }))}>
                      改写
                    </button>
                    <button
                      onClick={() => {
                        const t = prompt("在该段之前插入的新段落正文：");
                        if (t && t.trim())
                          pushCmd({
                            command: "insert",
                            paragraph_id: crypto.randomUUID(),
                            text: t,
                            placement: "before",
                            target_paragraph_id: p.id,
                          });
                      }}
                    >
                      前插
                    </button>
                    <button
                      onClick={() => {
                        const t = prompt("在该段之后插入的新段落正文：");
                        if (t && t.trim())
                          pushCmd({
                            command: "insert",
                            paragraph_id: crypto.randomUUID(),
                            text: t,
                            placement: "after",
                            target_paragraph_id: p.id,
                          });
                      }}
                    >
                      后插
                    </button>
                    <button
                      onClick={() => {
                        setSplitFor(p.id);
                        setSplitCuts([]);
                      }}
                    >
                      拆分
                    </button>
                    <button
                      onClick={() => {
                        if (confirm(`删除第 ${p.order} 段？`))
                          pushCmd({ command: "delete", paragraph_ids: [p.id] });
                      }}
                    >
                      删除
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
          <div className="card">
            <button
              onClick={() => {
                const t = prompt("追加到末尾的新段落正文：");
                if (t && t.trim())
                  pushCmd({
                    command: "insert",
                    paragraph_id: crypto.randomUUID(),
                    text: t,
                    placement: "append",
                    target_paragraph_id: null,
                  });
              }}
            >
              ＋ 末尾追加段落
            </button>
          </div>
        </div>

        <div className="editor-side">
          <h3>命令草稿（{commands.length}）</h3>
          {commands.length === 0 && <p className="hint">暂无命令。左侧对段落执行操作后会在此列出。</p>}
          <ol>
            {commands.map((c, i) => (
              <li key={i}>
                {i + 1}. {cmdLabel(c)}{" "}
                <button onClick={() => removeCmd(i)}>移除</button>
              </li>
            ))}
          </ol>
          <button onClick={doPreview} disabled={busy || commands.length === 0}>
            {busy ? "处理中…" : "预览影响"}
          </button>

          {preview && (
            <div className="preview-box">
              <h3>预览结果</h3>
              <p className="hint">
                指纹 {preview.preview_fingerprint.slice(0, 16)}… ｜ 预测{" "}
                {preview.paragraphs.length} 段
              </p>
              <h4>受影响锚点（{preview.anchor_impacts.length}）</h4>
              {preview.anchor_impacts
                .filter((a: any) => a.content_changed || a.display_range_changed || a.will_be_invalid)
                .map((a: any) => (
                  <div key={a.anchor_id} className="card">
                    <p>
                      <code>{a.anchor_id.slice(0, 8)}</code>{" "}
                      {a.old_range.start ?? "?"}-{a.old_range.end ?? "?"} →{" "}
                      {a.will_be_invalid ? "失效" : `${a.new_range.start}-${a.new_range.end}`}
                    </p>
                    <p className="hint">
                      {a.content_changed && "内容变化 "}
                      {a.display_range_changed && "范围变化 "}
                      {a.will_be_invalid && "将失效 "}
                      {a.relation_ids.length > 0 && `关联关系 ${a.relation_ids.length} 条（保留）`}
                    </p>
                  </div>
                ))}
              {preview.anchor_impacts.filter(
                (a: any) => a.content_changed || a.display_range_changed || a.will_be_invalid,
              ).length === 0 && <p className="hint">无锚点受影响</p>}
              <button onClick={doCommit} disabled={busy}>
                {busy ? "提交中…" : "确认提交"}
              </button>
              <p className="hint">
                提交携带预览指纹；若期间数据变化将返回 409 并保留草稿，请重新预览。
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
