"""
Transaction staging.

When the bank-statement extractor produces valid rows, this module turns
them into unapproved Transaction records in the spine. The accountant
reviews and approves via /clients/{id}/transactions before the rows
become visible to reports/KPIs.

Why "staging" not "ingestion": these rows are NOT trustworthy until the
accountant signs them off. They live with approval_status='unapproved'
and are explicitly excluded from analytical queries.
"""
from datetime import date as _date
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Transaction
from app.spine.periods import get_or_create_period


def _parse_extraction_date(s: str) -> _date | None:
    """Extractor outputs dates in DD-MM-YYYY (see _normalize_date in
    bank_extraction)."""
    if not s:
        return None
    try:
        d, m, y = s.split("-")
        return _date(int(y), int(m), int(d))
    except (ValueError, IndexError):
        return None


def stage_bank_statement_rows(
    db: Session,
    *,
    firm_id: UUID,
    client_id: UUID,
    source_document_id: UUID | None,
    rows: Iterable,
    created_by_id: UUID | None,
) -> tuple[int, int]:
    """Stage extracted bank-statement rows as unapproved Transactions.

    Returns (staged, skipped). Skipped rows are those with unparseable dates
    or duplicate signatures within the same (client, date, amount, description)
    combination — duplicates are common when the accountant re-runs an
    extraction on the same PDF.

    RLS context must already be set to firm_id.
    """
    staged = 0
    skipped = 0
    seen_signatures: set[tuple] = set()

    for r in rows:
        tx_date = _parse_extraction_date(r.date)
        if tx_date is None:
            skipped += 1
            continue

        # Convert Decimal-from-extractor into our DB type
        try:
            amount = Decimal(r.amount)
        except Exception:
            skipped += 1
            continue

        # Dedupe within this batch
        signature = (str(client_id), tx_date.isoformat(), str(amount), r.description.strip())
        if signature in seen_signatures:
            skipped += 1
            continue
        seen_signatures.add(signature)

        period = get_or_create_period(db, firm_id, client_id, tx_date)

        raw_ref = {
            "extractor_date": r.date,
            "extractor_time": getattr(r, "time", ""),
            "extractor_balance": str(r.balance),
            "extractor_receipt": getattr(r, "receipt", ""),
            "extractor_description": r.description,
        }

        db.add(Transaction(
            firm_id=firm_id,
            client_id=client_id,
            period_id=period.id,
            account_id=None,  # uncategorised until accountant codes it
            date=tx_date,
            description=r.description.strip(),
            amount=amount,
            source="pdf_extraction",
            raw_reference=raw_ref,
            source_document_id=source_document_id,
            approval_status="unapproved",
            created_by_id=created_by_id,
        ))
        staged += 1

    db.flush()
    return staged, skipped
