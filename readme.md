# PROMPT! — AI Literacy Card Game

A voice-first, fully-offline AI literacy game for children age 10+, running entirely on an NVIDIA Jetson AGX Thor. Children scan or pick a physical reflection card, read it, **say what they notice out loud**, and a coach voice gives kind, specific feedback. After each answer they can ask the coach free-form follow-up questions before moving on.

---

## Table of Contents

1. [Background & Motivation](#1-background--motivation)
2. [User Flow](#2-user-flow)
3. [Hardware Setup](#3-hardware-setup)
4. [Software Setup & Running the Game](#4-software-setup--running-the-game)
5. [System Architecture](#5-system-architecture)
6. [Card Format & Game Modes](#6-card-format--game-modes)
7. [Technology Choices & Rationale](#7-technology-choices--rationale)
8. [Version History](#8-version-history)
9. [Troubleshooting](#9-troubleshooting)
10. [Tuning Knobs](#10-tuning-knobs)
11. [Future Directions](#11-future-directions)

---

## 1. Background & Motivation

### The problem

Children growing up today encounter AI-generated content, algorithmic feeds, and emotionally engineered media before they have the cognitive tools to recognize what's happening. Traditional media literacy curricula are reading-heavy and didactic — they tell kids what to think rather than build the muscle of *noticing*.

Three specific cognitive habits are missing in most kids' (and many adults') media diet:

1. **Frame awareness** — recognizing that the same fact can be packaged through different lenses ("space relics" vs "space junk") for different audiences.
2. **Emotion recognition** — noticing when a post is engineered to hijack a feeling (fear, outrage, urgency) before passing it along.
3. **Prompt literacy** — knowing how to ask AI in ways that surface multiple viewpoints instead of locking into one.

### The design

PROMPT! is a card game that drills these habits through **spoken reflection** instead of multiple choice. Each card poses a scenario; the child reads it, says aloud what they notice, and a kind AI coach responds with three things: a reaction to their thinking, a habit to keep, and an invitation to ask follow-up questions.

The game is **fully on-device** — speech-to-text, LLM, text-to-speech, and OCR all run on the Jetson with zero cloud dependencies. This is intentional:

- **Privacy** — children's voices and answers never leave the device.
- **Offline-capable** — works in classrooms, libraries, and rural settings without internet.
- **Latency** — no network round-trips; coach feedback arrives in 2–4 seconds.
- **Sustainability** — no per-session API costs; the device is the entire stack.

### Target audience

- **Primary**: children age 10+ in school, library, or family settings.
- **Secondary**: educators and parents who want to introduce AI literacy without preachy lectures.

---

## 2. User Flow

### High-level flow

```
START
  │
  ▼
HOME ─────────────────┐
  │                   │
  ├─► [Scan Card]     │  scan a physical card
  │                   │
  └─► [Random]        │  pick a mode, get 6 cards dealt
                      │
                      ▼
                  SCAN screen (if scan mode)
                      │  camera detects #NN + title
                      │  shows confirmation panel
                      ▼
                   GAME screen
                      │  read card → speak answer
                      │  reveal back of card
                      │  hear feedback (3 lines)
                      │  optional follow-up Q&A
                      ▼
                  [Scan Next Card] ◄─── back to SCAN
                  [Next Card →]    ◄─── auto-advance (random mode)
                  [End game]       ───► SUMMARY
                      │
                      ▼
                  SUMMARY screen
                      │  total score
                      │  per-mode breakdown
                      │  follow-up count
                      │  one-line takeaway tip
                      ▼
                  [Play Again 🔄]
```

### Detailed answering loop

For each card, the child's experience is:

1. **Coach reads the card aloud** (Kokoro TTS plays the title + body + the question).
2. **Child taps the mic and speaks**. Mic auto-stops after 1.2s of silence (or after 15s max).
3. **Server transcribes** (Whisper) → **scores** (rule engine, optionally LLM-promoted) → **writes feedback** (Llama 3).
4. **Card flips** to its back side, showing Deep Insight, Habit, and (for usage cards) a strong example prompt.
5. **Coach speaks 3 short lines** in one continuous TTS clip:
   - **Reaction** — warm sentence about what the child said
   - **Habit** — the takeaway to carry forward
   - **Invite** — "Anything you want to ask me about this?"
6. **Child can either**:
   - Tap the mic to ask a follow-up question (up to 4 per card)
   - Hit "Scan Next Card" / "Next Card →" to move on
   - Hit "End game" to jump straight to summary

### Scoring tiers

Each answer falls into one of five tiers. The rule engine decides; the LLM never overrides it (with one tightly-scoped exception, see §7).

| Tier | Score | What it means |
|------|-------|---------------|
| `deep` | 10 | Identified the underlying frame, motive, audience, or full sequence |
| `mid` | 7 | Analyzed the descriptors, predicted outcome, or sequenced steps |
| `surface` | 3 | Spotted the basic contrast or named the emotion |
| `off` | 0 | Off-topic |
| `silent` | 0 | No speech detected (skipped) |

---

## 3. Hardware Setup

### Components

| Component | Model | Role |
|-----------|-------|------|
| Compute | NVIDIA Jetson AGX Thor Developer Kit | Runs everything: Whisper, Llama 3, Kokoro, FastAPI |
| Display | NLIEOPDA 7" HDMI Touchscreen (1024×600 IPS) | Kid-facing UI & Speaker|
| Camera | Logitech C270 USB Webcam | Card scanning &v Microphone |
| Power | USB-C PD adapter (Thor's stock supply) | Plugged into far-from-HDMI USB-C port |
| Cables | HDMI cable + USB-C data cable | Display + touchscreen control |

### Physical setup — order matters

The Thor has two USB-C ports near each other. **Power and data go on different ports.** Specifically:


**Step-by-step**:

1. **Power**: plug the USB-C power adapter into the **USB-C port FARTHER from the HDMI port**.
2. **Touchscreen data**: plug a USB-C data cable into the **USB-C port NEARER to the HDMI port** → into the touchscreen's data input. This is what makes the touch work; without it the screen still displays but won't respond to taps.
3. **Display signal**: plug the HDMI cable from Thor's HDMI port into the touchscreen.
4. **Camera**: plug the Logitech C270 into any USB-A port.

If the touchscreen displays but doesn't respond to touch, the data cable is on the wrong port — swap the two USB-C connections.

### Recommended physical card design

For best OCR recognition:

- **Card number** in **upper-left** corner: format `#NN` (e.g. `#14`), 18pt+ bold sans-serif font, black on white
- **Card title** as the main heading, matching the JSON exactly
- **High contrast**: black text on light background, matte finish if possible (glossy reflects the camera LED)
- **Card body** in normal paragraph form below the title — these texts are read aloud by the coach, not OCR'd

A card with both a clearly-printed `#14` AND 2-3 distinctive title words readable usually matches on the first frame in decent room light.

### System info (reference)

```
Operating System: Ubuntu 24.04.3 LTS
Kernel:           Linux 6.8.12-tegra
Architecture:     arm64
Hardware Model:   NVIDIA Jetson AGX Thor Developer Kit
Firmware Version: 38.4.0-gcid-43443517
```

---

## 4. Software Setup & Running the Game

### First-time install

```bash
# Activate the project's Python virtual environment
source .venv/bin/activate

# One-time install of all Python deps + pull llama3 weights via Ollama
./install_and_run.sh install
```

This installs FastAPI, uvicorn, Whisper, Kokoro TTS, the Ollama Python client, and pulls the Llama 3 model (~4 GB, takes a few minutes).

Kokoro will additionally download its ONNX weights (~325 MB) into `~/.cache/kokoro/` the first time you call it — this happens automatically on first server startup or first `tts-test`.

### Running the game

```bash
# Always activate the venv first
source .venv/bin/activate

# Start the server
./install_and_run.sh run
```

You'll see:

```
[run] Starting PROMPT! server on :8000 ...
[startup] Loading Whisper ...
[startup] Warming Kokoro TTS ...
[tts] Loading Kokoro pipeline...
[tts] Kokoro ready, voice=af_heart
[tts] warmup complete.
[startup] Ready.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

When you see `[startup] Ready.` and `Uvicorn running`, open the **browser on Thor itself** and navigate to:

```
http://localhost:8000
```

>  **Critical**: the browser must be on Thor (not on a laptop accessing Thor over the LAN). Browsers refuse camera access on plain HTTP unless the origin is `localhost` or `127.0.0.1`. The intended deployment is a kiosk-style touchscreen plugged directly into Thor.

### Stopping the server

In the terminal: `Ctrl + C`.

If you ran it in the background:

```bash
pkill -f "uvicorn server:app"
```

### Running in the background

```bash
source .venv/bin/activate
nohup ./install_and_run.sh run > prompt.log 2>&1 &

# View logs as they happen
tail -f prompt.log
```

### Quick smoke tests

Verify the TTS voices:

```bash
./install_and_run.sh tts-test
aplay /tmp/prompt_tone_test_warm.wav
```

Verify the server responds:

```bash
curl http://localhost:8000/api/scan_index | head -c 200
```

If you see `{"cards":[{"id":"#1",...` the server is healthy and the card index is loading.

---

## 5. System Architecture

### High-level diagram

```
                ┌─────────────────────────────────────────────────┐
                │                NVIDIA JETSON AGX THOR            │
                │                                                  │
                │  ┌────────────┐         ┌──────────────────┐   │
                │  │  Browser   │ ◄────►  │  FastAPI server  │   │
                │  │ (Chromium) │  HTTP   │   (uvicorn)      │   │
                │  │            │  :8000  │                  │   │
                │  │            │         │                  │   │
                │  │ ┌────────┐ │         │  ┌────────────┐  │   │
                │  │ │ HTML   │ │         │  │  rules.py  │  │   │
                │  │ │ + JS   │ │         │  │  (scoring) │  │   │
                │  │ │        │ │         │  └────────────┘  │   │
                │  │ │ + WebRTC mic       │                  │   │
                │  │ │ + Tesseract.js OCR │                  │   │
                │  │ └────────┘ │         │                  │   │
                │  └────────────┘         │                  │   │
                │       │  ▲              │                  │   │
                │ audio │  │ TTS audio    │                  │   │
                │       ▼  │              │                  │   │
                │  ┌────────────┐         │                  │   │
                │  │ Microphone │         │                  │   │
                │  └────────────┘         │   ┌─────────┐    │   │
                │                         │   │ Whisper │    │   │
                │  ┌────────────┐         │   │  STT    │    │   │
                │  │ Camera     │         │   └─────────┘    │   │
                │  │ (C270)     │         │                  │   │
                │  └────────────┘         │   ┌─────────┐    │   │
                │                         │   │ Kokoro  │    │   │
                │  ┌────────────┐         │   │  TTS    │    │   │
                │  │ HDMI       │         │   └─────────┘    │   │
                │  │ Touchscreen│         │                  │   │
                │  └────────────┘         │   ┌─────────┐    │   │
                │                         │   │ Ollama  │    │   │
                │                         │   │+Llama3  │    │   │
                │                         │   └─────────┘    │   │
                │                         └──────────────────┘   │
                │                                                │
                │  All model weights cached locally:             │
                │    Whisper:  ~/.cache/whisper/                 │
                │    Kokoro:   ~/.cache/kokoro/                  │
                │    Llama 3:  managed by ollama                 │
                │    Tesseract:served from CDN, browser-cached   │
                │                                                │
                └────────────────────────────────────────────────┘

                NO INTERNET TRAFFIC AT RUNTIME
```

### Per-turn data flow (answering one card)

```
1. ┌─────────────────────────────────────────────────────────────┐
   │ Browser: child taps mic, speaks "I see two different        │
   │          lenses, one nice and one scary..."                 │
   └─────────────────────────────────────────────────────────────┘
                                │  webm audio (browser MediaRecorder)
                                ▼
2. ┌─────────────────────────────────────────────────────────────┐
   │ POST /api/transcribe  →  Whisper small  →  text             │
   │                                            "I see two..."   │
   └─────────────────────────────────────────────────────────────┘
                                │  text
                                ▼
3. ┌─────────────────────────────────────────────────────────────┐
   │ POST /api/answer                                            │
   │   ├─► rules.py: keyword family matching                     │
   │   │     → tier = "mid", score = 7                           │
   │   ├─► (bias_inverter only) llm.judge_bias_inverter:         │
   │   │     can promote tier upward                             │
   │   └─► llm.generate_feedback (Llama 3):                      │
   │         → {reaction, habit, invite}                         │
   └─────────────────────────────────────────────────────────────┘
                                │  JSON: score + feedback + card_back
                                ▼
4. ┌─────────────────────────────────────────────────────────────┐
   │ Browser: flips card, shows feedback bubbles, calls TTS      │
   └─────────────────────────────────────────────────────────────┘
                                │  text "Nice catch. ..."
                                ▼
5. ┌─────────────────────────────────────────────────────────────┐
   │ POST /api/tts  →  Kokoro  →  WAV                            │
   └─────────────────────────────────────────────────────────────┘
                                │  WAV bytes
                                ▼
6. ┌─────────────────────────────────────────────────────────────┐
   │ Browser plays the WAV. Child can now ask a follow-up        │
   │ question (loops to step 1 against /api/followup) or         │
   │ tap "Scan Next Card" / "Next Card →".                       │
   └─────────────────────────────────────────────────────────────┘
```

### Card scan data flow

```
Browser camera (Logitech C270)
        │
        │  video frames @ 30 fps
        ▼
HTML5 <video> element
        │
        │  every 1.2s, grab center crop to canvas
        ▼
Tesseract.js worker (in-browser)
        │
        │  raw text "  #14  ULTRA-GUM WILL EXPLODE!  ..."
        ▼
matchAgainstIndex():
   1. extract id candidates  →  {"14"}
   2. score every card in scanIndex:
        - id hit (#14 found?)
        - title hit (% of title words present?)
        - body tiebreak
   3. require 2 consecutive frames agreeing
        │
        │  best match: #14 ULTRA-GUM
        ▼
Show confirmation panel:
  "Detected #14: ULTRA-GUM WILL EXPLODE!"
  [Rescan] [Yes, that's it]
        │
        │  user confirms
        ▼
POST /api/start_single  (first card)
  or
POST /api/append_card   (subsequent cards)
        │
        ▼
Game session begins for that card.
```

### File responsibilities

```
server.py            ◄── FastAPI app, routes, session state
  ├─ /api/start          quick-play: random deck of 6
  ├─ /api/start_single   scan: 1-card session
  ├─ /api/append_card    scan: extend session with another card
  ├─ /api/scan_index     ship the card index to browser OCR
  ├─ /api/answer         score + generate feedback
  ├─ /api/followup       free-form Q&A on current card
  ├─ /api/transcribe     Whisper STT
  ├─ /api/tts            Kokoro TTS
  └─ /api/summary        end-of-game stats + tip

cards_loader.py      ◄── Load both JSON files, normalize, build indexes
rules.py             ◄── Tiered keyword scoring (semantic families)
llm.py               ◄── Wrap Ollama for feedback, summary, follow-up, judge
prompts.py           ◄── All Llama 3 prompt templates
tts.py               ◄── Kokoro pipeline wrapper, single-voice
index.html           ◄── Single-page UI: home / scan / game / summary
                         All client logic in one file (no build step)

discernment_cards.json  ◄── Card data: lens audit + emotion hijack
usage_cards.json        ◄── Card data: bias inverter + task decomposition
```

### Network and storage footprint

| Resource | Size | Where |
|----------|------|-------|
| Whisper small | ~500 MB | `~/.cache/whisper/` |
| Kokoro ONNX weights | ~325 MB | `~/.cache/kokoro/` |
| Llama 3 (8B Q4) | ~4.7 GB | Ollama-managed |
| Tesseract.js + eng model | ~8 MB | Browser cache (CDN) |
| App code + cards | <1 MB | Project dir |
| TTS audio cache | grows over time | `/tmp/prompt_tts_cache/` |

After first run everything is local. No runtime internet required.

---

## 6. Card Format & Game Modes

### Two card families, four problem types

```
┌───────────────────────────────────────────────────────────── ─┐
│ DISCERNMENT — "Spot the Frame"                                │
│ ────────────────────────────────                              │
│  perspective_lens_audit                                       │
│    Two descriptions of the same thing. Find the hidden lens.  │
│    Example: "Orbital Relics" — beautiful relics vs metal      │
│             shards threatening satellites. Same satellites!   │
│                                                               │
│  affective_highjack                                           │
│    A post engineered to grab a strong emotion. Name the       │
│    feeling AND who gains if you share it.                     │
│    Example: "ULTRA-GUM WILL EXPLODE!" — fear bait that        │
│             only exists to spread panic.                      │
└─────────────────────────────────────────────────────── ───────┘

┌──────────────────────────────────────────────────────────── ──┐
│ AI USAGE — "Better Prompts"                                   │
│ ────────────────────────────────                              │
│  bias_inverter                                                │
│    An AI answer secretly centers one viewpoint. Propose a     │
│    follow-up prompt that exposes the bias.                    │
│    Example: "Mascot Remix" — answer says only teachers should │
│             pick the school mascot. What about students?      │
│                                                               │
│  task_decomposition_map                                       │
│    A big messy task. Break it into ordered sub-prompts.       │
│    Example: "Volcano Quest" — plan a science fair project     │
│             in steps: question → schedule → experiment →      │
│             draft → review.                                   │
└───────────────────────────────────────────────────────── ─────┘
```

### Card schema (JSON)

```json
{
  "card_id": "#14",
  "category": "discernment",
  "problem_type": "affective_highjack",
  "difficulty": "easy",
  "front": {
    "title": "ULTRA-GUM WILL EXPLODE!",
    "card_text": [
      "A scary rumor is spreading! Kids who chew Ultra-Gum...",
      "Everyone is throwing their gum away before it's too late!"
    ]
  },
  "back": {
    "verdict": "Playground Panic",
    "scoring_anchors": {
      "3_pts": "The news is spreading fear and surprise.",
      "7_pts": "The outcome could be kids wasting their candy.",
      "10_pts": "The intention is to cause harmless chaos."
    },
    "reality_anchor": "How silly rumors start"
  },
  "teacher_notes": {
    "deep_insight": "Even silly stories can feel real in the moment...",
    "habit": "When you feel scared by a rumor, ask 'is that possible?'",
    "references": [{"title": "...", "url": "..."}]
  }
}
```

For `bias_inverter` and `task_decomposition_map`, the `scoring_anchors` block uses `suggested_prompt` instead of the `3/7/10_pts` ladder — this is the example "good prompt" the child is being nudged toward.

### Game modes

```
QUICK PLAY (random)
   │
   ├── Discernment-only       6 random discernment cards
   ├── AI Usage-only          6 random usage cards
   └── Mixed (default)        6 cards balanced across both decks
                              with a soft easy → medium → hard ramp

SCAN MODE
   │
   └── Scan 1 card  →  answer  →  scan another  →  ...  →  Finish
                                                          (any time)
```

Scan mode has **no fixed length**. The child plays one card, then either scans another or finishes. The summary scores whatever they did play.

---

## 7. Technology Choices & Rationale

### Why fully on-device?

Children's voices and answers should not leave the device. Cloud APIs would also create latency (mic → cloud → response = 3–8s on residential broadband, vs 2–4s entirely local) and per-session costs that make this unviable in classroom deployments.

### STT: Whisper small (OpenAI, ~500 MB)

| Choice | Rationale |
|--------|-----------|
| `small` model size | Best accuracy/latency tradeoff for kid speech on Thor's GPU. `tiny` mishears too often; `medium` adds 2 seconds without improving real-world accuracy on these short utterances. |
| Local inference | Zero network round-trip. Privacy. |
| Language pinned to English | Tiny accuracy boost; can be relaxed in `server.transcribe_audio` if needed. |

### TTS: Kokoro 82M (was: ChatTTS in v2)

| Choice | Rationale |
|--------|-----------|
| Kokoro over ChatTTS | ChatTTS had a 25s cold start and audible per-segment stalls. Kokoro starts in 3s and produces seamless multi-sentence audio with one pipeline call. |
| Single fixed voice (`af_heart`) | The "consistent kind coach" character is more important than tonal variety. v2's 4-tone system was perceptually noisy more than engaging. |
| Speed-only tone variation | Tone parameter still exists for narrator/curious/warm/celebrate, but only nudges speed (0.98–1.05). No model swap, no timbre change. |
| Disk caching by `(voice, tone, text) → md5 → wav` | Common phrases like "Anything you want to ask?" render once and replay forever. |

### LLM: Llama 3 8B via Ollama

| Choice | Rationale |
|--------|-----------|
| Ollama as runtime | Zero-config local LLM serving with hot model reuse across requests. |
| Llama 3 8B Q4 | Smallest model that produces consistent 3-line, kid-friendly outputs at this prompt complexity. Larger models add latency without quality gains for this use case. |
| LLM never decides scoring | Scoring is the rule engine's job. The LLM only generates language. The single tightly-scoped exception (`judge_bias_inverter`) can only **promote** a borderline rule result, never demote — this protects against silent grade inflation. |

### OCR: Tesseract.js v5 (browser-side)

| Choice | Rationale |
|--------|-----------|
| Browser OCR over server OCR | Thor's CPU and GPU are already running Whisper + Llama 3 + Kokoro. Pushing OCR to the browser keeps the server unloaded. |
| Tesseract.js over WebAssembly alternatives (PaddleOCR-WASM, etc.) | Tesseract.js has the smallest cold-start (~8 MB), simplest API, and works without WebGPU — important for the Logitech webcam-driven workflow where the browser may not have GPU acceleration. |
| Two-signal matching (ID + title) | Single-signal OCR is too noisy: `0` reads as `O`, `6` as `G`, etc. Requiring both `#NN` AND title-word agreement makes false positives effectively zero. |
| Two-consecutive-frame confirmation | OCR results jitter on a moving card. The "must agree with itself twice" rule eliminates flicker without slowing the happy path noticeably. |

### Backend framework: FastAPI + uvicorn

| Choice | Rationale |
|--------|-----------|
| FastAPI | Async-native (matters for streaming TTS audio), Pydantic validation, automatic OpenAPI docs, low memory overhead. |
| Single-file `server.py` | The whole API surface is ~10 routes; a project structure would add complexity without benefit at this scale. |
| In-memory session state | Sessions don't need to survive server restarts. A dict keyed by session_id is the right granularity. If we ever add multi-device sync, swap to SQLite. |

### Frontend: vanilla HTML + JS, no build step

| Choice | Rationale |
|--------|-----------|
| No framework | The whole UI is one screen with a state machine. React/Vue would add 200KB and a build pipeline for zero functional benefit. |
| Single `index.html` file | Easy to ship, easy to read, no module resolution headaches in a kiosk context. |
| Tailwind-style CSS variables | All design tokens at the top of the file in `:root`. Color/sizing changes are one-line edits. |

### Scoring: rule engine over LLM-as-judge

This is the most opinionated technical decision. We use **deterministic keyword matching** with semantic families, not LLM grading.

**Why**: LLM grading drifts. The same answer on the same card scores `deep` one run and `mid` the next. Children deserve consistent feedback, and educators deserve to be able to validate the rubric without re-running 100 trials.

The semantic-family approach (see `rules.py`):

- `EMO_FAMILY` — 40+ emotion words including adjectives and noun forms
- `MOTIVE_FAMILY` — clicks, ads, money, manipulation, scam, ...
- `META_FAMILY` — frame, lens, perspective, audience, bias, ...
- `STRONG_REFRAME_FAMILY` — rewrite, rephrase, compare, contrast, ...
- ... and others per problem type

A child says "I'd ask the AI to rewrite this from a worker's view" — the rule engine sees `rewrite` (strong reframe) + `worker` (group noun matching the suggested prompt) and assigns `deep`. A child says "There might be another side" — only weak reframe markers, scores `surface`. Same logic every time.

The **single LLM exception** (`judge_bias_inverter`) is for the bias-inverter problem type, where children can produce genuine reframes that don't share specific keywords with the suggested prompt. The LLM judge is a single-word classifier (deep/mid/surface/off) at temperature 0.1, and can only promote a rule result upward — never down. This catches creative reframes without compromising rubric integrity.

---

## 8. Version History

The project went through four iterations, each focused on a specific user-experience problem.

### v1 — Initial prototype

- A/B/C/D multiple-choice cards
- Tap a letter to answer
- Piper TTS (`en-us-amy-low`, robotic)
- Fixed sequence

**Problem with v1**: multiple choice doesn't build the *noticing* habit. Kids guess. The tap interaction defeats the spoken-reflection goal.

### v2 — Open-ended reflection + ChatTTS

Major rewrite around a new card schema.

- New card format: open-ended scenarios with `scoring_anchors` instead of one correct letter
- Two card families: `discernment_cards.json` and `usage_cards.json`
- Four problem types: perspective lens audit, affective hijack, bias inverter, task decomposition
- Tiered scoring: 0/3/7/10 (silent / off / surface / mid / deep)
- ChatTTS with 4 tone profiles (narrator/curious/warm/celebrate) on one voice seed
- Mode picker: Discernment / AI Usage / Mixed
- Rule engine in `rules.py`
- LLM-generated 2-line feedback in `llm.py`

**Problems with v2**:
1. ChatTTS cold start was 25 seconds; multi-segment playback had audible stalls.
2. "Next Card" button didn't actually advance — repeated card 1.
3. Grading was too strict: required explicit `lens`/`frame` words for `deep`, missed synonyms like `terrified`/`afraid`.
4. No way to end the game early.

### v3 — Three focused fixes

#### 3.1 TTS: ChatTTS → Kokoro

- 82M-parameter model with deterministic single-pass inference
- Fixed `af_heart` voice (warm female, kid-appropriate)
- Cold start: 25s → **3s**
- Per-sentence inference: 1.5s → **0.15s**
- Multi-segment text now joins server-side and renders as ONE seamless WAV
- Tone parameter kept for API compatibility but only adjusts speed

#### 3.2 Next-card bug + End Game button

- **Bug fix**: `revealAnswer` now stashes `data.next_card` into a global; `nextCard()` reads it and advances. Card flipper is also reset on every render so the new card shows its front.
- **New**: "End game" button beside "Skip card" → jumps directly to summary. Score is computed over answered cards only; unanswered cards are ignored. `/api/summary` short-circuits to a generic tip when zero cards were answered.

#### 3.3 Grading overhaul

Rewrote `rules.py` with **semantic families** instead of prefix-stemming:

| Family | Purpose |
|--------|---------|
| `EMO_FAMILY` | Now catches `terrified`, `anxious`, `panicked`, ... |
| `MOTIVE_FAMILY` | `clicks`, `ads`, `money`, `manipulation`, ... — identifies "who benefits" |
| `OUTCOME_FAMILY` | `share`, `hoard`, `spread` — identifies consequences |
| `META_FAMILY` | `frame`, `lens`, `perspective` (deliberately narrow) |
| `DESCRIPTOR_FAMILY` | `scary`, `pretty`, `word`, `tone` — analyzed-the-how signal |
| `GROUP_NOUN_FAMILY` + `_has_audience_cue()` | Detects "for scientists vs for ranchers" without requiring `lens` |

New paths to `deep` on perspective cards:
1. Meta word + card engagement
2. Audience cue naming ≥2 distinct groups
3. Group noun + anchor content hit

Stress test across 48 realistic answers shows balanced distribution: deep 12 / mid 11 / surface 9 / off 8 / silent 8.

**LLM-assisted scoring (`bias_inverter` only)**: a single-word Llama 3 classifier at temperature 0.1 can promote `surface` or `mid` to `deep` when the child genuinely reframed the bias, even with novel vocabulary. Promotes only — never demotes.

### v3.1 — Follow-up Q&A

After answering each card, the child can now ask the coach free-form questions about what they just saw.

- **Feedback expanded from 2 lines to 3**: reaction + habit + invite. The new third line opens the door to follow-up questions ("Curious about anything else here?").
- **New `/api/followup` endpoint**: takes a question, returns a 2-sentence answer scoped to the current card and to general AI/media literacy. Off-topic questions get a soft redirect, not a refusal.
- **Per-card cap**: 4 follow-ups per card. Beyond that, the mic is gently disabled and the child is nudged toward the next card.
- **Conversation memory**: the prompt embeds the most recent 2 Q&A turns so the child can ask "what about the other example?" without restating context.
- **UI state machine**: voice panel now has 3 phases — `answering` (records the card answer), `followup` (records a question), `done` (summary).
- **Summary shows follow-up count**: "💬 You asked **3** follow-up questions — curiosity points!" Follow-ups are never scored.

### v4 — Physical card scanning

The biggest UX leap: instead of (or in addition to) random deck mode, a child can hold a printed card up to the webcam and the game loads that exact question.

- **HOME redesigned**: two big entry-point cards — "📷 Scan a Card" and "🎲 Random Deck"
- **New SCAN screen**: live camera preview with a dashed scanning frame, animated laser sweep, real-time OCR feedback
- **Browser-side OCR via Tesseract.js v5**: ~8 MB CDN download, cached after first use, runs entirely in-browser
- **Two-signal matching**: extracts `#NN` from OCR text AND counts distinctive title-word matches
- **Two-consecutive-frame confirmation** prevents flicker on shaky camera
- **New backend routes**:
  - `GET /api/scan_index` — ship card index to browser
  - `POST /api/start_single` — start session from one scanned card
  - `POST /api/append_card` — extend session deck with another scanned card
- **Manual fallback**: text input accepts `14` or `#14` directly when OCR struggles
- **Game-flow integration**: "Next Card →" becomes "Scan Next Card 📷" in scan sessions; tapping it returns to the scanner instead of auto-advancing

---

## 9. Troubleshooting

### Server won't start

```
Address already in use
```

Another server is already running. Kill it:

```bash
pkill -f "uvicorn server:app"
# wait a second
./install_and_run.sh run
```

### Coach feedback is generic instead of specific

Looks like:

> "You spotted the hidden angle — that's exactly the move."

This is the fallback that fires when **Ollama is not reachable**. Check:

```bash
# Is the Ollama daemon running?
curl http://localhost:11434/api/tags
```

If that fails, in another terminal:

```bash
ollama serve
```

And verify the model is pulled:

```bash
ollama list
# Should show llama3:latest or similar
```

If not:

```bash
ollama pull llama3
```

### TTS doesn't play / silent coach

1. Check audio output device:
   ```bash
   aplay -l
   ```
2. Test Kokoro directly:
   ```bash
   ./install_and_run.sh tts-test
   aplay /tmp/prompt_tone_test_warm.wav
   ```
3. If Kokoro itself works but the browser doesn't play, open browser DevTools → Console → look for `Audio.play()` errors. Some browsers block autoplay until first user interaction; this is why the welcome message plays after the user taps Start.

### Camera not detected on scan screen

Status: `Camera access denied. Try a USB webcam or check permissions.`

1. Confirm you're on `localhost`, not the LAN IP:
   ```
   http://localhost:8000   ✅
   http://192.168.x.x:8000 ❌  (browsers block camera on plain HTTP non-localhost)
   ```
2. Check the browser allowed camera access (icon in URL bar).
3. Verify the C270 is detected:
   ```bash
   v4l2-ctl --list-devices
   ```
4. Try a different browser. Chromium handles `getUserMedia` more permissively than Firefox on Linux.

### Touchscreen displays but doesn't respond to touch

The USB-C data cable is on the wrong port. Swap the two USB-C connections:

- Power → port FAR from HDMI
- Data → port NEAR HDMI (the touchscreen's data input)

### OCR keeps saying "Looking for a card..."

In order from quickest fix to most invasive:

1. **Better lighting**. The C270 is a low-end webcam; it needs strong even light to read printed text.
2. **Hold the card 15-25cm from the camera** so the printed `#NN` fills the upper-left quadrant of the dashed frame.
3. **Watch the preview text** below the camera — it shows the raw OCR output. If it's gibberish, lighting or angle is the problem. If it shows the right text but doesn't match, the title might not align with the JSON.
4. **Use the manual entry** at the bottom: type `14` or `#14` and tap Go.
5. **Lower the threshold** in `index.html` (`bestScore >= 70` → `>= 60`).

### "Already seen" error when scanning

Within one scan session, the same card cannot be played twice. Either pick a different card, or hit "End game" and start a new session.

### Kokoro download stuck

First-run downloads ~325 MB to `~/.cache/kokoro/`. If your network is slow:

```bash
# Check progress
du -sh ~/.cache/kokoro/

# If stuck, you can pre-download on a fast machine and rsync to Thor
```

---

## 10. Tuning Knobs

### Change the voice

Edit `tts.py`:

```python
VOICE_ID = "af_bella"   # was "af_heart"
```

Then clear the TTS cache so old clips don't replay:

```bash
rm -rf /tmp/prompt_tts_cache/*
```

Available warm-voice candidates: `af_heart`, `af_bella`, `af_sarah`, `af_nicole`. To audition them all:

```bash
python3 -c "
import tts
for v in ['af_heart', 'af_bella', 'af_sarah', 'af_nicole']:
    tts.VOICE_ID = v
    tts._PIPELINE = None  # force reload
    tts.synthesize('Hello! This is the coach voice.', tone='warm',
                   out_path=f'/tmp/voice_{v}.wav')
"
aplay /tmp/voice_af_bella.wav
```

### Game length (random mode)

In `server.py`:

```python
CARDS_PER_GAME = 6   # change to 4, 8, 10, ...
```

### Follow-up cap per card

In `server.py`:

```python
MAX_FOLLOWUPS_PER_CARD = 4   # default
```

Lower to 2 for stricter pacing in classrooms. Set to 0 to disable follow-ups entirely.

### OCR scan loop interval

In `index.html` (`startScanLoop`):

```javascript
scanLoopTimer = setInterval(() => { ... }, 1200);
//                                    ^^^^ ms between OCR frames
```

Lower to 800ms for faster recognition; raise to 1600ms if Thor is CPU-bound by other concurrent tasks.

### Scoring strictness

In `rules.py`, tighten or loosen any tier by editing the `if` ladders inside the `_score_*` functions. The semantic families themselves are at the top of the file — adding a new emotion word to `EMO_FAMILY` is a one-line change that takes effect on the next request, no restart needed (well, restart the server, but no model re-load).

### LLM-assisted bias_inverter scoring

In `server.py` (`/api/answer` route):

```python
result = check_answer(card, req.user_answer, llm_judge=_judge_wrapper)
```

To disable the LLM tiebreak (faster, more deterministic, may starve `deep` tier):

```python
result = check_answer(card, req.user_answer, llm_judge=None)
```

### Adding new cards

1. Add a JSON entry to `discernment_cards.json` or `usage_cards.json` with the schema in §6
2. (Optional) Print a physical card with `#NN` upper-left and the title prominently displayed
3. Restart the server
4. Test with `python3 test_rules_stress.py` to make sure the scoring anchors trigger correctly across realistic answers

---

## 11. Future Directions

These were considered but not implemented in v4:

### Adaptive difficulty
Session already tracks per-mode tier distribution. The next iteration could up- or down-rank card difficulty based on the tier the child is weakest in. Hooks: `session["per_mode"]` in `server.py`.

### Follow-up history in summary
Currently summary just shows the count. A foldout view of the actual Q&A threads would let parents/teachers see the child's curiosity arc.

### Multiple webcam selection
On Jetson with multiple USB cams, `facingMode: 'environment'` is a hint, not a guarantee. A `<select>` UI driven by `navigator.mediaDevices.enumerateDevices()` would let kids pick.

### RAG over the references
Each card has `references[]` with real URLs. A retrieval layer could fetch and summarize one of those when a child asks a follow-up like "is that really true?" — closing the loop between AI literacy and source-checking.

### Per-child profiles
Right now sessions are anonymous. A simple "who are you?" picker on Home + per-child progress tracking would let the game adapt over time.

### Multi-language
Whisper, Kokoro, and Llama 3 all support multiple languages. The card content and prompts would need translation, but the architecture wouldn't.

### Print-and-play card export
A small utility script that reads the JSON files and renders printable PDF cards with the right `#NN` format and font would close the loop on physical cards. Right now we maintain the cards manually.

---

## Quick reference — all in one place

```bash
# First time
source .venv/bin/activate
./install_and_run.sh install

# Every time you want to play
source .venv/bin/activate
./install_and_run.sh run

# Open in browser ON THOR
http://localhost:8000
http://127.0.0.1:3000
# Stop
# Ctrl+C  (or)  pkill -f "uvicorn server:app"

# Smoke test
curl http://localhost:8000/api/scan_index | head -c 200
```

Hardware checklist:

- [ ] Power adapter in USB-C port FAR from HDMI
- [ ] Touchscreen data cable in USB-C port NEAR HDMI
- [ ] HDMI cable from Thor to NLIEOPDA 7" screen
- [ ] Logitech C270 in any USB-A port
- [ ] Browser open at `http://localhost:8000` or 'http://127.0.0.1:3000' ON THOR (not LAN)