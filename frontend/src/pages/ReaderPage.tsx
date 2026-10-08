import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import GraphView from "../components/GraphView";
import UserMenu from "../components/UserMenu";
import { useAuth } from "../components/AuthContext";

interface Category {
  id: string;
  name: string;
  parent_id: string | null;
  children: Category[];
}

interface Issue {
  id: string;
  title: string;
}

interface Paragraph {
  id: string;
  order: number;
  text: string;
}

interface Discourse {
  id: string;
  title: string;
  paragraphs: Paragraph[];
}

interface Anchor {
  id: string;
  title: string | null;
  start_paragraph_id: string | null;
  end_paragraph_id: string | null;
  is_valid: boolean;
}

interface Relation {
  id: string;
  source_anchor_id: string;
  target_anchor_id: string;
  basis: string;
  reason: string;
}

function flattenCats(cats: Category[], depth = 0): { cat: Category; depth: number }[] {
  const out: { cat: Category; depth: number }[] = [];
  for (const c of cats) {
    out.push({ cat: c, depth });
    out.push(...flattenCats(c.children || [], depth + 1));
  }
  return out;
}

export default function ReaderPage() {
  const { issueId } = useParams();
  const [sp, setSp] = useSearchParams();
  const nav = useNavigate();
  const { me } = useAuth();
  const discourseId = sp.get("discourse");
  const anchorId = sp.get("anchor");
  const view = sp.get("view") === "graph" ? "graph" : "reader";
  const [selAnchor, setSelAnchor] = useState<string | null>(anchorId);

  const catsQ = useQuery({
    queryKey: ["cats"],
    queryFn: () => api.get("/categories/tree").then((r) => r.data as Category[]),
  });
  const issuesQ = useQuery({
    queryKey: ["issues"],
    queryFn: () => api.get("/issues/?limit=100").then((r) => r.items as Issue[]),
  });
  const issueDiscQ = useQuery({
    queryKey: ["issue-disc", issueId],
    queryFn: () =>
      api.get(`/issues/${issueId}/discourses`).then((r) => r.data as { id: string; title: string }[]),
    enabled: !!issueId,
  });
  const discQ = useQuery({
    queryKey: ["discourse", discourseId],
    queryFn: () => api.get(`/discourses/${discourseId}`).then((r) => r.data as Discourse),
    enabled: !!discourseId,
  });
  const anchorsQ = useQuery({
    queryKey: ["anchors", discourseId],
    queryFn: () =>
      api.get(`/anchors/?discourse_id=${discourseId}&limit=100`).then((r) => r.items as Anchor[]),
    enabled: !!discourseId,
  });
  const relsQ = useQuery({
    queryKey: ["relations", issueId],
    queryFn: () =>
      api.get(`/relations/?issue_id=${issueId}&limit=100`).then((r) => r.items as Relation[]),
    enabled: !!issueId,
  });

  useEffect(() => {
    setSelAnchor(anchorId);
  }, [anchorId]);

  const anchorRange = useMemo(() => {
    if (!selAnchor || !anchorsQ.data || !discQ.data) return new Set<string>();
    const a = anchorsQ.data.find((x) => x.id === selAnchor);
    if (!a || !a.is_valid) return new Set<string>();
    const ids = discQ.data.paragraphs.map((p) => p.id);
    const s = ids.indexOf(a.start_paragraph_id || "");
    const e = ids.indexOf(a.end_paragraph_id || "");
    if (s < 0 || e < 0) return new Set<string>();
    return new Set(ids.slice(Math.min(s, e), Math.max(s, e) + 1));
  }, [selAnchor, anchorsQ.data, discQ.data]);

  const activeIssue = issuesQ.data?.[0];
  useEffect(() => {
    if (!issueId && activeIssue) nav(`/issues/${activeIssue.id}`, { replace: true });
  }, [issueId, activeIssue, nav]);

  useEffect(() => {
    if (issueId && !discourseId && issueDiscQ.data?.length) {
      const np = new URLSearchParams(sp);
      np.set("discourse", issueDiscQ.data[0].id);
      setSp(np, { replace: true });
    }
  }, [issueId, discourseId, issueDiscQ.data, sp, setSp]);

  function pickAnchor(id: string) {
    const np = new URLSearchParams(sp);
    if (selAnchor === id) {
      np.delete("anchor");
      setSelAnchor(null);
    } else {
      np.set("anchor", id);
      setSelAnchor(id);
    }
    setSp(np, { replace: true });
  }

  const cats = catsQ.data ? flattenCats(catsQ.data) : [];

  return (
    <div>
      <div className="topbar">
        <Link to="/" className="brand" style={{ textDecoration: "none" }}>
          <img src="/assets/logo-sky.webp" alt="语言神wiki" />
          语言神wiki
        </Link>
        <nav>
          <Link to="/browse" className="btn-link">总览</Link>
          <Link to="/search" className="btn-link">检索</Link>
          {me && (
            <>
              <Link to="/intake" className="btn-link">录入</Link>
              <Link to="/relations" className="btn-link">关系</Link>
              <Link to="/fields" className="btn-link">字段</Link>
              <Link to="/history" className="btn-link">历史</Link>
              <Link to="/settings" className="btn-link">设置</Link>
            </>
          )}
        </nav>
        <UserMenu />
        <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button
            className={view === "reader" ? "tab-active" : ""}
            onClick={() => {
              const np = new URLSearchParams(sp);
              np.set("view", "reader");
              setSp(np, { replace: true });
            }}
          >
            阅读
          </button>
          <button
            className={view === "graph" ? "tab-active" : ""}
            onClick={() => {
              const np = new URLSearchParams(sp);
              np.set("view", "graph");
              setSp(np, { replace: true });
            }}
          >
            图谱
          </button>
        </span>
      </div>
      {view === "graph" ? (
        <div className="pane pane-center" style={{ padding: 16 }}>
          <GraphView
            issueId={issueId}
            onLocate={(dId, aId) => {
              const np = new URLSearchParams(sp);
              np.set("view", "reader");
              np.set("discourse", dId);
              np.set("anchor", aId);
              setSelAnchor(aId);
              setSp(np, { replace: true });
            }}
          />
        </div>
      ) : (
      <div className="app-shell" style={{ height: "calc(100vh - 53px)" }}>
        <div className="pane pane-left">
          <h3>分类</h3>
          {cats.map(({ cat, depth }) => (
            <div
              key={cat.id}
              className={`nav-item ${depth > 0 ? "indent-1" : ""}`}
              style={{ cursor: "default" }}
            >
              {cat.name}
            </div>
          ))}
          <h3 style={{ marginTop: 20 }}>争议问题</h3>
          {issuesQ.data?.map((i) => (
            <a
              key={i.id}
              className={`nav-item ${i.id === issueId ? "active" : ""}`}
              href={`/issues/${i.id}`}
              onClick={(e) => {
                e.preventDefault();
                nav(`/issues/${i.id}`);
              }}
            >
              {i.title}
            </a>
          ))}
          {issueDiscQ.data && issueDiscQ.data.length > 1 && (
            <>
              <h3 style={{ marginTop: 20 }}>本问题论述</h3>
              {issueDiscQ.data.map((d) => (
                <div
                  key={d.id}
                  className={`nav-item ${d.id === discourseId ? "active" : ""}`}
                  onClick={() => {
                    const np = new URLSearchParams(sp);
                    np.set("discourse", d.id);
                    np.delete("anchor");
                    setSelAnchor(null);
                    setSp(np);
                  }}
                >
                  {d.title.slice(0, 18)}…
                </div>
              ))}
            </>
          )}
        </div>

        <div className="pane pane-center">
          {discQ.isLoading && <p>加载中…</p>}
          {discQ.data && (
            <>
              <h2 className="serif" style={{ fontSize: 22 }}>
                {discQ.data.title}
              </h2>
              {me && (
                <div style={{ marginBottom: 12 }}>
                  <Link
                    to={`/issues/${issueId}/edit?discourse=${discourseId}`}
                    className="btn-link"
                  >
                    ✎ 编辑段落
                  </Link>
                </div>
              )}
              <div style={{ marginTop: 16 }}>
                {discQ.data.paragraphs.map((p) => (
                  <p
                    key={p.id}
                    className={`paragraph serif ${
                      anchorRange.has(p.id) ? "anchor-hit" : ""
                    } ${selAnchor && anchorRange.has(p.id) ? "selected" : ""}`}
                  >
                    <span className="pno">{p.order}</span>
                    {p.text}
                  </p>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="pane pane-right">
          <h3>锚点</h3>
          {anchorsQ.data?.map((a) => (
            <div
              key={a.id}
              className="card"
              style={{ cursor: "pointer", borderColor: selAnchor === a.id ? "var(--link)" : undefined }}
              onClick={() => pickAnchor(a.id)}
            >
              <h4>{(a.title || "未命名锚点")}</h4>
              <p>
                <span className={`badge ${a.is_valid ? "valid" : "invalid"}`}>
                  {a.is_valid ? "有效" : "失效"}
                </span>
              </p>
            </div>
          ))}
          <h3 style={{ marginTop: 20 }}>论辩关系</h3>
          {relsQ.data?.map((r) => (
            <div key={r.id} className="card">
              <p>
                <span className="badge basis">
                  {r.basis === "author_explicit" ? "原作者明确" : "研究者推定"}
                </span>
              </p>
              <p style={{ color: "var(--text)" }}>{r.reason}</p>
            </div>
          ))}
          {relsQ.data?.length === 0 && <p style={{ fontSize: 13, color: "var(--ink-mute)" }}>暂无关系</p>}
        </div>
      </div>
      )}
    </div>
  );
}
