"""Phase 4: publish columns on period_snapshots (SME portal)

Revision ID: 0006_phase4
Revises: 0005_phase3
Create Date: 2026-06-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "0006_phase4"
down_revision: Union[str, None] = "0005_phase3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("period_snapshots", sa.Column(
        "published", sa.Boolean(), nullable=False, server_default=sa.text("false"),
    ))
    op.add_column("period_snapshots", sa.Column(
        "published_at", sa.DateTime(timezone=True), nullable=True,
    ))
    op.add_column("period_snapshots", sa.Column(
        "published_by_id", UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    ))
    op.add_column("period_snapshots", sa.Column(
        "accountant_note", sa.Text(), nullable=True,
    ))
    # Explicit backfill per brief (already default false)
    op.execute("UPDATE period_snapshots SET published = false")


def downgrade() -> None:
    op.drop_column("period_snapshots", "accountant_note")
    op.drop_column("period_snapshots", "published_by_id")
    op.drop_column("period_snapshots", "published_at")
    op.drop_column("period_snapshots", "published")
