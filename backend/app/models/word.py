import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Word(Base):
    __tablename__ = "words"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    text: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    word_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pronunciation: Mapped[str | None] = mapped_column(String(128), nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    example: Mapped[str | None] = mapped_column(Text, nullable=True)
    synonyms: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    collocations: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    difficulty: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_sentence: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    up_vote: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    down_vote: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    query_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    last_queried_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class GameResult(Base):
    __tablename__ = "game_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    total_words: Mapped[int] = mapped_column(nullable=False)
    correct: Mapped[int] = mapped_column(nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(nullable=True)
    played_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
