"""Unit tests for pure helper functions (no DB, no Redis, no HTTP)."""

from types import SimpleNamespace

from app.routes.words import _is_wordish
from app.services.cache import cache_key
from app.services.vdict import vdict_to_explain_response


class TestIsWordish:
    def test_single_word(self):
        assert _is_wordish("hello") is True

    def test_single_word_with_leading_whitespace(self):
        assert _is_wordish("  hello  ") is True

    def test_two_words(self):
        assert _is_wordish("hello world") is False

    def test_three_words(self):
        assert _is_wordish("the quick fox") is False

    def test_hyphenated_counts_as_one(self):
        # "well-known" has no space — treated as a single token
        assert _is_wordish("well-known") is True


class TestCacheKey:
    def test_same_key_for_same_input(self):
        assert cache_key("model-a", "hello") == cache_key("model-a", "hello")

    def test_case_insensitive(self):
        assert cache_key("model", "Hello") == cache_key("model", "hello")

    def test_strips_whitespace(self):
        assert cache_key("model", "  hello  ") == cache_key("model", "hello")

    def test_different_model_different_key(self):
        assert cache_key("model-a", "hello") != cache_key("model-b", "hello")

    def test_different_text_different_key(self):
        assert cache_key("model", "hello") != cache_key("model", "world")

    def test_key_format(self):
        key = cache_key("gpt-4", "test")
        assert key.startswith("explain:gpt-4:")


class TestVdictToExplainResponse:
    def _make_vdict_word(self, **overrides):
        defaults = dict(
            text="abandon",
            word_type="Động từ",
            ipa="/əˈbændən/",
            meanings=[
                {
                    "pos": "Động từ",
                    "items": [{"vi": "Từ bỏ", "description": "rời bỏ hoàn toàn"}],
                }
            ],
            examples=[{"en": "He abandoned the ship.", "vi": "Anh ấy bỏ tàu."}],
            friendly={
                "synonyms": ["desert", "forsake"],
                "phrasal_verbs": [{"phrase": "abandon to", "vi": "giao phó cho"}],
                "idioms": [],
            },
            audio_url="https://audio.vdict.com/1/12345.mp3",
        )
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_kind_is_word(self):
        resp = vdict_to_explain_response(
            self._make_vdict_word(), cached=False, db_hit=True
        )
        assert resp.kind == "word"

    def test_text_passthrough(self):
        resp = vdict_to_explain_response(
            self._make_vdict_word(), cached=False, db_hit=True
        )
        assert resp.text == "abandon"

    def test_model_source_is_vdict(self):
        resp = vdict_to_explain_response(
            self._make_vdict_word(), cached=False, db_hit=True
        )
        assert resp.model_source == "vdict"

    def test_explanation_includes_pos_and_meaning(self):
        resp = vdict_to_explain_response(
            self._make_vdict_word(), cached=False, db_hit=True
        )
        assert "Động từ" in resp.explanation
        assert "Từ bỏ" in resp.explanation

    def test_first_example_becomes_example_field(self):
        resp = vdict_to_explain_response(
            self._make_vdict_word(), cached=False, db_hit=True
        )
        assert resp.example == "He abandoned the ship."

    def test_synonyms_extracted(self):
        resp = vdict_to_explain_response(
            self._make_vdict_word(), cached=False, db_hit=True
        )
        assert "desert" in resp.synonyms
        assert "forsake" in resp.synonyms

    def test_phrasal_verb_becomes_collocation(self):
        resp = vdict_to_explain_response(
            self._make_vdict_word(), cached=False, db_hit=True
        )
        assert any("abandon to" in c for c in resp.collocations)

    def test_audio_url_passthrough(self):
        resp = vdict_to_explain_response(
            self._make_vdict_word(), cached=False, db_hit=True
        )
        assert resp.audio_url == "https://audio.vdict.com/1/12345.mp3"

    def test_vdict_examples_populated(self):
        resp = vdict_to_explain_response(
            self._make_vdict_word(), cached=False, db_hit=True
        )
        assert len(resp.vdict_examples) == 1
        assert resp.vdict_examples[0]["en"] == "He abandoned the ship."

    def test_cached_flag_passthrough(self):
        resp = vdict_to_explain_response(
            self._make_vdict_word(), cached=True, db_hit=True
        )
        assert resp.cached is True

    def test_empty_meanings_gives_fallback_explanation(self):
        vw = self._make_vdict_word(meanings=[])
        resp = vdict_to_explain_response(vw, cached=False, db_hit=False)
        assert resp.explanation == "(no definition available)"

    def test_non_dict_friendly_handled_gracefully(self):
        vw = self._make_vdict_word(friendly=[])  # invalid type — should not crash
        resp = vdict_to_explain_response(vw, cached=False, db_hit=False)
        assert resp.synonyms == []
        assert resp.collocations == []
