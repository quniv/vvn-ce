from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class VdictWord(Base):
    """Read-only seed data crawled from vdict.com (dict_id=1, English → Vietnamese).

    Populated by `python -m app.jobs.crawl_vdict`. Used by `/api/explain` as a primary
    lookup before falling back to the LLM (Phase 8b — not in this CR).
    """

    __tablename__ = "vdict_words"

    # vdict's internal word_id is provided by the crawler — no autoincrement
    vdict_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=False
    )
    text: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    ipa: Mapped[str | None] = mapped_column(String(256), nullable=True)
    word_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # [{pos, items: [{vi, description}]}]
    meanings: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    # {synonyms: [...], phrasal_verbs: [{phrase, vi, examples}], idioms: [...]}
    friendly: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    # [{en, vi}]
    examples: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    audio_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
