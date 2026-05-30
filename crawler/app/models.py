from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class VdictWord(Base):
    """Mirrors backend/app/models/vdict_word.py — must stay in sync with that model."""

    __tablename__ = "vdict_words"

    vdict_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=False
    )
    text: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    ipa: Mapped[str | None] = mapped_column(String(256), nullable=True)
    word_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meanings: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    friendly: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    examples: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    audio_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
