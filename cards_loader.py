"""
Card loader for PROMPT! game.

Handles two card families with different shapes:
- discernment_cards.json: perspective_lens_audit, affective_highjack
- usage_cards.json:       bias_inverter, task_decomposition_map

Both are normalized into a common in-game card schema:
{
    "id": str,
    "category": "discernment" | "usage",
    "problem_type": str,
    "difficulty": "easy" | "medium" | "hard",
    "title": str,
    "body": list[str],              # text shown on the card front
    "verdict": str,                 # short label for the "answer side"
    "anchors": dict,                # scoring anchors (shape varies by problem_type)
    "suggested_prompt": str | None, # for usage cards only
    "reality_anchor": str,
    "deep_insight": str,
    "habit": str,
    "references": list[{title,url}],
    # Derived helpers for the rules engine:
    "anchor_keywords_3": list[str],
    "anchor_keywords_7": list[str],
    "anchor_keywords_10": list[str],
}
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

DISCERNMENT_PATH = "discernment_cards.json"
USAGE_PATH = "usage_cards.json"


# ─── Keyword extraction for rule-based scoring ───
# A scoring anchor is a short hint text. We turn it into keyword tokens so the
# rule engine can check the user's answer against each tier.
# Stopwords come in three groups:
#  1. Grammatical filler (usual).
#  2. Anchor meta-verbs — the words the card WRITER uses to describe what the
#     scorer is looking for ("identified", "detected", "noted", "spotted",
#     "analyzed", "check", "compare"). These describe the GRADING action, not
#     the CONTENT the child needs to say, so they must never feed scoring.
#  3. Weak-content fillers that would otherwise match kid speech too easily
#     ("kids", "their", "could", "might", "some", "many", "much").
_STOPWORDS = {
    # 1. grammatical
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "as", "is", "are", "be", "was", "were", "by", "at", "it", "its",
    "that", "this", "these", "those", "your", "you", "from", "into", "about",
    "vs", "vs.",
    # 2. anchor-writer meta-verbs (these describe the rubric, not the answer)
    "identified", "identify", "detected", "detect", "detects",
    "spotted", "spot", "noted", "note", "notice", "noticed",
    "analyzed", "analyze", "analysis", "analyse",
    "check", "checks", "checked", "checking",
    "compare", "compared", "comparing", "comparison",
    "scan", "scanned", "scanning",
    "contrast", "contrasted", "contrasting",
    "framing",  # meta term — "framing" describes the rubric act, not content
    "proposed", "propose",
    "tracked", "track",
    "trace",
    "saw", "spotted",
    # 3. weak/filler content words that would over-match child speech
    "could", "might", "should", "would", "will",
    "kids", "their", "them", "they", "there", "here",
    "some", "many", "much", "more", "less", "most",
    "thing", "things", "something", "someone",
    "really", "very", "just", "like", "well",
    "people", "person",
    "news",  # too common — child saying "the news" doesn't mean anything
    "post", "posts",  # same — trivial filler on affective_hijack cards
}


def _extract_keywords(text: str, min_len: int = 4) -> List[str]:
    """Pull content tokens out of an anchor string."""
    if not text:
        return []
    # Split on non-word chars, lowercase, drop stopwords and short tokens.
    tokens = re.split(r"[^A-Za-z0-9\-]+", text.lower())
    out = []
    for t in tokens:
        if len(t) < min_len:
            continue
        if t in _STOPWORDS:
            continue
        out.append(t)
    # De-dupe while preserving order
    seen = set()
    uniq = []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def _normalize_card(raw: Dict[str, Any], source_category: str) -> Dict[str, Any]:
    """Convert one raw card (from either file) into the common schema."""
    front = raw.get("front", {})
    back = raw.get("back", {})
    notes = raw.get("teacher_notes", {})
    anchors = back.get("scoring_anchors", {}) or {}

    # Discernment scoring_anchors: {3_pts, 7_pts, 10_pts}
    # Usage scoring_anchors:       {suggested_prompt}
    anchor_3 = anchors.get("3_pts", "")
    anchor_7 = anchors.get("7_pts", "")
    anchor_10 = anchors.get("10_pts", "")
    suggested_prompt = anchors.get("suggested_prompt", "")

    card = {
        "id": raw.get("card_id", "?"),
        "category": source_category,
        "problem_type": raw.get("problem_type", "unknown"),
        "difficulty": raw.get("difficulty", "easy"),
        "title": front.get("title", "Untitled"),
        "body": front.get("card_text", []) or [],
        "verdict": back.get("verdict", ""),
        "anchors": {
            "3_pts": anchor_3,
            "7_pts": anchor_7,
            "10_pts": anchor_10,
            "suggested_prompt": suggested_prompt,
        },
        "suggested_prompt": suggested_prompt or None,
        "reality_anchor": back.get("reality_anchor", ""),
        "deep_insight": notes.get("deep_insight", ""),
        "habit": notes.get("habit", ""),
        "references": notes.get("references", []) or [],
        # Pre-computed keywords so the rule engine stays fast
        "anchor_keywords_3": _extract_keywords(anchor_3),
        "anchor_keywords_7": _extract_keywords(anchor_7),
        "anchor_keywords_10": _extract_keywords(anchor_10),
        "habit_keywords": _extract_keywords(notes.get("habit", "")),
    }
    return card


def _load_file(path: str, source_category: str) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        return []
    return [_normalize_card(c, source_category) for c in raw]


def load_all_cards() -> Dict[str, List[Dict[str, Any]]]:
    """Return {'discernment': [...], 'usage': [...], 'all': [...]}."""
    disc = _load_file(DISCERNMENT_PATH, "discernment")
    usage = _load_file(USAGE_PATH, "usage")
    return {
        "discernment": disc,
        "usage": usage,
        "all": disc + usage,
    }


def pick_deck(mode: str, n: int = 6) -> List[Dict[str, Any]]:
    """
    mode:
      'discernment' -> only discernment cards
      'usage'       -> only usage cards
      'mixed'       -> a balanced mix of both, alternating
    Returns up to `n` cards, shuffled inside each category, with a mild
    easy -> medium -> hard difficulty ramp within the chosen deck.
    """
    import random

    decks = load_all_cards()
    if mode == "discernment":
        pool = list(decks["discernment"])
    elif mode == "usage":
        pool = list(decks["usage"])
    else:  # mixed
        d = list(decks["discernment"])
        u = list(decks["usage"])
        random.shuffle(d)
        random.shuffle(u)
        # Interleave so the player feels variety
        pool = []
        for a, b in zip(d, u):
            pool.append(a)
            pool.append(b)
        # Append leftovers
        longer = d if len(d) > len(u) else u
        pool.extend(longer[min(len(d), len(u)):])

    if mode != "mixed":
        random.shuffle(pool)

    pool = pool[:n]

    # Light difficulty ramp
    difficulty_order = {"easy": 0, "medium": 1, "hard": 2}
    pool.sort(key=lambda c: difficulty_order.get(c.get("difficulty", "easy"), 1))
    return pool