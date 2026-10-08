import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import PageHeader from "../components/PageHeader";
import UserMenu from "../components/UserMenu";
import { useAuth } from "../components/AuthContext";

interface Issue {
  id: string;
  title: string;
  summary?: string;
}

interface CatNode {
  id: string;
  name: string;
  description?: string;
  issues: Issue[];
  children: CatNode[];
}

function TreeNode({ node, depth }: { node: CatNode; depth: number }) {
  const [open, setOpen] = useState(depth < 1);
  const hasKids = node.children.length > 0;
  const hasIssues = node.issues.length > 0;
  const isLeaf = !hasKids && !hasIssues;

  return (
    <div className="tree-node" style={{ marginLeft: depth > 0 ? 18 : 0 }}>
      <div
        className="tree-row"
        onClick={() => !isLeaf && setOpen(!open)}
        style={{ cursor: isLeaf ? "default" : "pointer" }}
      >
        <span className="tree-toggle">{isLeaf ? "·" : open ? "▾" : "▸"}</span>
        <span className="tree-name">{node.name}</span>
        {hasIssues && <span className="badge">{node.issues.length} 词条</span>}
        {node.description && <span className="tree-desc">{node.description}</span>}
      </div>
      {open && (
        <div className="tree-children">
          {hasIssues &&
            node.issues.map((it) => (
              <div key={it.id} className="tree-issue" style={{ marginLeft: 18 }}>
                <Link to={`/issues/${it.id}`}>📄 {it.title}</Link>
                {it.summary && <span className="tree-desc">{it.summary.slice(0, 60)}</span>}
              </div>
            ))}
          {node.children.map((ch) => (
            <TreeNode key={ch.id} node={ch} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function CategoriesPage() {
  const { me } = useAuth();
  const q = useQuery({
    queryKey: ["cat-tree-issues"],
    queryFn: () => api.get("/categories/tree-with-issues").then((r: any) => r),
  });

  const roots: CatNode[] = q.data?.data || [];
  const orphans: Issue[] = q.data?.orphans || [];

  return (
    <div>
      <div className="topbar">
        <Link to="/" className="brand" style={{ textDecoration: "none" }}>
          <img src="/assets/logo-sky.webp" alt="语言神wiki" />
          语言神wiki
        </Link>
        <nav>
          <Link to="/browse" className="btn-link" style={{ fontWeight: 700 }}>总览</Link>
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
      </div>
      <div className="page-wrap">
        <PageHeader title="词条总览" subtitle="按分级分类展开浏览全部词条" />
        {q.isLoading && <p className="hint">加载中…</p>}
        {q.isError && <div className="alert error">加载失败</div>}
        {q.data && (
          <div className="card">
            {roots.map((n) => (
              <TreeNode key={n.id} node={n} depth={0} />
            ))}
            {orphans.length > 0 && (
              <div className="tree-node" style={{ marginTop: 12 }}>
                <div className="tree-row">
                  <span className="tree-toggle">·</span>
                  <span className="tree-name">未分类词条</span>
                  <span className="badge">{orphans.length} 词条</span>
                </div>
                <div className="tree-children">
                  {orphans.map((it) => (
                    <div key={it.id} className="tree-issue" style={{ marginLeft: 18 }}>
                      <Link to={`/issues/${it.id}`}>📄 {it.title}</Link>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {roots.length === 0 && orphans.length === 0 && (
              <p className="hint">暂无分类与词条</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
