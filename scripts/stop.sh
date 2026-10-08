#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# 注意：默认 docker compose down 会保留数据卷，数据不会丢失。
# 警告：不要轻易加 -v（docker compose down -v 会删除数据卷并丢失所有数据），仅在需要彻底重置时使用。
docker compose down

echo "[OK] 服务已停止（数据卷已保留）"
