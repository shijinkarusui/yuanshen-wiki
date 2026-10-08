import { useState } from "react";
import PageHeader from "../components/PageHeader";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import DualPaneView from "../components/DualPaneView";

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "8px 10px", fontSize: 14,
  border: "1px solid var(--border)", borderRadius: 6, boxSizing: "border-box",
};

function VerifyToggle({ kind, id, verified, onDone }: {
  kind: "relations" | "anchors"; id: string; verified: boolean; onDone: () => void;
}) {
  const [busy, setBusy] = useState(false);
  async function toggle() {
    setBusy(true);
    try {
      await api.post(`/${kind}/${id}/${verified ? "unverify" : "verify"}`, {});
      onDone();
    } catch (e: any) { alert(e.message); }
    finally { setBusy(false); }
  }
  return (
      <button onClick={toggle} disabled={busy} className="btn-link" style={{ fontSize: 13 }}>
      {verified ? "✓ 已校验（点击取消）" : "○ 未校验（点击校验）"}
    </button>
  );
}

export default function RelationsPage() {
  const [sp] = useSearchParams();
  const issueId = sp.get("issue") || "";
  const qc = useQueryClient();

  const [srcAnchor, setSrcAnchor] = useState("");
  const [tgtAnchor, setTgtAnchor] = useState("");
  const [kindCode, setKindCode] = useState("");
  const [basis, setBasis] = useState("author_explicit");
  const [reason, setReason] = useState("");
  const [dimCodes, setDimCodes] = useState<string[]>([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const issuesQ = useQuery({
    queryKey: ["issues"],
    queryFn: () => api.get("/issues/?limit=100").then((r) => r.items as { id: string; title: string }[]),
  });
  const anchorsQ = useQuery({
    queryKey: ["anchors-for-rel", issueId],
    queryFn: async () => {
      if (!issueId) return [];
      const discs = await api.get(`/issues/${issueId}/discourses`).then((r) => r.data as { id: string }[]);
      const all: any[] = [];
      for (const d of discs as any) {
        const as = await api.get(`/anchors/?discourse_id=${(d as any).id}&limit=100`).then((r) => r.items);
        all.push(...as.map((a: any) => ({ ...a, discourse_id: (d as any).id })));
      }
      return all;
    },
    enabled: !!issueId,
  });
  const kindsQ = useQuery({
    queryKey: ["rel-kinds"],
    queryFn: () => api.get("/relation-kinds/").then((r) => r.data as { code: string; name_cn: string }[]),
  });
  const dimsQ = useQuery({
    queryKey: ["dim-kinds"],
    queryFn: () => api.get("/dimension-kinds/").then((r) => r.data as { code: string; name_cn: string }[]),
  });
  const relsQ = useQuery({
    queryKey: ["rels-list", issueId],
    queryFn: () => api.get(`/relations/?issue_id=${issueId}&limit=100`).then((r) => r.items as any[]),
    enabled: !!issueId,
  });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg("");
    try {
      const r = await api.post("/relations/", {
        issue_id: issueId, source_anchor_id: srcAnchor, target_anchor_id: tgtAnchor,
        relation_kind_code: kindCode, basis, reason: reason.trim(),
        dimension_codes: dimCodes,
      });
      setMsg(`已创建关系：${r.data.id.slice(0, 8)}`);
      setSrcAnchor(""); setTgtAnchor(""); setReason(""); setDimCodes([]);
      qc.invalidateQueries({ queryKey: ["rels-list", issueId] });
    } catch (e: any) { setMsg(e.message || "创建失败"); }
    finally { setBusy(false); }
  }

  const activeIssue = issuesQ.data?.[0];
  const curIssue = issueId || activeIssue?.id || "";

  // 选中的关系用于全文对照
  const [compareRelId, setCompareRelId] = useState<string | null>(null);
  const compareRel = relsQ.data?.find((r: any) => r.id === compareRelId);

  return (
    <div className="editor-wrap">
      <PageHeader title="关系对读" subtitle="新建论辩关系 · 两端全文对照" />

      <div style={{ marginBottom: 16 }}>
        <label style={{ fontSize: 13, color: "var(--ink-mute)" }}>争议问题：</label>
        <select style={{ ...inputStyle, width: 300 }}
          value={curIssue}
          onChange={(e) => {
            const url = new URL(window.location.href);
            url.searchParams.set("issue", e.target.value);
            window.location.href = url.toString();
          }}>
          {issuesQ.data?.map((i) => <option key={i.id} value={i.id}>{i.title}</option>)}
        </select>
      </div>

      <div className="editor-cols">
        <div>
          <h3>新建关系</h3>
          <form onSubmit={submit}>
            <label style={{ display: "block", marginBottom: 12 }}>
              <div style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 4 }}>源锚点（A）*</div>
              <select style={inputStyle} value={srcAnchor} onChange={(e) => setSrcAnchor(e.target.value)} required>
                <option value="">— 选择 —</option>
                {anchorsQ.data?.map((a: any) => (
                  <option key={a.id} value={a.id}>{a.title || a.id.slice(0, 8)} {!a.is_valid && "(失效)"}</option>
                ))}
              </select>
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <div style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 4 }}>目标锚点（B）*</div>
              <select style={inputStyle} value={tgtAnchor} onChange={(e) => setTgtAnchor(e.target.value)} required>
                <option value="">— 选择 —</option>
                {anchorsQ.data?.map((a: any) => (
                  <option key={a.id} value={a.id}>{a.title || a.id.slice(0, 8)} {!a.is_valid && "(失效)"}</option>
                ))}
              </select>
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <div style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 4 }}>关系类型 *</div>
              <select style={inputStyle} value={kindCode} onChange={(e) => setKindCode(e.target.value)} required>
                <option value="">— 选择 —</option>
                {kindsQ.data?.map((k) => <option key={k.code} value={k.code}>{k.name_cn}</option>)}
              </select>
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <div style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 4 }}>依据 *</div>
              <select style={inputStyle} value={basis} onChange={(e) => setBasis(e.target.value)}>
                <option value="author_explicit">原作者明确</option>
                <option value="analyst_inferred">研究者推定</option>
              </select>
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <div style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 4 }}>理由 *</div>
              <textarea style={inputStyle} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} required />
            </label>
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 4 }}>维度</div>
              {dimsQ.data?.map((d) => (
                <label key={d.code} style={{ display: "block", fontSize: 14 }}>
                  <input type="checkbox" checked={dimCodes.includes(d.code)}
                    onChange={(e) => setDimCodes(e.target.checked ? [...dimCodes, d.code] : dimCodes.filter((x) => x !== d.code))} />{" "}
                  {d.name_cn}
                </label>
              ))}
            </div>
            <button disabled={busy || !curIssue || !srcAnchor || !tgtAnchor || !kindCode || !reason.trim()}>
              {busy ? "提交中…" : "创建关系"}
            </button>
            {msg && <p className={msg.startsWith("已创建") ? "ok" : "err"}>{msg}</p>}
          </form>
        </div>

        <div>
          <h3>已有关系（{relsQ.data?.length || 0}）</h3>
          {relsQ.data?.map((r: any) => (
            <div key={r.id} className="card" style={{ borderColor: compareRelId === r.id ? "var(--link)" : undefined }}>
              <p className="hint">
                <code>{r.source_anchor_id.slice(0, 8)}</code> → <code>{r.target_anchor_id.slice(0, 8)}</code>
              </p>
              <p>{r.reason}</p>
              <p>
                <span className="badge basis">{r.basis === "author_explicit" ? "原作者明确" : "研究者推定"}</span>{" "}
                {r.is_verified && <span className="badge valid">已校验</span>}
              </p>
              <div style={{ display: "flex", gap: 12 }}>
                <button className="btn-link" onClick={() => setCompareRelId(compareRelId === r.id ? null : r.id)}>
                  {compareRelId === r.id ? "收起对照" : "全文对照"}
                </button>
                <VerifyToggle kind="relations" id={r.id} verified={r.is_verified}
                  onDone={() => qc.invalidateQueries({ queryKey: ["rels-list", issueId] })} />
              </div>
            </div>
          ))}
          {relsQ.data?.length === 0 && <p className="hint">暂无关系</p>}

          {compareRel && (
            <>
              <h3>全文对照</h3>
              <DualPaneView sourceAnchorId={compareRel.source_anchor_id} targetAnchorId={compareRel.target_anchor_id} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
