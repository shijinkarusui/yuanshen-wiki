import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

export default function LoginPage() {
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api.login(name, pw);
      nav("/");
    } catch (e: any) {
      setErr(e.message || "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <div
        className="login-hero"
        style={{ backgroundImage: "url(/assets/hero-sky.webp)" }}
      >
        <div className="login-hero-text">
          <h1>语言神wiki</h1>
          <p>让每一次言语，都如羽般轻盈落定</p>
        </div>
      </div>
      <div className="login-panel">
        <form className="login-box" onSubmit={submit}>
          <img src="/assets/logo-sky.webp" alt="语言神wiki" className="logo-mark" />
          <h1>欢迎回来</h1>
          <p className="subtitle">登录以进入语言神知识图谱</p>
          <label>用户名</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="请输入用户名" autoComplete="username" />
          <label>密码</label>
          <input
            type="password"
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            placeholder="请输入密码"
            autoComplete="current-password"
          />
          <button type="submit" className="primary submit-btn" disabled={busy || !name.trim() || !pw}>
            {busy ? "登录中…" : "登 录"}
          </button>
          <div className="err">{err}</div>
        </form>
      </div>
    </div>
  );
}
