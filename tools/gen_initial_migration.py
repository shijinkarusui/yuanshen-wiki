#!/usr/bin/env python3
"""Generate the initial Alembic migration from Base.metadata DDL.

No live database needed: compiles CREATE TABLE / CREATE INDEX with the
PostgreSQL dialect and emits them via op.execute().
Run from backend/:  ../.venv/bin/python ../tools/gen_initial_migration.py
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from alembic.config import Config  # noqa: F401  (ensures alembic importable)
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

import app.features.identity.models  # noqa: F401
import app.features.history_write.models  # noqa: F401
import app.features.taxonomy.models  # noqa: F401
import app.features.custom_fields.models  # noqa: F401
import app.features.bibliography.models  # noqa: F401
import app.features.discourses.models  # noqa: F401
import app.features.relations.models  # noqa: F401
from app.db.base import Base

REVISION = uuid.uuid4().hex[:12]

dialect = postgresql.dialect()
stmts = []
stmts.append("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
stmts.append("CREATE SEQUENCE IF NOT EXISTS change_set_seq;")
for table in Base.metadata.sorted_tables:
    ddl = str(CreateTable(table).compile(dialect=dialect)).strip()
    stmts.append(ddl + ";")
    for index in table.indexes:
        # indexes already inlined? CreateTable does NOT emit standalone Index;
        # emit them explicitly, skipping ones already covered is unnecessary
        # as PG would error on duplicates -- but table.indexes ARE included in
        # CreateTable output? No: only indexes defined inside the Table
        # construct are inlined; Index() objects in __table_args__ are separate.
        idx_ddl = str(CreateIndex(index).compile(dialect=dialect)).strip()
        stmts.append(idx_ddl + ";")
stmts.append(
    "ALTER TABLE change_sets ALTER COLUMN sequence_no "
    "SET DEFAULT nextval('change_set_seq');"
)

drop_stmts = []
for table in reversed(Base.metadata.sorted_tables):
    drop_stmts.append(f'DROP TABLE IF EXISTS "{table.name}" CASCADE;')
drop_stmts.append("DROP SEQUENCE IF EXISTS change_set_seq;")

def q(s):
    return '"""' + s.replace('\\', '\\\\') + '"""'

upgrade_body = "\n".join(f"    op.execute({q(s)})" for s in stmts)
downgrade_body = "\n".join(f"    op.execute({q(s)})" for s in drop_stmts)

content = f'''"""initial schema (generated from metadata, no live DB)."""

revision = "{REVISION}"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
{upgrade_body}


def downgrade() -> None:
{downgrade_body}
'''

out_dir = os.path.join(os.path.dirname(__file__), "..", "backend", "migrations", "versions")
os.makedirs(out_dir, exist_ok=True)
out = os.path.join(out_dir, f"{REVISION}_initial_schema.py")
with open(out, "w", encoding="utf-8") as f:
    f.write(content)
print(f"wrote {out}")
print(f"tables: {len(Base.metadata.sorted_tables)}, statements: {len(stmts)}")
