"""add audio_url to vdict_words

Revision ID: e3f7a91b0c42
Revises: da6af16b2716
Create Date: 2026-05-26 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3f7a91b0c42"
down_revision: str | None = "da6af16b2716"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vdict_words",
        sa.Column("audio_url", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vdict_words", "audio_url")
