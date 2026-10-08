from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Index, String, Text, column, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, EntityMixin

archived_at = column("archived_at")


class FieldDefinition(Base, EntityMixin):
    __tablename__ = "field_definitions"

    key: Mapped[str] = mapped_column(String(128), nullable=False, comment="不可改")
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    value_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))

    __table_args__ = (
        CheckConstraint("value_type IN ('text', 'long_text', 'number', 'boolean', 'single_select', 'multi_select')", name="ck_field_definitions_value_type"),
        Index("uq_field_definitions_active_key", "entity_kind", "key", unique=True, postgresql_where=(archived_at.is_(None))),
    )
