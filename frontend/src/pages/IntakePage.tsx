import { useState } from "react";
import PageHeader from "../components/PageHeader";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

type Tab = "person" | "record" | "discourse" | "issue" | "anchor";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "block", marginBottom: 12 }}>
      <div style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 4 }}>{label}</div>
      {children}
    </label>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "8px 10px", fontSize: 14,
  border: "1px solid var(--border)", borderRadius: 6, boxSizing: "border-box",
};

function PersonForm() {
  const [name, setName] = useState("");
  const [aliases, setAliases] = useState("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg("");
    try {
      const r = await api.post("/persons/", {
        primary_name: name.trim(),
        aliases: aliases.split(/[,，、]/).map((s) => s.trim()).filter(Boolean),
        note: note.trim(),
      });
      setMsg(`已创建人物：${r.data.primary_name}`);
      setName(""); setAliases(""); setNote("");
    } catch (e: any) { setMsg(e.message || "创建失败"); }
    finally { setBusy(false); }
  }
  return (
    <form onSubmit={submit}>
      <Field label="姓名 *"><input style={inputStyle} value={name} onChange={(e) => setName(e.target.value)} required /></Field>
      <Field label="别名（逗号/顿号分隔）"><input style={inputStyle} value={aliases} onChange={(e) => setAliases(e.target.value)} /></Field>
      <Field label="备注"><textarea style={inputStyle} rows={3} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      <button disabled={busy || !name.trim()}>{busy ? "提交中…" : "创建人物"}</button>
      {msg && <p className={msg.startsWith("已创建") ? "ok" : "err"}>{msg}</p>}
    </form>
  );
}

function RecordForm() {
  const [recordType, setRecordType] = useState("book");
  const [title, setTitle] = useState("");
  const [year, setYear] = useState("");
  const [language, setLanguage] = useState("zh");
  const [doi, setDoi] = useState("");
  const [publication, setPublication] = useState("");
  const [contribs, setContribs] = useState<{ name: string; role: string }[]>([{ name: "", role: "author" }]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const personsQ = useQuery({
    queryKey: ["persons-all"],
    queryFn: () => api.get("/persons/?limit=100").then((r) => r.items as { id: string; primary_name: string }[]),
  });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg("");
    try {
      // 责任者：按姓名匹配现有人物，否则用字面名
      const contributors = contribs.filter((c) => c.name.trim()).map((c, i) => {
        const hit = personsQ.data?.find((p) => p.primary_name === c.name.trim());
        return hit
          ? { person_id: hit.id, role: c.role, ordinal: i }
          : { literal_name: c.name.trim(), role: c.role, ordinal: i };
      });
      const r = await api.post("/references/", {
        record_type: recordType, title: title.trim(),
        year: year ? parseInt(year, 10) : null, language,
        doi: doi.trim() || null, publication: publication.trim() || null,
        contributors,
      });
      setMsg(`已创建文献：${r.data.title}`);
      setTitle(""); setYear(""); setDoi(""); setPublication("");
      setContribs([{ name: "", role: "author" }]);
    } catch (e: any) { setMsg(e.message || "创建失败"); }
    finally { setBusy(false); }
  }
  return (
    <form onSubmit={submit}>
      <Field label="类型 *">
        <select style={inputStyle} value={recordType} onChange={(e) => setRecordType(e.target.value)}>
          <option value="book">专著</option>
          <option value="journal">期刊论文</option>
          <option value="thesis">学位论文</option>
          <option value="chapter">章节</option>
        </select>
      </Field>
      <Field label="标题 *"><input style={inputStyle} value={title} onChange={(e) => setTitle(e.target.value)} required /></Field>
      <Field label="年份"><input style={inputStyle} type="number" value={year} onChange={(e) => setYear(e.target.value)} /></Field>
      <Field label="语言">
        <select style={inputStyle} value={language} onChange={(e) => setLanguage(e.target.value)}>
          <option value="zh">中文</option><option value="en">英文</option><option value="other">其他</option>
        </select>
      </Field>
      <Field label="DOI"><input style={inputStyle} value={doi} onChange={(e) => setDoi(e.target.value)} /></Field>
      <Field label="出版信息"><input style={inputStyle} value={publication} onChange={(e) => setPublication(e.target.value)} /></Field>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 4 }}>责任者（按序）</div>
        {contribs.map((c, i) => (
          <div key={i} style={{ display: "flex", gap: 8, marginBottom: 6 }}>
            <input style={{ ...inputStyle, flex: 1 }} placeholder="姓名（匹配现有人物或字面名）"
              value={c.name} onChange={(e) => {
                const nx = [...contribs]; nx[i] = { ...nx[i], name: e.target.value }; setContribs(nx);
              }} />
            <select style={{ ...inputStyle, width: 100 }} value={c.role}
              onChange={(e) => { const nx = [...contribs]; nx[i] = { ...nx[i], role: e.target.value }; setContribs(nx); }}>
              <option value="author">作者</option><option value="editor">编者</option><option value="translator">译者</option>
            </select>
            <button type="button" onClick={() => setContribs(contribs.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
        <button type="button" className="btn-link" onClick={() => setContribs([...contribs, { name: "", role: "author" }])}>+ 添加责任者</button>
      </div>
      <button disabled={busy || !title.trim()}>{busy ? "提交中…" : "创建文献"}</button>
      {msg && <p className={msg.startsWith("已创建") ? "ok" : "err"}>{msg}</p>}
    </form>
  );
}

function DiscourseForm() {
  const [title, setTitle] = useState("");
  const [recordId, setRecordId] = useState("");
  const [locator, setLocator] = useState("");
  const [note, setNote] = useState("");
  const [rawText, setRawText] = useState("");
  const [issueIds, setIssueIds] = useState<string[]>([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const recordsQ = useQuery({
    queryKey: ["records-all"],
    queryFn: () => api.get("/references/?limit=100").then((r) => r.items),
  });
  const issuesQ = useQuery({
    queryKey: ["issues"],
    queryFn: () => api.get("/issues/?limit=100").then((r) => r.items as { id: string; title: string }[]),
  });

  // 分段预览：按空行分段
  const paragraphs = rawText.split(/\n\s*\n/).map((s) => s.trim()).filter(Boolean);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg("");
    try {
      const r = await api.post("/discourses/", {
        title: title.trim(),
        bibliographic_record_id: recordId || null,
        source_locator: locator.trim() ? { raw: locator.trim() } : {},
        attribution_note: note.trim(),
        paragraphs,
        issue_ids: issueIds,
      });
      setMsg(`已创建论述：${r.data.title}（${paragraphs.length} 段）`);
      setTitle(""); setRecordId(""); setLocator(""); setNote(""); setRawText(""); setIssueIds([]);
    } catch (e: any) { setMsg(e.message || "创建失败"); }
    finally { setBusy(false); }
  }

  return (
    <form onSubmit={submit}>
      <Field label="标题 *"><input style={inputStyle} value={title} onChange={(e) => setTitle(e.target.value)} required /></Field>
      <Field label="文献">
        <select style={inputStyle} value={recordId} onChange={(e) => setRecordId(e.target.value)}>
          <option value="">— 无 —</option>
          {recordsQ.data?.map((r: any) => <option key={r.id} value={r.id}>{r.title}</option>)}
        </select>
      </Field>
      <Field label="出处定位"><input style={inputStyle} value={locator} onChange={(e) => setLocator(e.target.value)} placeholder="如：页 12-15" /></Field>
      <Field label="归属说明"><input style={inputStyle} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      <Field label={`正文（空行分段，当前 ${paragraphs.length} 段）*`}>
        <textarea style={{ ...inputStyle, fontFamily: "serif" }} rows={10} value={rawText}
          onChange={(e) => setRawText(e.target.value)} placeholder="粘贴全文，空行处自动分段…" required />
      </Field>
      {paragraphs.length > 0 && (
        <details style={{ marginBottom: 12 }}>
          <summary>分段预览（{paragraphs.length}）</summary>
          <ol>{paragraphs.map((p, i) => <li key={i} className="hint">{p.slice(0, 60)}{p.length > 60 ? "…" : ""}</li>)}</ol>
        </details>
      )}
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 4 }}>挂载到争议问题</div>
        {issuesQ.data?.map((i: any) => (
          <label key={i.id} style={{ display: "block", fontSize: 14 }}>
            <input type="checkbox" checked={issueIds.includes(i.id)}
              onChange={(e) => setIssueIds(e.target.checked ? [...issueIds, i.id] : issueIds.filter((x) => x !== i.id))} />{" "}
            {i.title}
          </label>
        ))}
      </div>
      <button disabled={busy || !title.trim() || paragraphs.length === 0}>{busy ? "提交中…" : "创建论述"}</button>
      {msg && <p className={msg.startsWith("已创建") ? "ok" : "err"}>{msg}</p>}
    </form>
  );
}

function IssueForm() {
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [catId, setCatId] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const catsQ = useQuery({
    queryKey: ["cats-flat"],
    queryFn: () => api.get("/categories/tree").then((r) => r.data as any[]),
  });
  // 扁平化分类树用于下拉选择
  const flatCats: { id: string; name: string; depth: number }[] = [];
  (function walk(nodes: any[], depth: number) {
    for (const n of nodes || []) {
      flatCats.push({ id: n.id, name: n.name, depth });
      walk(n.children, depth + 1);
    }
  })(catsQ.data || [], 0);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg("");
    try {
      const r = await api.post("/issues/", { title: title.trim(), summary: summary.trim() });
      const newId = r.data.id;
      if (catId) {
        await api.post(`/issues/${newId}/categories`, { category_id: catId });
      }
      setMsg(`已创建问题：${r.data.title}${catId ? "（已挂靠分类）" : ""}`);
      setTitle(""); setSummary(""); setCatId("");
    } catch (e: any) { setMsg(e.message || "创建失败"); }
    finally { setBusy(false); }
  }
  return (
    <form onSubmit={submit}>
      <Field label="标题 *"><input style={inputStyle} value={title} onChange={(e) => setTitle(e.target.value)} required /></Field>
      <Field label="摘要"><textarea style={inputStyle} rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} /></Field>
      <Field label="挂靠分类">
        <select style={inputStyle} value={catId} onChange={(e) => setCatId(e.target.value)}>
          <option value="">— 不挂靠 —</option>
          {flatCats.map((c) => (
            <option key={c.id} value={c.id}>{"　".repeat(c.depth)}{c.name}</option>
          ))}
        </select>
      </Field>
      <button disabled={busy || !title.trim()}>{busy ? "提交中…" : "创建问题"}</button>
      {msg && <p className={msg.startsWith("已创建") ? "ok" : "err"}>{msg}</p>}
    </form>
  );
}

function AnchorForm() {
  const [discourseId, setDiscourseId] = useState("");
  const [startId, setStartId] = useState("");
  const [endId, setEndId] = useState("");
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const discsQ = useQuery({
    queryKey: ["discs-all"],
    queryFn: () => api.get("/discourses/?limit=100").then((r) => r.items as { id: string; title: string }[]),
  });
  const parasQ = useQuery({
    queryKey: ["paras-for-anchor", discourseId],
    queryFn: () => api.get(`/discourses/${discourseId}`).then((r) => r.data.paragraphs as { id: string; order: number; text: string }[]),
    enabled: !!discourseId,
  });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg("");
    try {
      await api.post("/anchors/", {
        discourse_id: discourseId,
        start_paragraph_id: startId || null,
        end_paragraph_id: endId || startId || null,
        title: title.trim() || null, note: note.trim(),
      });
      setMsg("已创建锚点");
      setStartId(""); setEndId(""); setTitle(""); setNote("");
    } catch (e: any) { setMsg(e.message || "创建失败"); }
    finally { setBusy(false); }
  }
  return (
    <form onSubmit={submit}>
      <Field label="论述 *">
        <select style={inputStyle} value={discourseId} onChange={(e) => { setDiscourseId(e.target.value); setStartId(""); setEndId(""); }} required>
          <option value="">— 选择 —</option>
          {discsQ.data?.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
        </select>
      </Field>
      {parasQ.data && (
        <>
          <Field label="起始段落 *">
            <select style={inputStyle} value={startId} onChange={(e) => setStartId(e.target.value)} required>
              <option value="">— 选择 —</option>
              {parasQ.data.map((p) => <option key={p.id} value={p.id}>#{p.order} {p.text.slice(0, 40)}…</option>)}
            </select>
          </Field>
          <Field label="结束段落（默认同起始）">
            <select style={inputStyle} value={endId} onChange={(e) => setEndId(e.target.value)}>
              <option value="">— 同起始 —</option>
              {parasQ.data.map((p) => <option key={p.id} value={p.id}>#{p.order} {p.text.slice(0, 40)}…</option>)}
            </select>
          </Field>
        </>
      )}
      <Field label="标题"><input style={inputStyle} value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
      <Field label="备注"><textarea style={inputStyle} rows={3} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      <button disabled={busy || !discourseId || !startId}>{busy ? "提交中…" : "创建锚点"}</button>
      {msg && <p className={msg.startsWith("已创建") ? "ok" : "err"}>{msg}</p>}
    </form>
  );
}

const TABS: { key: Tab; label: string }[] = [
  { key: "person", label: "人物" },
  { key: "record", label: "文献" },
  { key: "discourse", label: "论述" },
  { key: "issue", label: "争议问题" },
  { key: "anchor", label: "锚点" },
];

export default function IntakePage() {
  const [tab, setTab] = useState<Tab>("person");
  return (
    <div className="editor-wrap">
      <PageHeader title="录入" subtitle="人物 · 文献 · 论述 · 议题 · 锚点" />
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.key} className={tab === t.key ? "active" : ""}
            onClick={() => setTab(t.key)}>{t.label}</button>
        ))}
      </div>
      <div style={{ maxWidth: 640 }}>
        {tab === "person" && <PersonForm />}
        {tab === "record" && <RecordForm />}
        {tab === "discourse" && <DiscourseForm />}
        {tab === "issue" && <IssueForm />}
        {tab === "anchor" && <AnchorForm />}
      </div>
    </div>
  );
}
