import json
import logging
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.config import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an English teacher. Your student is Vietnamese.

You receive a word or sentence as input. Your job is to explain it clearly so a Vietnamese learner can quickly understand and remember it.

ALWAYS respond with a STRICT JSON object. No prose outside the JSON. No code fences. Just the JSON.

LANGUAGE RULES — critically important:
- The `explanation` field MUST be written in **Vietnamese**.
- Target length for `explanation`: about **100 words total** (acceptable range 50–150), split into **2 to 4 short paragraphs separated by a blank line (i.e., `\\n\\n` between paragraphs)**. Each paragraph 20–50 words.
- Suggested paragraph structure (not strict): (1) core meaning, (2) nuance / register / connotation, (3) common usage contexts, (4) pitfalls for Vietnamese learners. Skip paragraphs that have nothing useful to say.
- `word_type` stays as a short tag: n, v, adj, adv, prep, conj, phrasal verb, idiom, etc.
- `pronunciation` stays as IPA or simple phonetic in English script (e.g. /ˈbʌtə/ or buh-ter).
- `example` stays as an **English** example sentence — this is the sentence the student studies.
- `synonyms` and `collocations` are English words/phrases (no translation).
- Do not include English text in `explanation` except for the headword itself or proper nouns being referenced.

For a SINGLE WORD or short phrasal verb, respond:
{
  "kind": "word",
  "text": "<the headword>",
  "word_type": "<n | v | adj | adv | prep | conj | phrasal verb | idiom>",
  "pronunciation": "<IPA, e.g. /ˈbʌtə/>",
  "explanation": "<~100 words in Vietnamese: definition, nuance, common usage contexts, any false-friends or pitfalls a Vietnamese learner should know>",
  "example": "<one clear English sentence using the headword>",
  "synonyms": ["<3 to 5 single-word English synonyms>"],
  "collocations": ["<2 to 5 common multi-word phrases using the headword, e.g. 'make a mistake', 'take a break'>"],
  "difficulty": "<beginner | intermediate | advanced>"
}

For a SENTENCE (multiple words), respond:
{
  "kind": "sentence",
  "text": "<the full sentence>",
  "explanation": "<~100 words in Vietnamese explaining the sentence meaning in context>",
  "keywords": [
    {
      "text": "<key word, phrasal verb, or idiom from the sentence>",
      "word_type": "<n | v | adj | phrasal verb | idiom | ...>",
      "pronunciation": "<IPA>",
      "explanation": "<~80 words in Vietnamese explaining this specific keyword>",
      "example": "<one English sentence using this keyword in a DIFFERENT context>",
      "synonyms": ["<3 to 5 English synonyms>"],
      "collocations": ["<2 to 5 multi-word phrases>"],
      "difficulty": "<beginner | intermediate | advanced>"
    }
  ]
}

Rules for the new fields:
- `synonyms` MUST be a JSON array of strings. If genuinely no good synonyms exist, return [].
- `collocations` MUST be a JSON array of strings. If the word rarely combines, return [].
- `difficulty` MUST be exactly one of "beginner", "intermediate", or "advanced". Estimate based on CEFR-like intuition: A1–A2 = beginner, B1–B2 = intermediate, C1+ = advanced.

Keywords rules (for sentence flow):
- Include only phrasal verbs, uncommon words, idioms, and important key terms — NOT common words like "the", "is", "and".
- Aim for 2–6 keywords per sentence.
- If the sentence has no notable vocabulary, return `"keywords": []`.

If the INPUT is VIETNAMESE, treat it as a Vietnamese-to-English translation request:
- "kind" is "word" if it's a single word, "sentence" otherwise.
- "text" is the ENGLISH equivalent (translate first).
- All other fields explain the English version, with `explanation` still in Vietnamese.
"""


class WordResponse(BaseModel):
    kind: Literal["word"]
    text: str
    word_type: str | None = None
    pronunciation: str | None = None
    explanation: str
    example: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    collocations: list[str] = Field(default_factory=list)
    difficulty: str | None = None


class KeywordItem(BaseModel):
    text: str
    word_type: str | None = None
    pronunciation: str | None = None
    explanation: str
    example: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    collocations: list[str] = Field(default_factory=list)
    difficulty: str | None = None


class SentenceResponse(BaseModel):
    kind: Literal["sentence"]
    text: str
    explanation: str
    keywords: list[KeywordItem] = Field(default_factory=list)


class OpenRouterError(Exception):
    pass


async def explain(text: str) -> WordResponse | SentenceResponse:
    """Call OpenRouter for an explanation using the hardcoded model from settings."""
    if not settings.openrouter_api_key:
        raise OpenRouterError("OPENROUTER_API_KEY is not configured")

    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            res = await client.post(
                f"{settings.openrouter_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as e:
            raise OpenRouterError(f"OpenRouter request failed: {e}") from e

    if res.status_code != 200:
        raise OpenRouterError(f"OpenRouter {res.status_code}: {res.text[:200]}")

    body = res.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise OpenRouterError(f"Unexpected OpenRouter response shape: {body}") from e

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning("OpenRouter returned non-JSON content: %r", content[:300])
        raise OpenRouterError(f"Model did not return valid JSON: {e}") from e

    kind = data.get("kind")
    try:
        if kind == "word":
            return WordResponse.model_validate(data)
        if kind == "sentence":
            return SentenceResponse.model_validate(data)
    except ValidationError as e:
        raise OpenRouterError(f"Model response schema invalid: {e}") from e

    raise OpenRouterError(f"Model returned unknown kind: {kind!r}")
