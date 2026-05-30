"""Add documents.source column

Revision ID: 0002_document_source
Revises: 0001_initial
Create Date: 2026-05-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_document_source"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "source",
            sa.String(64),
            nullable=False,
            server_default="manual_upload",
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "source")
