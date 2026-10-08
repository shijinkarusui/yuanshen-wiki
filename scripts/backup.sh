#!/bin/bash
# M09B: PostgreSQL 备份（custom format + manifest + SHA-256）
set -e
BACKUP_DIR="${1:-$HOME/workspace/lingdebate-wiki/backups}"
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
DUMP_FILE="$BACKUP_DIR/lingdebate-$TIMESTAMP.dump"
MANIFEST="$BACKUP_DIR/lingdebate-$TIMESTAMP.manifest.json"

mkdir -p "$BACKUP_DIR"
echo "备份到 $DUMP_FILE ..."

# 先做一次写操作，确保有数据
export PGPASSWORD=lingdebate
pg_dump -h localhost -U lingdebate -Fc --no-owner --no-privileges \
  -f "$DUMP_FILE" lingdebate

DUMP_SHA=$(sha256sum "$DUMP_FILE" | awk '{print $1}')
ALEMBIC_HEAD=$(cd ~/workspace/lingdebate-wiki/backend && ../.venv/bin/alembic heads 2>/dev/null | head -1 | awk '{print $1}')
PG_MAJOR=$(psql -h localhost -U lingdebate -tAc "SHOW server_version_num;" lingdebate | cut -c1-2)

# 记录计数
COUNTS=$(psql -h localhost -U lingdebate -tAc "
SELECT json_build_object(
  'issues', (SELECT count(*) FROM issues WHERE archived_at IS NULL),
  'discourses', (SELECT count(*) FROM discourses WHERE archived_at IS NULL),
  'paragraphs', (SELECT count(*) FROM paragraphs WHERE archived_at IS NULL),
  'anchors', (SELECT count(*) FROM anchors WHERE archived_at IS NULL),
  'relations', (SELECT count(*) FROM relations WHERE archived_at IS NULL),
  'change_sets', (SELECT count(*) FROM change_sets)
);" lingdebate)

cat > "$MANIFEST" <<EOF
{
  "app_version": "mvp-20261007",
  "alembic_head": "$ALEMBIC_HEAD",
  "postgresql_major": "$PG_MAJOR",
  "created_utc": "$TIMESTAMP",
  "counts": $COUNTS,
  "dump_sha256": "$DUMP_SHA",
  "dump_file": "$(basename $DUMP_FILE)"
}
EOF

echo "备份完成：$DUMP_FILE"
echo "SHA-256: $DUMP_SHA"
