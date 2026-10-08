import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, column, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, EntityMixin

archived_at = column("archived_at")


class RelationKind(Base, EntityMixin):
    __tablename__ = "relation_kinds"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name_cn: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))


class DimensionKind(Base, EntityMixin):
    __tablename__ = "dimension_kinds"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name_cn: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))


class Relation(Base, EntityMixin):
    __tablename__ = "relations"
    __table_args__ = (
        CheckConstraint("basis IN ('author_explicit', 'analyst_inferred')", name="ck_relations_basis"),
    )

    issue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("issues.id"), nullable=False)
    source_anchor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("anchors.id"), nullable=False)
    target_anchor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("anchors.id"), nullable=False)
    relation_kind_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("relation_kinds.id"), nullable=False)
    basis: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_anchor_revision_at_creation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_anchor_revision_at_creation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_anchor_revision_at_verification: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_anchor_revision_at_verification: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_revision: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class RelationDimension(Base, EntityMixin):
    __tablename__ = "relation_dimensions"
    __table_args__ = (
        Index("uq_relation_dimensions_active", "relation_id", "dimension_kind_id", unique=True, postgresql_where=(archived_at.is_(None))),
    )

    relation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("relations.id"), nullable=False)
    dimension_kind_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dimension_kinds.id"), nullable=False)


class Annotation(Base, EntityMixin):
    __tablename__ = "annotations"
    __table_args__ = (
        CheckConstraint("(anchor_id IS NOT NULL)::int + (relation_id IS NOT NULL)::int = 1", name="ck_annotation_single_target"),
    )

    anchor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("anchors.id"), nullable=True)
    relation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("relations.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_revision: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
