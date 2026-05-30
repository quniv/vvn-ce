"""HTML parser for vdict.com word pages (dict_id=1, English → Vietnamese).

Parses the *friendly* definition section (richer, user-facing content).
Falls back to the academic section if the friendly section is empty.

Pure function — no I/O, no DB. Easy to unit-test with raw HTML strings.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from selectolax.parser import HTMLParser


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class ExamplePair:
    """A bilingual example: English sentence + Vietnamese translation."""

    en: str
    vi: str


@dataclass
class DefinitionItem:
    """One meaning entry inside a POS group."""

    vi: str  # bold short meaning, e.g. "Từ bỏ, bỏ rơi, ruồng bỏ"
    description: str  # explanation after the colon


@dataclass
class DefinitionGroup:
    """All meanings for one part-of-speech."""

    pos: str  # "Động từ", "Danh từ", …
    items: list[DefinitionItem] = field(default_factory=list)


@dataclass
class PhrasalEntry:
    """A phrasal verb or idiom entry."""

    phrase: str  # "to abandon to" / "With gay abandon"
    vi: str  # Vietnamese gloss
    examples: list[ExamplePair] = field(default_factory=list)


@dataclass
class ParsedEntry:
    vdict_id: int | None
    text: str
    ipa: str | None
    word_type: str | None  # first POS from definitions
    definitions: list[DefinitionGroup]
    examples: list[ExamplePair]
    synonyms: list[str]
    phrasal_verbs: list[PhrasalEntry]
    idioms: list[PhrasalEntry]
    audio_url: str | None = None


# ── Pre-compiled patterns ─────────────────────────────────────────────────────

_WORD_ID_PATTERN = re.compile(r'"word_id":\s*(\d+)')
_IPA_PATTERN = re.compile(r"/[^/]+/")
_WS_COLLAPSE = re.compile(r"\s+")


# ── Shared helpers ────────────────────────────────────────────────────────────


def _clean_text(s: str) -> str:
    return _WS_COLLAPSE.sub(" ", s).strip()


def _extract_word_id(html: str) -> int | None:
    decoded = html.replace("&#34;", '"').replace("&quot;", '"')
    m = _WORD_ID_PATTERN.search(decoded)
    return int(m.group(1)) if m else None


# ── Per-item parsers ──────────────────────────────────────────────────────────


def _parse_example_li(li) -> ExamplePair | None:
    """Parse one <li class="example"> into an ExamplePair.

    Format: <em>EN sentence</em> (VI translation)
    """
    div = li.css_first("div")
    if div is None:
        return None
    em = div.css_first("em")
    if em is None:
        return None
    en = _clean_text(em.text())
    if not en:
        return None
    full = _clean_text(div.text())
    # VI is in the last parenthesised chunk after the EN sentence
    # "The captain gave the order ... ship. (Thuyền trưởng...)"
    after_en = full[full.find(en) + len(en) :].strip() if en in full else ""
    if after_en.startswith("(") and after_en.endswith(")"):
        vi = _clean_text(after_en[1:-1])
    else:
        m = re.search(r"\((.+)\)\s*$", after_en, re.DOTALL)
        vi = _clean_text(m.group(1)) if m else ""
    return ExamplePair(en=en, vi=vi)


def _parse_definition_example_li(li) -> DefinitionItem | None:
    """Parse one meaning inside the 'Định nghĩa' list.

    Format: <strong>Từ bỏ, bỏ rơi</strong>: Hành động rời bỏ...
    """
    div = li.css_first("div")
    if div is None:
        return None
    strong = div.css_first("strong")
    full = _clean_text(div.text())
    if strong:
        vi = _clean_text(strong.text())
        after = (
            full[full.find(vi) + len(vi) :].lstrip(":").strip() if vi in full else ""
        )
        return DefinitionItem(vi=vi, description=after)
    # Fallback — no bold, treat entire text as the meaning
    return DefinitionItem(vi=full, description="") if full else None


def _parse_phrasal_li(li) -> PhrasalEntry | None:
    """Parse one <li class="meaning"> in phrasal-verb or idiom sections."""
    mv = li.css_first("div.meaning-value")
    if mv is None:
        return None
    # Phrase is in bold
    strong = mv.css_first("p strong") or mv.css_first("strong")
    if strong is None:
        return None
    phrase = _clean_text(strong.text())
    full = _clean_text(mv.text())
    after = (
        full[full.find(phrase) + len(phrase) :].lstrip(":").strip()
        if phrase in full
        else ""
    )
    examples = [
        ex
        for li_ex in li.css("ul.examples-list li.example")
        if (ex := _parse_example_li(li_ex)) is not None
    ]
    return PhrasalEntry(phrase=phrase, vi=after, examples=examples)


# ── Section parsers ───────────────────────────────────────────────────────────


def _parse_definitions(lst) -> list[DefinitionGroup]:
    """Parse the 'Định nghĩa' ol.meanings-list."""
    groups: list[DefinitionGroup] = []
    for li in lst.css("li.meaning"):
        mv = li.css_first("div.meaning-value")
        if mv is None:
            continue
        strong = mv.css_first("p strong") or mv.css_first("strong")
        pos = _clean_text(strong.text()) if strong else ""
        pos = pos.rstrip(":")
        items = [
            item
            for ex_li in li.css("ul.examples-list li.example")
            if (item := _parse_definition_example_li(ex_li)) is not None
        ]
        if pos or items:
            groups.append(DefinitionGroup(pos=pos, items=items))
    return groups


def _parse_examples(lst) -> list[ExamplePair]:
    """Parse the 'Ví dụ sử dụng' ul.meanings-list."""
    pairs: list[ExamplePair] = []
    for li in lst.css("li.meaning"):
        for ex_li in li.css("ul.examples-list li.example"):
            ex = _parse_example_li(ex_li)
            if ex:
                pairs.append(ex)
    return pairs


def _parse_synonyms_section(lst) -> list[str]:
    """Parse the 'Từ đồng nghĩa' ul.meanings-list into a flat word list."""
    words: list[str] = []
    for li in lst.css("li.meaning"):
        mv = li.css_first("div.meaning-value")
        if mv is None:
            continue
        text = _clean_text(mv.text())
        # Format: "Động từ (Nghĩa ...): Desert, leave, forsake."
        colon_idx = text.find(":")
        if colon_idx == -1:
            continue
        for w in text[colon_idx + 1 :].rstrip(".").split(","):
            w = _clean_text(w)
            if w:
                words.append(w)
    return words


def _parse_phrasal_section(lst) -> list[PhrasalEntry]:
    """Parse phrasal-verb or idiom ul.meanings-list."""
    return [
        entry
        for li in lst.css("li.meaning")
        if (entry := _parse_phrasal_li(li)) is not None
    ]


# ── Friendly section walker ───────────────────────────────────────────────────

_SECTION_KEYS = {
    "định nghĩa": "definitions",
    "ví dụ": "examples",
    "đồng nghĩa": "synonyms",
    "cụm từ": "phrasal_verbs",
    "phrasal": "phrasal_verbs",
    "thành ngữ": "idioms",
}


def _parse_friendly(
    tree,
) -> tuple[
    list[DefinitionGroup],
    list[ExamplePair],
    list[str],
    list[PhrasalEntry],
    list[PhrasalEntry],
]:
    """Walk the friendly section and return all structured data."""
    # The inner word-type-section is nested inside the outer one
    inner = tree.css_first("#friendlyDefinition .word-type-section .word-type-section")
    if inner is None:
        return [], [], [], [], []

    # Collect section headers and corresponding top-level lists IN ORDER
    headers = [_clean_text(n.text()) for n in inner.css("div.word-type")]
    # meanings-list = section-level lists; examples-list = item-level lists (won't match)
    lists = inner.css("ol.meanings-list, ul.meanings-list")

    definitions: list[DefinitionGroup] = []
    examples: list[ExamplePair] = []
    synonyms: list[str] = []
    phrasal_verbs: list[PhrasalEntry] = []
    idioms: list[PhrasalEntry] = []

    for i, header in enumerate(headers):
        if i >= len(lists):
            break
        lst = lists[i]
        h = header.lower()

        if "định nghĩa" in h:
            definitions.extend(_parse_definitions(lst))
        elif "ví dụ" in h:
            examples.extend(_parse_examples(lst))
        elif "đồng nghĩa" in h:
            synonyms.extend(_parse_synonyms_section(lst))
        elif "cụm từ" in h or "phrasal" in h:
            phrasal_verbs.extend(_parse_phrasal_section(lst))
        elif "thành ngữ" in h:
            idioms.extend(_parse_phrasal_section(lst))
        # Skip: "Các cách sử dụng nâng cao", "Biến thể và từ gần giống"

    return definitions, examples, synonyms, phrasal_verbs, idioms


# ── Academic fallback ─────────────────────────────────────────────────────────


def _parse_academic_fallback(tree) -> list[DefinitionGroup]:
    """Minimal fallback: extract meanings from #academicDefinition."""
    academic_root = tree.css_first("#academicDefinition")
    if academic_root is None:
        return []
    groups: list[DefinitionGroup] = []
    for sec in academic_root.css("div.word-type-section"):
        pos_node = sec.css_first("div.word-type")
        pos = _clean_text(pos_node.text()) if pos_node else ""
        items: list[DefinitionItem] = []
        for li in sec.css("ol.meanings-list li.meaning"):
            mv = li.css_first("div.meaning-value")
            if mv:
                text = _clean_text(mv.text())
                if text:
                    items.append(DefinitionItem(vi=text, description=""))
        if pos or items:
            groups.append(DefinitionGroup(pos=pos, items=items))
    return groups


# ── Main entry point ──────────────────────────────────────────────────────────


def parse_entry(html: str) -> Optional[ParsedEntry]:
    """Parse a vdict.com word page. Returns None if the page has no valid entry."""
    if not html or "<h1" not in html:
        return None

    tree = HTMLParser(html)

    h1 = tree.css_first("h1.mb-0")
    if h1 is None:
        return None
    text = _clean_text(h1.text())
    if not text:
        return None

    # IPA pronunciation
    ipa: str | None = None
    pron_node = tree.css_first("div.pronunciation")
    if pron_node is not None:
        m = _IPA_PATTERN.search(pron_node.text() or "")
        if m:
            ipa = m.group(0)

    # vdict internal word_id
    vdict_id = _extract_word_id(html)

    # Audio URL derived from word_id (pattern confirmed from main.js)
    audio_url: str | None = None
    if vdict_id is not None:
        audio_url = f"https://audio.vdict.com/1/{vdict_id}.mp3"

    # Parse friendly section (primary)
    definitions, examples, synonyms, phrasal_verbs, idioms = _parse_friendly(tree)

    # Fallback to academic section if friendly yields nothing
    if not definitions:
        definitions = _parse_academic_fallback(tree)

    word_type: str | None = definitions[0].pos if definitions else None

    return ParsedEntry(
        vdict_id=vdict_id,
        text=text,
        ipa=ipa,
        word_type=word_type,
        definitions=definitions,
        examples=examples,
        synonyms=synonyms,
        phrasal_verbs=phrasal_verbs,
        idioms=idioms,
        audio_url=audio_url,
    )
