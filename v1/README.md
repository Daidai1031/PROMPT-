# PROMPT! — Offline AI Literacy Game (Thor MVP)

## Overview

**PROMPT!** is an AI literacy card game designed to help players (age 10+) develop critical thinking skills when interacting with AI and online information.

The system teaches players to:

- Distinguish real vs. fake information
- Understand how AI works and fails
- Recognize misinformation strategies and motives

This MVP runs fully offline on NVIDIA Jetson AGX Thor, enabling:

- Accessibility without internet
- Privacy-preserving interaction
- Device-based AI tutoring

---

## System Architecture

### Core Device Pipeline (Current MVP)

1. Load local card database (JSON)
2. Select a card
3. Display or read question
4. Record user speech (microphone)
5. Transcribe speech → text (Whisper)
6. Evaluate answer via rule-based matching and keyword matching
7. Generate feedback (Llama 3 via Ollama)
8. Output feedback (text → future TTS)
9. Update score

---

## Project Structure

| File | Description |
|---|---|
| `app.py` | Main game loop |
| `rules.py` | Deterministic answer evaluation |
| `llm.py` | Feedback generation (local LLM) |
| `cards.json` | Structured card database |
| `test.wav` | Temporary audio file |

---

## Environment

### Hardware

- NVIDIA Jetson AGX Thor Developer Kit

### System

- Ubuntu 24.04 (JetPack R38)
- ARM64 architecture

---

## Models & Tools

### LLM

- Ollama 0.19.0
- Llama 3 (local, ~4.7 GB)

### Speech-to-Text

- Whisper (openai-whisper)
- PyTorch with CUDA

---

## Design Principles

### 1. Deterministic Judgement

The system does **not** rely on LLM for correctness. Instead, it uses exact answer matching and keyword-based reasoning. This ensures stability and avoids hallucination.

### 2. LLM as Tutor, Not Judge

LLM is **only** used for rewriting feedback and making explanations engaging and child-friendly. It does **not** decide whether the answer is correct or determine factual truth.

### 3. Offline-First System

Fully local execution with no dependency on cloud APIs, robust to low-connectivity environments.

---

## Card Design

Each card is structured with the following fields:

- Question
- Answer choices
- Correct answer
- Accepted keywords
- Explanation
- Teaching focus
- Verification tip
- Source note

The design emphasizes reasoning over guessing, habit formation (e.g., verify sources), and real-world transfer.

---

## Current Limitations (MVP)

- CLI interface only (no GUI yet)
- No TTS (text-only output, waiting for usb speaker)
- Whisper latency may affect interaction flow
- Limited card dataset
- No progression system yet

---

## Future Work

### Interaction & Hardware

- Add physical buzzer for competitive gameplay
- Support multi-player interaction
- Improve real-time responsiveness

### AI & Knowledge Layer

- Introduce RAG (Retrieval-Augmented Generation) grounded in research sources, fact-check datasets, and AI literacy frameworks
- Enable better explanations, context-aware tutoring, and an evolving knowledge base

### Learning Experience Design

- Add exploratory discussion sessions — not just right/wrong answers, but open-ended thinking ("Why do you think this?")
- Support reasoning chains, reflection prompts, and analogy-based learning
- **Goal:** move from quiz → thinking tool

### UI / Product

- Build screen-based gamified UI, on [7 Inches Touchscreen Monitor, HD 1024×600 IPS LCD Capacitive Touch Screen](https://www.amazon.com/gp/product/B0F3JFG4RS/ref=ewc_pr_img_1?smid=AV7XJI4JYMAJR&psc=1)
- Add score visualization, progression system (Apprentice → Pro), and category-based learning paths

### Voice Interaction

- Add TTS (Riva / Piper)
- Add wake-word interaction
- Improve STT robustness

### Content Expansion

- Expand to full 108-card system covering Real vs. Fake, AI Best Practices, and Bad Actors & Motive
- Improve difficulty balancing, educational scaffolding, and real-world relevance

---

## Future Architecture

### Offline Mode (Current)

Thor handles LLM, STT, game logic, and UI — all locally.

### Online Enhanced Mode (Planned)

- **Thor (local):** interaction, fallback logic
- **Cloud:** enhanced dialogue, better ASR, content updates, analytics

---


## Notes

- Card content is still evolving
- Feedback style is optimized for children (10+)
- Focus areas: AI literacy, misinformation awareness, democratic resilience
