"""
Rules engine for PROMPT! v3.

Design goals after v2 field testing:
  1. v2 required an explicit meta word ("lens"/"frame"/"perspective"/...) to
     reach `deep` on perspective cards. Kids who correctly named AUDIENCE
     ("for scientists vs for locals") or the FRAMING MOVE ("they use scary
     words on one side") got stuck at `surface`. That was too strict.
  2. v2 had no synonym awareness. "worried" matched "worry" via prefix, but
     "terrified" didn't match "fear"; "afraid" didn't match "fear". A child's
     vocabulary rarely lines up byte-for-byte with anchor vocabulary.
  3. v2 gave `bias_inverter` a near-impossible deep bar because it required a
     strong reframe verb AND content overlap with the suggested_prompt. That
     left deep ≈ 0% in practice.

Fixes in v3:
  - Expanded semantic groups (emotion family, motive family, reframe family,
    planning family) are matched through SETS, not prefix games.
  - `perspective_lens_audit` deep tier triggers on EITHER a meta/lens word OR
     an explicit audience phrase (words like "for", "to", "audience",
     "reader"), whichever the child happens to reach.
  - `bias_inverter` gets a lighter-touch ladder AND an optional LLM judge
     that can PROMOTE (never demote) a borderline answer to deep when the
     child's proposed prompt is a genuine reframing of the card's bias.
  - Tiebreaks still go DOWN for the pure rule layer. The LLM only bumps UP
     when explicitly enabled, so scoring stays predictable in offline runs.

The LLM assist is wired to `llm.judge_bias_inverter`, which is cheap and
runs on the same Ollama model already loaded for feedback. When Ollama is
not available the function is a no-op and the rule result stands.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

_WORD_RE = re.compile(r"[A-Za-z0-9\-]+")


def normalize(text: str) -> List[str]:
    if not text:
        return []
    return [t.lower() for t in _WORD_RE.findall(text)]


# ─── Semantic families ────────────────────────────────────────────
# Each family is a set of tokens that should count as "the child reached
# this concept". These are what we lookup inside the child's answer.

EMO_FAMILY = {
    "fear", "fears", "fearful", "afraid", "terrified", "terror", "terrifying",
    "scared", "scary", "scare", "frightened", "frightening",
    "panic", "panicked", "panicking", "panicky",
    "anger", "angry", "mad", "furious", "rage", "enraged",
    "sad", "sadness", "sorrow", "sorry", "upset",
    "worry", "worried", "worries", "worrying", "anxious", "anxiety",
    "guilt", "guilty", "ashamed", "shame",
    "shock", "shocked", "shocking", "surprise", "surprised",
    "greed", "greedy", "envy",
    "urgency", "urgent", "rush", "rushed",
    "outrage", "outraged", "disgust", "disgusted",
    "excited", "excitement", "thrilled",
    "emotion", "emotional", "feeling", "feelings", "feel", "feels",
}

# Words that signal the child understood WHO BENEFITS from the content.
MOTIVE_FAMILY = {
    "clicks", "click", "clicking", "clickbait",
    "money", "profit", "profits", "cash", "revenue",
    "attention", "views", "engagement", "likes", "shares",
    "manipulate", "manipulation", "manipulative", "manipulating",
    "unrest", "destabilize", "destabilise", "chaos",
    "steal", "stealing", "scam", "scams", "scammer", "phishing",
    "data", "ads", "advertising", "advertisers", "advertiser",
    "viral", "farm", "farming",
    "sell", "selling", "buy",   # as in "get you to buy"
    "influence", "influencing",
    "control", "controlling",
    "power",
    "fake", "fraud", "lies", "lie", "lying",
    "trick", "tricks", "tricking", "trickery",
    "propaganda",
}

# Words describing what will HAPPEN next if the post succeeds.
OUTCOME_FAMILY = {
    "share", "sharing", "shared", "spread", "spreading",
    "hoard", "hoarding", "stockpile", "stockpiling",
    "buy", "buying", "purchase", "purchasing",
    "trouble", "protest", "protesting",
    "isolate", "isolated", "withdraw", "withdrawing",
    "click", "clicking", "forward", "forwarding",
    "vote", "voting", "boycott",
    "rush", "run", "running",   # as in bank run, rush to store
    "panic-buy", "panic", "panicking",
}

# Explicit meta/lens awareness — the child SAID what the cognitive move is.
# Intentionally narrow: only tokens that name the cognitive move itself.
# Words like "word"/"words"/"describe" live in DESCRIPTOR_FAMILY instead, so
# they don't double-count when a child says "they use nice words vs scary words."
META_FAMILY = {
    "frame", "frames", "framing", "framed",
    "lens", "lenses",
    "perspective", "perspectives",
    "viewpoint", "viewpoints", "point-of-view", "pov",
    "audience", "audiences",
    "bias", "biased", "biases",
    "angle", "angles",
    "narrative", "narratives",
    "spin", "slant", "slanted",
}

# Audience-target phrasing — "written for kids", "aimed at scientists".
# These signal the child noticed the same info is packaged for different groups.
AUDIENCE_CUE_FAMILY = {
    "aimed", "written", "intended", "targeting", "targeted",
    "designed", "meant",
    # "for" and "to" are too generic on their own, so we check them
    # in combination with a GROUP noun below.
}
GROUP_NOUN_FAMILY = {
    "kids", "children", "adults", "parents", "teachers", "scientists",
    "workers", "farmers", "engineers", "experts", "officials",
    "neighbors", "locals", "residents", "ranchers", "citizens", "voters",
    "students", "reporters", "readers", "listeners",
    "scientist", "worker", "farmer", "expert", "official", "neighbor",
    "local", "resident", "rancher", "citizen", "voter",
    "student", "reporter",
    "someone", "people", "public",
}

# Descriptor / tone vocabulary the child uses to describe HOW the two sides
# speak. "word"/"words"/"describe" live here (not in META_FAMILY) because they
# belong to "the child talked about the descriptions", not "the child named
# the cognitive move." Keeping them out of META_FAMILY prevents double-counting
# when a child says "pretty words vs scary words" — that should score mid,
# not deep.
DESCRIPTOR_FAMILY = {
    # evaluative descriptors the two sides might use
    "scary", "nice", "pretty", "ugly", "good", "bad",
    "positive", "negative",
    "clean", "dirty", "dangerous", "safe",
    "threat", "threatening", "threaten",
    "beautiful", "awful", "terrible",
    "happy", "angry", "sad",
    "calm", "harsh",
    # meta-descriptor words about the ACT of describing
    "word", "words", "wording",
    "describe", "describes", "described", "describing", "description",
    "language", "tone", "phrasing",
    "story", "stories",
    "reader", "readers", "listener", "listeners",
}

# Strong reframing verbs — the child is ASKING AI to change view.
STRONG_REFRAME_FAMILY = {
    "rewrite", "rewrites", "rewrote",
    "rephrase", "rephrases", "rephrased",
    "reframe", "reframes", "reframing", "reframed",
    "compare", "compares", "comparing", "compared", "contrast",
    "perspective", "perspectives", "viewpoint", "viewpoints",
    "lens", "lenses",
    "stakeholders", "stakeholder",
    "opposing", "opposite",
    "both", "balance", "balanced",
}

# Weaker reframe signals.
WEAK_REFRAME_FAMILY = {
    "view", "views",
    "audience", "audiences", "perspectives",
    "instead", "also", "another", "other", "different",
    "whose", "who", "benefit", "benefits", "benefitting",
    "cost", "costs", "tradeoff", "tradeoffs", "trade-off", "trade-offs",
    "side", "sides",
    "miss", "missing", "missed", "left", "ignored", "forgot", "forgotten",
    "hidden", "hide", "hides", "hiding",
    "fair", "fairness", "fairer",
}

# Decomposition vocabulary.
SEQUENCE_FAMILY = {
    "first", "second", "third", "fourth", "fifth",
    "then", "next", "after", "afterward",
    "finally", "last", "lastly",
    "before", "beforehand",
    "step", "steps", "stage", "stages",
    "start", "begin", "beginning",
    "end", "ending",
}
PLANNING_FAMILY = {
    "plan", "plans", "planning",
    "outline", "outlines", "outlining",
    "draft", "drafts", "drafting",
    "design", "designs", "designing",
    "list", "listing",
    "organize", "organizing", "organise", "organising",
    "break", "breaking", "split", "splitting",
    "divide", "dividing",
    "decompose", "decomposing",
    "sequence", "sequencing",
    "order", "ordering",
    "map", "mapping",
    "sub-task", "subtask", "subtasks", "sub-tasks",
    "phase", "phases",
    "workflow", "checklist",
}
REVIEW_FAMILY = {
    "check", "checks", "checking", "checked",
    "review", "reviews", "reviewing",
    "revise", "revises", "revising", "revised",
    "test", "testing", "tested",
    "verify", "verifying", "verified", "verification",
    "edit", "editing", "edited",
    "refine", "refining", "refined",
    "polish", "polishing",
    "proofread",
}
ENUM_FAMILY = {
    "one", "two", "three", "four", "five", "six",
    "1", "2", "3", "4", "5", "6",
}


# ─── Small utilities ──────────────────────────────────────────────

def _family_hits(tokens: List[str], family: set) -> int:
    """How many DISTINCT family tokens the child said."""
    seen = set()
    for t in tokens:
        if t in family:
            seen.add(t)
    return len(seen)


def _has_audience_cue(tokens: List[str]) -> bool:
    """
    True when the child describes WHO something is aimed at.
    Either an AUDIENCE_CUE_FAMILY word ("aimed", "written"), or a
    preposition ("for"/"to") followed nearby by a GROUP_NOUN.
    """
    if any(t in AUDIENCE_CUE_FAMILY for t in tokens):
        return True
    for i, tok in enumerate(tokens):
        if tok in {"for", "to", "toward", "towards"}:
            # look ahead up to 3 tokens for a group noun
            for j in range(i + 1, min(i + 4, len(tokens))):
                if tokens[j] in GROUP_NOUN_FAMILY:
                    return True
    return False


def _build(score: int, matched_reason: str, tier: str) -> Dict[str, Any]:
    if score >= 10:
        judgement = "correct"
    elif score >= 7:
        judgement = "good"
    elif score >= 3:
        judgement = "partial"
    else:
        judgement = "incorrect"
    return {
        "score": score,
        "tier": tier,
        "judgement": judgement,
        "matched_reason": matched_reason,
    }


# ─── Per-problem-type scorers ─────────────────────────────────────

def _score_perspective_lens(card: Dict[str, Any], user_answer: str) -> Dict[str, Any]:
    """
    perspective_lens_audit ladder (v3 relaxed):
      deep(10):   child reached META awareness, via EITHER
                    (a) a meta word (frame/lens/perspective/audience/…), OR
                    (b) an audience cue that actually names groups
                        ("aimed at scientists vs ranchers", "for kids vs adults").
                  In both paths we also want SOME evidence they engaged the
                  card: an anchor hit, a descriptor hit, OR (for the audience
                  path) two distinct group nouns.
      mid(7):     contrasting descriptors / tone-word talk, OR an anchor-7
                  framing hit, OR meta/audience signal WITHOUT content.
      surface(3): basic contrast / single signal.
      off(0):     nothing on topic.
    """
    tokens = normalize(user_answer)
    if not tokens:
        return _build(0, "No speech detected.", "silent")

    hits_3 = _simple_overlap(tokens, card.get("anchor_keywords_3", []))
    hits_7 = _simple_overlap(tokens, card.get("anchor_keywords_7", []))
    hits_10 = _simple_overlap(tokens, card.get("anchor_keywords_10", []))
    anchor_hit = (hits_3 + hits_7 + hits_10) >= 1

    meta_hits = _family_hits(tokens, META_FAMILY)
    descriptor_hits = _family_hits(tokens, DESCRIPTOR_FAMILY)
    audience_cue = _has_audience_cue(tokens)
    distinct_groups = _family_hits(tokens, GROUP_NOUN_FAMILY)

    # Evidence the child engaged the SPECIFIC card, not just reframing boilerplate
    engaged = anchor_hit or descriptor_hits >= 1

    # DEEP — two paths:
    #  (1) meta + engagement
    #  (2) audience cue with at least TWO distinct named groups
    #      ("for scientists vs for ranchers" = two groups = legit audience-lens)
    if meta_hits >= 1 and engaged:
        return _build(10, "Deep: named the frame/lens/perspective.", "deep")
    if audience_cue and distinct_groups >= 2:
        return _build(10, "Deep: contrasted distinct audiences.", "deep")
    # Audience cue with one group + card engagement also earns deep
    if audience_cue and distinct_groups >= 1 and engaged:
        return _build(10, "Deep: named audience with card engagement.", "deep")

    # MID — talked about HOW, without full meta awareness
    #   multiple descriptors = real contrast talk
    #   anchor-7 hit = hit the framing anchor directly
    #   meta or audience signal with weak engagement = gave it a shot
    if descriptor_hits >= 2 or hits_7 >= 1 or (meta_hits >= 1 and anchor_hit):
        return _build(7, "Analyzed descriptors / framing.", "mid")
    if meta_hits >= 1 or audience_cue:
        return _build(7, "Named the move without full content engagement.", "mid")

    # SURFACE — basic contrast only
    if anchor_hit or descriptor_hits >= 1 or distinct_groups >= 1:
        return _build(3, "Spotted the basic contrast.", "surface")

    return _build(0, "No anchor content detected.", "off")


def _score_affective_hijack(card: Dict[str, Any], user_answer: str) -> Dict[str, Any]:
    """
    affective_highjack ladder (v3 synonym-aware):
      deep(10):   motive family hit — child said WHO BENEFITS (clicks,
                  ads, data, manipulation, tricks, ...).
      mid(7):     outcome family hit (what sharing WILL DO), OR they
                  echoed an anchor-7/10 content word from the card.
      surface(3): emotion family hit only — child named the feeling.
      off(0):     nothing on topic.
    """
    tokens = normalize(user_answer)
    if not tokens:
        return _build(0, "No speech detected.", "silent")

    hits_7 = _simple_overlap(tokens, card.get("anchor_keywords_7", []))
    hits_10 = _simple_overlap(tokens, card.get("anchor_keywords_10", []))

    motive_hits = _family_hits(tokens, MOTIVE_FAMILY)
    outcome_hits = _family_hits(tokens, OUTCOME_FAMILY)
    emo_hits = _family_hits(tokens, EMO_FAMILY)

    if motive_hits >= 1:
        return _build(10, "Named the motive/incentive.", "deep")
    if hits_7 >= 1 or outcome_hits >= 1 or hits_10 >= 1:
        return _build(7, "Predicted downstream outcome of sharing.", "mid")
    if emo_hits >= 1:
        return _build(3, "Named the emotion being targeted.", "surface")
    return _build(0, "No emotional-literacy content detected.", "off")


def _score_bias_inverter(card: Dict[str, Any], user_answer: str) -> Dict[str, Any]:
    """
    bias_inverter ladder (v3 relaxed):
      deep(10):   strong reframe verb AND some content-overlap OR audience cue.
                  (v2 required content overlap only — too strict when the
                  child names a stakeholder that isn't in the suggested
                  prompt word-for-word.)
      mid(7):     strong reframe verb alone, OR weak reframe + content/audience.
      surface(3): any reframe signal (weak or strong) or pure content overlap.
      off(0):     nothing on topic.

    Optional LLM PROMOTION (applied by check_answer when llm_judge is given):
      the LLM can upgrade a mid → deep if the child's answer is genuinely a
      bias-reversal of the card's framing. The rule layer never demotes.
    """
    tokens = normalize(user_answer)
    if not tokens:
        return _build(0, "No speech detected.", "silent")

    strong_hits = _family_hits(tokens, STRONG_REFRAME_FAMILY)
    weak_hits = _family_hits(tokens, WEAK_REFRAME_FAMILY)
    audience_cue = _has_audience_cue(tokens)

    # Content overlap against the suggested_prompt, but stripped of the
    # generic reframing vocabulary so it measures CARD-SPECIFIC nouns.
    from cards_loader import _extract_keywords
    raw_kws = _extract_keywords(card.get("suggested_prompt") or "")
    content_kws = [
        k for k in raw_kws
        if k not in STRONG_REFRAME_FAMILY and k not in WEAK_REFRAME_FAMILY
    ]
    content_hits = _simple_overlap(tokens, content_kws)

    if strong_hits >= 1 and (content_hits >= 1 or audience_cue):
        return _build(10, "Concrete reframing aligned with stakeholders.", "deep")
    if strong_hits >= 1 or (weak_hits >= 1 and (content_hits >= 1 or audience_cue)):
        return _build(7, "Reframing move started.", "mid")
    if weak_hits >= 1 or content_hits >= 1 or audience_cue:
        return _build(3, "Gestured toward another viewpoint.", "surface")
    return _build(0, "No reframing language detected.", "off")


def _score_task_decomposition(card: Dict[str, Any], user_answer: str) -> Dict[str, Any]:
    """
    task_decomposition_map ladder:
      deep(10):   planning + sequencing + (review OR multiple enumerations).
      mid(7):     any two of: planning, sequencing, enumeration.
      surface(3): any one signal.
      off(0):     nothing on topic.
    """
    tokens = normalize(user_answer)
    if not tokens:
        return _build(0, "No speech detected.", "silent")

    seq = _family_hits(tokens, SEQUENCE_FAMILY)
    plan = _family_hits(tokens, PLANNING_FAMILY)
    rev = _family_hits(tokens, REVIEW_FAMILY)
    enum = _family_hits(tokens, ENUM_FAMILY)

    signals = sum(x >= 1 for x in (seq, plan, enum))

    if plan >= 1 and seq >= 1 and (rev >= 1 or enum >= 2):
        return _build(10, "Multiple steps with a review stage.", "deep")
    if signals >= 2:
        return _build(7, "Sequenced multiple planning signals.", "mid")
    if signals >= 1:
        return _build(3, "Mentioned a planning step.", "surface")
    return _build(0, "No decomposition language detected.", "off")


# ─── Overlap helper (renamed, kept local) ─────────────────────────

def _simple_overlap(user_tokens: List[str], anchor_keywords: List[str]) -> int:
    """
    Count anchor keywords the child hit. Uses prefix matching for
    plurals/inflections but only on tokens of length ≥ 4 to avoid letting
    "a", "to", or "is" sweep through everything.
    """
    if not anchor_keywords or not user_tokens:
        return 0
    uset = set(user_tokens)
    hits = 0
    for kw in anchor_keywords:
        if kw in uset:
            hits += 1
            continue
        if len(kw) < 4:
            continue
        for t in uset:
            if len(t) < 4:
                continue
            if t.startswith(kw) or kw.startswith(t):
                hits += 1
                break
    return hits


# Kept for backwards compatibility with anything importing _overlap.
def _overlap(user_tokens: List[str], anchor_keywords: List[str]) -> int:
    return _simple_overlap(user_tokens, anchor_keywords)


# ─── Dispatcher & main entry ──────────────────────────────────────

_SCORERS: Dict[str, Callable] = {
    "perspective_lens_audit": _score_perspective_lens,
    "affective_highjack": _score_affective_hijack,
    "bias_inverter": _score_bias_inverter,
    "task_decomposition_map": _score_task_decomposition,
}

_TIER_ORDER = {"silent": 0, "off": 1, "surface": 2, "mid": 3, "deep": 4}
_TIER_TO_SCORE = {"silent": 0, "off": 0, "surface": 3, "mid": 7, "deep": 10}


def check_answer(
    card: Dict[str, Any],
    user_answer: str,
    llm_judge: Optional[Callable[[Dict[str, Any], str, Dict[str, Any]], Optional[str]]] = None,
) -> Dict[str, Any]:
    """
    Main entry. `llm_judge`, if provided, is called ONLY for bias_inverter
    cards and may return a tier name to PROMOTE the rule result. Never
    demotes. Signature: (card, user_answer, rule_result) -> Optional[tier].
    """
    problem_type = card.get("problem_type", "")
    scorer = _SCORERS.get(problem_type)
    if scorer is None:
        return _build(0, f"Unknown problem type: {problem_type}", "off")

    result = scorer(card, user_answer or "")

    # Optional LLM promotion for bias_inverter only. Rule layer stays honest;
    # LLM only bumps UP when the child's answer really does reframe the bias.
    if (
        llm_judge is not None
        and problem_type == "bias_inverter"
        and (user_answer or "").strip()
        and result["tier"] in ("surface", "mid")
    ):
        try:
            suggested = llm_judge(card, user_answer, result)
            if suggested in _TIER_ORDER and _TIER_ORDER[suggested] > _TIER_ORDER[result["tier"]]:
                promoted_score = _TIER_TO_SCORE[suggested]
                result = _build(
                    promoted_score,
                    f"LLM-promoted from {result['tier']} to {suggested}.",
                    suggested,
                )
        except Exception as e:
            print(f"[rules] llm_judge failed, keeping rule result: {e}")

    return result