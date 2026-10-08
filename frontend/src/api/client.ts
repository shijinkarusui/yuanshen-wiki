const BASE = "/api/v1";

async function request(path: string, init: RequestInit = {}) {
  const res = await fetch(BASE + path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let body: any = null;
    try {
      body = await res.json();
    } catch {
      /* ignore */
    }
    const code = body?.error?.code || `http_${res.status}`;
    throw new Error(code + (body?.error?.message ? `: ${body.error.message}` : ""));
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  get: (path: string) => request(path),
  post: (path: string, body: any) =>
    request(path, { method: "POST", body: JSON.stringify(body) }),
  patch: (path: string, body: any) =>
    request(path, { method: "PATCH", body: JSON.stringify(body) }),
  del: (path: string) => request(path, { method: "DELETE" }),
  login: (display_name: string, password: string) =>
    request("/auth/session", {
      method: "POST",
      body: JSON.stringify({ display_name, password }),
    }),
  me: () => request("/auth/me"),
  previewParagraphEdits: (discourseId: string, baseParaRev: number, commands: any[], ifMatch: string) =>
    request(`/discourses/${discourseId}/paragraph-edits/preview`, {
      method: "POST",
      headers: { "If-Match": ifMatch },
      body: JSON.stringify({ base_paragraph_revision: baseParaRev, commands }),
    }),
  commitParagraphEdits: (
    discourseId: string,
    baseParaRev: number,
    commands: any[],
    fingerprint: string,
    ifMatch: string,
    idempotencyKey: string,
  ) =>
    request(`/discourses/${discourseId}/paragraph-edits`, {
      method: "POST",
      headers: { "If-Match": ifMatch, "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        base_paragraph_revision: baseParaRev,
        commands,
        preview_fingerprint: fingerprint,
      }),
    }),
};
