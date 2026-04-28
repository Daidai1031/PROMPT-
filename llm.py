"""
LLM layer for PROMPT! v3.1.

Responsibilities:
  1. generate_feedback      — 3-line reaction/habit/invite after each answer.
  2. judge_bias_inverter    — optional tier-promotion for bias_inverter.
  3. generate_summary_tip   — end-of-game one-liner.
  4. answer_followup (NEW)  — free-form follow-up Q&A, scoped to the card
                              and to AI/media literacy.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ollama import chat

from prompts import (
    PERSPECTIVE_LENS_PROMPT,
    AFFECTIVE_HIJACK_PROMPT,
    BIAS_INVERTER_PROMPT,
    TASK_DECOMPOSITION_PROMPT,
    SUMMARY_PROMPT,
    BIAS_JUDGE_PROMPT,
    FOLLOWUP_PROMPT,
)


_TEMPLATES = {
    "perspective_lens_audit": PERSPECTIVE_LENS_PROMPT,
    "affective_highjack":     AFFECTIVE_HIJACK_PROMPT,
    "bias_inverter":          BIAS_INVERTER_PROMPT,
    "task_decomposition_map": TASK_DECOMPOSITION_PROMPT,
}


# ─── Feedback (3 lines now) ───────────────────────────────────────

def _fill(template: str, card: Dict[str, Any], user_answer: str, tier: str) -> str:
    return template.format(
        title=card.get("title", ""),
        deep_insight=card.get("deep_insight", ""),
        habit=card.get("habit", ""),
        suggested_prompt=card.get("suggested_prompt", "") or "",
        user_answer=(user_answer or "").strip() or "(no speech)",
        tier=tier,
    )


# A small rotating set of invite lines so we always have *something* even
# when the LLM fails or returns fewer than three lines. We pick by the
# length of the reaction so the same card always gets the same fallback.
_INVITE_POOL = [
    "Anything about this you want to dig into?",
    "Want to ask me more about it?",
    "Curious about anything else here?",
    "Got a question about what we just looked at?",
    "Anything I can clear up before the next card?",
]


def _pick_invite(seed: str) -> str:
    """Deterministic pick so the fallback doesn't feel random-jittery."""
    n = (len(seed) if seed else 1) % len(_INVITE_POOL)
    return _INVITE_POOL[n]


def _fallback(card: Dict[str, Any], tier: str) -> Tuple[str, str, str]:
    habit = card.get("habit") or "Pause and ask who this view leaves out."
    if tier == "deep":
        reaction = "You spotted the hidden angle — that's exactly the move."
    elif tier == "mid":
        reaction = "Nice catch on the framing. One step deeper and you'd nail it."
    elif tier == "surface":
        reaction = "Good start — you noticed the contrast."
    elif tier == "off":
        reaction = "Close — try looking at the actual words each side uses."
    else:
        reaction = "No worries — give the next one a try out loud."
    invite = _pick_invite(card.get("title", tier))
    return (reaction, habit, invite)


def _parse_three_lines(text: str) -> Tuple[str, str, str]:
    """
    Parse reaction / habit / invite. Tolerant of numbered prefixes, stray
    label prefixes ("Reaction:", "Line 1:"), markdown asterisks, and extra
    blank lines. Returns (reaction, habit, invite) — any of them may be "".
    """
    if not text:
        return ("", "", "")
    cleaned = text.strip().replace("**", "").replace("*", "")
    lines = [ln.strip() for ln in cleaned.split("\n") if ln.strip()]

    clean: List[str] = []
    for ln in lines:
        low = ln.lower()
        for prefix in (
            "line 1:", "line 2:", "line 3:",
            "reaction:", "habit:", "invite:", "tip:",
            "1.", "2.", "3.",
            "1)", "2)", "3)",
            "-", "•",
        ):
            if low.startswith(prefix):
                ln = ln[len(prefix):].strip()
                break
        if ln:
            clean.append(ln)

    if len(clean) >= 3:
        return (clean[0], clean[1], clean[2])
    if len(clean) == 2:
        return (clean[0], clean[1], "")
    if len(clean) == 1:
        only = clean[0]
        parts = only.split(". ", 2)
        if len(parts) == 3:
            return (parts[0].strip() + ".", parts[1].strip() + ".", parts[2].strip())
        if len(parts) == 2:
            return (parts[0].strip() + ".", parts[1].strip(), "")
        return (only, "", "")
    return ("", "", "")


def generate_feedback(
    model: str,
    card: Dict[str, Any],
    user_answer: str,
    tier: str,
) -> Dict[str, str]:
    """Returns {reaction, habit, invite}."""
    template = _TEMPLATES.get(card.get("problem_type", ""))
    if template is None:
        reaction, habit, invite = _fallback(card, tier)
        return {"reaction": reaction, "habit": habit, "invite": invite}

    prompt = _fill(template, card, user_answer, tier)

    try:
        resp = chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.7, "num_predict": 180},
        )
        raw = resp["message"]["content"].strip()
        reaction, habit, invite = _parse_three_lines(raw)
    except Exception as e:
        print(f"[llm] generate_feedback error: {e}")
        reaction, habit, invite = "", "", ""

    # Fill in any missing line with a safe fallback so the UI never looks empty.
    fb_reaction, fb_habit, fb_invite = _fallback(card, tier)
    if not reaction:
        reaction = fb_reaction
    if not habit:
        habit = card.get("habit") or fb_habit
    if not invite:
        invite = fb_invite
    return {"reaction": reaction, "habit": habit, "invite": invite}


# ─── Bias-inverter judge (unchanged from v3) ──────────────────────

_JUDGE_TIER_RE = re.compile(r"\b(deep|mid|surface|off)\b", re.IGNORECASE)


def judge_bias_inverter(
    card: Dict[str, Any],
    user_answer: str,
    rule_result: Dict[str, Any],
    model: str = "llama3",
) -> Optional[str]:
    user_answer = (user_answer or "").strip()
    if not user_answer:
        return None

    prompt = BIAS_JUDGE_PROMPT.format(
        title=card.get("title", ""),
        card_text=" ".join(card.get("body") or []),
        suggested_prompt=card.get("suggested_prompt", "") or "",
        user_answer=user_answer,
    )
    try:
        resp = chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 8},
        )
        raw = (resp["message"]["content"] or "").strip().lower()
        m = _JUDGE_TIER_RE.search(raw)
        if not m:
            return None
        return m.group(1).lower()
    except Exception as e:
        print(f"[llm] judge_bias_inverter error: {e}")
        return None


# ─── Summary (unchanged from v3) ──────────────────────────────────

def generate_summary_tip(
    model: str,
    score: int,
    total: int,
    best_mode: str,
    worst_mode: str,
) -> str:
    prompt = SUMMARY_PROMPT.format(
        score=score,
        total=total,
        best_mode=best_mode or "n/a",
        worst_mode=worst_mode or "n/a",
    )
    try:
        resp = chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.7, "num_predict": 60},
        )
        raw = resp["message"]["content"].strip()
        raw = raw.replace("**", "").replace("*", "").strip()
        for line in raw.split("\n"):
            line = line.strip().strip('"').strip("'")
            if line:
                return line
        return "Pause, check the source, and ask who benefits before you share."
    except Exception as e:
        print(f"[llm] summary error: {e}")
        return "Pause, check the source, and ask who benefits before you share."


# ─── Follow-up Q&A (NEW in v3.1) ──────────────────────────────────

def _format_history(history: List[Dict[str, str]], limit: int = 2) -> str:
    """Render recent Q&A turns for the follow-up prompt."""
    if not history:
        return "(no previous follow-up questions yet)"
    recent = history[-limit:]
    lines = []
    for turn in recent:
        q = (turn.get("question") or "").strip()
        a = (turn.get("answer") or "").strip()
        if q:
            lines.append(f"Child: {q}")
        if a:
            lines.append(f"You: {a}")
    return "\n".join(lines) if lines else "(no previous follow-up questions yet)"


def _clean_followup_reply(raw: str) -> str:
    """
    Defensive cleanup: the local model sometimes adds "Sure!", markdown, or
    a leading label. Trim all of that to a clean, speakable 2-sentence reply.
    """
    if not raw:
        return ""
    text = raw.strip().replace("**", "").replace("*", "")
    # Drop a leading label line (e.g. "Reply:" or "Your reply:")
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    cleaned_lines: List[str] = []
    for ln in lines:
        low = ln.lower()
        if low.startswith(("reply:", "your reply:", "answer:", "response:")):
            ln = ln.split(":", 1)[1].strip()
        ln = ln.strip().strip('"').strip("'")
        if ln:
            cleaned_lines.append(ln)
    text = " ".join(cleaned_lines)

    # Strip common filler openers
    for opener in (
        "great question!", "good question!", "that's a great question!",
        "sure!", "sure thing!", "of course!", "absolutely!",
    ):
        if text.lower().startswith(opener):
            text = text[len(opener):].strip()

    # Cap at 2 sentences so the reply stays speakable.
    parts = re.split(r"(?<=[.!?])\s+", text)
    if len(parts) > 2:
        text = " ".join(parts[:2]).strip()

    return text


def answer_followup(
    model: str,
    card: Dict[str, Any],
    last_feedback: Dict[str, str],
    history: List[Dict[str, str]],
    question: str,
) -> str:
    """
    Answer a free-form follow-up question.

    `history` is the list of prior Q&A turns in THIS card's session — each
    a dict {"question": ..., "answer": ...}. We embed the most recent 2
    turns into the prompt; older ones fade out so latency stays bounded.
    """
    question = (question or "").strip()
    if not question:
        return "I didn't catch a question — want to try again?"

    body = card.get("body") or []
    if isinstance(body, list):
        card_text = " ".join(body)
    else:
        card_text = str(body)

    prompt = FOLLOWUP_PROMPT.format(
        title=card.get("title", ""),
        problem_type=card.get("problem_type", ""),
        card_text=card_text,
        deep_insight=card.get("deep_insight", ""),
        habit=card.get("habit", ""),
        last_reaction=(last_feedback or {}).get("reaction", ""),
        last_habit=(last_feedback or {}).get("habit", ""),
        history=_format_history(history, limit=2),
        question=question,
    )

    try:
        resp = chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.6, "num_predict": 120},
        )
        raw = resp["message"]["content"]
        reply = _clean_followup_reply(raw)
        if not reply:
            return "That's a cool thought — let's stick with the card for now and come back to it."
        return reply
    except Exception as e:
        print(f"[llm] answer_followup error: {e}")
        return "Hmm, my brain glitched. Want to try asking that a different way?"