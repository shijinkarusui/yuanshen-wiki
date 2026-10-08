from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, column
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, EntityMixin, VerifiableMixin


class Person(Base, EntityMixin, VerifiableMixin):
    __tablename__ = "persons"

    primary_name: Mapped[str] = mapped_column(String(300), nullable=False)
    aliases: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class BibliographicRecord(Base, EntityMixin, VerifiableMixin):
    __tablename__ = "bibliographic_records"

    record_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    doi_normalized: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publication: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "record_type IN ('journal', 'book', 'chapter', 'thesis')",
            name="ck_bib_records_record_type",
        ),
        Index(
            "uq_bib_records_active_doi",
            "doi_normalized",
            unique=True,
            postgresql_where=(
                column("archived_at").is_(None)
                & column("doi_normalized").is_not(None)
            ),
        ),
    )


class BibliographicContributor(Base, EntityMixin):
    __tablename__ = "bibliographic_contributors"

    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bibliographic_records.id"),
        nullable=False,
    )
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id"),
        nullable=True,
    )
    literal_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="author", server_default="author"
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index(
            "uq_bib_contrib_active",
            "record_id",
            "role",
            "ordinal",
            unique=True,
            postgresql_where=column("archived_at").is_(None),
        ),
    )
