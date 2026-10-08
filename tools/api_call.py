#!/usr/bin/env python3
"""Call the user's model relay (muse-spark-1.3) with streaming.

Relay quirks (verified 2026-10-07):
- stream=true REQUIRED: non-streaming mode drops/corrupts content.
- max_tokens small (e.g. 60) returns empty content; use 100000.
- Key is passed via OCTO_KEY env var, never stored in files.

Usage:
    export OCTO_KEY='<key>'
    python3 tools/api_call.py < prompt.txt > out.txt
    python3 tools/api_call.py --system sys.txt < prompt.txt > out.txt
"""
import json
import os
import sys
import urllib.request

API_URL = "http://124.222.137.213:2113/v1/chat/completions"
MODEL = "OC/muse-spark-1.3-contributor-free"
KEY = os.environ.get("OCTO_KEY", "")
DEFAULT_MAX_TOKENS = 100000


def call(prompt, system=None, max_tokens=DEFAULT_MAX_TOKENS, timeout=900):
    if not KEY:
        raise RuntimeError("OCTO_KEY env var not set")
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    body = json.dumps({
        "model": MODEL,
        "max_tokens": max_tokens,
        "stream": True,
        "messages": msgs,
    }).encode()
    req = urllib.request.Request(
        API_URL, data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    parts = []
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                p = json.loads(payload)
            except json.JSONDecodeError:
                continue
            for c in p.get("choices", []):
                d = c.get("delta", {}).get("content")
                if d:
                    parts.append(d)
    return "".join(parts)


def main():
    system = None
    args = sys.argv[1:]
    if args[:1] == ["--system"] and len(args) >= 2:
        with open(args[1], encoding="utf-8") as f:
            system = f.read()
    prompt = sys.stdin.read()
    sys.stdout.write(call(prompt, system=system))


if __name__ == "__main__":
    main()
