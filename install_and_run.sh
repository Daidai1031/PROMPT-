#!/usr/bin/env bash
# PROMPT! v2 — first-time install + run helper for Jetson AGX Thor.
# Usage:
#   ./install_and_run.sh install   # installs Python deps (one-time)
#   ./install_and_run.sh run       # starts the FastAPI server on port 8000
#   ./install_and_run.sh tts-test  # quick smoke-test of ChatTTS multi-tone
set -euo pipefail

cmd="${1:-run}"

case "$cmd" in
  install)
    echo "[install] Python dependencies..."
    pip install --break-system-packages \
        fastapi "uvicorn[standard]" python-multipart \
        openai-whisper ollama \
        ChatTTS torch torchaudio numpy
    echo "[install] Pulling llama3 via Ollama..."
    ollama pull llama3 || echo "[warn] Ollama not running — pull llama3 manually later."
    echo "[install] Done."
    ;;

  run)
    echo "[run] Starting PROMPT! server on :8000 ..."
    uvicorn server:app --host 0.0.0.0 --port 8000 --reload
    ;;

  tts-test)
    echo "[tts-test] Generating one sample per tone..."
    python3 -c "
import tts
for tone in ['narrator', 'curious', 'warm', 'celebrate']:
    p = tts.synthesize(f'Hello! This is the {tone} voice speaking.', tone=tone,
                       out_path=f'/tmp/prompt_tone_test_{tone}.wav')
    print(f'  {tone}: {p}')
"
    echo "[tts-test] Play with: aplay /tmp/prompt_tone_test_warm.wav"
    ;;

  *)
    echo "Usage: $0 {install|run|tts-test}"
    exit 1
    ;;
esac