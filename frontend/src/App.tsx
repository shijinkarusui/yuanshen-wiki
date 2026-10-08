import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import LoginPage from "./pages/LoginPage";
import ReaderPage from "./pages/ReaderPage";
import EditorPage from "./pages/EditorPage";
import HistoryPage from "./pages/HistoryPage";
import IntakePage from "./pages/IntakePage";
import RelationsPage from "./pages/RelationsPage";
import SearchPage from "./pages/SearchPage";
import FieldsPage from "./pages/FieldsPage";
import SettingsPage from "./pages/SettingsPage";
import CategoriesPage from "./pages/CategoriesPage";
import RequireAuth from "./components/RequireAuth";
import { AuthProvider } from "./components/AuthContext";
import { api } from "./api/client";
import "./styles.css";

const qc = new QueryClient();

function HomeRedirect() {
  const { data, isLoading } = useQuery({
    queryKey: ["issues-first"],
    queryFn: () => api.get("/issues/?limit=1").then((r) => r.items as { id: string }[]),
    retry: false,
  });
  if (isLoading) return <div className="loading">加载中…</div>;
  const first = data?.[0];
  if (!first) return <Navigate to="/browse" replace />;
  return <Navigate to={`/issues/${first.id}`} replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          {/* 读页面：公开 */}
          <Route path="/issues/:issueId" element={<ReaderPage />} />
          <Route path="/browse" element={<CategoriesPage />} />
          <Route path="/search" element={<SearchPage />} />
          {/* 写页面：需登录 */}
          <Route path="/issues/:issueId/edit" element={<RequireAuth><EditorPage /></RequireAuth>} />
          <Route path="/history" element={<RequireAuth><HistoryPage /></RequireAuth>} />
          <Route path="/intake" element={<RequireAuth><IntakePage /></RequireAuth>} />
          <Route path="/relations" element={<RequireAuth><RelationsPage /></RequireAuth>} />
          <Route path="/fields" element={<RequireAuth><FieldsPage /></RequireAuth>} />
          <Route path="/settings" element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path="/" element={<HomeRedirect />} />
        </Routes>
      </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
