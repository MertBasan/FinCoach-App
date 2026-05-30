"""Initial schema with roles, addresses, notes, tasks, documents — and RLS

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "accounting_firms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # clients first because users reference clients
    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("accounting_firms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("industry", sa.String(128), nullable=True),
        sa.Column("base_currency", sa.String(3), nullable=False, server_default="GBP"),
        sa.Column("address_line1", sa.String(255), nullable=True),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(128), nullable=True),
        sa.Column("postcode", sa.String(32), nullable=True),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("submission_day_of_month", sa.Integer, nullable=False, server_default="10"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_clients_firm_id", "clients", ["firm_id"])

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("accounting_firms.id", ondelete="CASCADE"), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="accountant"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_firm_id", "users", ["firm_id"])
    op.create_index("ix_users_client_id", "users", ["client_id"])

    op.create_table(
        "notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("accounting_firms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notes_firm_id", "notes", ["firm_id"])
    op.create_index("ix_notes_client_id", "notes", ["client_id"])

    op.create_table(
        "task_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("accounting_firms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("category", sa.String(64), nullable=False, server_default="general"),
        sa.Column("day_of_month", sa.Integer, nullable=False, server_default="15"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_task_templates_firm_id", "task_templates", ["firm_id"])

    op.create_table(
        "client_monthly_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("accounting_firms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("task_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("category", sa.String(64), nullable=False, server_default="general"),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_cmt_firm_id", "client_monthly_tasks", ["firm_id"])
    op.create_index("ix_cmt_client_id", "client_monthly_tasks", ["client_id"])
    op.create_index("ix_cmt_period", "client_monthly_tasks", ["period"])

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("accounting_firms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("document_type", sa.String(64), nullable=False, server_default="other"),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("period", sa.String(7), nullable=True),
        sa.Column("visible_to_client", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_documents_firm_id", "documents", ["firm_id"])
    op.create_index("ix_documents_client_id", "documents", ["client_id"])

    # ---------- Row Level Security ----------
    # Pattern: every tenant-scoped table has firm_id; policies enforce that
    # only the current firm's rows are visible. Setting is empty -> deny all.

    rls_tables = [
        "clients",
        "notes",
        "task_templates",
        "client_monthly_tasks",
        "documents",
    ]
    for t in rls_tables:
        op.execute(f"""
            ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {t} FORCE ROW LEVEL SECURITY;
            CREATE POLICY {t}_firm_isolation ON {t}
            USING (
                firm_id::text = current_setting('app.current_firm_id', true)
                AND current_setting('app.current_firm_id', true) <> ''
            )
            WITH CHECK (
                firm_id::text = current_setting('app.current_firm_id', true)
                AND current_setting('app.current_firm_id', true) <> ''
            );
        """)


def downgrade() -> None:
    for t in ["documents", "client_monthly_tasks", "task_templates", "notes", "clients"]:
        op.execute(f"DROP POLICY IF EXISTS {t}_firm_isolation ON {t};")
    op.drop_table("documents")
    op.drop_table("client_monthly_tasks")
    op.drop_table("task_templates")
    op.drop_table("notes")
    op.drop_table("users")
    op.drop_table("clients")
    op.drop_table("accounting_firms")
