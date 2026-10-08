#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# 如无 .env 则从 .env.example 复制
if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    cp .env.example .env
    echo "已从 .env.example 创建 .env，请务必修改其中的密码后再使用！"
    echo "提示：请编辑 .env 文件修改默认密码。"
  else
    echo "[FAIL] 未找到 .env，且 .env.example 也不存在"
    exit 1
  fi
fi

echo "正在启动服务..."
docker compose up --build -d

echo "等待 API healthy (http://127.0.0.1:8080/api/v1/ops/live)，最多 120 秒..."
for i in $(seq 1 120); do
  if curl -fsS http://127.0.0.1:8080/api/v1/ops/live >/dev/null 2>&1; then
    echo "[OK] API 已就绪"
    echo "访问地址 http://127.0.0.1:8080"
    exit 0
  fi
  sleep 1
  if [ $((i % 10)) -eq 0 ]; then
    echo "等待中... ${i}s"
  fi
done

echo "[FAIL] 等待 API 超时（120s），请查看日志：docker compose logs"
exit 1
