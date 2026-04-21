import json
import random
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import whisper

from llm import generate_feedback, generate_summary_tip
from rules import check_answer


AUDIO_DEVICE = "plughw:2,0"
AUDIO_FILE = "answer.wav"
RECORD_SECONDS = 8
WHISPER_MODEL = "small"
OLLAMA_MODEL = "llama3"
NUM_QUESTIONS = 3
CARDS_PATH = "cards.json"


def load_cards(path: str) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Could not find {path}")
    with p.open("r", encoding="utf-8") as f:
        cards = json.load(f)
    if not isinstance(cards, list) or not cards:
        raise ValueError("cards.json must contain a non-empty list")
    return cards


def record_audio(output_file: str, device: str, duration: int) -> None:
    cmd = [
        "arecord",
        "-D", device,
        "-f", "S16_LE",
        "-r", "16000",
        "-c", "1",
        "-d", str(duration),
        output_file,
    ]
    print(f"\n🎤 Recording for {duration} seconds...")
    print("Speak now.")
    subprocess.run(cmd, check=True)


def transcribe_audio(model: whisper.Whisper, audio_file: str) -> str:
    print("🧠 Transcribing...")
    result = model.transcribe(audio_file, language="en", task="transcribe")
    return result.get("text", "").strip()


def print_card(card: Dict[str, Any], index: int, total: int) -> None:
    print("\n" + "=" * 60)
    print(f"Question {index}/{total}")
    print(f"Category: {card['category']}")
    print(f"\n{card['question']}\n")
    options = card.get("options", {})
    for key in ["A", "B", "C", "D"]:
        if key in options:
            print(f"{key}. {options[key]}")
    print("=" * 60)


def update_session(session: Dict[str, Any], card: Dict[str, Any], result: Dict[str, Any], user_answer: str) -> None:
    session["total_questions"] += 1
    session["total_score"] += result["score"]

    category = card["category"]
    if category not in session["category_stats"]:
        session["category_stats"][category] = {
            "total": 0,
            "score": 0.0,
            "correct": 0,
            "partial": 0,
            "incorrect": 0
        }

    stats = session["category_stats"][category]
    stats["total"] += 1
    stats["score"] += result["score"]
    stats[result["judgement"]] += 1

    session["history"].append(
        {
            "card_id": card["id"],
            "category": category,
            "question": card["question"],
            "user_answer": user_answer,
            "judgement": result["judgement"],
            "score": result["score"],
            "matched_reason": result["matched_reason"],
        }
    )


def get_best_and_worst_category(category_stats: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    if not category_stats:
        return {"best": "N/A", "worst": "N/A"}

    scored = []
    for category, stats in category_stats.items():
        total = stats["total"]
        avg_score = stats["score"] / total if total else 0
        scored.append((category, avg_score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return {
        "best": scored[0][0],
        "worst": scored[-1][0],
    }


def print_summary(session: Dict[str, Any]) -> None:
    print("\n" + "=" * 60)
    print("GAME SUMMARY")
    print("=" * 60)

    total = session["total_questions"]
    total_score = session["total_score"]
    print(f"Score: {total_score:.1f}/{total}")

    category_result = get_best_and_worst_category(session["category_stats"])
    print(f"Best category: {category_result['best']}")
    print(f"Weakest category: {category_result['worst']}")

    for category, stats in session["category_stats"].items():
        print(
            f"- {category}: "
            f"score={stats['score']:.1f}/{stats['total']}, "
            f"correct={stats['correct']}, partial={stats['partial']}, incorrect={stats['incorrect']}"
        )

    tip = generate_summary_tip(
        model=OLLAMA_MODEL,
        best_category=category_result["best"],
        worst_category=category_result["worst"],
        score=f"{total_score:.1f}/{total}",
    )
    print(f"\nAI literacy tip: {tip}")
    print("=" * 60)


def main() -> None:
    print("Starting PROMPT! Thor MVP...")
    cards = load_cards(CARDS_PATH)
    selected_cards = random.sample(cards, k=min(NUM_QUESTIONS, len(cards)))

    print("Loading Whisper model...")
    whisper_model = whisper.load_model(WHISPER_MODEL)

    session = {
        "total_questions": 0,
        "total_score": 0.0,
        "category_stats": {},
        "history": [],
    }

    input("\nPress Enter to start the game...")

    for i, card in enumerate(selected_cards, start=1):
        print_card(card, i, len(selected_cards))
        input("\nPress Enter, then answer out loud after recording starts...")

        try:
            record_audio(AUDIO_FILE, AUDIO_DEVICE, RECORD_SECONDS)
        except subprocess.CalledProcessError as e:
            print(f"Recording failed: {e}")
            continue

        user_text = transcribe_audio(whisper_model, AUDIO_FILE)
        print(f"\nYou said: {user_text if user_text else '[No speech detected]'}")

        result = check_answer(card, user_text)

        feedback = generate_feedback(
            model=OLLAMA_MODEL,
            question=card["question"],
            user_answer=user_text or "[No speech detected]",
            judgement=result["judgement"],
            explanation=card["explanation"],
            category=card["category"],
            matched_reason=result["matched_reason"],
            misconception=card.get("misconception", ""),
            teaching_focus=card.get("teaching_focus", ""),
            source_note=card.get("source_note", ""),
            verification_tip=card.get("verification_tip", ""),
        )

        label_map = {
            "correct": "Correct ✅",
            "partial": "Partially correct 🟡",
            "incorrect": "Incorrect ❌",
        }

        print("\nResult:", label_map[result["judgement"]])
        print(f"Score earned: {result['score']}")
        print("Why matched:", result["matched_reason"])
        print("\nAI Feedback:")
        print(feedback)

        update_session(session, card, result, user_text)

    print_summary(session)


if __name__ == "__main__":
    main()