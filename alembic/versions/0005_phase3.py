"""Phase 3: firm admin, client assignments, audit log, task assignment, period snapshots

Revision ID: 0005_phase3
Revises: 0004_tr_localization
Create Date: 2026-06-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision: str = "0005_phase3"
down_revision: Union[str, None] = "0004_tr_localization"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- Step 1: firm admin + active flag on users ----------
    op.add_column("users", sa.Column(
        "is_firm_admin", sa.Boolean, nullable=False, server_default=sa.text("false")
    ))
    op.add_column("users", sa.Column(
        "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
    ))

    # Backfill: earliest-created accountant per firm becomes admin
    op.execute("""
        UPDATE users u
        SET is_firm_admin = true
        FROM (
            SELECT DISTINCT ON (firm_id) id
            FROM users
            WHERE role = 'accountant' AND firm_id IS NOT NULL
            ORDER BY firm_id, created_at ASC
        ) sub
        WHERE u.id = sub.id
    """)

    # ---------- Step 2: client_assignments ----------
    op.create_table(
        "client_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("firm_id", UUID(as_uuid=True),
                  sa.ForeignKey("accounting_firms.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("client_id", UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("assigned_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_client_assignment", "client_assignments", ["client_id", "user_id"]
    )

    op.execute("""
        ALTER TABLE client_assignments ENABLE ROW LEVEL SECURITY;
        ALTER TABLE client_assignments FORCE ROW LEVEL SECURITY;
        CREATE POLICY client_assignments_firm_isolation ON client_assignments
        USING (
            firm_id::text = current_setting('app.current_firm_id', true)
            AND current_setting('app.current_firm_id', true) <> ''
        )
        WITH CHECK (
            firm_id::text = current_setting('app.current_firm_id', true)
            AND current_setting('app.current_firm_id', true) <> ''
        );
    """)

    # Backfill: assign every existing accountant to every existing client within firm
    op.execute("""
        INSERT INTO client_assignments (id, firm_id, client_id, user_id, created_at)
        SELECT gen_random_uuid(), c.firm_id, c.id, u.id, now()
        FROM clients c
        JOIN users u ON u.firm_id = c.firm_id AND u.role = 'accountant'
        ON CONFLICT DO NOTHING
    """)

    # ---------- Step 3: admin_audit_log ----------
    op.create_table(
        "admin_audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("firm_id", UUID(as_uuid=True),
                  sa.ForeignKey("accounting_firms.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("actor_user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("target_user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
    )

    op.execute("""
        ALTER TABLE admin_audit_log ENABLE ROW LEVEL SECURITY;
        ALTER TABLE admin_audit_log FORCE ROW LEVEL SECURITY;
        CREATE POLICY admin_audit_log_firm_isolation ON admin_audit_log
        USING (
            firm_id::text = current_setting('app.current_firm_id', true)
            AND current_setting('app.current_firm_id', true) <> ''
        )
        WITH CHECK (
            firm_id::text = current_setting('app.current_firm_id', true)
            AND current_setting('app.current_firm_id', true) <> ''
        );
    """)

    # ---------- Step 4: task assignment ----------
    op.add_column("client_monthly_tasks", sa.Column(
        "assigned_to_user_id", UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    ))

    # ---------- Step 5: period_snapshots ----------
    op.create_table(
        "period_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("firm_id", UUID(as_uuid=True),
                  sa.ForeignKey("accounting_firms.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("client_id", UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("period_id", UUID(as_uuid=True),
                  sa.ForeignKey("accounting_periods.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        # source: manual | eta_sql_import | logo_import | mikro_import |
        #         netsis_import | csv_import
        sa.Column("source", sa.String(64), nullable=False, server_default="manual"),
        # approval_status: unapproved | approved
        sa.Column("approval_status", sa.String(16), nullable=False,
                  server_default="unapproved"),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
        # Financial fields — all DECIMAL
        sa.Column("revenue", sa.Numeric(18, 2), nullable=True),
        sa.Column("cogs", sa.Numeric(18, 2), nullable=True),
        sa.Column("gross_profit", sa.Numeric(18, 2), nullable=True),
        sa.Column("operating_expenses", sa.Numeric(18, 2), nullable=True),
        sa.Column("net_profit", sa.Numeric(18, 2), nullable=True),
        sa.Column("cash_balance_opening", sa.Numeric(18, 2), nullable=True),
        sa.Column("cash_balance_closing", sa.Numeric(18, 2), nullable=True),
        sa.Column("cash_inflows", sa.Numeric(18, 2), nullable=True),
        sa.Column("cash_outflows", sa.Numeric(18, 2), nullable=True),
        sa.Column("ar_total", sa.Numeric(18, 2), nullable=True),
        sa.Column("ap_total", sa.Numeric(18, 2), nullable=True),
        sa.Column("vat_input", sa.Numeric(18, 2), nullable=True),
        sa.Column("vat_output", sa.Numeric(18, 2), nullable=True),
        sa.Column("expense_breakdown", JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("source_document_id", UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_unique_constraint(
        "uq_period_snapshot", "period_snapshots", ["client_id", "period_id"]
    )

    op.execute("""
        ALTER TABLE period_snapshots ENABLE ROW LEVEL SECURITY;
        ALTER TABLE period_snapshots FORCE ROW LEVEL SECURITY;
        CREATE POLICY period_snapshots_firm_isolation ON period_snapshots
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
    op.drop_table("period_snapshots")
    op.drop_column("client_monthly_tasks", "assigned_to_user_id")
    op.drop_table("admin_audit_log")
    op.drop_table("client_assignments")
    op.drop_column("users", "is_active")
    op.drop_column("users", "is_firm_admin")
