"""vdict_words: change friendly column default from [] to {}

Revision ID: f1b8d293a047
Revises: e3f7a91b0c42
Create Date: 2026-05-26 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1b8d293a047"
down_revision: str | None = "e3f7a91b0c42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "vdict_words",
        "friendly",
        server_default="{}",
        existing_type=sa.dialects.postgresql.JSONB(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "vdict_words",
        "friendly",
        server_default="[]",
        existing_type=sa.dialects.postgresql.JSONB(),
        existing_nullable=False,
    )
