"""
Stress test for v3 rules engine.

Covers 2 cards per problem type and 6 realistic answers per card
(ranging from deep through silent) so we can see the tier distribution
and make sure v3's changes fixed the v2 problems:

  v2 complaints tested here:
    - "relic on one side, shard on the other" should NOT hit deep.
      (it didn't say LENS/FRAME/AUDIENCE — stays at surface/mid.)
    - "for scientists vs for ranchers" SHOULD reach deep on perspective.
      (v2 missed this because no "lens" word — v3 audience cue catches it.)
    - "terrified of the water" should hit surface on affective.
      (v2 missed "terrified" — v3 emotion family includes it.)
    - bias_inverter should actually produce some deeps.
"""

from cards_loader import _normalize_card
from rules import check_answer

PERSPECTIVE_CARDS = [
    {"card_id":"P1","category":"discernment","problem_type":"perspective_lens_audit","difficulty":"easy",
     "front":{"title":"Orbital Relics","card_text":["Glittering stardust clouds orbit Earth, beautiful relics of our greatest space adventures.","Jagged metal shards zip through the void, threatening to crush our newest satellites."]},
     "back":{"verdict":"Awe vs. Danger Lens","scoring_anchors":{"3_pts":"Identified relic vs. shard contrast.","7_pts":"Detected 'adventure' vs. 'threat' framing.","10_pts":"Check for 'Space Junk' vs 'Space Heritage' terminology."},"reality_anchor":"NASA orbital debris"},
     "teacher_notes":{"deep_insight":"Explorer's lens vs safety lens.","habit":"Ask if a 'relic' is trash.","references":[]}},
    {"card_id":"P11","category":"discernment","problem_type":"perspective_lens_audit","difficulty":"easy",
     "front":{"title":"Wolf Return","card_text":["Silver hunters rebalance the valley, and willow, beaver, and songbird life surges back.","Shadowy predators cross fence lines at dusk, leaving ranchers guarding calves through the night."]},
     "back":{"verdict":"Restoration vs. Threat","scoring_anchors":{"3_pts":"Spotted ecosystem healer vs. livestock danger.","7_pts":"Noted valley-wide gains vs. household losses.","10_pts":"Ask who benefits—and who pays."},"reality_anchor":"Yellowstone wolves"},
     "teacher_notes":{"deep_insight":"Ecosystem lens vs Livelihood lens.","habit":"Zoom out and zoom in.","references":[]}},
]

AFFECTIVE_CARDS = [
    {"card_id":"A14","category":"discernment","problem_type":"affective_highjack","difficulty":"easy",
     "front":{"title":"ULTRA-GUM WILL EXPLODE!","card_text":["A scary rumor is spreading! Kids who chew Ultra-Gum might have it POP in their mouths."]},
     "back":{"verdict":"Playground Panic","scoring_anchors":{"3_pts":"The news is spreading fear and surprise.","7_pts":"The outcome could be kids wasting their candy.","10_pts":"The intention behind the rumor is to cause chaos."},"reality_anchor":"silly rumors"},
     "teacher_notes":{"deep_insight":"Silly stories feel real in the moment.","habit":"Ask if it is possible.","references":[]}},
    {"card_id":"A19","category":"discernment","problem_type":"affective_highjack","difficulty":"medium",
     "front":{"title":"LOCAL WATER SUPPLY TAINTED","card_text":["URGENT: Traces of toxic chemical X found in city reservoir!"]},
     "back":{"verdict":"Panic Fuel","scoring_anchors":{"3_pts":"The news is spreading immediate terror.","7_pts":"The outcome could be dangerous stockpiling and shortages.","10_pts":"The intention behind the alert is to create public distrust."},"reality_anchor":"water panic"},
     "teacher_notes":{"deep_insight":"Leverages need for safety.","habit":"Wait for official alerts.","references":[]}},
]

BIAS_CARDS = [
    {"card_id":"B27","category":"usage","problem_type":"bias_inverter","difficulty":"easy",
     "front":{"title":"Mascot Remix","card_text":["The new school mascot should be picked by teachers because they know what looks serious and respectable."]},
     "back":{"verdict":"Add student voice","scoring_anchors":{"suggested_prompt":"Can you rewrite this from students' view too? Show what teachers care about, what kids care about, and make the final choice feel fair."},"reality_anchor":"school mascot"},
     "teacher_notes":{"deep_insight":"Compare two groups with different goals.","habit":"Ask whose choice it is.","references":[]}},
    {"card_id":"B35","category":"usage","problem_type":"bias_inverter","difficulty":"medium",
     "front":{"title":"Robot Jobs Lens","card_text":["Automation is good because efficiency matters most, and job losses are just part of progress."]},
     "back":{"verdict":"Expose the tradeoff","scoring_anchors":{"suggested_prompt":"Rewrite this from worker and community perspectives too. Compare efficiency with retraining, transition costs, and who absorbs the downside."},"reality_anchor":"automation workers"},
     "teacher_notes":{"deep_insight":"Economic answers hide value choices.","habit":"Ask who benefits, who pays.","references":[]}},
]

DECOMP_CARDS = [
    {"card_id":"D40","category":"usage","problem_type":"task_decomposition_map","difficulty":"easy",
     "front":{"title":"Volcano Quest","card_text":["Create a volcano fair project in one week: question, materials, experiment, display board, and short talk."]},
     "back":{"verdict":"Break it down","scoring_anchors":{"suggested_prompt":"1) Pick a focused question. 2) Make a schedule. 3) Plan the experiment. 4) Draft board sections. 5) Review with a checklist."},"reality_anchor":"science fair"},
     "teacher_notes":{"deep_insight":"Sequencing prevents messy output.","habit":"Plan, build, check, revise, package.","references":[]}},
    {"card_id":"D50","category":"usage","problem_type":"task_decomposition_map","difficulty":"hard",
     "front":{"title":"Phone Ban Brief","card_text":["Draft a balanced school phone-ban brief."]},
     "back":{"verdict":"Design the workflow","scoring_anchors":{"suggested_prompt":"1) Map stakeholders. 2) Generate evidence questions. 3) Compare benefits and risks. 4) Draft options. 5) Review for balance and summarize."},"reality_anchor":"phone ban"},
     "teacher_notes":{"deep_insight":"High-stakes writing needs process.","habit":"Map stakeholders before recommendations.","references":[]}},
]

ALL = (
    [_normalize_card(c, "discernment") for c in PERSPECTIVE_CARDS + AFFECTIVE_CARDS] +
    [_normalize_card(c, "usage") for c in BIAS_CARDS + DECOMP_CARDS]
)

# Six answers per problem type, from strongest to silent.
# Designed to test specific v2 failure modes.
ANSWERS = {
    "perspective_lens_audit": [
        # deep: explicit meta-awareness AND content engagement
        "These use two different lenses. One is an explorer frame, the other a safety frame, written for different audiences.",
        # deep by audience-cue path — v2 missed this, v3 should catch it
        "The first is aimed at scientists who care about history, the second is for ranchers worried about their cattle.",
        # mid: contrasting descriptors
        "One side uses pretty words like 'beautiful' and the other side uses scary words like 'threatening'.",
        # surface: bare restatement (v2 mistakenly promoted this to deep)
        "Relics on one side, shards on the other.",
        # off
        "Space is really cool and I want to be an astronaut.",
        # silent
        "",
    ],
    "affective_highjack": [
        # deep: motive named
        "This post is trying to stir panic so it gets clicks and ad money.",
        # deep: motive with different vocabulary
        "It's clickbait designed to manipulate people and harvest attention.",
        # mid: outcome-focused
        "It wants people to share it and to hoard water.",
        # surface: emotion only (v2 missed 'terrified' — v3 should catch it)
        "This makes me feel terrified and worried about our water.",
        # off
        "I drink lots of water every day.",
        # silent
        "",
    ],
    "bias_inverter": [
        # deep: strong reframe + audience cue
        "Rewrite this from a worker's perspective too, comparing efficiency with retraining costs.",
        # deep: different wording (v2 required content overlap — v3 relaxes)
        "Reframe the answer by asking who gets laid off and what they do next.",
        # mid: weak reframe with content
        "What about the people who lose their jobs?",
        # surface: vague hint
        "There might be another side.",
        # off
        "Robots are cool and useful.",
        # silent
        "",
    ],
    "task_decomposition_map": [
        # deep: plan + sequence + review
        "First map stakeholders, then list evidence questions, next compare risks, finally review and summarize.",
        # mid: sequence + enumeration
        "Step one plan the outline, step two draft it, step three finish.",
        # mid: plan + sequence
        "Start by outlining, then write the sections.",
        # surface: one signal only
        "Make a plan.",
        # off
        "Phones.",
        # silent
        "",
    ],
}

from collections import Counter

print(f"{'card':6s} {'ptype':26s} {'answer':56s} score tier")
print("-" * 108)
totals = Counter()
per_ptype = {}
for card in ALL:
    per_ptype.setdefault(card["problem_type"], Counter())
    for ans in ANSWERS[card["problem_type"]]:
        r = check_answer(card, ans)  # no llm_judge in offline test
        disp = ans[:54] + ("..." if len(ans) > 54 else "")
        print(f"{card['id']:6s} {card['problem_type']:26s} {disp:56s} {r['score']:3d}  {r['tier']}")
        totals[r["tier"]] += 1
        per_ptype[card["problem_type"]][r["tier"]] += 1
    print()

print("=" * 108)
print("Overall tier distribution:")
for tier in ["deep", "mid", "surface", "off", "silent"]:
    print(f"  {tier:8s} {totals[tier]}")
print()
print("Per-problem-type:")
for pt, c in per_ptype.items():
    print(f"  {pt}:")
    for tier in ["deep", "mid", "surface", "off", "silent"]:
        print(f"    {tier:8s} {c[tier]}")