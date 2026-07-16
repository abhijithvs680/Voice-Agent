"""Local knowledge base.

A deliberately simple, dependency-free retrieval layer over `knowledge/knowledge.json`.
The agent calls `search()` (exposed as the `search_knowledge_base` tool) to answer
questions about the business before falling back to its general knowledge.

Scoring is lightweight keyword/word-overlap matching, which is plenty for a
prototype FAQ and keeps latency effectively zero.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from app.utils.logger import logger

KNOWLEDGE_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "knowledge.json"


@lru_cache
def _load() -> Dict[str, Any]:
    """Load and cache the knowledge base file."""
    try:
        with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load knowledge base at {KNOWLEDGE_PATH}: {e}")
        return {"business": {}, "faqs": []}


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _score(query_tokens: List[str], faq: Dict[str, Any]) -> int:
    """Score a FAQ against the query using keyword and question overlap."""
    score = 0
    keywords = [k.lower() for k in faq.get("keywords", [])]
    haystack = " ".join(query_tokens)

    # Strong signal: a configured keyword phrase appears in the query.
    for kw in keywords:
        if kw in haystack:
            score += 3

    # Weaker signal: individual word overlap with keywords + question text.
    faq_tokens = set(_tokenize(faq.get("question", "")) + _tokenize(" ".join(keywords)))
    score += sum(1 for t in query_tokens if t in faq_tokens)
    return score


def search(query: str, top_k: int = 2) -> Dict[str, Any]:
    """Return the best-matching knowledge base entries for a query.

    Args:
        query: The user's question (any language; matching is best on English keywords).
        top_k: Maximum number of matches to return.

    Returns:
        A dict with the matched answers and the general business info, suitable
        for handing straight back to the LLM as tool output.
    """
    data = _load()
    faqs = data.get("faqs", [])
    query_tokens = _tokenize(query)

    scored = sorted(
        ((_score(query_tokens, faq), faq) for faq in faqs),
        key=lambda pair: pair[0],
        reverse=True,
    )
    matches = [
        {"question": faq["question"], "answer": faq["answer"]}
        for score, faq in scored[:top_k]
        if score > 0
    ]

    result: Dict[str, Any] = {
        "business": data.get("business", {}),
        "matches": matches,
    }
    if not matches:
        result["note"] = (
            "No specific FAQ matched. Use the general business info if relevant, "
            "otherwise tell the caller you'll check and offer to take a message."
        )
    return result


def business_info() -> Dict[str, Any]:
    """Expose the raw business info block (name, address, phone, etc.)."""
    return _load().get("business", {})
