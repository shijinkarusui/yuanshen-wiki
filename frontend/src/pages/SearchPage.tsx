import { useState } from "react";
import PageHeader from "../components/PageHeader";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

interface Hit {
  type: string;
  type_label: string;
  id: string;
  title: string;
  snippet: string;
  extra?: { discourse_id?: string };
}

const ALL_TYPES = ["issue", "discourse", "paragraph", "anchor", "person", "record"];

export default function SearchPage() {
  const [q, setQ] = useState("");
  const [types, setTypes] = useState<string[]>([]);
  const [hits, setHits] = useState<Hit[]>([]);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const nav = useNavigate();

  async function doSearch(e?: React.FormEvent) {
    e?.preventDefault();
    if (!q.trim()) return;
    setBusy(true); setErr("");
    try {
      const r = await api.get(
        `/search?q=${encodeURIComponent(q.trim())}${types.length ? `&types=${types.join(",")}` : ""}&limit=50`,
      );
      setHits(r.items as Hit[]);
      setTotal(r.total);
    } catch (e: any) { setErr(e.message || "检索失败"); }
    finally { setBusy(false); }
  }

  function go(h: Hit) {
    if (h.type === "issue") nav(`/issues/${h.id}`);
    else if (h.type === "discourse" || h.type === "paragraph") {
      // 找到所属 issue
      api.get("/issues/?limit=100").then((r) => {
        const first = (r.items as any[])[0];
        const discId = h.type === "discourse" ? h.id : h.extra?.discourse_id;
        nav(first ? `/issues/${first.id}?discourse=${discId}` : "/");
      });
    } else if (h.type === "anchor" && h.extra?.discourse_id) {
      api.get("/issues/?limit=100").then((r) => {
        const first = (r.items as any[])[0];
        nav(first ? `/issues/${first.id}?discourse=${h.extra!.discourse_id}&anchor=${h.id}` : "/");
      });
    }
  }

  return (
      <div className="editor-wrap">
      <PageHeader title="全局检索" subtitle="跨人物 · 文献 · 论述 · 议题 · 锚点 · 关系" />
      <form onSubmit={doSearch} style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <input
          style={{ flex: 1, padding: "8px 10px", fontSize: 15, border: "1px solid var(--border)", borderRadius: 6 }}
          value={q} onChange={(e) => setQ(e.target.value)} placeholder="输入关键词（中文短词亦可）…" />
        <button disabled={busy || !q.trim()}>{busy ? "检索中…" : "检索"}</button>
      </form>
      <div style={{ marginBottom: 16, fontSize: 14, display: "flex", alignItems: "center", flexWrap: "wrap", gap: 4 }}>
        <span style={{ color: "var(--ink-mute)", marginRight: 8 }}>类型筛选：</span>
        {ALL_TYPES.map((t) => (
          <label key={t} style={{ display: "inline-flex", alignItems: "center", gap: 6, marginRight: 16, margin: 0, cursor: "pointer", fontSize: 14, color: "var(--ink-soft)" }}>
            <input type="checkbox" checked={types.includes(t)}
              onChange={(e) => setTypes(e.target.checked ? [...types, t] : types.filter((x) => x !== t))} />
            {{ issue: "问题", discourse: "论述", paragraph: "段落", anchor: "锚点", person: "人物", record: "文献" }[t]}
          </label>
        ))}
        {types.length > 0 && <button className="btn-link" onClick={() => setTypes([])}>清除</button>}
      </div>
      {err && <p className="err">{err}</p>}
      {hits.length > 0 && <p className="hint">共 {total} 条</p>}
      {hits.map((h) => (
        <div key={`${h.type}-${h.id}`} className="card" style={{ cursor: "pointer" }} onClick={() => go(h)}>
          <p><span className="badge">{h.type_label}</span> <strong>{h.title}</strong></p>
          {h.snippet && <p className="hint">{h.snippet}</p>}
        </div>
      ))}
      {!busy && q && hits.length === 0 && !err && <p className="hint">无结果</p>}
    </div>
  );
}
