import { useState } from "react";
import PageHeader from "../components/PageHeader";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "8px 10px", fontSize: 14,
  border: "1px solid var(--border)", borderRadius: 6, boxSizing: "border-box",
};

export default function SettingsPage() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [newToken, setNewToken] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const tokensQ = useQuery({
    queryKey: ["tokens"],
    queryFn: () => api.get("/auth/tokens").then((r) => r as any[]),
  });

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(""); setNewToken("");
    try {
      const r = await api.post("/auth/tokens", { display_name: name.trim() });
      setNewToken(r.token_plaintext);
      setMsg("已创建 token，请立即复制保存（只显示一次）");
      setName("");
      qc.invalidateQueries({ queryKey: ["tokens"] });
    } catch (e: any) { setMsg(e.message || "创建失败"); }
    finally { setBusy(false); }
  }

  async function revoke(id: string) {
    if (!confirm("确定撤销该 token？")) return;
    try {
      await api.post(`/auth/tokens/${id}/revoke`, {});
      qc.invalidateQueries({ queryKey: ["tokens"] });
    } catch (e: any) { alert(e.message); }
  }

  return (
      <div className="editor-wrap">
      <PageHeader title="设置" subtitle="仅 owner 可见" />

      <h3>Agent Token</h3>
      <p className="hint">Agent token 用于程序化访问 API。Agent 无法管理 token、无法校验、无法管理字段定义（服务端强制）。</p>

      <form onSubmit={create} style={{ display: "flex", gap: 8, marginBottom: 16, maxWidth: 500 }}>
        <input style={{ ...inputStyle, flex: 1 }} value={name}
          onChange={(e) => setName(e.target.value)} placeholder="Agent 名称" required />
        <button disabled={busy || !name.trim()}>{busy ? "创建中…" : "创建 Token"}</button>
      </form>
      {msg && <p className={newToken ? "ok" : "err"}>{msg}</p>}
      {newToken && (
        <div className="card" style={{ maxWidth: 600, marginBottom: 16 }}>
          <p><strong>新 Token（只显示一次）：</strong></p>
          <code style={{ wordBreak: "break-all", fontSize: 13 }}>{newToken}</code>
        </div>
      )}

      <h4>已有 Token（{tokensQ.data?.length || 0}）</h4>
      {tokensQ.data?.map((t: any) => (
        <div key={t.id} className="card" style={{ opacity: t.revoked_at ? 0.6 : 1 }}>
          <p><strong>{t.display_name}</strong> <code>{t.public_id}</code>{" "}
            {t.revoked_at ? <span className="badge warn">已撤销</span> : <span className="badge valid">有效</span>}
          </p>
          <p className="hint">创建：{t.created_at?.slice(0, 19).replace("T", " ")}
            {t.last_used_at && ` · 上次使用：${t.last_used_at.slice(0, 19).replace("T", " ")}`}</p>
          {!t.revoked_at && (
            <button className="btn-link" onClick={() => revoke(t.id)}>撤销</button>
          )}
        </div>
      ))}
    </div>
  );
}
