"""
ChatTTS multi-tone TTS module for PROMPT! game.

Design:
- ONE fixed speaker (young, lively female voice) — locked by torch seed
- MULTIPLE tone profiles for the same speaker, controlled via:
    * params_refine_text prompts: [oral_X][laugh_X][break_X]
    * temperature: higher = more expressive/varied
    * inline tags inserted into text: [uv_break], [laugh], [lbreak]
- Four tone roles, matching the four moments in a turn:
    1. NARRATOR  — reads card body neutrally, clear and steady
    2. CURIOUS   — reads the "tip/verification habit" with playful curiosity
    3. WARM      — reads personalized feedback with encouragement
    4. CELEBRATE — reads scores / game results with excitement
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import torch
import torchaudio

import ChatTTS


# ─── Voice selection ───
# Seed 4099 = young female voice (per community testing).
# Alternative lively female seeds: 3333, 5099.
# You can change this once to shift the whole character.
VOICE_SEED = 4099
SAMPLE_RATE = 24_000

# Cache directory for pre-generated or repeated TTS output
TTS_CACHE_DIR = Path("/tmp/prompt_tts_cache")
TTS_CACHE_DIR.mkdir(exist_ok=True)


# ─── Tone profiles ───
# Each profile defines how the SAME speaker should deliver a different kind of line.
# refine_prompt is the ChatTTS control string for the text-refinement stage.
# temperature controls variability; higher = more expressive.
# inline_hint is a tag pattern we can inject into the text for extra flavor.
TONE_PROFILES: Dict[str, Dict] = {
    "narrator": {
        # Card body — clear, neutral, measured. Minimal oral fillers, medium pauses.
        "refine_prompt": "[oral_1][laugh_0][break_4]",
        "temperature": 0.3,
        "top_P": 0.7,
        "top_K": 20,
        "inline_style": "neutral",
    },
    "curious": {
        # Tips / "ask yourself..." habits — playful, inquisitive, slightly conspiratorial.
        "refine_prompt": "[oral_3][laugh_0][break_5]",
        "temperature": 0.45,
        "top_P": 0.7,
        "top_K": 20,
        "inline_style": "curious",
    },
    "warm": {
        # Feedback — kind, encouraging, a little conversational.
        "refine_prompt": "[oral_4][laugh_1][break_5]",
        "temperature": 0.4,
        "top_P": 0.7,
        "top_K": 20,
        "inline_style": "warm",
    },
    "celebrate": {
        # Scores & game-end — bright, energetic, with a light laugh.
        "refine_prompt": "[oral_5][laugh_1][break_3]",
        "temperature": 0.5,
        "top_P": 0.7,
        "top_K": 20,
        "inline_style": "celebrate",
    },
}


# ─── Inline text decoration ───
# We lightly inject ChatTTS control tags into the text per tone, so even the
# same sentence sounds different under narrator vs celebrate.
_SENTENCE_END = re.compile(r"([.!?])(\s+|$)")


def _decorate_text(text: str, style: str) -> str:
    """Inject [uv_break] / [laugh] tags to match the tone."""
    t = text.strip()
    if not t:
        return t

    if style == "neutral":
        # Add gentle breaks between sentences, nothing else.
        return _SENTENCE_END.sub(r"\1 [uv_break] ", t)

    if style == "curious":
        # Soft breaks + a little rising end.
        decorated = _SENTENCE_END.sub(r"\1 [uv_break] ", t)
        return decorated + " [lbreak]"

    if style == "warm":
        # Warm breaks; one tiny chuckle at the end if the sentence is positive.
        decorated = _SENTENCE_END.sub(r"\1 [uv_break] ", t)
        # Heuristic: add light laugh marker for encouraging words
        if re.search(r"\b(great|awesome|nice|love|brilliant|well done)\b", t, re.I):
            decorated = decorated + " [laugh]"
        return decorated

    if style == "celebrate":
        # More energetic breaks + laugh tag for game-over cheer.
        decorated = _SENTENCE_END.sub(r"\1 [uv_break] ", t)
        return decorated + " [laugh] [lbreak]"

    return t


# ─── Model singleton ───
_CHAT: Optional[ChatTTS.Chat] = None
_SPEAKER_EMB = None


def _ensure_loaded() -> None:
    """Lazy-load ChatTTS and fix the speaker embedding."""
    global _CHAT, _SPEAKER_EMB
    if _CHAT is not None:
        return

    print("[tts] Loading ChatTTS...")
    chat = ChatTTS.Chat()
    # compile=True is faster on capable GPUs but slow to start; keep False by default.
    chat.load(compile=False)

    # Lock the speaker identity so every tone uses the same voice.
    torch.manual_seed(VOICE_SEED)
    _SPEAKER_EMB = chat.sample_random_speaker()
    _CHAT = chat
    print(f"[tts] Voice locked with seed {VOICE_SEED}.")


def _save_wav(audio, out_path: str) -> bool:
    """
    Save ChatTTS output to a WAV file, handling both old and new torchaudio
    dimensional expectations. Mirrors the pattern in the official README.
    """
    try:
        if isinstance(audio, np.ndarray):
            tensor = torch.from_numpy(audio).float()
        else:
            tensor = audio.float()

        if tensor.dim() == 1:
            # Newer torchaudio expects (channels, samples) — unsqueeze.
            try:
                torchaudio.save(out_path, tensor.unsqueeze(0), SAMPLE_RATE)
                return True
            except Exception:
                # Older torchaudio was happy with 1D.
                torchaudio.save(out_path, tensor, SAMPLE_RATE)
                return True
        else:
            torchaudio.save(out_path, tensor, SAMPLE_RATE)
            return True
    except Exception as e:
        print(f"[tts] _save_wav error: {e}")
        return False


# ─── Public API ───
def synthesize(text: str, tone: str = "narrator", out_path: Optional[str] = None) -> Optional[str]:
    """
    Generate a WAV file for `text` using the given `tone`.
    Returns the file path on success, or None on failure.
    """
    if not text or not text.strip():
        return None

    if tone not in TONE_PROFILES:
        tone = "narrator"

    profile = TONE_PROFILES[tone]
    decorated = _decorate_text(text, profile["inline_style"])

    if out_path is None:
        out_path = str(TTS_CACHE_DIR / f"tts_{tone}_{int(time.time() * 1000)}.wav")

    try:
        _ensure_loaded()
        assert _CHAT is not None and _SPEAKER_EMB is not None

        params_infer_code = ChatTTS.Chat.InferCodeParams(
            spk_emb=_SPEAKER_EMB,
            temperature=profile["temperature"],
            top_P=profile["top_P"],
            top_K=profile["top_K"],
        )
        params_refine_text = ChatTTS.Chat.RefineTextParams(
            prompt=profile["refine_prompt"],
        )

        wavs = _CHAT.infer(
            [decorated],
            params_refine_text=params_refine_text,
            params_infer_code=params_infer_code,
        )

        if not wavs or len(wavs) == 0:
            return None

        if _save_wav(wavs[0], out_path):
            return out_path
        return None

    except Exception as e:
        print(f"[tts] synthesize failed ({tone}): {e}")
        return None


def synthesize_multi(segments: list[Tuple[str, str]], out_path: Optional[str] = None) -> Optional[str]:
    """
    Synthesize multiple (text, tone) segments and concatenate them into one WAV.
    Useful for: narrator reads card -> warm reads feedback -> curious reads tip.
    """
    if not segments:
        return None

    audio_parts = []
    try:
        _ensure_loaded()
        assert _CHAT is not None and _SPEAKER_EMB is not None

        for text, tone in segments:
            if not text or not text.strip():
                continue
            if tone not in TONE_PROFILES:
                tone = "narrator"
            profile = TONE_PROFILES[tone]
            decorated = _decorate_text(text, profile["inline_style"])

            params_infer_code = ChatTTS.Chat.InferCodeParams(
                spk_emb=_SPEAKER_EMB,
                temperature=profile["temperature"],
                top_P=profile["top_P"],
                top_K=profile["top_K"],
            )
            params_refine_text = ChatTTS.Chat.RefineTextParams(
                prompt=profile["refine_prompt"],
            )
            wavs = _CHAT.infer(
                [decorated],
                params_refine_text=params_refine_text,
                params_infer_code=params_infer_code,
            )
            if wavs and len(wavs) > 0:
                a = wavs[0]
                if isinstance(a, np.ndarray):
                    audio_parts.append(torch.from_numpy(a).float())
                else:
                    audio_parts.append(a.float())
                # 0.3s silence between segments for natural pacing
                audio_parts.append(torch.zeros(int(SAMPLE_RATE * 0.3)))

        if not audio_parts:
            return None

        combined = torch.cat(audio_parts, dim=0)
        if out_path is None:
            out_path = str(TTS_CACHE_DIR / f"tts_multi_{int(time.time() * 1000)}.wav")
        if _save_wav(combined, out_path):
            return out_path
        return None

    except Exception as e:
        print(f"[tts] synthesize_multi failed: {e}")
        return None


def warmup() -> None:
    """Optional: load model + run one tiny inference so first real request is fast."""
    _ensure_loaded()
    try:
        synthesize("Ready.", tone="narrator", out_path=str(TTS_CACHE_DIR / "warmup.wav"))
        print("[tts] warmup complete.")
    except Exception as e:
        print(f"[tts] warmup failed: {e}")