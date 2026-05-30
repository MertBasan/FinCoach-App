"""
Default chart of accounts for Turkish SMEs — Tek Düzen Hesap Planı (TDHP).

TDHP is government-mandated; the numbering scheme is regulated and must
follow exactly. This is a curated SME-appropriate subset (~30 accounts).
The full TDHP has ~200 entries for large corporates; we don't seed those.

Format: (code, name, type, is_cogs, parent_code).

`is_cogs` matters for the reporting engine — it identifies cost-of-sales
accounts explicitly, instead of guessing from the code prefix. The UK chart
uses 5000s for COGS; TDHP uses 621 and 622.

Type mapping per TDHP convention:
  100s, 200s         → asset
  257 specifically   → asset but contra (Birikmiş Amortismanlar)
  300s, 400s         → liability
  500s               → equity
  600/601/642/646    → income
  610/611/656/660    → income (contra; revenue reductions and FX losses
                       are journalled to revenue-side accounts)
  621/622            → expense AND is_cogs=True
  632/760/770/689    → expense
  690/692            → computed (period P&L), not user-postable
"""

# (code, name, type, is_cogs, parent_code)
DEFAULT_TDHP_SME: list[tuple[str, str, str, bool, str | None]] = [
    # ─────── 100s — Dönen Varlıklar (Current Assets) ───────
    ("100", "Kasa",                                 "asset",     False, None),
    ("102", "Bankalar",                             "asset",     False, None),
    ("108", "Diğer Hazır Değerler",                 "asset",     False, None),
    ("120", "Alıcılar",                             "asset",     False, None),
    ("121", "Alacak Senetleri",                     "asset",     False, None),
    ("153", "Ticari Mallar",                        "asset",     False, None),
    ("191", "İndirilecek KDV",                      "asset",     False, None),

    # ─────── 200s — Duran Varlıklar (Fixed Assets) ───────
    ("252", "Binalar",                              "asset",     False, None),
    ("253", "Tesis, Makine ve Cihazlar",            "asset",     False, None),
    ("254", "Taşıtlar",                             "asset",     False, None),
    ("255", "Demirbaşlar",                          "asset",     False, None),
    # 257 is a contra-asset — treated as asset in the type enum, but
    # represents accumulated depreciation. Sign handling at posting time.
    ("257", "Birikmiş Amortismanlar",               "asset",     False, None),

    # ─────── 300s — Kısa Vadeli Yabancı Kaynaklar (ST Liabilities) ───────
    ("300", "Banka Kredileri",                      "liability", False, None),
    ("320", "Satıcılar",                            "liability", False, None),
    ("321", "Borç Senetleri",                       "liability", False, None),
    ("335", "Personele Borçlar",                    "liability", False, None),
    ("360", "Ödenecek Vergi ve Fonlar",             "liability", False, None),
    ("361", "Ödenecek Sosyal Güvenlik Kesintileri", "liability", False, None),
    ("391", "Hesaplanan KDV",                       "liability", False, None),

    # ─────── 400s — Uzun Vadeli Yabancı Kaynaklar (LT Liabilities) ───────
    ("400", "Banka Kredileri (Uzun Vadeli)",        "liability", False, None),

    # ─────── 500s — Özkaynaklar (Equity) ───────
    ("500", "Sermaye",                              "equity",    False, None),
    ("540", "Yasal Yedekler",                       "equity",    False, None),
    ("570", "Geçmiş Yıllar Kârları",                "equity",    False, None),
    ("590", "Dönem Net Kârı",                       "equity",    False, None),

    # ─────── 600s — Gelir Tablosu Hesapları ───────
    # Revenue
    ("600", "Yurtiçi Satışlar",                     "income",    False, None),
    ("601", "Yurtdışı Satışlar",                    "income",    False, None),
    # Sales returns and discounts — contra-revenue (typed as income so
    # they aggregate into revenue lines; sign convention handles reduction)
    ("610", "Satıştan İadeler",                     "income",    False, None),
    ("611", "Satış İskontoları",                    "income",    False, None),
    # COGS — flagged is_cogs=True so the engine splits them out of opex
    ("621", "Satılan Ticari Mallar Maliyeti",       "expense",   True,  None),
    ("622", "Satılan Hizmet Maliyeti",              "expense",   True,  None),
    # Operating expense (this is where most expenses land in SME practice)
    ("632", "Genel Yönetim Giderleri",              "expense",   False, None),
    # Financial income
    ("642", "Faiz Gelirleri",                       "income",    False, None),
    ("646", "Kambiyo Kârları",                      "income",    False, None),
    # Financial expense
    ("656", "Kambiyo Zararları",                    "expense",   False, None),
    ("660", "Kısa Vadeli Borçlanma Giderleri",      "expense",   False, None),
    # Extraordinary
    ("689", "Diğer Olağandışı Gider ve Zararlar",   "expense",   False, None),

    # ─────── 700s — Detay Gider Hesapları (Detailed Expense Tracking) ───────
    ("760", "Pazarlama, Satış ve Dağıtım Giderleri", "expense",  False, None),
    ("770", "Genel Yönetim Giderleri (Detay)",       "expense",  False, None),

    # Note: 690 (Dönem Kârı veya Zararı) and 692 (Dönem Net Kârı veya Zararı)
    # are NOT seeded. These represent the computed period result and would
    # be system-posted at month-end close, not user-categorised.
]


def seed_default_coa(db, firm_id, client_id) -> int:
    """Create the default chart of accounts for a client.
    Idempotent — returns 0 if any account already exists for this client.
    Returns count created otherwise."""
    from sqlalchemy import select
    from app.db.models import Account

    existing = db.scalar(
        select(Account.id).where(Account.client_id == client_id).limit(1)
    )
    if existing:
        return 0

    by_code: dict[str, Account] = {}
    for code, name, type_, is_cogs, _parent in DEFAULT_TDHP_SME:
        a = Account(
            firm_id=firm_id, client_id=client_id,
            code=code, name=name, type=type_,
            is_cogs=is_cogs,
        )
        db.add(a)
        db.flush()
        by_code[code] = a

    for code, _, _, _, parent_code in DEFAULT_TDHP_SME:
        if parent_code and parent_code in by_code:
            by_code[code].parent_id = by_code[parent_code].id

    db.flush()
    return len(by_code)


# Backwards-compatible export name (other modules may import this constant)
DEFAULT_COA = DEFAULT_TDHP_SME
