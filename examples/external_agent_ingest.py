#!/usr/bin/env python3
"""M09A: 外部 Agent 示例。仅使用 HTTP API，从环境变量读取 token。"""
import os
import sys
import uuid
import httpx

BASE = os.getenv("LDW_BASE_URL", "http://127.0.0.1:8000/api/v1")
TOKEN = os.getenv("LDW_TOKEN", "")

def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=30, trust_env=False)
    if TOKEN:
        c.headers["Authorization"] = f"Bearer {TOKEN}"
        print("使用 Agent token 认证")
    else:
        r = c.post("/auth/session", json={"display_name": "demo-owner", "password": "demo1234"})
        r.raise_for_status()
        print("使用 demo 账号登录（演示版虚构数据）")
    r = c.get("/search", params={"q": "处置", "limit": 5})
    r.raise_for_status()
    hits = r.json()
    print(f"\n1. 搜索'处置': {hits['total']} 条")
    for h in hits["items"][:3]:
        print(f"   [{h['type_label']}] {h['title'][:40]}")
    issue = c.get("/issues/", params={"limit": 1}).json()["items"][0]["id"]
    discs = c.get(f"/issues/{issue}/discourses").json()["data"]
    d = c.get(f"/discourses/{discs[0]['id']}").json()["data"]
    print(f"\n2. 论述: {d['title'][:30]} rev-{d['revision']}")
    paras = d["paragraphs"]
    cmds = [{"command": "update_text", "paragraph_id": paras[0]["id"],
             "text": paras[0]["text"] + "【agent校订】"}]
    r = c.post(f"/discourses/{d['id']}/paragraph-edits/preview",
        headers={"If-Match": f'"rev-{d["revision"]}"'},
        json={"base_paragraph_revision": d["paragraph_revision"], "commands": cmds})
    r.raise_for_status()
    pv = r.json()["data"]
    print(f"\n3. 预览: 指纹 {pv['preview_fingerprint'][:12]}...")
    key = str(uuid.uuid4())
    r = c.post(f"/discourses/{d['id']}/paragraph-edits",
        headers={"If-Match": f'"rev-{d["revision"]}"', "Idempotency-Key": key},
        json={"base_paragraph_revision": d["paragraph_revision"], "commands": cmds,
              "preview_fingerprint": pv["preview_fingerprint"]})
    r.raise_for_status()
    cs_id = r.json()["data"]["change_set_id"]
    print(f"   提交: change_set {cs_id[:8]}")
    r = c.post(f"/discourses/{d['id']}/paragraph-edits",
        headers={"If-Match": f'"rev-{d["revision"]}"', "Idempotency-Key": key},
        json={"base_paragraph_revision": d["paragraph_revision"], "commands": cmds,
              "preview_fingerprint": pv["preview_fingerprint"]})
    assert r.json()["data"]["change_set_id"] == cs_id
    print("   幂等重放: 返回同一 change_set ✓")
    r = c.get("/history/change-sets", params={"limit": 3})
    r.raise_for_status()
    h = r.json()
    print(f"\n4. 历史: 共 {h['total']} 条")
    print("\n演示完成（虚构数据）")
    return 0

if __name__ == "__main__":
    sys.exit(main())
