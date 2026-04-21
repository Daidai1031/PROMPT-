"""
PROMPT! Game Server v2 — discernment + usage cards, ChatTTS multi-tone.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

import whisper
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import tts
from cards_loader import pick_deck
from llm import generate_feedback, generate_summary_tip
from rules import check_answer

# ─── Config ───
WHISPER_MODEL = "small"
OLLAMA_MODEL = "llama3"
CARDS_PER_GAME = 6

# ─── App ───
app = FastAPI(title="PROMPT! Game Server v2")

# ─── Runtime state ───
_whisper_model = None
_sessions: Dict[str, Dict[str, Any]] = {}


# ─── Request models ───
class StartRequest(BaseModel):
    mode: str = "mixed"  # "discernment" | "usage" | "mixed"
    num_cards: Optional[int] = None


class AnswerRequest(BaseModel):
    session_id: str
    user_answer: str


class TTSRequest(BaseModel):
    text: str
    tone: str = "narrator"  # narrator | curious | warm | celebrate


# ─── Startup ───
@app.on_event("startup")
async def startup() -> None:
    global _whisper_model
    print("[startup] Loading Whisper ...")
    _whisper_model = whisper.load_model(WHISPER_MODEL)
    print("[startup] Warming ChatTTS ...")
    try:
        tts.warmup()
    except Exception as e:
        print(f"[startup] TTS warmup skipped: {e}")
    print("[startup] Ready.")


# ─── Helpers ───
def _mode_of(card: Dict[str, Any]) -> str:
    return card.get("category", "unknown")


def _public_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """Return only the fields the frontend needs to render the FRONT of the card."""
    return {
        "id": card["id"],
        "category": card["category"],
        "problem_type": card["problem_type"],
        "difficulty": card["difficulty"],
        "title": card["title"],
        "body": card["body"],
    }


def _back_view(card: Dict[str, Any]) -> Dict[str, Any]:
    """Return fields used on the flipped BACK of the card after an answer."""
    return {
        "verdict": card["verdict"],
        "deep_insight": card["deep_insight"],
        "habit": card["habit"],
        "references": card["references"],
        "suggested_prompt": card.get("suggested_prompt"),
    }


def _summarize_session(session: Dict[str, Any]) -> Dict[str, Any]:
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
    return {
        "score": int(session["score"]),
        "max_score": int(session["total_cards"]) * 10,
        "total_cards": session["total_cards"],
        "per_mode": per_mode,
        "best_mode": best or "n/a",
        "worst_mode": worst or "n/a",
        "history": session["history"],
    }


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
        "per_mode": {},   # {"discernment": {"total": n, "score": x}, ...}
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
    result = check_answer(card, req.user_answer)

    # LLM generates the two-line feedback
    feedback = generate_feedback(
        model=OLLAMA_MODEL,
        card=card,
        user_answer=req.user_answer,
        tier=result["tier"],
    )

    # Update session state
    mode = _mode_of(card)
    stats = session["per_mode"].setdefault(mode, {"total": 0, "score": 0})
    stats["total"] += 1
    stats["score"] += result["score"]
    session["score"] += result["score"]

    session["history"].append({
        "card_id": card["id"],
        "problem_type": card["problem_type"],
        "category": card["category"],
        "user_answer": req.user_answer,
        "score": result["score"],
        "tier": result["tier"],
        "judgement": result["judgement"],
    })

    # Advance
    session["index"] += 1
    has_next = session["index"] < session["total_cards"]
    next_card = session["deck"][session["index"]] if has_next else None

    return {
        "score": result["score"],
        "tier": result["tier"],
        "judgement": result["judgement"],
        "matched_reason": result["matched_reason"],
        "feedback": feedback,  # {"reaction": str, "habit": str}
        "card_back": _back_view(card),
        "current_total_score": session["score"],
        "max_possible": session["total_cards"] * 10,
        "has_next": has_next,
        "next_card": _public_card(next_card) if next_card else None,
    }


@app.post("/api/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)) -> Dict[str, str]:
    """Save upload to a temp file, transcribe with Whisper."""
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
    """Generate a wav in the requested tone and return it."""
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
    tip = generate_summary_tip(
        model=OLLAMA_MODEL,
        score=summary["score"],
        total=summary["max_score"],
        best_mode=summary["best_mode"],
        worst_mode=summary["worst_mode"],
    )
    summary["tip"] = tip
    return summary