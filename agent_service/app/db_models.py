"""SQLAlchemy models for Phase 3 persistence (searches, plans, sessions, suburbs)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    execution_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    query_plan: Mapped[QueryPlanRecord | None] = relationship(
        back_populates="search", uselist=False, cascade="all, delete-orphan"
    )
    recommendation_result: Mapped[RecommendationResult | None] = relationship(
        back_populates="search", uselist=False, cascade="all, delete-orphan"
    )
    answer_log: Mapped[AnswerLog | None] = relationship(
        back_populates="search", uselist=False, cascade="all, delete-orphan"
    )


class QueryPlanRecord(Base):
    __tablename__ = "query_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("searches.id"), nullable=False, unique=True)
    raw_llm_plan: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    normalized_plan: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    trust_gate: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    search: Mapped[Search] = relationship(back_populates="query_plan")


class RecommendationResult(Base):
    __tablename__ = "recommendation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("searches.id"), nullable=False, unique=True)
    result_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    search: Mapped[Search] = relationship(back_populates="recommendation_result")


class AnswerLog(Base):
    __tablename__ = "answer_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("searches.id"), nullable=False, unique=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    used_answer_llm: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    search: Mapped[Search] = relationship(back_populates="answer_log")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    latest_preferences: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class Suburb(Base):
    """Curated 200-town reference dataset (Phase 3C)."""

    __tablename__ = "suburbs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
