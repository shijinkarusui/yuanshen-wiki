import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

interface GraphNode {
  id: string;
  title: string;
  discourse_id: string;
  is_valid: boolean;
  archived: boolean;
  is_verified: boolean;
  range: { start: number | null; end: number | null };
}

interface GraphEdge {
  id: string;
  source_anchor_id: string;
  target_anchor_id: string;
  basis: string;
  reason: string;
  is_verified: boolean;
}

interface Props {
  issueId?: string;
  discourseId?: string;
  /** 点击节点时定位原文 */
  onLocate?: (discourseId: string, anchorId: string) => void;
}

const W = 900;
const H = 560;

export default function GraphView({ issueId, discourseId, onLocate }: Props) {
  const [basisFilter, setBasisFilter] = useState<string>("all");
  const [selEdge, setSelEdge] = useState<string | null>(null);

  const q = useQuery({
    queryKey: ["graph", issueId, discourseId],
    queryFn: () =>
      api
        .get(
          `/graph?${issueId ? `issue_id=${issueId}` : `discourse_id=${discourseId}`}`,
        )
        .then((r) => r.data as {
          nodes: GraphNode[];
          edges: GraphEdge[];
          total_nodes: number;
          total_edges: number;
          truncated: boolean;
        }),
    enabled: !!(issueId || discourseId),
  });

  const layout = useMemo(() => {
    const nodes = q.data?.nodes || [];
    const cx = W / 2;
    const cy = H / 2;
    const R = Math.min(W, H) / 2 - 70;
    const pos = new Map<string, { x: number; y: number }>();
    nodes.forEach((n, i) => {
      const a = (2 * Math.PI * i) / Math.max(nodes.length, 1) - Math.PI / 2;
      pos.set(n.id, { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) });
    });
    return pos;
  }, [q.data]);

  if (q.isLoading) return <p>图谱加载中…</p>;
  if (!q.data) return <p>无图谱数据</p>;
  const { nodes, edges, truncated, total_nodes, total_edges } = q.data;

  const visEdges =
    basisFilter === "all" ? edges : edges.filter((e) => e.basis === basisFilter);
  const nodeIdsInEdges = new Set<string>();
  visEdges.forEach((e) => {
    nodeIdsInEdges.add(e.source_anchor_id);
    nodeIdsInEdges.add(e.target_anchor_id);
  });
  const visNodes =
    basisFilter === "all" ? nodes : nodes.filter((n) => nodeIdsInEdges.has(n.id));

  const selEdgeObj = visEdges.find((e) => e.id === selEdge);

  return (
    <div className="graph-wrap">
      <div className="graph-toolbar">
        <label>
          关系依据：
          <select value={basisFilter} onChange={(e) => setBasisFilter(e.target.value)}>
            <option value="all">全部</option>
            <option value="author_explicit">原作者明确</option>
            <option value="analyst_inferred">研究者推定</option>
          </select>
        </label>
        <span className="hint">
          {visNodes.length}/{total_nodes} 节点 · {visEdges.length}/{total_edges} 边
        </span>
        {truncated && (
          <span className="badge warn">数据超限已截断，请缩小范围或筛选</span>
        )}
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="graph-svg"
        role="img"
        aria-label="论辩关系图谱"
      >
        <defs>
          <marker
            id="arr"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M 0 1 L 9 5 L 0 9" fill="none" stroke="#2458B8" strokeWidth="1.6" />
          </marker>
          <marker
            id="arr-verified"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M 0 1 L 9 5 L 0 9" fill="none" stroke="#277A4B" strokeWidth="1.8" />
          </marker>
        </defs>
        {visEdges.map((e) => {
          const s = layout.get(e.source_anchor_id);
          const t = layout.get(e.target_anchor_id);
          if (!s || !t) return null;
          const sel = selEdge === e.id;
          return (
            <g key={e.id}>
              <line
                x1={s.x}
                y1={s.y}
                x2={t.x}
                y2={t.y}
                stroke={e.is_verified ? "#277A4B" : "#2458B8"}
                strokeWidth={sel ? 3 : 1.4}
                strokeDasharray={e.basis === "analyst_inferred" ? "6 3" : undefined}
                markerEnd={`url(#${e.is_verified ? "arr-verified" : "arr"})`}
                style={{ cursor: "pointer" }}
                onClick={() => setSelEdge(sel ? null : e.id)}
              >
                <title>{e.reason}</title>
              </line>
            </g>
          );
        })}
        {visNodes.map((n) => {
          const p = layout.get(n.id);
          if (!p) return null;
          return (
            <g
              key={n.id}
              transform={`translate(${p.x},${p.y})`}
              style={{ cursor: onLocate ? "pointer" : "default" }}
              onClick={() => onLocate?.(n.discourse_id, n.id)}
            >
              <title>{n.title}</title>
              <circle
                r={n.is_valid ? 26 : 20}
                fill={!n.is_valid ? "#f3e8e8" : n.is_verified ? "#e6f4ea" : "#fff"}
                stroke={!n.is_valid ? "#B42318" : n.archived ? "#9A5B00" : "#1E3A5F"}
                strokeWidth={2}
                strokeDasharray={!n.is_valid || n.archived ? "4 3" : undefined}
              />
              <text textAnchor="middle" dy={-32} fontSize={11} fill="#172033">
                {n.title.length > 10 ? n.title.slice(0, 10) + "…" : n.title}
              </text>
              {!n.is_valid && (
                <text textAnchor="middle" dy={5} fontSize={11} fill="#B42318">
                  失效
                </text>
              )}
              {n.archived && (
                <text textAnchor="middle" dy={5} fontSize={11} fill="#9A5B00">
                  归档
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {selEdgeObj && (
        <div className="card">
          <p>
            <span className="badge basis">
              {selEdgeObj.basis === "author_explicit" ? "原作者明确" : "研究者推定"}
            </span>{" "}
            {selEdgeObj.is_verified && <span className="badge valid">已校验</span>}
          </p>
          <p>{selEdgeObj.reason}</p>
        </div>
      )}

      {/* 键盘可操作的等价关系列表 */}
      <h3>关系列表（键盘可操作）</h3>
      <ul className="graph-list">
        {visEdges.map((e) => {
          const s = visNodes.find((n) => n.id === e.source_anchor_id);
          const t = visNodes.find((n) => n.id === e.target_anchor_id);
          return (
            <li key={e.id}>
              <button className="btn-link" onClick={() => setSelEdge(e.id)}>
                {(s?.title || "?").slice(0, 12)} → {(t?.title || "?").slice(0, 12)}
              </button>{" "}
              <span className="hint">
                {e.basis === "author_explicit" ? "原作者明确" : "研究者推定"}
                {e.is_verified ? " · 已校验" : ""}
              </span>
            </li>
          );
        })}
      </ul>
      {visEdges.length === 0 && <p className="hint">暂无关系</p>}
    </div>
  );
}
