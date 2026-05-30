"""Data spine: chart of accounts, accounting periods, transactions

Revision ID: 0003_spine
Revises: 0002_document_source
Create Date: 2026-05-28

The spine holds transactional/accounting data that flows into analytical
services (P&L, KPIs, etc.). Operational tables (tasks, notes, documents)
remain separate.

Amount sign convention on transactions.amount:
  - POSITIVE means money INTO the business
  - NEGATIVE means money OUT
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0003_spine"
down_revision: Union[str, None] = "0002_document_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- accounts ----------
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("accounting_firms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_accounts_firm_id", "accounts", ["firm_id"])
    op.create_index("ix_accounts_client_id", "accounts", ["client_id"])
    op.create_index("ix_accounts_client_code",
                    "accounts", ["client_id", "code"], unique=True)

    # ---------- accounting_periods ----------
    op.create_table(
        "accounting_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("accounting_firms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_periods_firm_id", "accounting_periods", ["firm_id"])
    op.create_index("ix_periods_client_id", "accounting_periods", ["client_id"])
    op.create_index(
        "ix_periods_client_year_month",
        "accounting_periods", ["client_id", "year", "month"], unique=True,
    )

    # ---------- transactions ----------
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("accounting_firms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("accounting_periods.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("source", sa.String(64), nullable=False, server_default="manual"),
        sa.Column("raw_reference", postgresql.JSONB, nullable=True),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approval_status", sa.String(16), nullable=False, server_default="unapproved"),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_transactions_firm_id", "transactions", ["firm_id"])
    op.create_index("ix_transactions_client_id", "transactions", ["client_id"])
    op.create_index("ix_transactions_period_id", "transactions", ["period_id"])
    op.create_index("ix_transactions_account_id", "transactions", ["account_id"])
    op.create_index("ix_transactions_date", "transactions", ["date"])
    op.create_index("ix_transactions_approval_status",
                    "transactions", ["approval_status"])

    # ---------- Row Level Security ----------
    rls_tables = ["accounts", "accounting_periods", "transactions"]
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
    for t in ["transactions", "accounting_periods", "accounts"]:
        op.execute(f"DROP POLICY IF EXISTS {t}_firm_isolation ON {t};")
    op.drop_table("transactions")
    op.drop_table("accounting_periods")
    op.drop_table("accounts")
