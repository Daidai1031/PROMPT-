"""
PROMPT! Game Server
FastAPI backend for the touchscreen + voice interactive game.
Connects: Whisper (STT), Ollama (LLM), Piper (TTS), rule-based evaluation.
"""

import json
import random
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import whisper
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from llm import generate_feedback, generate_summary_tip
from rules import check_answer

# ─── Config ───
WHISPER_MODEL = "small"
OLLAMA_MODEL = "llama3"
CARDS_PATH = "cards.json"
PIPER_BIN = str(Path.home() / ".local" / "bin" / "piper")
PIPER_MODEL = str(Path.home() / "thor_game_mvp" / "en-us-amy-low.onnx")
TTS_OUTPUT = "/tmp/tts_game_output.wav"

# ─── App ───
app = FastAPI(title="PROMPT! Game Server")

# ─── State ───
whisper_model = None
game_sessions: Dict[str, Any] = {}


# ─── Models ───
class AnswerRequest(BaseModel):
    session_id: str
    selected_option: str  # "A", "B", "C", "D"


class TTSRequest(BaseModel):
    text: str


# ─── Helpers ───
def load_cards() -> List[Dict[str, Any]]:
    p = Path(CARDS_PATH)
    if not p.exists():
        raise FileNotFoundError(f"Could not find {CARDS_PATH}")
    with p.open("r", encoding="utf-8") as f:
        cards = json.load(f)
    return cards


def do_tts(text: str) -> Optional[str]:
    """Generate TTS wav file, return path if successful."""
    if not text or not text.strip():
        return None
    clean = text.encode("ascii", "ignore").decode("ascii").strip()
    if not clean:
        return None
    # Use unique temp file to avoid race conditions
    out_path = f"/tmp/tts_{int(time.time() * 1000)}.wav"
    try:
        result = subprocess.run(
            [PIPER_BIN, "--model", PIPER_MODEL, "--output_file", out_path],
            input=clean,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0 and Path(out_path).exists():
            return out_path
    except Exception:
        pass
    return None


def get_best_and_worst(category_stats):
    if not category_stats:
        return {"best": "N/A", "worst": "N/A"}
    scored = []
    for cat, stats in category_stats.items():
        total = stats["total"]
        avg = stats["correct"] / total if total else 0
        scored.append((cat, avg))
    scored.sort(key=lambda x: x[1], reverse=True)
    return {"best": scored[0][0], "worst": scored[-1][0]}


# ─── Startup ───
@app.on_event("startup")
async def startup():
    global whisper_model
    print("Loading Whisper model...")
    whisper_model = whisper.load_model(WHISPER_MODEL)
    print("Whisper model loaded.")


# ─── Routes ───

@app.get("/", response_class=HTMLResponse)
async def index():
    return Path("index.html").read_text(encoding="utf-8")


@app.get("/api/cards")
async def get_cards():
    """Return all cards (frontend will handle selection)."""
    cards = load_cards()
    return cards


@app.post("/api/start")
async def start_game():
    """Start a new game session, return shuffled card IDs."""
    cards = load_cards()
    random.shuffle(cards)
    session_id = f"s_{int(time.time() * 1000)}"
    game_sessions[session_id] = {
        "cards": cards,
        "current_index": 0,
        "score": 0,
        "total": len(cards),
        "results": [],
        "category_stats": {},
    }
    return {
        "session_id": session_id,
        "total_cards": len(cards),
        "card": cards[0],
    }


@app.post("/api/answer")
async def submit_answer(req: AnswerRequest):
    """Submit a touch-selected answer."""
    session = game_sessions.get(req.session_id)
    if not session:
        return {"error": "Invalid session"}

    idx = session["current_index"]
    card = session["cards"][idx]

    # Build a fake user_answer from selected option for rule matching
    option_text = card["options"].get(req.selected_option, "")
    user_answer = f"{req.selected_option} {option_text}"

    result = check_answer(card, user_answer)

    # Generate LLM feedback
    feedback = generate_feedback(
        model=OLLAMA_MODEL,
        question=card["question"],
        user_answer=user_answer,
        judgement=result["judgement"],
        explanation=card["explanation"],
        category=card["category"],
        matched_reason=result["matched_reason"],
        misconception=card.get("misconception", ""),
        teaching_focus=card.get("teaching_focus", ""),
        source_note=card.get("source_note", ""),
        verification_tip=card.get("verification_tip", ""),
    )

    # Update session
    if result["judgement"] == "correct":
        session["score"] += 1
    cat = card["category"]
    if cat not in session["category_stats"]:
        session["category_stats"][cat] = {"total": 0, "correct": 0, "partial": 0, "incorrect": 0}
    session["category_stats"][cat]["total"] += 1
    session["category_stats"][cat][result["judgement"]] += 1
    session["results"].append(result["judgement"])

    # Advance
    session["current_index"] += 1
    has_next = session["current_index"] < session["total"]
    next_card = session["cards"][session["current_index"]] if has_next else None

    return {
        "judgement": result["judgement"],
        "score": result["score"],
        "matched_reason": result["matched_reason"],
        "feedback": feedback,
        "explanation": card["explanation"],
        "verification_tip": card.get("verification_tip", ""),
        "current_score": session["score"],
        "has_next": has_next,
        "next_card": next_card,
    }


@app.post("/api/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    """Receive audio from browser, transcribe with Whisper."""
    # Save uploaded audio
    suffix = ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = whisper_model.transcribe(tmp_path, language="en", task="transcribe")
        text = result.get("text", "").strip()
    except Exception as e:
        text = ""
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return {"text": text}


@app.post("/api/tts")
async def text_to_speech(req: TTSRequest):
    """Generate TTS audio and return wav file."""
    wav_path = do_tts(req.text)
    if wav_path and Path(wav_path).exists():
        return FileResponse(wav_path, media_type="audio/wav", filename="speech.wav")
    return {"error": "TTS failed"}


@app.post("/api/summary")
async def get_summary(session_id: str):
    """Get game summary with LLM tip."""
    session = game_sessions.get(session_id)
    if not session:
        return {"error": "Invalid session"}

    cat_result = get_best_and_worst(session["category_stats"])
    score = session["score"]
    total = session["total"]

    tip = generate_summary_tip(
        model=OLLAMA_MODEL,
        best_category=cat_result["best"],
        worst_category=cat_result["worst"],
        score=f"{score}/{total}",
    )

    return {
        "score": score,
        "total": total,
        "best_category": cat_result["best"],
        "worst_category": cat_result["worst"],
        "category_stats": session["category_stats"],
        "tip": tip,
        "results": session["results"],
    }