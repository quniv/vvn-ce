import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WordVote(Base):
    __tablename__ = "word_votes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    word_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("words.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_email: Mapped[str] = mapped_column(String(320), nullable=False)
    direction: Mapped[str] = mapped_column(String(4), nullable=False)
    voted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("word_id", "user_email", name="uq_word_votes_word_user"),
        CheckConstraint("direction IN ('up', 'down')", name="ck_word_votes_direction"),
    )
