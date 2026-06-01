import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import (
    String, ForeignKey, DateTime, Date, Integer, Boolean, Text,
    BigInteger, Numeric, JSON, func, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


# ---------- Tenants ----------

class AccountingFirm(Base):
    __tablename__ = "accounting_firms"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="firm")
    clients: Mapped[list["Client"]] = relationship(back_populates="firm")


# ---------- Users with roles ----------
# Roles:
#   - "superuser"  : platform admin, can see all firms
#   - "accountant" : full accounting operations within their firm
#   - "client"     : external SME user, scoped to a single client_id

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounting_firms.id", ondelete="CASCADE"),
        nullable=True,  # superuser has no firm
        index=True,
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="accountant", nullable=False)
    # Phase 3: firm admin flag and active flag
    is_firm_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    firm: Mapped[AccountingFirm | None] = relationship(back_populates="users")
    client: Mapped["Client | None"] = relationship(foreign_keys=[client_id])


# ---------- Clients ----------

class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounting_firms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    base_currency: Mapped[str] = mapped_column(String(3), default="TRY", nullable=False)

    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)

    # Turkish tax identifiers (optional, only relevant in TR locale).
    vkn: Mapped[str | None] = mapped_column(String(10), nullable=True)
    tckn: Mapped[str | None] = mapped_column(String(11), nullable=True)

    submission_day_of_month: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    firm: Mapped[AccountingFirm] = relationship(back_populates="clients")


# ---------- Client Assignments (Phase 3) ----------

class ClientAssignment(Base):
    """Maps which accountants are assigned to which clients within a firm."""
    __tablename__ = "client_assignments"
    __table_args__ = (
        UniqueConstraint("client_id", "user_id", name="uq_client_assignment"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounting_firms.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped[Client] = relationship(foreign_keys=[client_id])
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    assigner: Mapped[User | None] = relationship(foreign_keys=[assigned_by])


# ---------- Admin Audit Log (Phase 3) ----------

class AdminAuditLog(Base):
    """Records admin actions for firm-level audit trail."""
    __tablename__ = "admin_audit_log"

    # Valid action values:
    #   create_user, disable_user, enable_user, reset_password, change_email,
    #   assign_client, unassign_client, create_task, delete_task

    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounting_firms.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    actor: Mapped[User | None] = relationship(foreign_keys=[actor_user_id])
    target: Mapped[User | None] = relationship(foreign_keys=[target_user_id])


# ---------- Notes ----------

class Note(Base):
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounting_firms.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    author: Mapped[User | None] = relationship(foreign_keys=[author_id])
    client: Mapped[Client | None] = relationship(foreign_keys=[client_id])


# ---------- Tasks (monthly workflow) ----------

class TaskTemplate(Base):
    """Firm-level template: 'VAT prep', 'Monthly close', etc."""
    __tablename__ = "task_templates"

    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounting_firms.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(64), default="general", nullable=False)
    day_of_month: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ClientMonthlyTask(Base):
    __tablename__ = "client_monthly_tasks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounting_firms.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_templates.id", ondelete="SET NULL"), nullable=True
    )
    # Phase 3: which accountant this task is assigned to (None = unassigned)
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="general", nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # "2026-05"
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    client: Mapped[Client] = relationship(foreign_keys=[client_id])
    assigned_to: Mapped[User | None] = relationship(foreign_keys=[assigned_to_user_id])


# ---------- Documents ----------

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounting_firms.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(String(64), default="other", nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="manual_upload", nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    period: Mapped[str | None] = mapped_column(String(7), nullable=True)
    visible_to_client: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped[Client] = relationship(foreign_keys=[client_id])
    uploaded_by: Mapped[User | None] = relationship(foreign_keys=[uploaded_by_id])


# ============================================================================
# Data spine: chart of accounts, periods, transactions
# ============================================================================

class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounting_firms.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    is_cogs: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    client: Mapped[Client] = relationship(foreign_keys=[client_id])


class AccountingPeriod(Base):
    __tablename__ = "accounting_periods"

    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounting_firms.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    client: Mapped[Client] = relationship(foreign_keys=[client_id])

    @property
    def period_str(self) -> str:
        return f"{self.year}-{self.month:02d}"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounting_firms.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounting_periods.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    amount: Mapped["Decimal"] = mapped_column(Numeric(18, 2), nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)
    raw_reference: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    approval_status: Mapped[str] = mapped_column(
        String(16), default="unapproved", nullable=False, index=True,
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped[Client] = relationship(foreign_keys=[client_id])
    account: Mapped[Account | None] = relationship(foreign_keys=[account_id])
    period: Mapped[AccountingPeriod] = relationship(foreign_keys=[period_id])
    source_document: Mapped[Document | None] = relationship(foreign_keys=[source_document_id])


# ---------- Period Snapshots (Phase 3) ----------

class PeriodSnapshot(Base):
    """Aggregated period-level financial data from external sources or manual entry.

    Reports prefer an approved snapshot over transaction-computed numbers.
    Trust model mirrors transactions: only approval_status='approved' snapshots
    flow into reports. Never mix snapshot + transactions within a single period.
    """
    __tablename__ = "period_snapshots"
    __table_args__ = (
        UniqueConstraint("client_id", "period_id", name="uq_period_snapshot"),
    )

    # source values:
    #   manual | eta_sql_import | logo_import | mikro_import |
    #   netsis_import | csv_import

    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounting_firms.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounting_periods.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    approval_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unapproved")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Financial fields (all nullable — may be partially filled)
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    cogs: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    gross_profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    operating_expenses: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    net_profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    cash_balance_opening: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    cash_balance_closing: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    cash_inflows: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    cash_outflows: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    ar_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    ap_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    vat_input: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    vat_output: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    expense_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True,
    )

    client: Mapped[Client] = relationship(foreign_keys=[client_id])
    period: Mapped[AccountingPeriod] = relationship(foreign_keys=[period_id])
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by])
    approver: Mapped[User | None] = relationship(foreign_keys=[approved_by])
    source_document: Mapped[Document | None] = relationship(foreign_keys=[source_document_id])
