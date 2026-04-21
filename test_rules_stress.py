"""
Stress test: feed many realistic answers into each problem-type scorer
across synthesized cards matching the real schema, then print a tier
distribution so we can see if any tier is starved or over-represented.

Run with:  python3 test_rules_stress.py
"""
from cards_loader import _normalize_card
from rules import check_answer

# Synthesize one card per problem type using realistic field shapes
# pulled from the real JSON files provided in the documents.

PERSPECTIVE_CARDS = [
    {
        "card_id": "P1", "category":"discernment", "problem_type":"perspective_lens_audit", "difficulty":"easy",
        "front":{"title":"Orbital Relics","card_text":["Glittering stardust clouds orbit Earth, beautiful relics of our greatest space adventures.","Jagged metal shards zip through the void, threatening to crush our newest satellites."]},
        "back":{"verdict":"Awe vs. Danger Lens","scoring_anchors":{"3_pts":"Identified relic vs. shard contrast.","7_pts":"Detected 'adventure' vs. 'threat' framing.","10_pts":"Check for 'Space Junk' vs 'Space Heritage' terminology."},"reality_anchor":"NASA orbital debris"},
        "teacher_notes":{"deep_insight":"Science reporting picks between explorer's lens and safety lens.","habit":"When you see something called a 'relic,' ask if it's trash.","references":[]}
    },
    {
        "card_id":"P2","category":"discernment","problem_type":"perspective_lens_audit","difficulty":"easy",
        "front":{"title":"Clean Wind","card_text":["Elegant white sails catch the breeze to light up homes without any smoke.","Steel towers spin heavy blades, casting shadows and blocking the mountain view."]},
        "back":{"verdict":"Function vs. Aesthetics Audit","scoring_anchors":{"3_pts":"Note 'sails' vs. 'steel towers.'","7_pts":"Analyze 'clean' vs. 'view-blocking' framing.","10_pts":"Identify benefit for 'city' vs. cost for 'local'."},"reality_anchor":"Wind turbine efficiency vs visual impact"},
        "teacher_notes":{"deep_insight":"The 'Green' narrative and the 'Local' narrative.","habit":"Search what the neighbors think.","references":[]}
    },
]
AFFECTIVE_CARDS = [
    {
        "card_id":"A1","category":"discernment","problem_type":"affective_highjack","difficulty":"easy",
        "front":{"title":"ULTRA-GUM WILL EXPLODE!","card_text":["A scary rumor is spreading! Kids who chew Ultra-Gum might have it POP in their mouths."]},
        "back":{"verdict":"Playground Panic","scoring_anchors":{"3_pts":"The news is spreading fear and surprise.","7_pts":"The outcome could be kids wasting their candy.","10_pts":"The intention behind the rumor is to cause chaos."},"reality_anchor":"silly rumors"},
        "teacher_notes":{"deep_insight":"Silly stories feel real in the moment.","habit":"Ask 'Is that even possible?'","references":[]}
    },
    {
        "card_id":"A2","category":"discernment","problem_type":"affective_highjack","difficulty":"medium",
        "front":{"title":"LOCAL WATER SUPPLY TAINTED","card_text":["URGENT: Traces of toxic chemical X found in city reservoir! Do NOT drink tap water until further notice."]},
        "back":{"verdict":"Panic Fuel","scoring_anchors":{"3_pts":"The news is spreading immediate terror.","7_pts":"The outcome could be dangerous stockpiling and shortages.","10_pts":"The intention behind the alert is to create public distrust."},"reality_anchor":"water panic"},
        "teacher_notes":{"deep_insight":"Leverages need for safety.","habit":"Wait for official alerts.","references":[]}
    },
]
BIAS_CARDS = [
    {
        "card_id":"B1","category":"usage","problem_type":"bias_inverter","difficulty":"easy",
        "front":{"title":"Mascot Remix","card_text":["The mascot should be picked by teachers because they know what looks respectable."]},
        "back":{"verdict":"Add student voice","scoring_anchors":{"suggested_prompt":"Can you rewrite this from students' view too? Show what teachers care about, what kids care about, and make the choice fair."},"reality_anchor":"school mascot"},
        "teacher_notes":{"deep_insight":"Compares two groups with different goals.","habit":"Ask whose choice it is.","references":[]}
    },
    {
        "card_id":"B2","category":"usage","problem_type":"bias_inverter","difficulty":"medium",
        "front":{"title":"Robot Jobs Lens","card_text":["Automation is good because efficiency matters most, and job losses are part of progress."]},
        "back":{"verdict":"Expose the tradeoff","scoring_anchors":{"suggested_prompt":"Rewrite this from worker and community perspectives too. Compare efficiency with retraining, transition costs, and who absorbs the downside."},"reality_anchor":"automation"},
        "teacher_notes":{"deep_insight":"Economic answers hide value choices.","habit":"Ask who benefits, who pays, and when.","references":[]}
    },
]
DECOMP_CARDS = [
    {
        "card_id":"D1","category":"usage","problem_type":"task_decomposition_map","difficulty":"easy",
        "front":{"title":"Volcano Quest","card_text":["Create a volcano fair project in one week."]},
        "back":{"verdict":"Break it down","scoring_anchors":{"suggested_prompt":"1) Pick a focused question. 2) Make a schedule. 3) Plan the experiment. 4) Draft board sections. 5) Review with a checklist."},"reality_anchor":"science fair"},
        "teacher_notes":{"deep_insight":"Sequencing prevents messy output.","habit":"Plan, build, check, revise, package.","references":[]}
    },
    {
        "card_id":"D2","category":"usage","problem_type":"task_decomposition_map","difficulty":"hard",
        "front":{"title":"Phone Ban Brief","card_text":["Draft a balanced school phone-ban brief: stakeholders, evidence questions, tradeoffs, recommendations, summary."]},
        "back":{"verdict":"Design the workflow","scoring_anchors":{"suggested_prompt":"1) Map stakeholders. 2) Generate evidence questions. 3) Compare benefits and risks. 4) Draft options. 5) Review for balance and summarize."},"reality_anchor":"phone ban"},
        "teacher_notes":{"deep_insight":"High-stakes writing needs process.","habit":"Map stakeholders before recommendations.","references":[]}
    },
]

ALL_CARDS = [
    _normalize_card(c, "discernment") for c in PERSPECTIVE_CARDS + AFFECTIVE_CARDS
] + [
    _normalize_card(c, "usage") for c in BIAS_CARDS + DECOMP_CARDS
]

# Generic test answers per problem type. Each list goes from strong -> silent.
ANSWER_BANK = {
    "perspective_lens_audit": [
        "This uses two different lenses, one celebrating the relics and the other warning about the shards, aimed at different audiences.",
        "The first is an adventure frame and the second is a threat frame with very different words.",
        "One side uses nice words and the other side uses scary words.",
        "The clouds are pretty.",
        "",
    ],
    "affective_highjack": [
        "The post is trying to stir panic so it gets clicks and ad money from attention.",
        "It wants us to share and hoard and maybe buy water.",
        "This feels scary and makes me worried.",
        "Water is wet.",
        "",
    ],
    "bias_inverter": [
        "I'd rewrite the answer from a worker perspective too so we can compare efficiency with retraining and community cost.",
        "Maybe also ask who loses out.",
        "Ask another side.",
        "Robots are cool.",
        "",
    ],
    "task_decomposition_map": [
        "First map stakeholders, second ask evidence questions, third compare risks, fourth draft options, finally review.",
        "Break it into a plan and then draft it in steps.",
        "Make a plan.",
        "Phones.",
        "",
    ],
}

from collections import Counter
print(f"{'card':6s} {'ptype':26s} {'answer':40s} score  tier")
print("-" * 90)
totals = Counter()
for card in ALL_CARDS:
    for ans in ANSWER_BANK[card["problem_type"]]:
        r = check_answer(card, ans)
        disp = ans[:38] + ("..." if len(ans) > 38 else "")
        print(f"{card['id']:6s} {card['problem_type']:26s} {disp:40s} {r['score']:3d}   {r['tier']}")
        totals[r["tier"]] += 1
    print()

print("=" * 90)
print("Tier distribution across realistic answer bank:")
for tier in ["deep", "mid", "surface", "off", "silent"]:
    print(f"  {tier:8s} {totals[tier]}")