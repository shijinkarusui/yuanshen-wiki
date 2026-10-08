#!/usr/bin/env bash
# recover-native.sh — VM 重置后一键恢复 wiki 本机服务（PostgreSQL 内嵌 + 后端 :8000 + 前端 :5173）
# 背景：VM 重置会清空 /tmp（数据库）和所有 apt 安装的包；本脚本用 pgserver 内嵌 PG16 重建。
# 数据目录在仓库内 .pgdata（持久化）：重置后直接启动已有数据库，不再丢数据；
# 只有数据目录为空时才 initdb 并从备份恢复。
# 用法：sudo bash scripts/recover-native.sh
# 幂等：可重复执行；已有数据时直接启动，跳过建库与恢复备份。
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv"
PGBIN="$VENV/lib/python3.12/site-packages/pgserver/pginstall"
export PATH="$PGBIN/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export LD_LIBRARY_PATH="$PGBIN/lib"
# 数据目录放在仓库内（持久化）：VM 重置后数据仍在，不再随 /tmp 丢失
PGDATA="$ROOT/.pgdata"
DUMP="$(ls -t "$ROOT/backups"/*.dump 2>/dev/null | head -1)"

[ -d "$PGBIN/bin" ] || { echo "[FAIL] pgserver 未安装：先在 venv 里 pip install pgserver"; exit 1; }
[ -n "$DUMP" ] || { echo "[FAIL] backups/ 下没有 .dump 备份"; exit 1; }
echo "[INFO] 使用备份：$DUMP"

# 1. pguser（initdb/postgres 拒绝 root 运行）
id pguser >/dev/null 2>&1 || useradd -m -s /bin/bash pguser
usermod -aG nogroup pguser 2>/dev/null || true
chmod o+x /home/hatch /home/hatch/workspace /home/hatch/workspace/lingdebate-wiki "$VENV" 2>/dev/null || true
chmod -R a+rX "$VENV" "$ROOT/backups"

# 2. 停掉可能残留的旧进程
pkill -f 'uvicorn app.main:app' 2>/dev/null || true
su pguser -c "$PGBIN/bin/pg_ctl -D $PGDATA stop -m fast" >/dev/null 2>&1 || true

# 3. 初始化并启动 PostgreSQL（PGDATA 持久化：只有数据目录为空时才 initdb，
#    已有数据则直接启动，保留用户录入的内容；本次为重置后首次运行，会重建空库）
mkdir -p "$PGDATA" && chown pguser:pguser "$PGDATA"
FIRST_INIT=0
if [ ! -f "$PGDATA/PG_VERSION" ]; then
  FIRST_INIT=1
  rm -rf "$PGDATA" && mkdir -p "$PGDATA" && chown pguser:pguser "$PGDATA"
  su pguser -c "env LD_LIBRARY_PATH=$PGBIN/lib PATH=$PGBIN/bin:/usr/bin:/bin $PGBIN/bin/initdb -D $PGDATA -U postgres --auth=trust" >/tmp/initdb.log 2>&1
fi
su pguser -c "env LD_LIBRARY_PATH=$PGBIN/lib PATH=$PGBIN/bin:/usr/bin:/bin $PGBIN/bin/pg_ctl -D $PGDATA -l /tmp/pg.log -o '-p 5432' start"
su pguser -c "env LD_LIBRARY_PATH=$PGBIN/lib PATH=$PGBIN/bin:/usr/bin:/bin $PGBIN/bin/pg_isready -h localhost -p 5432"

# 4-5. 仅首次初始化时建角色/库并恢复备份；已有数据则跳过，避免覆盖用户数据
if [ "$FIRST_INIT" = "1" ]; then
# 4. 建角色与库（与 backend 默认配置一致：lingdebate 用户、lingdebate 库、5432 端口）
su pguser -c "env LD_LIBRARY_PATH=$PGBIN/lib PATH=$PGBIN/bin:/usr/bin:/bin $PGBIN/bin/psql -h localhost -U postgres -c \"DROP DATABASE IF EXISTS lingdebate;\""
su pguser -c "env LD_LIBRARY_PATH=$PGBIN/lib PATH=$PGBIN/bin:/usr/bin:/bin $PGBIN/bin/psql -h localhost -U postgres -c \"DROP ROLE IF EXISTS lingdebate;\""
su pguser -c "env LD_LIBRARY_PATH=$PGBIN/lib PATH=$PGBIN/bin:/usr/bin:/bin $PGBIN/bin/psql -h localhost -U postgres -c \"CREATE ROLE lingdebate LOGIN PASSWORD 'lingdebate';\""
su pguser -c "env LD_LIBRARY_PATH=$PGBIN/lib PATH=$PGBIN/bin:/usr/bin:/bin $PGBIN/bin/psql -h localhost -U postgres -c 'CREATE DATABASE lingdebate OWNER lingdebate;'"

# 5. 恢复备份（pg_trgm 缺失的报错为预期，可忽略）
su pguser -c "env LD_LIBRARY_PATH=$PGBIN/lib PATH=$PGBIN/bin:/usr/bin:/bin PGPASSWORD=lingdebate $PGBIN/bin/pg_restore -h localhost -U lingdebate -d lingdebate --no-owner --no-privileges '$DUMP'" 2>&1 | grep -v 'pg_trgm' || true
else
echo "[INFO] 检测到已有数据库，直接启动，跳过建库与恢复备份"
fi

# 6. 启动后端（:8000，同时 serve API 与前端生产构建）与前端 dev（:5173）
export DATABASE_URL='postgresql+psycopg://lingdebate:lingdebate@localhost:5432/lingdebate'
# npx 位于 /opt/hatch-image/bin，不在 sudo 受限 PATH 中，显式补上
export PATH="/opt/hatch-image/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
cd "$ROOT/backend"
nohup "$VENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000 >/tmp/uvicorn.log 2>&1 &
cd "$ROOT/frontend"
nohup npx vite --host 127.0.0.1 --port 5173 >/tmp/vite.log 2>&1 &

# 7. 健康检查
for i in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8000/api/v1/ops/ready >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS http://127.0.0.1:8000/api/v1/ops/ready && echo && echo "[OK] 恢复完成：http://127.0.0.1:8000"
