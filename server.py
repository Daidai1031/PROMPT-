"""
PROMPT! Game Server v3.1.

Changes from v3:
  - /api/answer now returns feedback with THREE fields: reaction, habit, invite.
  - NEW /api/followup endpoint: free-form follow-up Q&A scoped to the card
    the child just answered. Not scored; the count appears on the summary.
  - Session bookkeeping tracks follow-up count per card and total.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import whisper
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import tts
from cards_loader import pick_deck
from llm import (
    answer_followup,
    generate_feedback,
    generate_summary_tip,
    judge_bias_inverter,
)
from rules import check_answer

# ─── Config ───
WHISPER_MODEL = "small"
OLLAMA_MODEL = "llama3"
CARDS_PER_GAME = 6

# Guardrails for follow-up Q&A
MAX_FOLLOWUPS_PER_CARD = 4      # after this we politely stop
FOLLOWUP_HISTORY_WINDOW = 2     # how many prior turns the LLM sees

# ─── App ───
app = FastAPI(title="PROMPT! Game Server v3.1")

# ─── Runtime state ───
_whisper_model = None
_sessions: Dict[str, Dict[str, Any]] = {}


# ─── Request models ───
class StartRequest(BaseModel):
    mode: str = "mixed"
    num_cards: Optional[int] = None


class AnswerRequest(BaseModel):
    session_id: str
    user_answer: str


class FollowupRequest(BaseModel):
    session_id: str
    question: str


class TTSRequest(BaseModel):
    text: str
    tone: str = "narrator"


# ─── Startup ───
@app.on_event("startup")
async def startup() -> None:
    global _whisper_model
    print("[startup] Loading Whisper ...")
    _whisper_model = whisper.load_model(WHISPER_MODEL)
    print("[startup] Warming Kokoro TTS ...")
    try:
        tts.warmup()
    except Exception as e:
        print(f"[startup] TTS warmup skipped: {e}")
    print("[startup] Ready.")


# ─── Helpers ───
def _mode_of(card: Dict[str, Any]) -> str:
    return card.get("category", "unknown")


def _public_card(card: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": card["id"],
        "card_id": card["id"],
        "category": card["category"],
        "problem_type": card["problem_type"],
        "difficulty": card["difficulty"],
        "title": card["title"],
        "body": card["body"],
    }


def _back_view(card: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "verdict": card["verdict"],
        "deep_insight": card["deep_insight"],
        "habit": card["habit"],
        "references": card["references"],
        "suggested_prompt": card.get("suggested_prompt"),
    }


def _summarize_session(session: Dict[str, Any]) -> Dict[str, Any]:
    answered_cards = session.get("index", 0)
    per_mode = session.get("per_mode", {})
    best = worst = None
    best_avg = -1.0
    worst_avg = 999.0
    for mode, s in per_mode.items():
        if s["total"] == 0:
            continue
        avg = s["score"] / s["total"]
        if avg > best_avg:
            best_avg = avg
            best = mode
        if avg < worst_avg:
            worst_avg = avg
            worst = mode

    # Count total follow-ups across all cards played.
    total_followups = sum(
        len(h.get("followups", []))
        for h in session.get("history", [])
    )

    return {
        "score": int(session["score"]),
        "max_score": int(answered_cards) * 10 if answered_cards else 10,
        "total_cards": answered_cards,
        "deck_size": session["total_cards"],
        "per_mode": per_mode,
        "best_mode": best or "n/a",
        "worst_mode": worst or "n/a",
        "history": session["history"],
        "total_followups": total_followups,
    }


def _judge_wrapper(card, user_answer, rule_result):
    return judge_bias_inverter(card, user_answer, rule_result, model=OLLAMA_MODEL)


# ─── Routes ───
@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return Path("index.html").read_text(encoding="utf-8")


@app.post("/api/start")
async def start_game(req: StartRequest) -> Dict[str, Any]:
    mode = req.mode if req.mode in ("discernment", "usage", "mixed") else "mixed"
    n = req.num_cards or CARDS_PER_GAME
    deck = pick_deck(mode, n=n)
    if not deck:
        return {"error": f"No cards available for mode={mode}"}

    session_id = f"s_{int(time.time() * 1000)}"
    _sessions[session_id] = {
        "mode": mode,
        "deck": deck,
        "index": 0,
        "total_cards": len(deck),
        "score": 0,
        "per_mode": {},
        "history": [],
    }
    return {
        "session_id": session_id,
        "mode": mode,
        "total_cards": len(deck),
        "card": _public_card(deck[0]),
    }


@app.post("/api/answer")
async def submit_answer(req: AnswerRequest) -> Dict[str, Any]:
    session = _sessions.get(req.session_id)
    if not session:
        return {"error": "Invalid session"}

    idx = session["index"]
    if idx >= session["total_cards"]:
        return {"error": "Game already finished"}

    card = session["deck"][idx]
    result = check_answer(card, req.user_answer, llm_judge=_judge_wrapper)

    feedback = generate_feedback(
        model=OLLAMA_MODEL,
        card=card,
        user_answer=req.user_answer,
        tier=result["tier"],
    )

    mode = _mode_of(card)
    stats = session["per_mode"].setdefault(mode, {"total": 0, "score": 0})
    stats["total"] += 1
    stats["score"] += result["score"]
    session["score"] += result["score"]

    # NEW: history entry carries a followups[] list so we can append later
    # without rebuilding the record. The current answer card's position in
    # the deck is `idx`, i.e. the LAST entry in history once appended.
    session["history"].append({
        "card_id": card["id"],
        "problem_type": card["problem_type"],
        "category": card["category"],
        "user_answer": req.user_answer,
        "score": result["score"],
        "tier": result["tier"],
        "judgement": result["judgement"],
        "feedback": feedback,
        "followups": [],
    })

    session["index"] += 1
    has_next = session["index"] < session["total_cards"]
    next_card = session["deck"][session["index"]] if has_next else None

    return {
        "score": result["score"],
        "tier": result["tier"],
        "judgement": result["judgement"],
        "matched_reason": result["matched_reason"],
        "feedback": feedback,
        "card_back": _back_view(card),
        "current_total_score": session["score"],
        "max_possible": session["total_cards"] * 10,
        "has_next": has_next,
        "next_card": _public_card(next_card) if next_card else None,
        "followups_allowed": MAX_FOLLOWUPS_PER_CARD,
    }


@app.post("/api/followup")
async def submit_followup(req: FollowupRequest) -> Dict[str, Any]:
    """
    Handle a follow-up question about the CARD MOST RECENTLY ANSWERED.

    Follow-ups attach to the last entry in session['history'], which was
    appended by /api/answer. We cap the number of follow-ups per card so
    conversations can't run forever and clog the queue.
    """
    session = _sessions.get(req.session_id)
    if not session:
        return {"error": "Invalid session"}

    if not session["history"]:
        return {"error": "No card answered yet in this session"}

    last_entry = session["history"][-1]
    followups: List[Dict[str, str]] = last_entry.setdefault("followups", [])
    if len(followups) >= MAX_FOLLOWUPS_PER_CARD:
        return {
            "answer": "Let's save more questions for after the game — ready for the next card?",
            "followups_used": len(followups),
            "followups_allowed": MAX_FOLLOWUPS_PER_CARD,
            "limit_reached": True,
        }

    # The card the follow-up is about is at deck[index-1] (we already advanced).
    last_card_index = session["index"] - 1
    if last_card_index < 0 or last_card_index >= len(session["deck"]):
        return {"error": "No active card for follow-up"}
    card = session["deck"][last_card_index]

    question = (req.question or "").strip()
    reply = answer_followup(
        model=OLLAMA_MODEL,
        card=card,
        last_feedback=last_entry.get("feedback") or {},
        history=followups,
        question=question,
    )

    followups.append({"question": question, "answer": reply})

    return {
        "answer": reply,
        "followups_used": len(followups),
        "followups_allowed": MAX_FOLLOWUPS_PER_CARD,
        "limit_reached": len(followups) >= MAX_FOLLOWUPS_PER_CARD,
    }


@app.post("/api/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)) -> Dict[str, str]:
    suffix = Path(audio.filename or "a.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name

    text = ""
    try:
        assert _whisper_model is not None
        result = _whisper_model.transcribe(tmp_path, language="en", task="transcribe")
        text = (result.get("text") or "").strip()
    except Exception as e:
        print(f"[transcribe] error: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return {"text": text}


@app.post("/api/tts")
async def text_to_speech(req: TTSRequest):
    wav_path = tts.synthesize(req.text, tone=req.tone)
    if wav_path and Path(wav_path).exists():
        return FileResponse(wav_path, media_type="audio/wav", filename="speech.wav")
    return {"error": "TTS failed"}


@app.post("/api/summary")
async def get_summary(session_id: str) -> Dict[str, Any]:
    session = _sessions.get(session_id)
    if not session:
        return {"error": "Invalid session"}

    summary = _summarize_session(session)
    if summary["total_cards"] == 0:
        summary["tip"] = "Every answer counts — try speaking out loud next time."
        return summary

    tip = generate_summary_tip(
        model=OLLAMA_MODEL,
        score=summary["score"],
        total=summary["max_score"],
        best_mode=summary["best_mode"],
        worst_mode=summary["worst_mode"],
    )
    summary["tip"] = tip
    return summary