import { useState } from "react";
import PageHeader from "../components/PageHeader";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

interface ChangeSet {
  id: string;
  sequence_no: number;
  operation: string;
  summary: string;
  effect_direction: string;
  created_at: string;
}

function opLabel(op: string): string {
  const m: Record<string, string> = {
    paragraph_edits: "段落编辑",
    revert: "撤销/重做",
  };
  return m[op] || op;
}

export default function HistoryPage() {
  const [selId, setSelId] = useState<string | null>(null);
  const [revertPreview, setRevertPreview] = useState<any>(null);
  const [revertMsg, setRevertMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const listQ = useQuery({
    queryKey: ["history-list"],
    queryFn: () => api.get("/history/change-sets?limit=50").then((r) => r.items as ChangeSet[]),
  });
  const detailQ = useQuery({
    queryKey: ["history-detail", selId],
    queryFn: () => api.get(`/history/change-sets/${selId}`).then((r) => r.data),
    enabled: !!selId,
  });

  async function doRevertPreview() {
    if (!selId) return;
    setBusy(true);
    setRevertMsg("");
    try {
      const r = await api.post(`/history/change-sets/${selId}/revert-preview`, {});
      setRevertPreview(r.data);
    } catch (e: any) {
      setRevertMsg(e.message || "撤销预览失败");
    } finally {
      setBusy(false);
    }
  }

  async function doRevertCommit() {
    if (!selId || !revertPreview) return;
    setBusy(true);
    setRevertMsg("");
    try {
      const r = await api.post(`/history/change-sets/${selId}/revert`, {
        revert_preview_token: revertPreview.revert_preview_token,
        idempotency_key: crypto.randomUUID(),
      });
      setRevertMsg(
        `成功：${r.data.direction === "inverse" ? "已撤销" : "已重做"}（变更 ${r.data.change_set_id.slice(0, 8)}）`,
      );
      setRevertPreview(null);
      listQ.refetch();
      detailQ.refetch();
    } catch (e: any) {
      // 过期后刷新：409 history_stale → 提示重新预览
      setRevertMsg(e.message || "撤销提交失败");
    } finally {
      setBusy(false);
    }
  }

  const d = detailQ.data;

  return (
      <div className="editor-wrap">
      <PageHeader title="修改历史" subtitle="所有段落编辑的完整记录 · 可预览撤销" />
      {revertMsg && (
        <div className={`alert ${revertMsg.startsWith("成功") ? "ok" : "error"}`}>
          {revertMsg}
        </div>
      )}
      <div className="editor-cols">
        <div>
          <h3>变更列表</h3>
          {listQ.data?.map((cs) => (
            <div
              key={cs.id}
              className="card"
              style={{
                cursor: "pointer",
                borderColor: selId === cs.id ? "var(--link)" : undefined,
              }}
              onClick={() => {
                setSelId(cs.id);
                setRevertPreview(null);
                setRevertMsg("");
              }}
            >
              <p>
                <span className="badge">#{cs.sequence_no}</span>{" "}
                <strong>{opLabel(cs.operation)}</strong>{" "}
                {cs.effect_direction === "inverse" && (
                  <span className="badge warn">撤销</span>
                )}
              </p>
              <p className="hint">{cs.summary}</p>
              <p className="hint">{cs.created_at?.replace("T", " ").slice(0, 19)}</p>
            </div>
          ))}
          {listQ.data?.length === 0 && <p className="hint">暂无历史记录</p>}
        </div>

        <div className="editor-side" style={{ gridColumn: "span 1" }}>
          {!d && <p className="hint">点击左侧变更查看详情</p>}
          {d && (
            <>
              <h3>变更详情 #{d.sequence_no}</h3>
              <p>
                <strong>{opLabel(d.operation)}</strong> · {d.summary}
              </p>
              <p className="hint">
                状态：{d.is_applied ? "已应用" : "已撤销"} · 方向 {d.effect_direction}
              </p>

              <h4>实体变更（{d.items.length}）</h4>
              {d.items.map((it: any) => (
                <div key={it.id} className="card">
                  <p>
                    <code>{it.entity_kind}</code> rev-{it.before_revision} → rev-
                    {it.after_revision}
                  </p>
                  {it.changed_fields?.map((f: string) => (
                    <p key={f} className="hint">
                      {f}
                    </p>
                  ))}
                  {/* 段落差异：显示增删 */}
                  {it.before?.paragraphs && it.after?.paragraphs && (
                    <details>
                      <summary>段落差异</summary>
                      <p className="hint">
                        {it.before.paragraphs.length} → {it.after.paragraphs.length} 段
                      </p>
                    </details>
                  )}
                </div>
              ))}

              {d.paragraph_lineage?.length > 0 && (
                <>
                  <h4>段落命令（{d.paragraph_lineage.length}）</h4>
                  <ol>
                    {d.paragraph_lineage.map((l: any) => (
                      <li key={l.step_index} className="hint">
                        {l.command_type}：{l.source_orders.join(",")} →{" "}
                        {l.target_orders.join(",") || "—"}
                      </li>
                    ))}
                  </ol>
                </>
              )}

              {d.anchor_adjustments?.length > 0 && (
                <>
                  <h4>锚点调整（{d.anchor_adjustments.length}）</h4>
                  {d.anchor_adjustments.map((a: any, i: number) => (
                    <div key={i} className="card">
                      <p className="hint">
                        <code>{a.anchor_id.slice(0, 8)}</code> {a.old_start_order}-
                        {a.old_end_order} →{" "}
                        {a.new_start_order ?? "?"}-{a.new_end_order ?? "?"}
                        {a.content_changed && " · 内容变化"}
                        {a.validity_changed && " · 有效性变化"}
                      </p>
                    </div>
                  ))}
                </>
              )}

              {d.relation_anchor_adjustments?.length > 0 && (
                <>
                  <h4>关系端点时间线</h4>
                  {d.relation_anchor_adjustments.map((a: any, i: number) => (
                    <p key={i} className="hint">
                      锚点 <code>{a.anchor_id.slice(0, 8)}</code> 端点范围变化：
                      {a.old_start_order}-{a.old_end_order} → {a.new_start_order}-
                      {a.new_end_order}
                    </p>
                  ))}
                </>
              )}

              <h4>撤销</h4>
              <button onClick={doRevertPreview} disabled={busy}>
                {busy ? "处理中…" : d.is_applied ? "预览撤销" : "预览重做"}
              </button>
              {revertPreview && (
                <div className="preview-box">
                  <p>
                    方向：{revertPreview.direction === "inverse" ? "撤销" : "重做"}
                  </p>
                  {revertPreview.conflicts.length > 0 ? (
                    <>
                      <p className="alert error">
                        存在冲突，无法撤销：
                      </p>
                      <ul>
                        {revertPreview.conflicts.map((c: any, i: number) => (
                          <li key={i} className="hint">{c.message}</li>
                        ))}
                      </ul>
                    </>
                  ) : (
                    <>
                      <p className="hint">
                        将调整 {revertPreview.new_anchor_mappings.length} 个锚点映射
                        {revertPreview.will_invalidate_anchors.length > 0 &&
                          `，${revertPreview.will_invalidate_anchors.length} 个将失效`}
                      </p>
                      <button onClick={doRevertCommit} disabled={busy}>
                        {busy ? "提交中…" : "确认提交"}
                      </button>
                    </>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
