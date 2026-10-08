import { useState } from "react";
import PageHeader from "../components/PageHeader";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "8px 10px", fontSize: 14,
  border: "1px solid var(--border)", borderRadius: 6, boxSizing: "border-box",
};

const TYPES = ["text", "long_text", "number", "boolean", "single_select", "multi_select"];
const TYPE_CN: Record<string, string> = {
  text: "短文本", long_text: "长文本", number: "数字",
  boolean: "布尔", single_select: "单选", multi_select: "多选",
};

export default function FieldsPage() {
  const qc = useQueryClient();
  const [key, setKey] = useState("");
  const [label, setLabel] = useState("");
  const [entityKind, setEntityKind] = useState("discourse");
  const [valueType, setValueType] = useState("text");
  const [options, setOptions] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const listQ = useQuery({
    queryKey: ["field-defs"],
    queryFn: () => api.get("/field-definitions/?include_archived=true").then((r) => r.items as any[]),
  });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg("");
    try {
      await api.post("/field-definitions/", {
        key: key.trim(), label: label.trim(), entity_kind: entityKind,
        value_type: valueType,
        options: ["single_select", "multi_select"].includes(valueType)
          ? options.split(/[,，]/).map((s) => s.trim()).filter(Boolean) : [],
      });
      setMsg("已创建字段定义");
      setKey(""); setLabel(""); setOptions("");
      qc.invalidateQueries({ queryKey: ["field-defs"] });
    } catch (e: any) { setMsg(e.message || "创建失败"); }
    finally { setBusy(false); }
  }

  async function archive(id: string, archived: boolean) {
    try {
      await api.post(`/field-definitions/${id}/${archived ? "restore" : "archive"}`, {});
      qc.invalidateQueries({ queryKey: ["field-defs"] });
    } catch (e: any) { alert(e.message); }
  }

  return (
      <div className="editor-wrap">
      <PageHeader title="自定义字段" subtitle="仅 owner 可管理 · 字段值存于实体的 attributes" />
      <div className="editor-cols">
        <div>
          <h3>新建字段定义</h3>
          <form onSubmit={submit}>
            <label style={{ display: "block", marginBottom: 12 }}>
              <div style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 4 }}>key（小写字母/数字/下划线，不可改）*</div>
              <input style={inputStyle} value={key} onChange={(e) => setKey(e.target.value)} required pattern="[a-z][a-z0-9_]*" />
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <div style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 4 }}>显示名 *</div>
              <input style={inputStyle} value={label} onChange={(e) => setLabel(e.target.value)} required />
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <div style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 4 }}>实体类型 *</div>
              <select style={inputStyle} value={entityKind} onChange={(e) => setEntityKind(e.target.value)}>
                <option value="discourse">论述</option>
                <option value="anchor">锚点</option>
                <option value="relation">关系</option>
                <option value="person">人物</option>
                <option value="bibliographic_record">文献</option>
                <option value="issue">争议问题</option>
              </select>
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <div style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 4 }}>值类型 *</div>
              <select style={inputStyle} value={valueType} onChange={(e) => setValueType(e.target.value)}>
                {TYPES.map((t) => <option key={t} value={t}>{TYPE_CN[t]}</option>)}
              </select>
            </label>
            {["single_select", "multi_select"].includes(valueType) && (
              <label style={{ display: "block", marginBottom: 12 }}>
                <div style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 4 }}>选项（逗号分隔）*</div>
                <input style={inputStyle} value={options} onChange={(e) => setOptions(e.target.value)} required />
              </label>
            )}
            <button disabled={busy || !key.trim() || !label.trim()}>{busy ? "提交中…" : "创建"}</button>
            {msg && <p className={msg.startsWith("已创建") ? "ok" : "err"}>{msg}</p>}
          </form>
        </div>
        <div>
          <h3>已有定义（{listQ.data?.length || 0}）</h3>
          {listQ.data?.map((d: any) => (
            <div key={d.id} className="card" style={{ opacity: d.archived ? 0.6 : 1 }}>
              <p><code>{d.key}</code> <strong>{d.label}</strong>{" "}
                <span className="badge">{d.entity_kind}</span>{" "}
                <span className="badge">{TYPE_CN[d.value_type] || d.value_type}</span>
                {d.archived && <span className="badge warn">已归档</span>}
                {d.is_system && <span className="badge">系统</span>}
              </p>
              {d.options?.length > 0 && <p className="hint">选项：{d.options.join(" / ")}</p>}
              {!d.is_system && (
                <button className="btn-link" onClick={() => archive(d.id, d.archived)}>
                  {d.archived ? "恢复" : "归档"}
                </button>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
