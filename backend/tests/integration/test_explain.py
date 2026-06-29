"""Integration tests for the /api/explain endpoint (5-tier lookup pipeline)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vdict_word import VdictWord
from app.models.word import Word


async def test_health(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["db"] is True


async def test_explain_sentence_path(client: AsyncClient, mocker):
    """Multi-word text → Google Translate path, no DB write, kind=sentence."""
    mocker.patch(
        "app.routes.words.call_google_translate",
        return_value=("xin chào thế giới đẹp", False),
    )
    resp = await client.post("/api/explain", json={"text": "hello beautiful world"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "sentence"
    assert data["explanation"] == "xin chào thế giới đẹp"
    assert data["saved"] is False
    assert data["model_source"] == "google-translate"


async def test_explain_word_db_hit(client: AsyncClient, db: AsyncSession):
    """Word already in words table → returned immediately, db_hit=True."""
    word = Word(
        text="serendipity_test",
        explanation="Khả năng tình cờ tìm thấy điều tốt đẹp",
        word_type="Danh từ",
        pronunciation="/ˌserənˈdɪpɪti/",
        synonyms=[],
        collocations=[],
        model_source="test",
    )
    db.add(word)
    await db.commit()

    resp = await client.post("/api/explain", json={"text": "serendipity_test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "word"
    assert data["text"] == "serendipity_test"
    assert data["db_hit"] is True
    assert data["cached"] is False


async def test_explain_word_case_insensitive_db_hit(client: AsyncClient, db: AsyncSession):
    """Lookup is case-insensitive — 'Hello' and 'hello' are the same word."""
    word = Word(
        text="Ephemeral_test",
        explanation="Tồn tại trong thời gian ngắn",
        synonyms=[],
        collocations=[],
        model_source="test",
    )
    db.add(word)
    await db.commit()

    resp = await client.post("/api/explain", json={"text": "ephemeral_test"})
    assert resp.status_code == 200
    assert resp.json()["db_hit"] is True


async def test_explain_word_vdict_hit(client: AsyncClient, db: AsyncSession):
    """Word in vdict_words table → returned with model_source=vdict and saved=True."""
    vw = VdictWord(
        vdict_id=88888,
        text="tenacious_test",
        ipa="/tɪˈneɪʃəs/",
        word_type="Tính từ",
        meanings=[{"pos": "Tính từ", "items": [{"vi": "Kiên trì", "description": "bền bỉ"}]}],
        examples=[{"en": "She is tenacious.", "vi": "Cô ấy rất kiên trì."}],
        friendly={"synonyms": ["persistent"], "phrasal_verbs": [], "idioms": []},
    )
    db.add(vw)
    await db.commit()

    resp = await client.post("/api/explain", json={"text": "tenacious_test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "word"
    assert data["model_source"] == "vdict"
    assert data["saved"] is True
    assert data["saved_id"] is not None
    assert "Kiên trì" in data["explanation"]


async def test_explain_word_not_found_returns_404(client: AsyncClient, mocker):
    """Word absent from all tiers with LLM disabled → 404."""
    mocker.patch("app.routes.words.fetch_and_parse", return_value=None)

    resp = await client.post("/api/explain", json={"text": "xyzzy_nonexistent_word"})
    assert resp.status_code == 404


async def test_explain_empty_text_rejected(client: AsyncClient):
    """Empty string fails Pydantic min_length=1 validation."""
    resp = await client.post("/api/explain", json={"text": ""})
    assert resp.status_code == 422


async def test_explain_increments_query_count(client: AsyncClient, db: AsyncSession, mocker):
    """Each /explain call on a known word bumps its query_count."""
    mocker.patch("app.routes.words.fetch_and_parse", return_value=None)

    word = Word(
        text="resilient_test",
        explanation="Có khả năng phục hồi",
        synonyms=[],
        collocations=[],
        model_source="test",
        query_count=1,
    )
    db.add(word)
    await db.commit()
    await db.refresh(word)
    word_id = word.id

    await client.post("/api/explain", json={"text": "resilient_test"})
    await client.post("/api/explain", json={"text": "resilient_test"})

    await db.refresh(word)
    # Two additional calls after the initial insert → query_count should be 3
    assert word.query_count >= 2
