"""Turkish formatting helpers.

Money: 1.234,56 ₺   (period thousands, comma decimal, ₺ after the number)
Date:  30.05.2026   (DD.MM.YYYY)
Long:  30 Mayıs 2026
Period: Mayıs 2026 (from a YYYY-MM string or year/month integers)

Do not hardcode UK formatting anywhere else in the codebase. Always go
through these helpers.
"""
from datetime import date
from decimal import Decimal


TR_MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]

CURRENCY_SYMBOL = "₺"


def _format_number_tr(value: Decimal | float | int, decimals: int = 2) -> str:
    """Format a number using Turkish separators (1.234,56)."""
    if value is None:
        return "—"
    # Build with English locale, then swap separators. Two-step swap
    # avoids the period→comma→period collision: '.' -> 'X' (temp),
    # ',' -> '.', 'X' -> ','.
    if isinstance(value, Decimal):
        # Use the Decimal directly to preserve precision
        s = f"{value:,.{decimals}f}"
    else:
        s = f"{float(value):,.{decimals}f}"
    return s.replace(".", "X").replace(",", ".").replace("X", ",")


def format_money_tr(amount: Decimal | float | int | None,
                    *,
                    include_symbol: bool = True,
                    sign: bool = False) -> str:
    """Format an amount the Turkish way: '1.234,56 ₺'.

    Pass sign=True for accounting-style explicit + for positives (used in
    cash inflows so '+ 1.000,00 ₺' reads naturally)."""
    if amount is None:
        return "—"
    # Handle Decimal vs float uniformly via Decimal
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))

    abs_str = _format_number_tr(abs(amount), decimals=2)
    if amount < 0:
        prefix = "-"
    elif sign and amount > 0:
        prefix = "+"
    else:
        prefix = ""
    body = f"{prefix}{abs_str}"
    return f"{body} {CURRENCY_SYMBOL}" if include_symbol else body


def format_date_tr(d: date | None) -> str:
    """30.05.2026"""
    if d is None:
        return "—"
    return f"{d.day:02d}.{d.month:02d}.{d.year:04d}"


def format_date_long_tr(d: date | None) -> str:
    """30 Mayıs 2026"""
    if d is None:
        return "—"
    return f"{d.day} {TR_MONTHS[d.month - 1]} {d.year}"


def format_period_tr(period_str: str | None = None,
                     year: int | None = None,
                     month: int | None = None) -> str:
    """Format a period as 'Mayıs 2026'. Accepts either a 'YYYY-MM' string
    or year+month ints."""
    if period_str is not None:
        try:
            y, m = period_str.split("-")
            year, month = int(y), int(m)
        except (ValueError, AttributeError):
            return period_str or "—"
    if year is None or month is None:
        return "—"
    if not 1 <= month <= 12:
        return f"{year}-{month:02d}"
    return f"{TR_MONTHS[month - 1]} {year}"


def format_percent_tr(value: Decimal | float | None,
                       decimals: int = 1) -> str:
    """Format a percentage with Turkish decimal separator: '90,7%'."""
    if value is None:
        return "—"
    return _format_number_tr(value, decimals=decimals) + "%"
