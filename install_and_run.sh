#!/usr/bin/env bash
# PROMPT! v3 — install + run for Jetson AGX Thor.
# Usage:
#   ./install_and_run.sh install   # one-time: Python deps + Kokoro weights
#   ./install_and_run.sh run       # starts FastAPI server on :8000
#   ./install_and_run.sh tts-test  # quick TTS smoke test
set -euo pipefail

cmd="${1:-run}"

case "$cmd" in
  install)
    echo "[install] Python dependencies..."
    # Core service + STT
    python -m pip install --break-system-packages \
        fastapi "uvicorn[standard]" python-multipart \
        openai-whisper ollama

    # Kokoro TTS — 82M model, downloads ~325 MB of ONNX weights on first use
    python -m pip install --break-system-packages \
        kokoro soundfile numpy

    echo "[install] Pulling llama3 via Ollama..."
    ollama pull llama3 || echo "[warn] Ollama not running — pull llama3 manually later."
    echo "[install] Done."
    ;;

  run)
    echo "[run] Starting PROMPT! v4 server on :8000 ..."
    pkill -f "uvicorn server:app" || true
    python -m uvicorn server:app --host 0.0.0.0 --port 8000
    ;;

  tts-test)
    echo "[tts-test] Rendering one sample per tone (same voice, different speeds)..."
    python -c "
import tts, time
for tone in ['narrator', 'curious', 'warm', 'celebrate']:
    t0 = time.time()
    p = tts.synthesize(f'Hello! This is the {tone} voice speaking.',
                       tone=tone, out_path=f'/tmp/prompt_tone_test_{tone}.wav')
    dt = time.time() - t0
    print(f'  {tone:10s} -> {p}  ({dt:.2f}s)')
"
    echo "[tts-test] Play with: aplay /tmp/prompt_tone_test_warm.wav"
    ;;

  *)
    echo "Usage: $0 {install|run|tts-test}"
    exit 1
    ;;
esac