"""
Deterministic financial computations.

Every number in this module comes from approved transactions only. No AI,
no estimates, no fabrication. If a number isn't reachable from the data,
the function returns None — never a guess.

Amount sign convention (transactions.amount):
  POSITIVE = money into the business
  NEGATIVE = money out

Account type mapping for P&L:
  income    -> revenue line
  expense   -> COGS or operating, depending on account code prefix
                (codes starting with '5' are treated as cost of sales;
                 everything else expense-typed is operating expense)
"""
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AccountingPeriod, Account, Transaction
from app.spine.queries import approved_transactions_for_period


# ---------- Helpers ----------

def _is_cost_of_sales(account: Account | None) -> bool:
    """COGS is identified by the explicit is_cogs flag set per seed.
    Set on UK 5000-series codes and on TDHP 621/622."""
    if not account or account.type != "expense":
        return False
    return bool(account.is_cogs)


def _zero() -> Decimal:
    return Decimal("0.00")


# ---------- Result containers ----------

@dataclass
class CategoryLine:
    """One line in a category breakdown — e.g. 'Marketing & Advertising: -1,200'."""
    account_code: str
    account_name: str
    total: Decimal


@dataclass
class PLReport:
    period_label: str          # "2026-05"
    revenue: Decimal           # positive = good
    cost_of_sales: Decimal     # positive number representing total spent
    gross_profit: Decimal
    operating_expenses: Decimal  # positive number
    net_profit: Decimal
    revenue_lines: list[CategoryLine] = field(default_factory=list)
    cogs_lines: list[CategoryLine] = field(default_factory=list)
    opex_lines: list[CategoryLine] = field(default_factory=list)
    uncategorised_count: int = 0
    uncategorised_total: Decimal = field(default_factory=_zero)


@dataclass
class CashSnapshot:
    period_label: str
    inflows: Decimal       # positive total of all credits
    outflows: Decimal      # positive total of all debits
    net_change: Decimal    # inflows - outflows
    # Opening / closing balance can be None when we have no
    # cross-period reconciliation yet.
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None


@dataclass
class KPISet:
    period_label: str
    revenue: Decimal
    net_profit: Decimal
    gross_margin_pct: Decimal | None   # None if revenue == 0
    transaction_count: int
    uncategorised_pct: int             # 0-100
    top_expense_lines: list[CategoryLine]  # top 3 by absolute size


@dataclass
class PeriodComparison:
    current: PLReport
    prior_period: PLReport | None      # immediately previous month
    prior_year: PLReport | None        # same month, 12 months earlier


# ---------- Core computations ----------

def _aggregate_by_account(
    txs: Iterable[Transaction],
) -> tuple[
    Decimal,  # revenue (positive total)
    Decimal,  # cogs (positive total of cost-of-sales spending)
    Decimal,  # opex (positive total of other operating spending)
    list[CategoryLine],  # revenue lines
    list[CategoryLine],  # cogs lines
    list[CategoryLine],  # opex lines
    int,                 # uncategorised_count
    Decimal,             # uncategorised_total (signed)
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
            revenue += tx.amount  # positive amounts add to revenue
            revenue_by_acc[key] += tx.amount
        elif acc.type == "expense":
            spend = -tx.amount  # spend is positive when amount is negative
            if _is_cost_of_sales(acc):
                cogs += spend
                cogs_by_acc[key] += spend
            else:
                opex += spend
                opex_by_acc[key] += spend
        # asset/liability/equity transactions don't affect P&L

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


def compute_pl(
    db: Session,
    period: AccountingPeriod,
) -> PLReport:
    """P&L for a single period, computed from APPROVED transactions only."""
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
    )


def compute_cash(
    db: Session,
    period: AccountingPeriod,
) -> CashSnapshot:
    """Cash position for a period. Approved transactions only."""
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
    )


def compute_kpis(
    db: Session,
    period: AccountingPeriod,
) -> KPISet:
    """KPI tile values."""
    pl = compute_pl(db, period)
    txs = db.scalars(approved_transactions_for_period(period.id)).all()

    gm_pct: Decimal | None = None
    if pl.revenue > 0:
        gm_pct = (pl.gross_profit / pl.revenue * Decimal(100)).quantize(Decimal("0.1"))

    # Uncategorised includes both unapproved (not in `txs` since approved-only)
    # AND approved-but-no-account. The latter is what we report here, because
    # the unapproved ones are tracked separately on the review page.
    total_approved = len(txs)
    no_account = sum(1 for t in txs if t.account_id is None)
    unc_pct = int((no_account / total_approved) * 100) if total_approved else 0

    top_expenses = sorted(
        pl.cogs_lines + pl.opex_lines,
        key=lambda c: c.total,
        reverse=True,
    )[:3]

    return KPISet(
        period_label=f"{period.year:04d}-{period.month:02d}",
        revenue=pl.revenue,
        net_profit=pl.net_profit,
        gross_margin_pct=gm_pct,
        transaction_count=total_approved,
        uncategorised_pct=unc_pct,
        top_expense_lines=top_expenses,
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


def compute_comparison(
    db: Session,
    period: AccountingPeriod,
) -> PeriodComparison:
    """P&L for the period plus prior period and prior year, where available."""
    current = compute_pl(db, period)

    # Prior period: previous month
    pp_year, pp_month = period.year, period.month - 1
    if pp_month == 0:
        pp_month = 12
        pp_year -= 1
    pp_period = find_period(db, period.client_id, pp_year, pp_month)
    prior_period = compute_pl(db, pp_period) if pp_period else None

    # Prior year: same month, last year
    py_period = find_period(db, period.client_id, period.year - 1, period.month)
    prior_year = compute_pl(db, py_period) if py_period else None

    return PeriodComparison(
        current=current,
        prior_period=prior_period,
        prior_year=prior_year,
    )
