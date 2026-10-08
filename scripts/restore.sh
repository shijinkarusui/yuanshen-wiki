#!/bin/bash
# M09B: PostgreSQL 恢复到新建空数据库
set -e
DUMP_FILE="$1"
TARGET_DB="${2:-lingdebate_restored}"

if [ -z "$DUMP_FILE" ]; then
  echo "用法: $0 <dump文件> [目标库名]"
  exit 1
fi

export PGPASSWORD=lingdebate
echo "创建空数据库 $TARGET_DB ..."
su postgres -c "psql -c 'DROP DATABASE IF EXISTS $TARGET_DB;'" >/dev/null 2>&1
su postgres -c "psql -c 'CREATE DATABASE $TARGET_DB OWNER lingdebate;'" >/dev/null 2>&1

echo "恢复 $DUMP_FILE 到 $TARGET_DB ..."
pg_restore -h localhost -U lingdebate -d "$TARGET_DB" --no-owner --no-privileges "$DUMP_FILE"

echo "恢复完成"
