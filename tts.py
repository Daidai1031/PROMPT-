"""
Kokoro TTS module for PROMPT! v3.

Why Kokoro over ChatTTS:
  - 82M params vs ChatTTS's ~500M → fast cold start (~3s vs ~30s)
  - deterministic, no refine-text pass → no per-segment stall
  - single-voice by design → matches our "one coach" brief
  - ~0.15s inference for a typical sentence on Jetson AGX Thor

API kept COMPATIBLE with the old tts.py:
  - synthesize(text, tone=..., out_path=None) -> str | None
  - synthesize_multi(segments, out_path=None) -> str | None
  - warmup() -> None

Tone is accepted but only lightly varied — we nudge speed/pitch, not timbre.
One consistent warm voice is what the child actually hears, and that is the
point. Tone-switching inside one utterance was the source of the stall in v2.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import soundfile as sf

# Kokoro is a small HF pipeline package. Install with:
#   pip install kokoro soundfile --break-system-packages
# It pulls its own ONNX weights on first run (~325 MB) into ~/.cache/kokoro.
from kokoro import KPipeline


# ── Config ─────────────────────────────────────────────────────────
# af_heart / af_bella / af_sarah are the community-tested warm female voices.
VOICE_ID = "af_bella"
LANG_CODE = "a"   # 'a' = American English
SAMPLE_RATE = 24_000

TTS_CACHE_DIR = Path("/tmp/prompt_tts_cache")
TTS_CACHE_DIR.mkdir(exist_ok=True)

# Tone = a tiny speed tweak. No model swap, no voice swap.
# Kokoro's `speed` parameter is the only prosodic knob we expose.
TONE_SPEED: Dict[str, float] = {
    "narrator":  1.00,   # calm, explaining the card
    "curious":   1.00,   # asking a question
    "warm":      0.98,   # giving feedback — just a hair slower to feel kind
    "celebrate": 1.05,   # slightly brighter for welcome/finale
}

_PIPELINE: Optional[KPipeline] = None


# ── Helpers ────────────────────────────────────────────────────────

def _ensure_loaded() -> None:
    global _PIPELINE
    if _PIPELINE is not None:
        return
    print("[tts] Loading Kokoro pipeline...")
    _PIPELINE = KPipeline(lang_code=LANG_CODE)
    print(f"[tts] Kokoro ready, voice={VOICE_ID}")


def _cache_path(text: str, tone: str) -> str:
    key = hashlib.md5(f"{VOICE_ID}::{tone}::{text}".encode("utf-8")).hexdigest()
    return str(TTS_CACHE_DIR / f"{key}.wav")


def _collect_audio(generator) -> Optional[np.ndarray]:
    """
    Kokoro yields (graphemes, phonemes, audio_chunk) per sentence.
    We concatenate all audio chunks into a single numpy array so the frontend
    gets ONE seamless clip — this is what v2 lacked, causing audible gaps.
    """
    chunks: List[np.ndarray] = []
    for _, _, audio in generator:
        if audio is None:
            continue
        arr = audio.cpu().numpy() if hasattr(audio, "cpu") else np.asarray(audio)
        if arr.size == 0:
            continue
        chunks.append(arr.astype(np.float32))
    if not chunks:
        return None
    return np.concatenate(chunks)


def _save_wav(audio: np.ndarray, out_path: str) -> bool:
    try:
        sf.write(out_path, audio, SAMPLE_RATE)
        return True
    except Exception as e:
        print(f"[tts] _save_wav error: {e}")
        return False


# ── Public API (kept identical to v2) ──────────────────────────────

def synthesize(
    text: str,
    tone: str = "narrator",
    out_path: Optional[str] = None,
) -> Optional[str]:
    """Render ONE utterance at the chosen tone-speed. Cached on disk."""
    if not text or not text.strip():
        return None

    cleaned = " ".join(text.strip().split())
    speed = TONE_SPEED.get(tone, 1.0)
    if out_path is None:
        out_path = _cache_path(cleaned, tone)

    if Path(out_path).exists():
        return out_path

    try:
        _ensure_loaded()
        assert _PIPELINE is not None
        generator = _PIPELINE(cleaned, voice=VOICE_ID, speed=speed)
        audio = _collect_audio(generator)
        if audio is None or audio.size == 0:
            return None
        if _save_wav(audio, out_path):
            return out_path
        return None
    except Exception as e:
        print(f"[tts] synthesize failed ({tone}): {e}")
        return None


def synthesize_multi(
    segments: List[Tuple[str, str]],
    out_path: Optional[str] = None,
) -> Optional[str]:
    """
    Combine multiple (text, tone) segments into one continuous utterance.

    v2 stalled because each segment restarted the model pipeline. In v3 we
    concatenate the TEXT first (Kokoro handles sentence-level prosody
    internally), and use the first valid tone's speed for the whole clip.
    That yields a single seamless WAV with ONE model call.
    """
    if not segments:
        return None

    valid_texts: List[str] = []
    chosen_tone = "narrator"
    picked = False
    for text, tone in segments:
        if text and text.strip():
            valid_texts.append(" ".join(text.strip().split()))
            if not picked and tone in TONE_SPEED:
                chosen_tone = tone
                picked = True

    if not valid_texts:
        return None

    # Join with a soft pause — periods make Kokoro insert a natural beat.
    combined = ". ".join(t.rstrip(".") for t in valid_texts) + "."
    return synthesize(combined, tone=chosen_tone, out_path=out_path)


def warmup() -> None:
    """Pre-load weights and render one tiny clip so the first real call is fast."""
    _ensure_loaded()
    try:
        synthesize("Ready.", tone="narrator",
                   out_path=str(TTS_CACHE_DIR / "warmup.wav"))
        print("[tts] warmup complete.")
    except Exception as e:
        print(f"[tts] warmup failed: {e}")