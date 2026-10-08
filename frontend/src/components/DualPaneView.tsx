import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

interface Props {
  sourceAnchorId: string;
  targetAnchorId: string;
}

/** 关系两端全文对照：左右两栏显示锚点所在段落全文，锚点范围高亮。 */
export default function DualPaneView({ sourceAnchorId, targetAnchorId }: Props) {
  const srcQ = useQuery({
    queryKey: ["anchor-detail", sourceAnchorId],
    queryFn: () => api.get(`/anchors/${sourceAnchorId}`).then((r) => r.data),
    enabled: !!sourceAnchorId,
  });
  const tgtQ = useQuery({
    queryKey: ["anchor-detail", targetAnchorId],
    queryFn: () => api.get(`/anchors/${targetAnchorId}`).then((r) => r.data),
    enabled: !!targetAnchorId,
  });

  if (!sourceAnchorId || !targetAnchorId) return null;
  if (srcQ.isLoading || tgtQ.isLoading) return <p>加载中…</p>;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 12 }}>
      <Pane title="A 端（源锚点）" anchor={srcQ.data} />
      <Pane title="B 端（目标锚点）" anchor={tgtQ.data} />
    </div>
  );
}

function Pane({ title, anchor }: { title: string; anchor: any }) {
  const discQ = useQuery({
    queryKey: ["discourse", anchor?.discourse_id],
    queryFn: () => api.get(`/discourses/${anchor.discourse_id}`).then((r) => r.data),
    enabled: !!anchor?.discourse_id,
  });
  if (!anchor) return <div><h4>{title}</h4><p className="hint">未选择</p></div>;
  const paras = discQ.data?.paragraphs || [];

  // 锚点范围内的段落 ID 集合
  const ids = paras.map((p: any) => p.id);
  const s = ids.indexOf(anchor.start_paragraph_id);
  const e = ids.indexOf(anchor.end_paragraph_id);
  const inRange = new Set<string>();
  if (s >= 0 && e >= 0) {
    ids.slice(Math.min(s, e), Math.max(s, e) + 1).forEach((id: string) => inRange.add(id));
  }

  return (
    <div className="card" style={{ maxHeight: 480, overflowY: "auto" }}>
      <h4>{title}：{anchor.title || "未命名"}</h4>
      {!anchor.is_valid && <p><span className="badge invalid">锚点已失效</span></p>}
      {paras.map((p: any) => (
        <p key={p.id} className={`paragraph serif ${inRange.has(p.id) ? "anchor-hit" : ""}`}
          style={{ fontSize: 14 }}>
          <span className="pno">{p.order}</span>{p.text}
        </p>
      ))}
    </div>
  );
}
