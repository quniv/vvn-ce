import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ExplainRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    source_url: str | None = None


class KeywordItem(BaseModel):
    text: str
    word_type: str | None = None
    pronunciation: str | None = None
    explanation: str
    example: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    collocations: list[str] = Field(default_factory=list)
    difficulty: str | None = None


class MeaningItem(BaseModel):
    vi: str
    description: str


class MeaningGroup(BaseModel):
    pos: str
    items: list[MeaningItem] = Field(default_factory=list)


class ExplainResponse(BaseModel):
    kind: str  # "word" or "sentence"
    text: str
    word_type: str | None = None
    pronunciation: str | None = None
    explanation: str
    example: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    collocations: list[str] = Field(default_factory=list)
    difficulty: str | None = None
    keywords: list[KeywordItem] = Field(default_factory=list)
    saved: bool = False
    saved_id: uuid.UUID | None = None
    model_source: str | None = None
    query_count: int = 1
    cached: bool = False    # True if served from Redis
    db_hit: bool = False    # True if served from Postgres (skipped LLM)
    audio_url: str | None = None  # vdict audio: https://audio.vdict.com/1/{vdict_id}.mp3
    vdict_examples: list[dict] = Field(default_factory=list)  # [{en, vi}] bilingual pairs
    meanings: list[MeaningGroup] = Field(default_factory=list)  # structured pos-grouped definitions


class SaveKeywordsRequest(BaseModel):
    source_sentence: str
    source_url: str | None = None
    keywords: list[KeywordItem]


class WordRead(BaseModel):
    id: uuid.UUID
    text: str
    word_type: str | None
    pronunciation: str | None
    explanation: str
    example: str | None
    synonyms: list[str] = Field(default_factory=list)
    collocations: list[str] = Field(default_factory=list)
    difficulty: str | None = None
    source_url: str | None
    source_sentence: str | None
    model_source: str | None
    query_count: int
    last_queried_at: datetime
    created_at: datetime


class GameWordPair(BaseModel):
    id: uuid.UUID
    word: str
    definition: str


class GameTodayResponse(BaseModel):
    pairs: list[GameWordPair]


class GameResultRequest(BaseModel):
    total_words: int = Field(..., ge=0)
    correct: int = Field(..., ge=0)
    duration_seconds: int | None = None
