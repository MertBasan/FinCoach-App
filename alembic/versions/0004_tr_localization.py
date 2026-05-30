"""Localization deltas: is_cogs flag on accounts, VKN/TCKN on clients

Revision ID: 0004_tr_localization
Revises: 0003_spine
Create Date: 2026-05-30

This migration carries two changes:

1. `accounts.is_cogs` — boolean flag identifying cost-of-sales accounts.
   The UK seed sets this on 5000-series codes (5000 Cost of Sales,
   5010 Materials, 5020 Subcontractors). The Turkish TDHP seed sets it on
   621 (Satılan Ticari Mallar Maliyeti) and 622 (Satılan Hizmet Maliyeti).
   Replaces the brittle "code starts with 5" heuristic in reporting/engine.py.

2. `clients.vkn` and `clients.tckn` — Turkish tax identifiers. Optional;
   only used in the Turkish version. Kept in the shared migration so the
   schema stays identical between locales (per the localization brief —
   one branch, one schema).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_tr_localization"
down_revision: Union[str, None] = "0003_spine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. is_cogs flag on accounts
    op.add_column(
        "accounts",
        sa.Column(
            "is_cogs", sa.Boolean,
            nullable=False, server_default=sa.text("false"),
        ),
    )

    # 2. VKN/TCKN tax identifiers on clients (optional)
    op.add_column(
        "clients",
        sa.Column("vkn", sa.String(10), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("tckn", sa.String(11), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clients", "tckn")
    op.drop_column("clients", "vkn")
    op.drop_column("accounts", "is_cogs")
