import { Navigate } from "react-router-dom";
import { useAuth } from "./AuthContext";

/** 写操作页守卫：未登录跳到 /login。读页面不再使用此组件。 */
export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const { me, loading } = useAuth();
  if (loading) return <div className="loading">加载中…</div>;
  if (!me) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
