"""
LLM feedback layer for PROMPT! v2.

Uses Ollama (local Llama 3) to generate two-line reflection feedback:
  Line 1 (reaction): the WARM tone reads this.
  Line 2 (habit):    the CURIOUS tone reads this.

The rule engine has already decided the score. The LLM only crafts language.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from ollama import chat

from prompts import (
    PERSPECTIVE_LENS_PROMPT,
    AFFECTIVE_HIJACK_PROMPT,
    BIAS_INVERTER_PROMPT,
    TASK_DECOMPOSITION_PROMPT,
    SUMMARY_PROMPT,
)


_TEMPLATES = {
    "perspective_lens_audit": PERSPECTIVE_LENS_PROMPT,
    "affective_highjack":     AFFECTIVE_HIJACK_PROMPT,
    "bias_inverter":          BIAS_INVERTER_PROMPT,
    "task_decomposition_map": TASK_DECOMPOSITION_PROMPT,
}


def _fill(template: str, card: Dict[str, Any], user_answer: str, tier: str) -> str:
    return template.format(
        title=card.get("title", ""),
        deep_insight=card.get("deep_insight", ""),
        habit=card.get("habit", ""),
        suggested_prompt=card.get("suggested_prompt", "") or "",
        user_answer=(user_answer or "").strip() or "(no speech)",
        tier=tier,
    )


def _fallback(card: Dict[str, Any], tier: str) -> Tuple[str, str]:
    """If Ollama fails, still return something kind and on-topic."""
    habit = card.get("habit") or "Pause and ask who this view leaves out."
    if tier == "deep":
        return ("You spotted the hidden angle — that's exactly the move.", habit)
    if tier == "mid":
        return ("Nice catch on the framing. One step deeper and you'd nail it.", habit)
    if tier == "surface":
        return ("Good start — you noticed the contrast.", habit)
    if tier == "off":
        return ("Close — try looking at the actual words each side uses.", habit)
    return ("No worries — give the next one a try out loud.", habit)


def _parse_two_lines(text: str) -> Tuple[str, str]:
    """Split the model's output into (reaction, habit). Be tolerant of formats."""
    if not text:
        return ("", "")
    # Normalize
    cleaned = text.strip().replace("**", "").replace("*", "")
    # Strip any "Line 1:" / "Reaction:" style prefixes
    lines = [ln.strip() for ln in cleaned.split("\n") if ln.strip()]
    # Drop obvious label prefixes
    clean_lines = []
    for ln in lines:
        low = ln.lower()
        for prefix in ("line 1:", "line 2:", "reaction:", "habit:", "tip:", "1.", "2.", "-"):
            if low.startswith(prefix):
                ln = ln[len(prefix):].strip()
                break
        if ln:
            clean_lines.append(ln)
    if len(clean_lines) >= 2:
        return (clean_lines[0], clean_lines[1])
    if len(clean_lines) == 1:
        # Try to split on a period in the middle
        only = clean_lines[0]
        parts = only.split(". ", 1)
        if len(parts) == 2:
            return (parts[0].strip() + ".", parts[1].strip())
        return (only, "")
    return ("", "")


def generate_feedback(
    model: str,
    card: Dict[str, Any],
    user_answer: str,
    tier: str,
) -> Dict[str, str]:
    """
    Returns {"reaction": str, "habit": str}.
    Both lines are short and safe to send straight to TTS.
    """
    template = _TEMPLATES.get(card.get("problem_type", ""))
    if template is None:
        reaction, habit = _fallback(card, tier)
        return {"reaction": reaction, "habit": habit}

    prompt = _fill(template, card, user_answer, tier)

    try:
        resp = chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.7, "num_predict": 120},
        )
        raw = resp["message"]["content"].strip()
        reaction, habit = _parse_two_lines(raw)
        if not reaction:
            reaction, habit_fb = _fallback(card, tier)
            if not habit:
                habit = habit_fb
        if not habit:
            habit = card.get("habit") or "Ask who this view leaves out."
        return {"reaction": reaction, "habit": habit}
    except Exception as e:
        print(f"[llm] generate_feedback error: {e}")
        reaction, habit = _fallback(card, tier)
        return {"reaction": reaction, "habit": habit}


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
        # Take just the first sentence, no markdown
        raw = raw.replace("**", "").replace("*", "").strip()
        # If the model returned multiple lines, keep the first non-empty one
        for line in raw.split("\n"):
            line = line.strip().strip('"').strip("'")
            if line:
                return line
        return "Pause, check the source, and ask who benefits before you share."
    except Exception as e:
        print(f"[llm] summary error: {e}")
        return "Pause, check the source, and ask who benefits before you share."