from ollama import chat


CATEGORY_GUIDANCE = {
    "real_vs_fake": "Focus on checking evidence, sources, and context.",
    "ai_best_practices": "Focus on using AI carefully, clearly, and responsibly.",
    "bad_actors": "Focus on motive, incentives, and who benefits when false information spreads."
}


def generate_feedback(
    model: str,
    question: str,
    user_answer: str,
    judgement: str,
    explanation: str,
    category: str,
    matched_reason: str,
    misconception: str,
    teaching_focus: str,
    source_note: str,
    verification_tip: str,
) -> str:
    category_guidance = CATEGORY_GUIDANCE.get(
        category,
        "Focus on clear and encouraging learning feedback."
    )

    prompt = f"""
You are a playful, kind AI game companion for players age 10+.

The system has already judged the answer.
Do NOT judge the answer yourself.
Your job is only to give short spoken feedback.

Style rules:
- 1 or 2 short sentences
- warm, cheerful, and encouraging
- simple words for kids age 10+
- not preachy
- not too formal
- sound like a friendly robot game host
- avoid sarcasm
- avoid politics-heavy wording
- do not repeat the whole question
- do not mention "matched reason"
- do not say "misconception"
- if incorrect, be gentle and explain the key idea simply
- if partial, praise what was right and add one missing idea
- if correct, celebrate briefly and reinforce the lesson
- whenever helpful, include one simple verification habit

Category guidance:
{category_guidance}

Question: {question}
User answer: {user_answer}
Judgement: {judgement}
Explanation: {explanation}
Teaching focus: {teaching_focus}
Source note: {source_note}
Verification tip: {verification_tip}
""".strip()

    try:
        response = chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response["message"]["content"].strip()
    except Exception as e:
        fallback_map = {
            "correct": f"Nice job! {teaching_focus}",
            "partial": f"You are close! {teaching_focus}",
            "incorrect": f"Good try! {explanation} {verification_tip}",
        }
        return fallback_map.get(judgement, f"Thanks for playing! {verification_tip}") + f" (LLM error: {e})"


def generate_summary_tip(
    model: str,
    best_category: str,
    worst_category: str,
    score: str,
) -> str:
    prompt = f"""
You are a playful, kind AI game companion for players age 10+.

Generate exactly one short end-of-game tip.
Rules:
- under 16 words
- very simple
- practical
- friendly
- suitable for children
- related to checking information or using AI carefully

Score: {score}
Best category: {best_category}
Weakest category: {worst_category}
""".strip()

    try:
        response = chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response["message"]["content"].strip()
    except Exception:
        return "Pause, check the source, and ask who benefits before you share."