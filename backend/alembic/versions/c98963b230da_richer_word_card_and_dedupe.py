"""richer word card and dedupe

Revision ID: c98963b230da
Revises: dd624386b50f
Create Date: 2026-05-24 17:00:54.419248

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c98963b230da'
down_revision: Union[str, Sequence[str], None] = 'dd624386b50f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Add new columns
    op.add_column('words', sa.Column('synonyms', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False))
    op.add_column('words', sa.Column('collocations', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False))
    op.add_column('words', sa.Column('difficulty', sa.String(length=16), nullable=True))
    op.add_column('words', sa.Column('query_count', sa.Integer(), server_default='1', nullable=False))
    op.add_column('words', sa.Column('last_queried_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))

    # 2. Collapse duplicates by LOWER(text). For each duplicate group:
    #    - keep the row with the highest net score (up_vote - down_vote)
    #      tie-broken by most recent created_at
    #    - sum query_count from all rows into the kept row
    #    - delete the rest
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                LOWER(text) AS key,
                ROW_NUMBER() OVER (
                    PARTITION BY LOWER(text)
                    ORDER BY (up_vote - down_vote) DESC, created_at DESC
                ) AS rn,
                SUM(query_count) OVER (PARTITION BY LOWER(text)) AS total_count
            FROM words
        ),
        keepers AS (
            SELECT id, total_count FROM ranked WHERE rn = 1
        )
        UPDATE words
        SET query_count = keepers.total_count
        FROM keepers
        WHERE words.id = keepers.id
          AND words.query_count <> keepers.total_count;
        """
    )
    op.execute(
        """
        DELETE FROM words
        WHERE id IN (
            SELECT id FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY LOWER(text)
                        ORDER BY (up_vote - down_vote) DESC, created_at DESC
                    ) AS rn
                FROM words
            ) ranked
            WHERE rn > 1
        );
        """
    )

    # 3. Now safe to create the case-insensitive unique index
    op.create_index(
        'uq_words_lower_text',
        'words',
        [sa.text('LOWER(text)')],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_words_lower_text', table_name='words')
    op.drop_column('words', 'last_queried_at')
    op.drop_column('words', 'query_count')
    op.drop_column('words', 'difficulty')
    op.drop_column('words', 'collocations')
    op.drop_column('words', 'synonyms')
