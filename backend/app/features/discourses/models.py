from __future__ import annotations

import datetime
import uuid

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, column
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, EntityMixin, VerifiableMixin

archived_at = column("archived_at")


class Discourse(Base, EntityMixin, VerifiableMixin):
    __tablename__ = "discourses"

    bibliographic_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bibliographic_records.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_locator: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    attribution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    paragraph_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class Paragraph(Base, EntityMixin):
    __tablename__ = "paragraphs"
    __table_args__ = (
        UniqueConstraint("discourse_id", "current_order", name="uq_paragraphs_discourse_order", deferrable=True, initially="DEFERRED"),
    )

    discourse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("discourses.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    current_order: Mapped[int | None] = mapped_column(Integer, nullable=True)


class IssueDiscourse(Base, EntityMixin):
    __tablename__ = "issue_discourses"
    __table_args__ = (
        Index("uq_issue_discourses_active", "issue_id", "discourse_id", unique=True, postgresql_where=(archived_at.is_(None))),
    )

    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("issues.id"), nullable=False)
    discourse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("discourses.id"), nullable=False)


class Anchor(Base, EntityMixin):
    __tablename__ = "anchors"

    discourse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("discourses.id"), nullable=False)
    start_paragraph_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("paragraphs.id"), nullable=True)
    end_paragraph_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("paragraphs.id"), nullable=True)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    invalid_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_known_range: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    verified_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_revision: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
