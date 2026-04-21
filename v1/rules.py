import re
from typing import Any, Dict, Optional


OPTION_PATTERNS = {
    "A": [r"\ba\b", r"\boption a\b", r"\bi choose a\b", r"\bi think a\b"],
    "B": [r"\bb\b", r"\boption b\b", r"\bi choose b\b", r"\bi think b\b"],
    "C": [r"\bc\b", r"\boption c\b", r"\bi choose c\b", r"\bi think c\b"],
    "D": [r"\bd\b", r"\boption d\b", r"\bi choose d\b", r"\bi think d\b"],
}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def detect_option(text: str) -> Optional[str]:
    text = normalize(text)
    if not text:
        return None

    for option, patterns in OPTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                return option
    return None


def keyword_match(text: str, keywords: list[str]) -> bool:
    text = normalize(text)
    if not text:
        return False

    for kw in keywords:
        if normalize(kw) in text:
            return True
    return False


def build_result(judgement: str, matched_reason: str) -> Dict[str, Any]:
    score_map = {
        "correct": 1.0,
        "partial": 0.5,
        "incorrect": 0.0,
    }
    return {
        "judgement": judgement,
        "is_correct": judgement == "correct",
        "score": score_map[judgement],
        "matched_reason": matched_reason,
    }


def check_answer(card: Dict[str, Any], user_answer: str) -> Dict[str, Any]:
    correct_answer = card["correct_answer"].strip().upper()
    accepted_keywords = card.get("accepted_keywords", [])
    partial_keywords = card.get("partial_keywords", [])

    if not user_answer or not user_answer.strip():
        return build_result("incorrect", "No speech detected")

    detected = detect_option(user_answer)
    if detected:
        if detected == correct_answer:
            return build_result("correct", f"Matched explicit option: {detected}")
        return build_result("incorrect", f"Matched wrong explicit option: {detected}")

    if keyword_match(user_answer, accepted_keywords):
        return build_result("correct", "Matched accepted keyword(s)")

    if keyword_match(user_answer, partial_keywords):
        return build_result("partial", "Matched partial keyword(s)")

    return build_result("incorrect", "No valid option or keyword matched")