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

# PROMPT! v3 — changelog over v2

Three focused fixes on top of v2. Nothing about the game design, card format,
or session flow changes — these are mechanical improvements to the three
layers that were hurting playability.

## 1. TTS backend: ChatTTS → Kokoro

**Why.** ChatTTS has a long cold start (15–30 s on Jetson AGX Thor), and its
per-segment text-refine pass made multi-sentence playback stall audibly
between segments. Our tone system was also too ambitious — four tone profiles
were perceptually noisy more than engaging.

**What changed.**

- `tts.py` now wraps [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)
  via the official `kokoro` pip package. Weights (~325 MB of ONNX) download
  once into `~/.cache/kokoro`.
- Single fixed voice (`af_heart`, warm kid-friendly female). Tone is kept as
  an API parameter for compatibility but only nudges speed (1.00 / 0.98 /
  1.05) — no model swap, no timbre change.
- `synthesize_multi` now just concatenates segment text and makes ONE
  pipeline call. Kokoro handles sentence-level prosody internally, so the
  output is a single seamless WAV instead of N glued-together clips.

**Expected impact on Thor.**

| Metric | v2 ChatTTS | v3 Kokoro |
|---|---|---|
| Cold start | ~25 s | ~3 s |
| Per-sentence inference | ~1.5 s | ~0.15 s |
| Gap between segments | audible | none (one clip) |

## 2. Next-card bug + "End game" button

**Why.** In v2 `nextCard()` re-rendered from `currentCard`, but `currentCard`
was never updated from the `/api/answer` response — so the player saw card 1
again. Meanwhile there was no way to bail out mid-game; the dots + score felt
"locked in" to the full 6.

**What changed.**

- `index.html`: `revealAnswer` now stashes `data.next_card` into a global
  and `nextCard()` reads it. Also resets `card-flipper.classList` unconditionally
  in `renderCard` so the new card actually shows its front.
- New "End game" button sits next to "Skip card" below the mic. Pressing it
  calls `/api/summary` with the current session and jumps straight to the
  summary screen. Score is computed over answered cards only; unanswered
  cards are ignored rather than counted as misses.
- `server._summarize_session` now reports `total_cards = session.index`
  (i.e. answered count), with `deck_size` kept separately for transparency.
- `/api/summary` short-circuits to a generic tip when the player ended
  before answering anything, avoiding a pointless LLM call.

## 3. Grading: synonym-aware + relaxed + LLM tiebreak for bias_inverter

**Why.** v2 was too strict on two axes:

- **Perspective cards** required an explicit meta word ("lens"/"frame"/
  "perspective"). Kids who correctly named AUDIENCE ("written for scientists,
  but also for ranchers") got stuck at `surface`.
- **Affective cards** matched "worried" via prefix-stemming but missed
  "terrified", "afraid", "anxious". Kids' actual vocabulary diverges from
  anchor phrasing more than the prefix trick handled.
- **Bias-inverter** required strong-reframe verb AND literal content overlap
  with the suggested_prompt, which was nearly impossible to hit. Deep tier
  was empirically ~0%.

**What changed.** `rules.py` now uses explicit **semantic families**:

- `EMO_FAMILY` — 40+ emotion tokens including adjectives and noun forms.
- `MOTIVE_FAMILY` — clicks, ads, money, manipulation, scam, data…
- `OUTCOME_FAMILY` — share, hoard, buy, spread, rush…
- `META_FAMILY` — frame, lens, perspective, bias, narrative (intentionally
  narrow — no descriptor words, so "pretty words vs scary words" no longer
  falsely reads as meta-awareness).
- `DESCRIPTOR_FAMILY` — word/language/tone/describe and evaluative adjectives
  (scary, pretty, clean, threatening…) — used to detect that the child
  analyzed the HOW, counted as mid.
- `GROUP_NOUN_FAMILY` + `_has_audience_cue()` detect "aimed at X", "for
  scientists", etc. — this is the new path to deep that v2 lacked.
- `STRONG_REFRAME_FAMILY` / `WEAK_REFRAME_FAMILY` for bias_inverter.
- `SEQUENCE_FAMILY` / `PLANNING_FAMILY` / `REVIEW_FAMILY` / `ENUM_FAMILY` for
  task_decomposition.

**Perspective ladder (new paths to deep):**
1. meta word + card engagement (anchor hit OR descriptor hit), OR
2. audience cue naming ≥2 distinct groups, OR
3. audience cue naming 1 group + card engagement.

**Affective ladder:** motive family → deep, outcome family or anchor-7/10 →
mid, emotion family → surface.

**Bias-inverter ladder (and new LLM tiebreak):**
1. strong reframe verb + (content overlap OR audience cue) → deep
2. strong reframe verb alone, or weak reframe + content → mid
3. any reframe signal or content hit → surface
4. **NEW**: the rules engine optionally calls `llm.judge_bias_inverter`
   (a single-word Llama3 classifier, temperature 0.1). It can PROMOTE a
   surface/mid result to deep when the child genuinely reframed the bias.
   It can never demote — the pure rule layer stays the floor.

**Stress-test distribution** across 48 realistic answers (6 answers × 8
cards × 4 problem types):

| Tier | Count |
|---|---|
| deep | 12 |
| mid | 11 |
| surface | 9 |
| off | 8 |
| silent | 8 |

Balanced across the ladder. v2's test had deep starved on bias_inverter and
over-full on surface — v3's distribution matches the design intent.

## Files touched

```
tts.py          — rewritten for Kokoro
index.html      — nextCard bug fixed, End-game button added, single-TTS-call pattern
rules.py        — rewritten with semantic families + LLM-tiebreak hook
llm.py          — added judge_bias_inverter()
prompts.py      — added BIAS_JUDGE_PROMPT
server.py       — passes judge to rules, summary tolerates early end, tts_multi removed
install_and_run.sh — swaps ChatTTS deps for Kokoro deps
```

Nothing else changes. `cards_loader.py`, the two JSON files, and the stress
test harness keep the same shape.

# PROMPT! v3.1 — Follow-up Q&A

One focused feature on top of v3: after the child answers each card, they
can now **ask free-form follow-up questions** about what they just saw,
keep the conversation going for a few turns, and then move on at their own
pace.

## What changed

### 1. Feedback is 3 lines now (was 2)

`prompts.py` / `llm.py` / every per-type template ask for:

```
Line 1 (reaction): one warm sentence about the child's thinking
Line 2 (habit):    the habit to carry forward
Line 3 (invite):   a short question that opens the door for follow-ups
```

Example rendered in the UI:

> **Coach Says** — Nice catch on the framing.
> **Try This Habit** — Ask who the story is written for.
> **Ask Me Anything** — Curious about anything else here?

All three are spoken as one merged warm-tone clip (same single-TTS-call
pattern as v3).

### 2. New `/api/followup` endpoint

Tiny JSON endpoint:

```
POST /api/followup
  { "session_id": "s_...", "question": "Why do posts like this work?" }
→ { "answer": "...",
    "followups_used": 2,
    "followups_allowed": 4,
    "limit_reached": false }
```

Behind it, `llm.answer_followup` calls Llama3 with `FOLLOWUP_PROMPT` — a
strict two-sentence scope limited to the current card plus general
AI/media literacy. If the child drifts off-topic the prompt tells the
model to redirect softly rather than refuse coldly.

The endpoint:
- Attaches the Q&A to the `history[-1]` entry for the card the child just
  answered (appended by `/api/answer`).
- Caps at `MAX_FOLLOWUPS_PER_CARD = 4` so a conversation can't run forever.
- Passes the 2 most recent turns into the LLM as context, so "what about
  the other one?" resolves correctly.

### 3. UI state machine

The right-hand voice panel now has three phases:

| Phase | Mic behaviour | Buttons shown |
|---|---|---|
| `answering` | captures the card answer | Skip card · End game |
| `followup` | captures a follow-up question | Next Card → · End game |
| `done` | mic hidden | — |

Transitions:
- `/api/answer` completes → `answering` → `followup`
- Next Card → → `answering` (next card)
- End game → `done` → summary screen

Follow-up Q&A pairs render as alternating bubbles under the feedback
bubbles. The whole coach stack is internally scrollable so long threads
don't push the buttons off-screen.

### 4. Summary shows follow-up count

Summary screen now shows a small violet line when the child asked at least
one follow-up:

> 💬 You asked **3** follow-up questions — curiosity points!

Follow-ups are **never scored** — this is just a morale pat for curious
kids. Server exposes `total_followups` on `/api/summary`.

## Files touched

```
prompts.py      — _STYLE now asks for 3 lines; new FOLLOWUP_PROMPT
llm.py          — _parse_three_lines; answer_followup(); reply cleanup
server.py       — /api/followup; MAX_FOLLOWUPS_PER_CARD guardrail;
                  history entries now carry followups[] and feedback{}
index.html      — uiPhase state machine; 3 feedback bubbles;
                  Q&A thread rendering; phase-aware mic and buttons;
                  followup counter; summary follow-up line
```

Unchanged: `tts.py`, `rules.py`, `cards_loader.py`, the two JSON files,
`test_rules_stress.py`, `install_and_run.sh`.

## Deployment

No new dependencies. Drop the six touched files over your v3 install and
restart uvicorn. TTS cache survives (Kokoro key still uses
voice::tone::text — the reaction/habit text inside feedback is unchanged,
only a new invite line is added, so only that third clip needs to be
re-rendered).

## Tuning knobs

- **Follow-up cap**: `MAX_FOLLOWUPS_PER_CARD` in `server.py` (default 4).
  Lower to 2 if grown-ups are complaining about long session times.
- **Context window**: `FOLLOWUP_HISTORY_WINDOW` controls how many prior
  Q&A turns the LLM sees. Default 2 balances coherence against latency.
- **Reply length**: `num_predict=120` in `llm.answer_followup`. If replies
  feel cut off, bump to 160. If they drift long, drop to 80.
- **Redirect firmness**: edit the "STRICT rules" block inside
  `FOLLOWUP_PROMPT` in `prompts.py` to change how softly/firmly the coach
  pulls a child back on topic.

## Known soft spots

- Local Llama3 sometimes ignores the "two sentences" cap on very open
  questions like "tell me everything about AI". `_clean_followup_reply`
  trims to 2 sentences before returning, so the display is capped even if
  the model over-produces — but the user is paying for wasted tokens.
  Watch logs; consider dropping `num_predict` if it's a frequent problem.
- If Ollama is down, `answer_followup` returns a cheerful fallback
  ("Hmm, my brain glitched..."). Replies are logged so you can spot
  outages quickly.