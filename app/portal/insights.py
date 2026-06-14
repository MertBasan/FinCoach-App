"""Deterministic comparison label logic for the SME portal KPI tiles.

No AI — all labels are computed from two consecutive published snapshots.
"""
from __future__ import annotations

from app.locale.format import TR_MONTHS


def _fmt_pct(value: float) -> str:
    """Format to 1 decimal with Turkish separator: 12.3 → '12,3'"""
    s = f"{abs(value):.1f}"
    return s.replace(".", ",")


def _gross_margin_pct(snap) -> float | None:
    """gross_profit / revenue * 100, or None if not computable."""
    try:
        rev = float(snap.revenue)
        gp = float(snap.gross_profit)
        if rev == 0:
            return None
        return gp / rev * 100
    except (TypeError, AttributeError):
        return None


def _compare_simple(current, prior) -> dict:
    """Compare two scalar values (revenue or net_profit)."""
    no_prior = {
        "text": "Karşılaştırma için önceki dönem bekleniyor",
        "direction": "none",
    }
    if prior is None or current is None:
        return no_prior

    prior_f = float(prior)
    current_f = float(current)

    if prior_f == 0:
        if current_f != 0:
            return {
                "text": f"Geçen ay veri yok — bu dönem {current_f:,.2f}",
                "direction": "none",
            }
        return {"text": "Geçen ayla aynı seviyede", "direction": "flat"}

    pct = (current_f - prior_f) / abs(prior_f) * 100
    pct_r = round(pct, 1)

    if pct_r > 0:
        return {
            "text": f"Geçen aya göre %{_fmt_pct(pct_r)} artış",
            "direction": "up",
        }
    if pct_r < 0:
        return {
            "text": f"Geçen aya göre %{_fmt_pct(pct_r)} düşüş",
            "direction": "down",
        }
    return {"text": "Geçen ayla aynı seviyede", "direction": "flat"}


def _compare_margin(current_margin: float | None, prior_margin: float | None) -> dict:
    """Compare gross margin in percentage points (not % of %)."""
    no_prior = {
        "text": "Karşılaştırma için önceki dönem bekleniyor",
        "direction": "none",
    }
    if current_margin is None or prior_margin is None:
        return no_prior

    diff = round(current_margin - prior_margin, 1)

    if diff > 0:
        return {
            "text": f"Geçen aya göre {_fmt_pct(diff)} puan artış",
            "direction": "up",
        }
    if diff < 0:
        return {
            "text": f"Geçen aya göre {_fmt_pct(diff)} puan düşüş",
            "direction": "down",
        }
    return {"text": "Geçen ayla aynı seviyede", "direction": "flat"}


def compute_comparison_labels(snapshot, prior_snapshot) -> dict:
    """Return comparison label dicts for the three KPI tiles.

    Keys: 'revenue', 'net_profit', 'gross_margin'
    Each value: {'text': str, 'direction': 'up'|'down'|'flat'|'none'}
    """
    no_prior_label = {
        "text": "Karşılaştırma için önceki dönem bekleniyor",
        "direction": "none",
    }

    if prior_snapshot is None:
        return {
            "revenue": no_prior_label,
            "net_profit": no_prior_label,
            "gross_margin": no_prior_label,
        }

    return {
        "revenue": _compare_simple(snapshot.revenue, prior_snapshot.revenue),
        "net_profit": _compare_simple(snapshot.net_profit, prior_snapshot.net_profit),
        "gross_margin": _compare_margin(
            _gross_margin_pct(snapshot),
            _gross_margin_pct(prior_snapshot),
        ),
    }


def period_label_tr(year: int, month: int) -> str:
    """'Mayıs 2026' from year+month ints."""
    return f"{TR_MONTHS[month - 1]} {year}"
