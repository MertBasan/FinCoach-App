import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, ForeignKey, DateTime, Date, Integer, Boolean, Text, BigInteger, Numeric, JSON, func
from sqlalchemy.dialects.postgresql import UUID
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
    # VKN = Vergi Kimlik Numarası (company tax ID, 10 digits)
    # TCKN = T.C. Kimlik Numarası (individual tax ID, 11 digits)
    vkn: Mapped[str | None] = mapped_column(String(10), nullable=True)
    tckn: Mapped[str | None] = mapped_column(String(11), nullable=True)

    # day of month the client should submit their info to the accountant
    submission_day_of_month: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    firm: Mapped[AccountingFirm] = relationship(back_populates="clients")


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
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="general", nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # "2026-05"
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    # status: pending | in_progress | done
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    client: Mapped[Client] = relationship(foreign_keys=[client_id])


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
    # Where this document came from. Values include:
    #   "manual_upload" (default)
    #   "pdf_extraction_input"   (source PDF for an extraction run)
    #   "pdf_extraction_output"  (resulting XLSX from an extraction run)
    # Future sources will appear here without schema change.
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
#
# These tables hold the transactional/accounting data that feeds analytical
# services (P&L, KPIs, anomaly detection). They are deliberately kept
# separate from operational tables (tasks, notes, document attachments).
#
# Amount-sign convention (transactions.amount, Decimal/Numeric):
#   - POSITIVE means money INTO the business (income, deposits, receipts)
#   - NEGATIVE means money OUT (expenses, payments, withdrawals)
#
# Approval status:
#   - "unapproved"   : raw, may have been touched by AI; never used in reports
#   - "ai_suggested" : AI has proposed an account/category; awaits accountant
#   - "approved"     : human-signed-off; ONLY status that flows into KPIs
#
# Downstream KPI/reporting code must filter on approval_status='approved'.

class Account(Base):
    """Chart-of-accounts entry. Scoped to a single client (each SME has its
    own chart)."""
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
    # asset | liability | equity | income | expense
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    # Identifies cost-of-sales accounts explicitly. Set per seed (not derived
    # from code prefix), because chart-of-accounts numbering varies by
    # jurisdiction — UK uses 5000s for COGS, Turkish TDHP uses 621/622.
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
    """A single accounting month, per client."""
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
    # open | closed (closed = locked, no more transactions added)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    client: Mapped[Client] = relationship(foreign_keys=[client_id])

    @property
    def period_str(self) -> str:
        return f"{self.year}-{self.month:02d}"


class Transaction(Base):
    """A single ledger entry. Signed amount: + into business, − out.

    Numbers are computed deterministically; AI may suggest accounts/categories
    but never invents amounts. Only approval_status='approved' rows flow into
    reports."""
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
    amount: Mapped["Decimal"] = mapped_column(
        Numeric(18, 2), nullable=False,
    )
    # "pdf_extraction" | "manual" | "csv_import" | ...
    source: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)
    # Original parsed row from the source document, JSON-encoded
    raw_reference: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # source_document_id: which Document this came from (input PDF, if any)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    # approval_status: unapproved | ai_suggested | approved
    approval_status: Mapped[str] = mapped_column(
        String(16), default="unapproved", nullable=False, index=True,
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    client: Mapped[Client] = relationship(foreign_keys=[client_id])
    account: Mapped[Account | None] = relationship(foreign_keys=[account_id])
    period: Mapped[AccountingPeriod] = relationship(foreign_keys=[period_id])
    source_document: Mapped[Document | None] = relationship(foreign_keys=[source_document_id])
