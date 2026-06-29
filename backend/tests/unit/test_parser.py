"""Unit tests for the vdict HTML parser (pure function, no I/O)."""

from app.jobs.vdict_parser import (
    ParsedEntry,
    _clean_text,
    _extract_word_id,
    parse_entry,
)

# Minimal vdict.com-shaped HTML for "abandon"
_ABANDON_HTML = """
<!DOCTYPE html>
<html><head></head><body>
<h1 class="mb-0">abandon</h1>
<div class="pronunciation">/əˈbændən/</div>
<script>var word = {"word_id": 12345};</script>
<div id="friendlyDefinition">
  <div class="word-type-section">
    <div class="word-type-section">
      <div class="word-type">Định nghĩa</div>
      <ol class="meanings-list">
        <li class="meaning">
          <div class="meaning-value"><p><strong>Động từ</strong></p></div>
          <ul class="examples-list">
            <li class="example">
              <div><strong>Từ bỏ, bỏ rơi</strong>: Hành động rời bỏ</div>
            </li>
          </ul>
        </li>
      </ol>
      <div class="word-type">Ví dụ sử dụng</div>
      <ul class="meanings-list">
        <li class="meaning">
          <ul class="examples-list">
            <li class="example">
              <div>
                <em>He abandoned the sinking ship.</em>
                (Anh ấy đã bỏ rơi con tàu đang chìm.)
              </div>
            </li>
          </ul>
        </li>
      </ul>
      <div class="word-type">Từ đồng nghĩa</div>
      <ul class="meanings-list">
        <li class="meaning">
          <div class="meaning-value">Động từ (Nghĩa 1): Desert, forsake.</div>
        </li>
      </ul>
    </div>
  </div>
</div>
</body></html>
"""


class TestCleanText:
    def test_collapses_whitespace(self):
        assert _clean_text("  hello   world  ") == "hello world"

    def test_strips_newlines(self):
        assert _clean_text("foo\n  \tbar") == "foo bar"

    def test_empty_string(self):
        assert _clean_text("") == ""


class TestExtractWordId:
    def test_finds_word_id(self):
        html = 'var data = {"word_id": 99}'
        assert _extract_word_id(html) == 99

    def test_handles_html_entity_encoding(self):
        html = "var data = {&#34;word_id&#34;: 42};"
        assert _extract_word_id(html) == 42

    def test_returns_none_when_absent(self):
        assert _extract_word_id("<html><body>no id here</body></html>") is None


class TestParseEntry:
    def test_returns_none_for_empty_html(self):
        assert parse_entry("") is None

    def test_returns_none_without_h1_tag(self):
        assert parse_entry("<html><body><p>no h1 here</p></body></html>") is None

    def test_returns_none_without_h1_mb0(self):
        # has <h1 but not class="mb-0"
        assert parse_entry("<html><h1>word</h1></html>") is None

    def test_parses_word_text(self):
        entry = parse_entry(_ABANDON_HTML)
        assert isinstance(entry, ParsedEntry)
        assert entry.text == "abandon"

    def test_parses_ipa(self):
        entry = parse_entry(_ABANDON_HTML)
        assert entry.ipa == "/əˈbændən/"

    def test_parses_vdict_id(self):
        entry = parse_entry(_ABANDON_HTML)
        assert entry.vdict_id == 12345

    def test_derives_audio_url_from_id(self):
        entry = parse_entry(_ABANDON_HTML)
        assert entry.audio_url == "https://audio.vdict.com/1/12345.mp3"

    def test_parses_word_type_from_first_definition(self):
        entry = parse_entry(_ABANDON_HTML)
        assert entry.word_type == "Động từ"

    def test_parses_definition_pos(self):
        entry = parse_entry(_ABANDON_HTML)
        assert len(entry.definitions) == 1
        assert entry.definitions[0].pos == "Động từ"

    def test_parses_definition_item(self):
        entry = parse_entry(_ABANDON_HTML)
        items = entry.definitions[0].items
        assert len(items) == 1
        assert items[0].vi == "Từ bỏ, bỏ rơi"
        assert items[0].description == "Hành động rời bỏ"

    def test_parses_examples(self):
        entry = parse_entry(_ABANDON_HTML)
        assert len(entry.examples) == 1
        assert entry.examples[0].en == "He abandoned the sinking ship."
        assert "Anh ấy" in entry.examples[0].vi

    def test_parses_synonyms(self):
        entry = parse_entry(_ABANDON_HTML)
        assert "Desert" in entry.synonyms
        assert "forsake" in entry.synonyms

    def test_audio_url_none_when_no_word_id(self):
        html = _ABANDON_HTML.replace('{"word_id": 12345}', "{}")
        entry = parse_entry(html)
        assert entry is not None
        assert entry.vdict_id is None
        assert entry.audio_url is None
