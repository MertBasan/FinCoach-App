"""Deterministic financial computations.

Every number in this module comes from approved transactions only, or
from an approved period snapshot when one is present. No AI, no estimates,
no fabrication. If a number isn't reachable from the data, the function
returns None — never a guess.

Phase 3 rule: if an approved PeriodSnapshot exists for a period, ALL
financial figures for that period come from the snapshot. If not, they
are computed from approved transactions. The two sources are NEVER mixed
within a single period.

Amount sign convention (transactions.amount):
  POSITIVE = money into the business
  NEGATIVE = money out
"""
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AccountingPeriod, Account, Transaction, PeriodSnapshot
from app.spine.queries import approved_transactions_for_period


# ---------- Helpers ----------

def _is_cost_of_sales(account: Account | None) -> bool:
    if not account or account.type != "expense":
        return False
    return bool(account.is_cogs)


def _zero() -> Decimal:
    return Decimal("0.00")


# ---------- Result containers ----------

@dataclass
class CategoryLine:
    account_code: str
    account_name: str
    total: Decimal


@dataclass
class PLReport:
    period_label: str
    revenue: Decimal
    cost_of_sales: Decimal
    gross_profit: Decimal
    operating_expenses: Decimal
    net_profit: Decimal
    revenue_lines: list[CategoryLine] = field(default_factory=list)
    cogs_lines: list[CategoryLine] = field(default_factory=list)
    opex_lines: list[CategoryLine] = field(default_factory=list)
    uncategorised_count: int = 0
    uncategorised_total: Decimal = field(default_factory=_zero)
    # Phase 3: data source ("transactions" or snapshot.source e.g. "manual")
    data_source: str = "transactions"


@dataclass
class CashSnapshot:
    period_label: str
    inflows: Decimal
    outflows: Decimal
    net_change: Decimal
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    data_source: str = "transactions"


@dataclass
class KPISet:
    period_label: str
    revenue: Decimal
    net_profit: Decimal
    gross_margin_pct: Decimal | None
    transaction_count: int
    uncategorised_pct: int
    top_expense_lines: list[CategoryLine]
    data_source: str = "transactions"


@dataclass
class PeriodComparison:
    current: PLReport
    prior_period: PLReport | None
    prior_year: PLReport | None


# ---------- Snapshot helpers ----------

def get_approved_snapshot(db: Session, period: AccountingPeriod) -> PeriodSnapshot | None:
    """Return the approved snapshot for a period if one exists."""
    return db.scalar(
        select(PeriodSnapshot)
        .where(PeriodSnapshot.period_id == period.id)
        .where(PeriodSnapshot.approval_status == "approved")
    )


def _build_pl_from_snapshot(snapshot: PeriodSnapshot, period: AccountingPeriod) -> PLReport:
    label = f"{period.year:04d}-{period.month:02d}"
    rev = snapshot.revenue or _zero()
    cogs = snapshot.cogs or _zero()
    gross = snapshot.gross_profit if snapshot.gross_profit is not None else (rev - cogs)
    opex = snapshot.operating_expenses or _zero()
    net = snapshot.net_profit if snapshot.net_profit is not None else (gross - opex)

    opex_lines: list[CategoryLine] = []
    for name, amount in (snapshot.expense_breakdown or {}).items():
        opex_lines.append(CategoryLine(
            account_code="",
            account_name=name,
            total=Decimal(str(amount)),
        ))
    opex_lines.sort(key=lambda x: x.total, reverse=True)

    return PLReport(
        period_label=label,
        revenue=rev,
        cost_of_sales=cogs,
        gross_profit=gross,
        operating_expenses=opex,
        net_profit=net,
        opex_lines=opex_lines,
        data_source=snapshot.source,
    )


def _build_cash_from_snapshot(snapshot: PeriodSnapshot, period: AccountingPeriod) -> CashSnapshot:
    label = f"{period.year:04d}-{period.month:02d}"
    inflows = snapshot.cash_inflows or _zero()
    outflows = snapshot.cash_outflows or _zero()
    return CashSnapshot(
        period_label=label,
        inflows=inflows,
        outflows=outflows,
        net_change=inflows - outflows,
        opening_balance=snapshot.cash_balance_opening,
        closing_balance=snapshot.cash_balance_closing,
        data_source=snapshot.source,
    )


def _build_kpis_from_snapshot(snapshot: PeriodSnapshot, period: AccountingPeriod) -> KPISet:
    pl = _build_pl_from_snapshot(snapshot, period)
    label = f"{period.year:04d}-{period.month:02d}"

    gm_pct: Decimal | None = None
    if pl.revenue > 0:
        gm_pct = (pl.gross_profit / pl.revenue * Decimal(100)).quantize(Decimal("0.1"))

    top_expenses = sorted(pl.opex_lines, key=lambda c: c.total, reverse=True)[:3]

    return KPISet(
        period_label=label,
        revenue=pl.revenue,
        net_profit=pl.net_profit,
        gross_margin_pct=gm_pct,
        transaction_count=0,
        uncategorised_pct=0,
        top_expense_lines=top_expenses,
        data_source=snapshot.source,
    )


# ---------- Transaction-based core ----------

def _aggregate_by_account(
    txs: Iterable[Transaction],
) -> tuple[
    Decimal, Decimal, Decimal,
    list[CategoryLine], list[CategoryLine], list[CategoryLine],
    int, Decimal,
]:
    revenue = _zero()
    cogs = _zero()
    opex = _zero()

    revenue_by_acc: dict[tuple[str, str], Decimal] = defaultdict(_zero)
    cogs_by_acc:    dict[tuple[str, str], Decimal] = defaultdict(_zero)
    opex_by_acc:    dict[tuple[str, str], Decimal] = defaultdict(_zero)

    uncategorised_count = 0
    uncategorised_total = _zero()

    for tx in txs:
        if tx.account is None:
            uncategorised_count += 1
            uncategorised_total += tx.amount
            continue
        acc = tx.account
        key = (acc.code, acc.name)
        if acc.type == "income":
            revenue += tx.amount
            revenue_by_acc[key] += tx.amount
        elif acc.type == "expense":
            spend = -tx.amount
            if _is_cost_of_sales(acc):
                cogs += spend
                cogs_by_acc[key] += spend
            else:
                opex += spend
                opex_by_acc[key] += spend

    def _lines(d: dict, sort_desc: bool = True) -> list[CategoryLine]:
        items = [
            CategoryLine(account_code=c, account_name=n, total=t)
            for (c, n), t in d.items()
        ]
        items.sort(key=lambda x: x.total, reverse=sort_desc)
        return items

    return (
        revenue, cogs, opex,
        _lines(revenue_by_acc),
        _lines(cogs_by_acc),
        _lines(opex_by_acc),
        uncategorised_count,
        uncategorised_total,
    )


# ---------- Public API ----------

def compute_pl(db: Session, period: AccountingPeriod) -> PLReport:
    """P&L for a single period. Prefers approved snapshot; falls back to transactions."""
    snapshot = get_approved_snapshot(db, period)
    if snapshot:
        return _build_pl_from_snapshot(snapshot, period)

    txs = db.scalars(approved_transactions_for_period(period.id)).all()
    revenue, cogs, opex, rev_lines, cogs_lines, opex_lines, unc_n, unc_t = \
        _aggregate_by_account(txs)
    gross_profit = revenue - cogs
    net_profit = gross_profit - opex
    return PLReport(
        period_label=f"{period.year:04d}-{period.month:02d}",
        revenue=revenue,
        cost_of_sales=cogs,
        gross_profit=gross_profit,
        operating_expenses=opex,
        net_profit=net_profit,
        revenue_lines=rev_lines,
        cogs_lines=cogs_lines,
        opex_lines=opex_lines,
        uncategorised_count=unc_n,
        uncategorised_total=unc_t,
        data_source="transactions",
    )


def compute_cash(db: Session, period: AccountingPeriod) -> CashSnapshot:
    """Cash position. Prefers approved snapshot; falls back to transactions."""
    snapshot = get_approved_snapshot(db, period)
    if snapshot:
        return _build_cash_from_snapshot(snapshot, period)

    txs = db.scalars(approved_transactions_for_period(period.id)).all()
    inflows = _zero()
    outflows = _zero()
    for tx in txs:
        if tx.amount > 0:
            inflows += tx.amount
        else:
            outflows += -tx.amount
    return CashSnapshot(
        period_label=f"{period.year:04d}-{period.month:02d}",
        inflows=inflows,
        outflows=outflows,
        net_change=inflows - outflows,
        data_source="transactions",
    )


def compute_kpis(db: Session, period: AccountingPeriod) -> KPISet:
    """KPI tiles. Prefers approved snapshot; falls back to transactions."""
    snapshot = get_approved_snapshot(db, period)
    if snapshot:
        return _build_kpis_from_snapshot(snapshot, period)

    pl = compute_pl(db, period)
    txs = db.scalars(approved_transactions_for_period(period.id)).all()

    gm_pct: Decimal | None = None
    if pl.revenue > 0:
        gm_pct = (pl.gross_profit / pl.revenue * Decimal(100)).quantize(Decimal("0.1"))

    total_approved = len(txs)
    no_account = sum(1 for t in txs if t.account_id is None)
    unc_pct = int((no_account / total_approved) * 100) if total_approved else 0

    top_expenses = sorted(
        pl.cogs_lines + pl.opex_lines, key=lambda c: c.total, reverse=True,
    )[:3]

    return KPISet(
        period_label=f"{period.year:04d}-{period.month:02d}",
        revenue=pl.revenue,
        net_profit=pl.net_profit,
        gross_margin_pct=gm_pct,
        transaction_count=total_approved,
        uncategorised_pct=unc_pct,
        top_expense_lines=top_expenses,
        data_source="transactions",
    )


def find_period(
    db: Session,
    client_id: UUID,
    year: int,
    month: int,
) -> AccountingPeriod | None:
    return db.scalar(
        select(AccountingPeriod)
        .where(AccountingPeriod.client_id == client_id)
        .where(AccountingPeriod.year == year)
        .where(AccountingPeriod.month == month)
    )


def compute_comparison(db: Session, period: AccountingPeriod) -> PeriodComparison:
    """P&L for the period plus prior period and prior year, where available."""
    current = compute_pl(db, period)

    pp_year, pp_month = period.year, period.month - 1
    if pp_month == 0:
        pp_month = 12
        pp_year -= 1
    pp_period = find_period(db, period.client_id, pp_year, pp_month)
    prior_period = compute_pl(db, pp_period) if pp_period else None

    py_period = find_period(db, period.client_id, period.year - 1, period.month)
    prior_year = compute_pl(db, py_period) if py_period else None

    return PeriodComparison(
        current=current,
        prior_period=prior_period,
        prior_year=prior_year,
    )
