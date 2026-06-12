"""Initial Phase 3A schema."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "searches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("execution_status", sa.Text(), nullable=True),
        sa.Column("message_code", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index("ix_searches_request_id", "searches", ["request_id"])
    op.create_index("ix_searches_session_id", "searches", ["session_id"])

    op.create_table(
        "query_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("search_id", sa.Integer(), nullable=False),
        sa.Column("raw_llm_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("normalized_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trust_gate", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["search_id"], ["searches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("search_id"),
    )

    op.create_table(
        "recommendation_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("search_id", sa.Integer(), nullable=False),
        sa.Column("result_type", sa.Text(), nullable=True),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["search_id"], ["searches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("search_id"),
    )

    op.create_table(
        "answer_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("search_id", sa.Integer(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("used_answer_llm", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["search_id"], ["searches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("search_id"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("latest_preferences", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index("ix_sessions_session_id", "sessions", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_sessions_session_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_audit_events_request_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("answer_logs")
    op.drop_table("recommendation_results")
    op.drop_table("query_plans")
    op.drop_index("ix_searches_session_id", table_name="searches")
    op.drop_index("ix_searches_request_id", table_name="searches")
    op.drop_table("searches")
