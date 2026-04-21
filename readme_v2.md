# PROMPT! v2 — Offline AI Literacy Game (Thor)

A voice-first AI literacy game for children age 10+, running fully on-device on NVIDIA Jetson AGX Thor. Children read reflection cards, **say what they notice out loud**, and a coach voice (ChatTTS, one character, four tones) gives kind, specific feedback.

## What changed from v1

| Layer | v1 | v2 |
|---|---|---|
| Card format | A/B/C/D multiple choice | Open-ended reflection (`discernment_cards.json` + `usage_cards.json`) |
| Answer input | Tap a letter, or say "A" | **Speak your thinking** — no options, no letters |
| Scoring | Exact match | **Tiered 0 / 3 / 7 / 10** against `scoring_anchors` |
| TTS | Piper `en-us-amy-low` (flat) | **ChatTTS**, one young female voice, **four tones** |
| Game flow | Fixed sequence | Player picks deck: **Discernment / AI Usage / Mixed** |
| UI | Letter buttons + flip | Dual-lens bubbles + big mic + reaction/habit bubbles |

## Card families

### Discernment deck — "Spot the Frame"
- **`perspective_lens_audit`**: two descriptions of the same thing (e.g. "space relics" vs "space junk"). Child names the hidden lens.
- **`affective_highjack`**: a post engineered to hook a strong emotion. Child names the feeling *and* who gains from the share.

### AI Usage deck — "Better Prompts"
- **`bias_inverter`**: an AI answer centers one audience. Child proposes a reframing prompt.
- **`task_decomposition_map`**: a big messy task. Child breaks it into ordered sub-prompts.

## Tiered scoring

| Tier | Score | Meaning |
|---|---|---|
| `deep` | 10 | Identified the frame / motive / concrete reframe / full sequence with review |
| `mid` | 7 | Analyzed descriptors / predicted outcome / gestured at another view / sequenced steps |
| `surface` | 3 | Spotted the contrast / named the emotion / used a reframing word |
| `off` | 0 | Off-topic |
| `silent` | 0 | No speech detected |

The LLM layer **never** decides the score — it only produces warm, kid-friendly feedback tied to the tier the rule engine already picked.

## Four-tone ChatTTS

**One fixed voice** (seed `4099`, young female) + **four tone profiles** that change prosody only:

| Tone | Used for | Refine prompt | Temperature |
|---|---|---|---|
| `narrator` | Card title + body | `[oral_1][laugh_0][break_4]` | 0.3 |
| `curious` | Tips, "ask yourself..." habits | `[oral_3][laugh_0][break_5]` | 0.45 |
| `warm` | Personalized feedback | `[oral_4][laugh_1][break_5]` | 0.4 |
| `celebrate` | Welcome, high scores, game over | `[oral_5][laugh_1][break_3]` | 0.5 |

Same speaker embedding flows through every tone → one consistent character who shifts mood naturally. Change the whole character by editing `VOICE_SEED` in `tts.py` (community-tested lively female voices: `3333`, `4099`, `5099`).

## Install & run (Thor)

```bash
# first time only
./install_and_run.sh install

# start server
./install_and_run.sh run
# → open http://<thor-ip>:8000 in the kiosk browser

# quick smoke test of the four tones
./install_and_run.sh tts-test
aplay /tmp/prompt_tone_test_warm.wav
```

## Project layout

```
thor_game_mvp/
├── server.py                  # FastAPI backend
├── tts.py                     # ChatTTS multi-tone module
├── cards_loader.py            # unified loader for both card files
├── rules.py                   # tiered keyword scoring (17/17 calibrated)
├── llm.py                     # per-problem-type feedback generator
├── prompts.py                 # four specialized LLM prompts
├── index.html                 # voice-first UI with mode selection
├── discernment_cards.json     # unchanged from your input
├── usage_cards.json           # unchanged from your input
├── test_rules_stress.py       # harness for adding new cards
├── install_and_run.sh         # one-shot setup/run helper
└── README.md
```

## API endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/api/start` | `{mode: "discernment"\|"usage"\|"mixed"}` | `session_id`, first card |
| `POST` | `/api/answer` | `{session_id, user_answer}` | score, tier, 2-line feedback, card back, next card |
| `POST` | `/api/transcribe` | form-data `audio` | `{text}` (Whisper STT) |
| `POST` | `/api/tts` | `{text, tone}` | WAV stream (ChatTTS) |
| `POST` | `/api/summary?session_id=...` | — | per-mode breakdown + summary tip |

## Tuning the rule engine for new cards

When you add a card, the scorer pulls content keywords out of `scoring_anchors`. Two gotchas:

1. **Rubric-instruction verbs** (like "identified", "detected", "noted", "analyzed") are already in the stopword list — they describe the grading action, not the content the child should say.
2. **For `bias_inverter`**, the `suggested_prompt` provides the content keywords. Write it with concrete nouns (stakeholders, roles, actions) so keyword matching has something to hit. Generic phrases like "consider another view" have no content words and will score weakly no matter what the child says.

Run `python3 test_rules_stress.py` after adding cards to see tier distribution.

## Design notes for future work

- **TTS caching**: identical `(text, tone)` pairs could be cached under `/tmp/prompt_tts_cache` keyed by hash, saving 1–3s per reused clip.
- **Per-child voice calibration**: let a guardian pick a different `VOICE_SEED` at setup and pin it forever.
- **RAG grounding**: the `references` on each card already point to real URLs — feed those into a retrieval layer so the "Deep Insight" panel can expand on demand.
- **Adaptive difficulty**: the session already tracks per-mode stats. Next iteration can up- or down-rank difficulty based on the tier a child is weakest in.