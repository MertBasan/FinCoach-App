"""KDV (Katma Değer Vergisi / VAT) rate constants for Türkiye.

Rates as of mid-2024 onwards. Reference only — no logic here yet.
KDV-related features (KDV beyannamesi, automated VAT classification, etc.)
are out of scope per the localization brief.
"""

KDV_STANDARD = 0.20       # 20% — standard rate (most goods and services)
KDV_REDUCED = 0.10        # 10% — food, healthcare, accommodation
KDV_SUPER_REDUCED = 0.01  # 1% — basic foodstuffs, newspapers

# 0% includes exports and certain exempt categories
KDV_RATES = [0.00, 0.01, 0.10, 0.20]
