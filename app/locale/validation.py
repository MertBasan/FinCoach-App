"""Validation for Turkish tax identifiers.

VKN  (Vergi Kimlik Numarası):   10 digits, company tax ID
TCKN (T.C. Kimlik Numarası):    11 digits, individual tax ID

We do basic format validation only (length + numeric). The full TCKN
checksum algorithm exists but accountants paste IDs from many sources;
being too strict means rejecting valid IDs that have a leading apostrophe
or spaces from Excel. Strict checksum validation can come later as a
warning, not a hard reject.
"""
import re


def clean_tax_id(raw: str | None) -> str:
    """Strip whitespace and non-digit characters; return the digits."""
    if not raw:
        return ""
    return re.sub(r"\D+", "", raw)


def validate_vkn(raw: str | None) -> bool:
    """A VKN is exactly 10 digits."""
    cleaned = clean_tax_id(raw)
    return len(cleaned) == 10 and cleaned.isdigit()


def validate_tckn(raw: str | None) -> bool:
    """A TCKN is exactly 11 digits, the first must not be zero."""
    cleaned = clean_tax_id(raw)
    if len(cleaned) != 11 or not cleaned.isdigit():
        return False
    if cleaned[0] == "0":
        return False
    return True
