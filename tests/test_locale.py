"""
Locale tests for the Turkish version.

These are pure-Python tests; they don't touch the database except for the
chart-of-accounts seeding test which needs a session.
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db import set_firm_context
from app.db.models import Account, AccountingFirm, Client
from app.locale.format import (
    format_money_tr, format_date_tr, format_date_long_tr,
    format_period_tr, format_percent_tr, TR_MONTHS,
)
from app.locale.validation import (
    validate_vkn, validate_tckn, clean_tax_id,
)
from app.spine.chart_of_accounts import seed_default_coa, DEFAULT_TDHP_SME


# ---------- Money / number formatting ----------

def test_money_format_uses_turkish_separators():
    assert format_money_tr(Decimal("1234.56")) == "1.234,56 ₺"


def test_money_format_zero():
    assert format_money_tr(Decimal("0.00")) == "0,00 ₺"


def test_money_format_large_number():
    assert format_money_tr(Decimal("1234567.89")) == "1.234.567,89 ₺"


def test_money_format_negative():
    assert format_money_tr(Decimal("-1234.56")) == "-1.234,56 ₺"


def test_money_format_sign_positive():
    assert format_money_tr(Decimal("1234.56"), sign=True) == "+1.234,56 ₺"


def test_money_format_without_symbol():
    assert format_money_tr(Decimal("1234.56"), include_symbol=False) == "1.234,56"


def test_money_format_none():
    assert format_money_tr(None) == "—"


def test_money_format_float_input():
    """Accepts float input too, not just Decimal."""
    assert format_money_tr(1234.56) == "1.234,56 ₺"


# ---------- Date formatting ----------

def test_date_format_uses_dd_mm_yyyy():
    assert format_date_tr(date(2026, 5, 30)) == "30.05.2026"


def test_date_format_pads_single_digits():
    assert format_date_tr(date(2026, 1, 3)) == "03.01.2026"


def test_date_format_none():
    assert format_date_tr(None) == "—"


def test_date_long_format_uses_turkish_month():
    assert format_date_long_tr(date(2026, 5, 30)) == "30 Mayıs 2026"


def test_date_long_format_all_months():
    expected = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
                "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    assert TR_MONTHS == expected
    for i, month_name in enumerate(expected, start=1):
        assert format_date_long_tr(date(2026, i, 15)) == f"15 {month_name} 2026"


def test_period_format_from_string():
    assert format_period_tr("2026-05") == "Mayıs 2026"
    assert format_period_tr("2026-12") == "Aralık 2026"
    assert format_period_tr("2025-01") == "Ocak 2025"


def test_period_format_from_ints():
    assert format_period_tr(year=2026, month=5) == "Mayıs 2026"


def test_period_format_invalid_falls_back():
    assert format_period_tr("garbage") == "garbage"
    assert format_period_tr(year=2026, month=13) == "2026-13"


# ---------- Percent formatting ----------

def test_percent_format_turkish_decimal():
    assert format_percent_tr(Decimal("90.7")) == "90,7%"


def test_percent_format_none():
    assert format_percent_tr(None) == "—"


# ---------- VKN / TCKN validation ----------

def test_vkn_field_accepts_10_digits():
    assert validate_vkn("1234567890") is True


def test_vkn_rejects_short_input():
    assert validate_vkn("123456789") is False


def test_vkn_rejects_letters():
    assert validate_vkn("abc") is False
    assert validate_vkn("123abc4567") is False


def test_vkn_rejects_empty():
    assert validate_vkn("") is False
    assert validate_vkn(None) is False


def test_vkn_accepts_with_spaces_after_clean():
    """clean_tax_id should strip non-digits; then validate against the cleaned form."""
    cleaned = clean_tax_id("1234 567 890")
    assert cleaned == "1234567890"
    assert validate_vkn(cleaned) is True


def test_tckn_accepts_11_digits():
    assert validate_tckn("12345678901") is True


def test_tckn_rejects_leading_zero():
    assert validate_tckn("01234567890") is False


def test_tckn_rejects_short():
    assert validate_tckn("1234567890") is False


def test_clean_tax_id_strips_non_digits():
    assert clean_tax_id("12-34 56:7890") == "1234567890"
    assert clean_tax_id("") == ""
    assert clean_tax_id(None) == ""


# ---------- TDHP chart-of-accounts seed ----------

def test_chart_of_accounts_seeds_tdhp(db):
    """A new client gets the TDHP chart of accounts. Spot-check the key codes."""
    firm = AccountingFirm(id=uuid4(), name="Test Firma A.Ş.")
    db.add(firm)
    db.commit()
    set_firm_context(db, str(firm.id))

    client = Client(firm_id=firm.id, name="Test Müşteri")
    db.add(client)
    db.flush()

    created = seed_default_coa(db, firm.id, client.id)
    db.commit()

    assert created > 25, f"Expected ~30 accounts; got {created}"

    # Spot-check codes that should exist with Turkish names
    accounts = {a.code: a for a in db.scalars(select(Account).where(Account.client_id == client.id)).all()}

    assert "100" in accounts and accounts["100"].name == "Kasa"
    assert "102" in accounts and accounts["102"].name == "Bankalar"
    assert "120" in accounts and accounts["120"].name == "Alıcılar"
    assert "191" in accounts and accounts["191"].name == "İndirilecek KDV"
    assert "320" in accounts and accounts["320"].name == "Satıcılar"
    assert "391" in accounts and accounts["391"].name == "Hesaplanan KDV"
    assert "500" in accounts and accounts["500"].name == "Sermaye"
    assert "600" in accounts and accounts["600"].name == "Yurtiçi Satışlar"
    assert "601" in accounts and accounts["601"].name == "Yurtdışı Satışlar"
    assert "621" in accounts and accounts["621"].name == "Satılan Ticari Mallar Maliyeti"
    assert "622" in accounts and accounts["622"].name == "Satılan Hizmet Maliyeti"


def test_tdhp_cogs_flag_set_correctly(db):
    """621 and 622 must be flagged as is_cogs; revenue accounts must not."""
    firm = AccountingFirm(id=uuid4(), name="COGS Test")
    db.add(firm)
    db.commit()
    set_firm_context(db, str(firm.id))
    client = Client(firm_id=firm.id, name="X")
    db.add(client); db.flush()
    seed_default_coa(db, firm.id, client.id)
    db.commit()

    accounts = {a.code: a for a in db.scalars(select(Account).where(Account.client_id == client.id)).all()}

    # COGS accounts
    assert accounts["621"].is_cogs is True
    assert accounts["622"].is_cogs is True
    # NOT COGS
    assert accounts["600"].is_cogs is False
    assert accounts["632"].is_cogs is False
    assert accounts["770"].is_cogs is False


def test_tdhp_seed_is_idempotent(db):
    firm = AccountingFirm(id=uuid4(), name="Idem Test")
    db.add(firm); db.commit()
    set_firm_context(db, str(firm.id))
    client = Client(firm_id=firm.id, name="X")
    db.add(client); db.flush()

    first = seed_default_coa(db, firm.id, client.id)
    db.commit()
    second = seed_default_coa(db, firm.id, client.id)
    db.commit()
    assert first > 0 and second == 0


def test_tdhp_seed_definition_uses_only_valid_types():
    """The TDHP seed entries must use the allowed account type values."""
    allowed = {"asset", "liability", "equity", "income", "expense"}
    for code, name, type_, is_cogs, _parent in DEFAULT_TDHP_SME:
        assert type_ in allowed, f"Code {code} ({name}) has invalid type {type_!r}"
        # is_cogs implies expense
        if is_cogs:
            assert type_ == "expense", f"Code {code} ({name}) is_cogs=True but type={type_!r}"


def test_tdhp_seed_has_no_duplicate_codes():
    codes = [c for c, _, _, _, _ in DEFAULT_TDHP_SME]
    assert len(codes) == len(set(codes)), "Duplicate codes in TDHP seed"
