"""Add verification fields to discourses."""

revision = "b2c3d4e5f607"
down_revision = "f2e21130cdc8"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


def upgrade() -> None:
    op.add_column("discourses", sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("discourses", sa.Column("verified_by", PG_UUID(as_uuid=True), nullable=True))
    op.add_column("discourses", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("discourses", sa.Column("verified_revision", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("discourses", "verified_revision")
    op.drop_column("discourses", "verified_at")
    op.drop_column("discourses", "verified_by")
    op.drop_column("discourses", "is_verified")
