"""
Rules engine for PROMPT! (v2).

Unlike the old MCQ engine, the new cards are open-ended reflection prompts.
We score on a 0/3/7/10 rubric matching the scoring_anchors in each card:

  0  pts  — silent / totally off-topic
  3  pts  — surface-level: noticed the basic contrast
  7  pts  — midway: analyzed the framing / descriptors
  10 pts  — deep: identified the underlying frame or audience

For usage cards, scoring measures how well the user's attempt approaches the
suggested_prompt (does it reframe, name stakeholders, decompose steps, etc.).

The rules engine is intentionally lenient and transparent:
- We use keyword overlap with the anchor hints as the ONLY signal.
- Ties break DOWN (choose the lower tier) so we stay honest.
- The LLM layer takes it from there with warm, specific feedback.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

_WORD_RE = re.compile(r"[A-Za-z0-9\-]+")


def normalize(text: str) -> List[str]:
    """Lowercase word tokens."""
    if not text:
        return []
    return [t.lower() for t in _WORD_RE.findall(text)]


def _overlap(user_tokens: List[str], anchor_keywords: List[str]) -> int:
    """
    Count how many anchor keywords appear in the user's tokens.

    Matching rules (designed to avoid false positives from short filler tokens):
      - Exact token match always counts.
      - Stem-style match counts only when BOTH tokens are ≥ 4 chars AND one starts
        with the other (so 'frame' matches 'framing', but 'a' no longer matches
        'space' and 'i' no longer matches 'heritage').
    """
    if not anchor_keywords or not user_tokens:
        return 0
    uset = set(user_tokens)
    hits = 0
    for kw in anchor_keywords:
        if kw in uset:
            hits += 1
            continue
        if len(kw) < 4:
            continue
        matched = False
        for t in uset:
            if len(t) < 4:
                continue
            # Only accept prefix-style overlap: kw starts with t or t starts with kw.
            # This captures plural/verb inflections ("relic"/"relics", "frame"/"framing")
            # without letting generic 1-2 letter tokens leak through.
            if t.startswith(kw) or kw.startswith(t):
                matched = True
                break
        if matched:
            hits += 1
    return hits


# ─── Problem-type specific scorers ───

def _score_perspective_lens(card: Dict[str, Any], user_answer: str) -> Dict[str, Any]:
    """
    perspective_lens_audit: two competing narratives about the same thing.

    Tier ladder (deliberate and strict):
      surface (3): just named the contrast words (e.g. "relic vs shard")
      mid     (7): talked about HOW the descriptions differ — the framing move
      deep   (10): named the LENS, AUDIENCE, or FRAME EXPLICITLY — meta-awareness

    The earlier version let a simple restatement ("relic on one side, shard on
    the other") reach deep because the 10-pt anchor keywords overlapped with
    the answer through loose substring matching. Now we require an explicit
    meta term (lens / frame / perspective / audience / bias / viewpoint) to
    reach deep tier — restatement alone stays at surface.
    """
    tokens = normalize(user_answer)
    if not tokens:
        return _build(0, "No speech detected.", "silent")

    hits_3 = _overlap(tokens, card["anchor_keywords_3"])
    hits_7 = _overlap(tokens, card["anchor_keywords_7"])
    hits_10 = _overlap(tokens, card["anchor_keywords_10"])

    # Strong meta-awareness words: explicit naming of the cognitive move.
    meta_words = {"frame", "frames", "framing", "lens", "lenses",
                  "perspective", "perspectives", "viewpoint", "viewpoints",
                  "audience", "audiences", "bias", "biased", "angle", "angles",
                  "describe", "describes", "description", "word", "words",
                  "language", "wording", "story", "stories", "narrative"}
    meta_hits = sum(1 for t in tokens if t in meta_words)

    # Deep requires explicit meta-awareness. Hitting a 10-pt keyword alone is
    # not enough — the child must SAY the move, not just echo card content.
    if meta_hits >= 1 and (hits_7 >= 1 or hits_10 >= 1):
        return _build(10, "Named the frame or lens explicitly.", "deep")
    # Mid: hit the 7-pt framing anchors, OR combine surface contrast with any meta hint.
    if hits_7 >= 1 or (hits_3 >= 1 and meta_hits >= 1):
        return _build(7, "Analyzed the descriptors / framing.", "mid")
    # Surface: named the basic contrast, OR gestured at "framing" without content.
    if hits_3 >= 1 or meta_hits >= 1:
        return _build(3, "Spotted the basic contrast.", "surface")
    return _build(0, "No anchor content detected.", "off")


def _score_affective_hijack(card: Dict[str, Any], user_answer: str) -> Dict[str, Any]:
    """
    affective_highjack: post designed to hook an emotion.
    Tier ladder: noticing the emotion (3) -> the likely outcome (7) -> the intent/incentive (10).
    """
    tokens = normalize(user_answer)
    if not tokens:
        return _build(0, "No speech detected.", "silent")

    hits_3 = _overlap(tokens, card["anchor_keywords_3"])
    hits_7 = _overlap(tokens, card["anchor_keywords_7"])
    hits_10 = _overlap(tokens, card["anchor_keywords_10"])

    # Emotional-literacy vocabulary. Covers adjectives AND noun forms the child
    # is likely to use aloud. ("scary"/"scared", "worried"/"worry"/"worries".)
    emo_words = {
        "fear", "fears", "fearful", "afraid",
        "scared", "scary", "scare",
        "panic", "panicked", "panicking",
        "anger", "angry", "mad", "furious",
        "sad", "sadness", "sorry",
        "worry", "worried", "worries", "worrying",
        "guilt", "guilty",
        "shock", "shocked", "shocking",
        "greed", "greedy",
        "urgency", "urgent",
        "outrage", "outraged",
        "emotion", "emotional", "feeling", "feelings",
    }
    intent_words = {"clicks", "click", "money", "profit", "attention", "engagement",
                    "manipulate", "manipulation", "unrest", "destabilize", "steal",
                    "data", "ads", "advertising", "viral"}
    outcome_words = {"share", "sharing", "panic", "hoard", "buy", "buying",
                     "trouble", "isolate", "withdraw"}

    emo_hits = sum(1 for t in tokens if t in emo_words)
    intent_hits = sum(1 for t in tokens if t in intent_words)
    outcome_hits = sum(1 for t in tokens if t in outcome_words)

    # Deep requires explicit motive vocabulary ("clicks", "money", "attention",
    # "manipulate", "ads", etc.). Echoing an anchor_10 word like "rumor" while
    # describing the emotion/outcome — a valid but incomplete answer — stays
    # at mid. This keeps the "deep" label honest: reserved for children who
    # articulate WHO BENEFITS and HOW, not just what harm spreads.
    if intent_hits >= 1:
        return _build(10, "Named the motive/incentive behind the post.", "deep")
    # Mid: anchor_7 (outcome-focused), outcome vocab, or anchor_10 alone
    # (they echoed a motive word from the card without actually explaining it).
    if hits_7 >= 1 or outcome_hits >= 1 or hits_10 >= 1:
        return _build(7, "Predicted a downstream outcome of sharing.", "mid")
    # Surface: named the emotion only.
    if hits_3 >= 1 or emo_hits >= 1:
        return _build(3, "Named the emotion being targeted.", "surface")
    return _build(0, "No emotional-literacy content detected.", "off")


def _score_bias_inverter(card: Dict[str, Any], user_answer: str) -> Dict[str, Any]:
    """
    bias_inverter: the user should propose a reframing prompt that exposes the bias.
    We compare against the suggested_prompt's keywords plus reframing language.

    Deliberately we do NOT use the card's `habit` text as a scoring signal — the
    habit is teacher-facing notes about how to think, not content the child has
    to say out loud. Letting habit words leak into scoring caused "Teachers know
    best" to score as mid because the habit said "teachers".
    """
    tokens = normalize(user_answer)
    if not tokens:
        return _build(0, "No speech detected.", "silent")

    # Strong reframing markers — these are the move the child is learning to make.
    strong_reframe = {
        "rewrite", "rephrase", "reframe", "reframes", "reframing",
        "compare", "comparing", "contrast",
        "perspective", "perspectives", "viewpoint", "viewpoints",
        "lens", "lenses", "stakeholders",
    }
    # Weaker supporting markers.
    weak_reframe = {
        "view", "views", "audience", "audiences",
        "instead", "also", "both", "another", "other",
        "whose", "who", "benefit", "benefits",
        "cost", "costs", "tradeoff", "tradeoffs", "trade-off",
        "side", "sides",
    }

    strong_hits = sum(1 for t in tokens if t in strong_reframe)
    weak_hits = sum(1 for t in tokens if t in weak_reframe)

    # For suggested-prompt overlap we strip out the generic reframe vocabulary.
    # Otherwise a kid saying "compare viewpoints" triple-counts: once as a strong
    # marker, and again because "view"/"compare" also appear in the suggested
    # prompt's keyword list. What we want is CONTENT overlap — did the child
    # reference the specific stakeholders or actions the suggested prompt names?
    from cards_loader import _extract_keywords
    raw_suggested_kws = _extract_keywords(card.get("suggested_prompt") or "")
    content_suggested_kws = [
        k for k in raw_suggested_kws
        if k not in strong_reframe and k not in weak_reframe
    ]
    suggested_hits = _overlap(tokens, content_suggested_kws)

    # Deep: strong reframing verb AND concrete overlap with the content of the
    # suggested prompt (i.e. the child named a stakeholder or action that
    # actually belongs in a good prompt for THIS card, not a generic template).
    if strong_hits >= 1 and suggested_hits >= 1:
        return _build(10, "Proposed a concrete reframing aligned with the better prompt.", "deep")
    # Mid: any strong reframing verb, OR weak markers backed by content overlap.
    if strong_hits >= 1 or (weak_hits >= 1 and suggested_hits >= 1):
        return _build(7, "Hinted at a reframing approach.", "mid")
    # Surface: plain weak markers, OR content overlap with the suggested prompt alone.
    if weak_hits >= 1 or suggested_hits >= 1:
        return _build(3, "Gestured toward another viewpoint.", "surface")
    return _build(0, "No reframing language detected.", "off")


def _score_task_decomposition(card: Dict[str, Any], user_answer: str) -> Dict[str, Any]:
    """
    task_decomposition_map: the user should break a big task into ordered steps.
    We reward: listing multiple steps, sequencing words, mapping to sub-tasks.
    """
    tokens = normalize(user_answer)
    if not tokens:
        return _build(0, "No speech detected.", "silent")

    # Step-counting: did they enumerate?
    sequence_words = {"first", "second", "third", "then", "next", "after",
                      "finally", "last", "before", "step", "steps", "stage", "stages"}
    planning_words = {"plan", "outline", "draft", "design", "list", "organize",
                      "break", "split", "divide", "decompose", "sequence",
                      "order", "map", "sub-task", "subtask", "phase"}
    review_words = {"check", "review", "revise", "test", "verify", "edit", "refine"}

    seq_hits = sum(1 for t in tokens if t in sequence_words)
    plan_hits = sum(1 for t in tokens if t in planning_words)
    rev_hits = sum(1 for t in tokens if t in review_words)

    # Also: count numeric enumeration ("one", "two", "1", "2"...)
    enum_tokens = {"one", "two", "three", "four", "five",
                   "1", "2", "3", "4", "5"}
    enum_hits = sum(1 for t in tokens if t in enum_tokens)

    if plan_hits >= 1 and seq_hits >= 1 and (rev_hits >= 1 or enum_hits >= 2):
        return _build(10, "Laid out multiple steps with a review stage.", "deep")
    if (seq_hits >= 1 and enum_hits >= 1) or (plan_hits >= 1 and seq_hits >= 1):
        return _build(7, "Listed a sequence with ordering language.", "mid")
    if plan_hits >= 1 or seq_hits >= 1 or enum_hits >= 1:
        return _build(3, "Mentioned planning or a step.", "surface")
    return _build(0, "No decomposition language detected.", "off")


# ─── Dispatcher ───
_SCORERS = {
    "perspective_lens_audit": _score_perspective_lens,
    "affective_highjack": _score_affective_hijack,
    "bias_inverter": _score_bias_inverter,
    "task_decomposition_map": _score_task_decomposition,
}


def _build(score: int, matched_reason: str, tier: str) -> Dict[str, Any]:
    """Common result shape."""
    # Map score to judgement label for UI + TTS phrasing
    if score >= 10:
        judgement = "correct"
    elif score >= 7:
        judgement = "good"
    elif score >= 3:
        judgement = "partial"
    else:
        judgement = "incorrect"
    return {
        "score": score,
        "tier": tier,
        "judgement": judgement,
        "matched_reason": matched_reason,
    }


def check_answer(card: Dict[str, Any], user_answer: str) -> Dict[str, Any]:
    """Main entry point for the rule engine."""
    problem_type = card.get("problem_type", "")
    scorer = _SCORERS.get(problem_type)
    if scorer is None:
        return _build(0, f"Unknown problem type: {problem_type}", "off")
    return scorer(card, user_answer or "")