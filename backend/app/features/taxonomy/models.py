from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text, column, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, EntityMixin, VerifiableMixin

archived_at = column("archived_at")


class Category(Base, EntityMixin, VerifiableMixin):
    __tablename__ = "categories"

    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_key: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))


class Issue(Base, EntityMixin, VerifiableMixin):
    __tablename__ = "issues"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class IssueCategory(Base, EntityMixin):
    __tablename__ = "issue_categories"

    issue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("issues.id"), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)

    __table_args__ = (
        Index("uq_issue_categories_active", "issue_id", "category_id", unique=True, postgresql_where=(archived_at.is_(None))),
    )
