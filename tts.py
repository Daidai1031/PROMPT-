"""
ChatTTS simplified TTS module for PROMPT! game.

Goals:
- one fixed engaging female voice
- avoid per-segment tone switching inside one long utterance
- generate one continuous utterance for smoother playback
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import torch
import torchaudio

import ChatTTS


VOICE_SEED = 4099
SAMPLE_RATE = 24_000

TTS_CACHE_DIR = Path("/tmp/prompt_tts_cache")
TTS_CACHE_DIR.mkdir(exist_ok=True)


TONE_PROFILES: Dict[str, Dict] = {
    "narrator": {
        "refine_prompt": "[oral_2][laugh_0][break_4]",
        "temperature": 0.30,
        "top_P": 0.70,
        "top_K": 20,
    },
    "curious": {
        "refine_prompt": "[oral_3][laugh_0][break_4]",
        "temperature": 0.32,
        "top_P": 0.70,
        "top_K": 20,
    },
    "warm": {
        "refine_prompt": "[oral_3][laugh_0][break_4]",
        "temperature": 0.32,
        "top_P": 0.70,
        "top_K": 20,
    },
    "celebrate": {
        "refine_prompt": "[oral_3][laugh_0][break_4]",
        "temperature": 0.34,
        "top_P": 0.70,
        "top_K": 20,
    },
}

_SENTENCE_END = re.compile(r"([.!?])(\s+|$)")
_CHAT: Optional[ChatTTS.Chat] = None
_SPEAKER_EMB = None


def _decorate_text(text: str) -> str:
    """
    Keep decoration minimal.
    Just insert soft sentence breaks.
    """
    t = " ".join((text or "").strip().split())
    if not t:
        return t
    return _SENTENCE_END.sub(r"\1 [uv_break] ", t).strip()


def _ensure_loaded() -> None:
    global _CHAT, _SPEAKER_EMB
    if _CHAT is not None:
        return

    print("[tts] Loading ChatTTS...")
    chat = ChatTTS.Chat()
    chat.load(compile=False)

    torch.manual_seed(VOICE_SEED)
    _SPEAKER_EMB = chat.sample_random_speaker()
    _CHAT = chat
    print(f"[tts] Voice locked with seed {VOICE_SEED}.")


def _save_wav(audio, out_path: str) -> bool:
    try:
        if isinstance(audio, np.ndarray):
            tensor = torch.from_numpy(audio).float()
        else:
            tensor = audio.float()

        if tensor.dim() == 1:
            try:
                torchaudio.save(out_path, tensor.unsqueeze(0), SAMPLE_RATE)
                return True
            except Exception:
                torchaudio.save(out_path, tensor, SAMPLE_RATE)
                return True
        else:
            torchaudio.save(out_path, tensor, SAMPLE_RATE)
            return True
    except Exception as e:
        print(f"[tts] _save_wav error: {e}")
        return False


def _cache_path(text: str, tone: str) -> str:
    key = hashlib.md5(f"{tone}::{text}".encode("utf-8")).hexdigest()
    return str(TTS_CACHE_DIR / f"{key}.wav")


def synthesize(text: str, tone: str = "narrator", out_path: Optional[str] = None) -> Optional[str]:
    if not text or not text.strip():
        return None

    if tone not in TONE_PROFILES:
        tone = "narrator"

    cleaned = " ".join(text.strip().split())
    decorated = _decorate_text(cleaned)
    if out_path is None:
        out_path = _cache_path(decorated, tone)

    if Path(out_path).exists():
        return out_path

    profile = TONE_PROFILES[tone]

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
    Combine multiple text segments into one long utterance.
    Use ONE tone only, taken from the first valid segment.
    This avoids tone-switch stalls and makes playback smoother.
    """
    if not segments:
        return None

    valid_segments = []
    chosen_tone = "narrator"

    for text, tone in segments:
        if text and text.strip():
            valid_segments.append(" ".join(text.strip().split()))
            if tone in TONE_PROFILES and chosen_tone == "narrator":
                chosen_tone = tone

    if not valid_segments:
        return None

    combined_text = " ".join(valid_segments)
    return synthesize(combined_text, tone=chosen_tone, out_path=out_path)


def warmup() -> None:
    _ensure_loaded()
    try:
        synthesize("Ready.", tone="narrator", out_path=str(TTS_CACHE_DIR / "warmup.wav"))
        print("[tts] warmup complete.")
    except Exception as e:
        print(f"[tts] warmup failed: {e}")