#!/usr/bin/env bash
# doctor.sh - 环境预检
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# 1. 检查 docker 命令存在
if command -v docker >/dev/null 2>&1; then
  echo "[OK] docker 命令存在: $(command -v docker)"
else
  echo "[FAIL] 未找到 docker 命令，请先安装 Docker"
  exit 1
fi

# 2. 检查 docker compose version >= 2.24
if ! docker compose version >/dev/null 2>&1; then
  echo "[FAIL] docker compose 不可用，请安装 Compose v2 插件"
  exit 1
fi
COMPOSE_RAW="$(docker compose version --short 2>/dev/null || docker compose version 2>/dev/null)"
COMPOSE_VER="$(echo "$COMPOSE_RAW" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)"
if [ -z "$COMPOSE_VER" ]; then
  echo "[FAIL] 无法解析 docker compose 版本: $COMPOSE_RAW"
  exit 1
fi
MAJOR="$(echo "$COMPOSE_VER" | cut -d. -f1)"
MINOR="$(echo "$COMPOSE_VER" | cut -d. -f2)"
if [ "$MAJOR" -gt 2 ] || { [ "$MAJOR" -eq 2 ] && [ "$MINOR" -ge 24 ]; }; then
  echo "[OK] docker compose 版本 $COMPOSE_VER 符合要求 (>= 2.24)"
else
  echo "[FAIL] docker compose 版本 $COMPOSE_VER 过低，需要 >= 2.24"
  exit 1
fi

# 3. 检查 8080 端口未被占用
if command -v ss >/dev/null 2>&1; then
  if ss -ltn 2>/dev/null | grep -q ':8080'; then
    echo "[FAIL] 8080 端口已被占用，请释放后再启动"
    exit 1
  else
    echo "[OK] 8080 端口未被占用"
  fi
elif command -v netstat >/dev/null 2>&1; then
  if netstat -ltn 2>/dev/null | grep -q ':8080'; then
    echo "[FAIL] 8080 端口已被占用，请释放后再启动"
    exit 1
  else
    echo "[OK] 8080 端口未被占用"
  fi
else
  echo "[FAIL] 未找到 ss 或 netstat，无法检查端口，请安装 iproute2 或 net-tools"
  exit 1
fi

# 4. 检查 .env 存在
if [ -f ".env" ]; then
  echo "[OK] .env 文件存在"
else
  echo "[FAIL] .env 文件不存在，请执行: cp .env.example .env 并修改密码"
  exit 1
fi

echo "[OK] 环境检查全部通过"
