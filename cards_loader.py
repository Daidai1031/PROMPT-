"""cards_loader.py — same as v2, kept verbatim for the stress test."""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any, Dict, List

DISCERNMENT_PATH = "discernment_cards.json"
USAGE_PATH = "usage_cards.json"

_STOPWORDS = {
    "the","a","an","and","or","but","of","to","in","on","for","with","as","is","are","be","was","were","by","at","it","its",
    "that","this","these","those","your","you","from","into","about","vs","vs.",
    "identified","identify","detected","detect","detects","spotted","spot","noted","note","notice","noticed",
    "analyzed","analyze","analysis","analyse","check","checks","checked","checking","compare","compared","comparing","comparison",
    "scan","scanned","scanning","contrast","contrasted","contrasting","framing","proposed","propose","tracked","track","trace","saw",
    "could","might","should","would","will","kids","their","them","they","there","here","some","many","much","more","less","most",
    "thing","things","something","someone","really","very","just","like","well","people","person","news","post","posts",
}

def _extract_keywords(text: str, min_len: int = 4) -> List[str]:
    if not text: return []
    tokens = re.split(r"[^A-Za-z0-9\-]+", text.lower())
    out = []
    for t in tokens:
        if len(t) < min_len: continue
        if t in _STOPWORDS: continue
        out.append(t)
    seen=set(); uniq=[]
    for t in out:
        if t not in seen:
            seen.add(t); uniq.append(t)
    return uniq

def _normalize_card(raw: Dict[str, Any], source_category: str) -> Dict[str, Any]:
    front = raw.get("front", {})
    back = raw.get("back", {})
    notes = raw.get("teacher_notes", {})
    anchors = back.get("scoring_anchors", {}) or {}
    anchor_3 = anchors.get("3_pts", "")
    anchor_7 = anchors.get("7_pts", "")
    anchor_10 = anchors.get("10_pts", "")
    suggested_prompt = anchors.get("suggested_prompt", "")
    return {
        "id": raw.get("card_id","?"),
        "category": source_category,
        "problem_type": raw.get("problem_type","unknown"),
        "difficulty": raw.get("difficulty","easy"),
        "title": front.get("title","Untitled"),
        "body": front.get("card_text", []) or [],
        "verdict": back.get("verdict",""),
        "anchors": {"3_pts":anchor_3,"7_pts":anchor_7,"10_pts":anchor_10,"suggested_prompt":suggested_prompt},
        "suggested_prompt": suggested_prompt or None,
        "reality_anchor": back.get("reality_anchor",""),
        "deep_insight": notes.get("deep_insight",""),
        "habit": notes.get("habit",""),
        "references": notes.get("references", []) or [],
        "anchor_keywords_3": _extract_keywords(anchor_3),
        "anchor_keywords_7": _extract_keywords(anchor_7),
        "anchor_keywords_10": _extract_keywords(anchor_10),
        "habit_keywords": _extract_keywords(notes.get("habit","")),
    }

def _load_file(path: str, source_category: str) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists(): return []
    with p.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list): return []
    return [_normalize_card(c, source_category) for c in raw]

def load_all_cards() -> Dict[str, List[Dict[str, Any]]]:
    disc = _load_file(DISCERNMENT_PATH,"discernment")
    usage = _load_file(USAGE_PATH,"usage")
    return {"discernment":disc,"usage":usage,"all":disc+usage}

def get_card_by_id(card_id: str) -> Dict[str, Any] | None:
    """
    Look up a single card by its `card_id` (e.g. "#14" or "14").
    Accepts IDs with or without the leading '#', with or without leading zeros.
    """
    if not card_id:
        return None
    raw = str(card_id).strip().lstrip("#").lstrip("0") or "0"
    all_cards = load_all_cards()["all"]
    for c in all_cards:
        cid = str(c.get("id", "")).lstrip("#").lstrip("0") or "0"
        if cid == raw:
            return c
    return None


def build_scan_index() -> List[Dict[str, Any]]:
    """
    Build a compact card index for the frontend scanner.

    Each entry has the absolute minimum the OCR matcher needs:
      - id        : "#14"
      - id_num    : "14" (canonical, no '#', no leading zeros)
      - title     : card title
      - body_snip : first 80 chars of body, lowercased, for fuzzy matching

    The frontend ships this list to the OCR loop so we can match offline
    without round-tripping candidate strings to the server every frame.
    """
    out = []
    for c in load_all_cards()["all"]:
        raw_id = str(c.get("id", "")).strip()
        id_num = raw_id.lstrip("#").lstrip("0") or "0"
        body = c.get("body") or []
        if isinstance(body, list):
            body_text = " ".join(body)
        else:
            body_text = str(body)
        out.append({
            "id": raw_id,
            "id_num": id_num,
            "title": c.get("title", ""),
            "category": c.get("category", ""),
            "problem_type": c.get("problem_type", ""),
            "difficulty": c.get("difficulty", ""),
            "body_snip": (body_text[:120] or "").lower(),
        })
    return out


def pick_deck(mode: str, n: int = 6) -> List[Dict[str, Any]]:
    import random
    decks = load_all_cards()
    if mode=="discernment": pool = list(decks["discernment"])
    elif mode=="usage": pool = list(decks["usage"])
    else:
        d = list(decks["discernment"]); u = list(decks["usage"])
        random.shuffle(d); random.shuffle(u)
        pool = []
        for a,b in zip(d,u):
            pool.append(a); pool.append(b)
        longer = d if len(d)>len(u) else u
        pool.extend(longer[min(len(d),len(u)):])
    if mode!="mixed": random.shuffle(pool)
    pool = pool[:n]
    do = {"easy":0,"medium":1,"hard":2}
    pool.sort(key=lambda c: do.get(c.get("difficulty","easy"),1))
    return pool