import datetime
import uuid
from typing import Optional

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChangeSet(Base):
    __tablename__ = "change_sets"
    __table_args__ = (
        CheckConstraint("effect_direction IN ('forward', 'inverse')", name="ck_change_sets_effect_direction"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sequence_no: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
        comment="由PG sequence lingdebate.change_set_seq赋值，迁移中创建",
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("actors.id"), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    reverts_change_set_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("change_sets.id"), nullable=True
    )
    root_effect_change_set_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("change_sets.id"), nullable=False
    )
    effect_direction: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ChangeItem(Base):
    __tablename__ = "change_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    change_set_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("change_sets.id", ondelete="CASCADE"), nullable=False
    )
    entity_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    before_revision: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    after_revision: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    before: Mapped[Optional[dict]] = mapped_column("before", JSONB, nullable=True)
    after: Mapped[Optional[dict]] = mapped_column("after", JSONB, nullable=True)
    changed_fields: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))


class ParagraphLineage(Base):
    __tablename__ = "paragraph_lineage"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    change_set_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("change_sets.id", ondelete="CASCADE"), nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    command_type: Mapped[str] = mapped_column(String(32), nullable=False)
    discourse_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    source_orders: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    target_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    target_orders: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))


class AnchorAdjustment(Base):
    __tablename__ = "anchor_adjustments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    change_set_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("change_sets.id", ondelete="CASCADE"), nullable=False
    )
    anchor_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    old_start_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    old_end_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    new_start_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    new_end_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    display_range_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    validity_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))


class AnchorAdjustmentRelation(Base):
    __tablename__ = "anchor_adjustment_relations"

    adjustment_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("anchor_adjustments.id", ondelete="CASCADE"), primary_key=True
    )
    relation_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)


class ChangeEffectState(Base):
    __tablename__ = "change_effect_states"

    root_effect_change_set_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("change_sets.id", ondelete="CASCADE"), primary_key=True
    )
    is_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    last_toggle_change_set_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("change_sets.id"), nullable=False
    )
