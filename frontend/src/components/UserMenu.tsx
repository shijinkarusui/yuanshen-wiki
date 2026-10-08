import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "./AuthContext";
import { api } from "../api/client";

/** 顶栏右侧用户区：未登录显示登录按钮，已登录显示用户名+退出 */
export default function UserMenu() {
  const { me, loading } = useAuth();
  const nav = useNavigate();
  const qc = useQueryClient();

  async function logout() {
    try { await api.del("/auth/session"); } catch { /* ignore */ }
    qc.invalidateQueries({ queryKey: ["me"] });
    nav("/");
  }

  if (loading) return null;
  if (!me) {
    return (
      <Link to="/login" className="btn-link" style={{ fontWeight: 700, color: "var(--sky-600)" }}>
        登录
      </Link>
    );
  }
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: "auto" }}>
      <span style={{ fontSize: 13, color: "var(--ink-mute)" }}>{me.display_name}</span>
      <button onClick={logout} style={{ padding: "6px 16px", fontSize: 13 }}>退出</button>
    </span>
  );
}
