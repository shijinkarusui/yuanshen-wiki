#!/usr/bin/env python3
"""Extract files from the model relay's output.

Protocol: the model wraps each file as

    ### FILE: relative/path/to/file
    ```lang
    ...content...
    ```

Any text outside file blocks is ignored (printed as notes).
Writes files under the project root, creating directories as needed.
Refuses absolute paths and '..' escapes.

Usage:
    python3 tools/api_call.py < task1.txt | python3 tools/extract_files.py
    python3 tools/extract_files.py < response.txt
"""
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FILE_RE = re.compile(r"^### FILE:\s*(.+?)\s*$")
FENCE_RE = re.compile(r"^```(\w*)\s*$")


def main():
    text = sys.stdin.read()
    lines = text.splitlines()
    i, n = 0, len(lines)
    written = []
    notes = []
    while i < n:
        m = FILE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        rel = m.group(1).strip().replace("\\", "/")
        i += 1
        # expect opening fence
        if i < n and FENCE_RE.match(lines[i]):
            i += 1
        buf = []
        while i < n and not lines[i].startswith("```"):
            buf.append(lines[i])
            i += 1
        if i < n and lines[i].startswith("```"):
            i += 1  # consume closing fence
        # safety: no absolute paths, no escapes
        if os.path.isabs(rel) or ".." in rel.split("/"):
            notes.append(f"SKIPPED unsafe path: {rel}")
            continue
        dest = os.path.join(PROJECT_ROOT, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write("\n".join(buf) + ("\n" if buf else ""))
        written.append(rel)
    print(f"wrote {len(written)} files:")
    for w in written:
        print("  " + w)
    for note_text in notes:
        print("NOTE: " + note_text, file=sys.stderr)


if __name__ == "__main__":
    main()
