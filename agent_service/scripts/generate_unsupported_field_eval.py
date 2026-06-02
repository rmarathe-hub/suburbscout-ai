#!/usr/bin/env python3
"""Generate app/evals/unsupported_field_eval.json (100+ prompts)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

OUT = SERVICE_ROOT / "app" / "evals" / "unsupported_field_eval.json"

# (category, prompt template with {town})
TEMPLATES: dict[str, list[str]] = {
    "lifestyle": [
        "Is {town} walkable?",
        "Does {town} have good restaurants?",
        "Is {town} touristy?",
        "Is {town} snobby?",
        "Is {town} sketchy?",
        "Is {town} urban?",
        "Is {town} boring?",
        "Does {town} have a real downtown?",
        "Is {town} good for nightlife?",
        "Is {town} rural or suburban?",
        "Is {town} elitist?",
        "Is {town} tourist-heavy?",
        "Is {town} pedestrian-friendly?",
        "Does {town} have a lively town center?",
        "Is {town} good for young professionals?",
    ],
    "transit": [
        "Is {town} good for public transit?",
        "Does {town} have easy MBTA access?",
        "Is {town} car-dependent?",
        "Can I take the train from {town}?",
        "Does {town} have commuter rail access in your data?",
        "Is {town} good without a car?",
        "Does {town} have subway access?",
        "Is {town} bad for transit?",
        "How is parking in {town}?",
        "Is {town} good for bus access?",
        "Does {town} have rush hour traffic?",
        "Is {town} good for bike commute?",
    ],
    "demographics": [
        "Is {town} diverse?",
        "Does {town} have a big Indian population?",
        "Is {town} liberal?",
        "Is {town} conservative?",
        "Is {town} mostly immigrant?",
        "Does {town} have a large Asian population?",
        "Is {town} low-income?",
        "Is {town} highly educated?",
        "Does {town} have many young families?",
        "Is {town} religiously diverse?",
        "Is {town} mostly college-educated?",
        "Does {town} have a large Latino population?",
    ],
    "risk_environment": [
        "Is {town} mountainous?",
        "Is {town} at flood risk?",
        "Does {town} have coastal flooding risk?",
        "Is {town} polluted?",
        "Is {town} noisy because of highways?",
        "Is {town} hilly?",
        "Is {town} forested?",
        "Is {town} vulnerable to sea-level rise?",
        "Does {town} have bad air quality?",
        "Is {town} risky for storms?",
        "Does {town} have wetland conservation land?",
        "Is {town} flat or hilly?",
    ],
    "live_market": [
        "Are there homes for sale in {town} right now?",
        "Is {town} appreciating fast?",
        "Will {town} home values go up?",
        "What are current rents in {town}?",
        "Is {town}'s crime rate still current?",
        "Are there bidding wars in {town}?",
        "Is {town} a good investment?",
        "Are prices dropping in {town}?",
        "How many houses are on the market in {town}?",
        "What is today's market like in {town}?",
        "Are there Zillow listings for {town} now?",
        "Is {town}'s home price forecast strong?",
    ],
    "neighborhood": [
        "What is the best neighborhood in {town}?",
        "Which part of {town} is safest?",
        "Are schools different by neighborhood in {town}?",
        "Is downtown {town} safer than the outskirts?",
        "What are the best streets in {town}?",
        "Does {town} have dangerous blocks?",
        "Which part of {town} should I avoid?",
        "What elementary school zone is best in {town}?",
        "Is north {town} better than south {town}?",
        "Does {town} have zip-code-level data?",
    ],
    "school_detail": [
        "Which elementary school in {town} is best?",
        "Does {town} have good special education?",
        "How are AP classes in {town}?",
        "Does {town} have good school sports?",
        "Is there bullying in {town} schools?",
        "Which school zone in {town} is best?",
        "Are there good private schools near {town}?",
        "Does {town} have good daycare options?",
        "What is the class size in {town}?",
        "Does {town} have good school buses?",
    ],
    "safety_granular": [
        "Is downtown {town} safe at night?",
        "Are there car break-ins in {town}?",
        "Is {town} safe to walk at night?",
        "Does {town} have recent crime spikes?",
        "Is there gang activity in {town}?",
        "Are there unsafe neighborhoods in {town}?",
        "How fast is police response in {town}?",
        "Is {town} mall area safe at night?",
        "Does {town} have package theft?",
        "Is {town} safer now than last year?",
    ],
    "utilities": [
        "Does {town} have fiber internet?",
        "Is cell service good in {town}?",
        "Does {town} get power outages?",
        "Are roads bad in {town}?",
        "Does {town} have septic issues?",
        "How is snow plowing in {town}?",
        "Is {town} good for town services?",
        "Does {town} have sewer problems?",
        "Are building permits easy in {town}?",
        "Does {town} have bad potholes?",
    ],
    "taxes": [
        "What are property taxes in {town}?",
        "Is {town} expensive for taxes?",
        "Does {town} have high water bills?",
        "Does {town} pass overrides?",
        "Are {town} town fees high?",
        "What is {town}'s exact tax rate?",
        "Does {town} have municipal debt?",
        "Are trash fees included in {town}?",
        "Does {town} have HOA-heavy neighborhoods?",
        "Is {town} cheap after taxes?",
    ],
    "healthcare": [
        "Does {town} have good hospitals nearby?",
        "Is {town} good for pediatricians?",
        "Is {town} close to urgent care?",
        "Does {town} have senior services?",
        "Are there good doctors in {town}?",
        "Is {town} close to a hospital?",
        "Does {town} have pharmacies nearby?",
        "How is ambulance access in {town}?",
        "Is {town} good for healthcare?",
        "Are there mental health services in {town}?",
    ],
    "jobs": [
        "Are there tech jobs near {town}?",
        "Is {town} good for office jobs?",
        "Does {town} have local employment?",
        "Is {town} good for remote workers?",
        "Is {town} close to biotech jobs?",
        "Are there major employers in {town}?",
        "Does {town} have job growth?",
        "Is {town} good for local work?",
        "How is unemployment in {town}?",
        "Is {town} good for commuting to Cambridge?",
    ],
    "recreation": [
        "Does {town} have good parks?",
        "Is {town} good for hiking?",
        "Does {town} have beaches?",
        "Are there lakes in {town}?",
        "Does {town} have dog parks?",
        "Is {town} good for boating?",
        "Does {town} have good gyms?",
        "Are there playgrounds in {town}?",
        "Is {town} good for outdoor recreation?",
        "Does {town} have trails?",
    ],
    "food_culture": [
        "Does {town} have Indian grocery stores?",
        "Are there temples near {town}?",
        "Does {town} have Asian markets?",
        "Does {town} have good restaurants?",
        "Is {town} good for Indian food?",
        "Does {town} have cultural events?",
        "Are there halal restaurants in {town}?",
        "Does {town} have farmers markets?",
        "Does {town} have a good library?",
        "Is {town} good for vegetarian food?",
    ],
    "legal_zoning": [
        "Does {town} allow ADUs?",
        "Can I rent out a basement in {town}?",
        "Are short-term rentals allowed in {town}?",
        "Does {town} have strict zoning?",
        "Are there tenant protections in {town}?",
        "Does {town} allow multifamily housing?",
        "Can I build an addition in {town}?",
        "Are school enrollment rules strict in {town}?",
        "Does {town} allow accessory apartments?",
        "Are there rental restrictions in {town}?",
    ],
}

TOWNS = [
    "Shrewsbury", "Newton", "Concord", "Salem", "Lynn", "Brookline", "Westford",
    "Framingham", "Quincy", "Acton", "Wellesley", "Plymouth", "Burlington",
    "Chelsea", "Peabody", "Worcester", "Lexington", "Waltham", "Needham",
    "Beverly", "Hingham", "Marblehead", "Natick", "Arlington", "Somerville",
]

# Supported-field controls (should NOT route unsupported_field)
CONTROLS = [
    {"id": "ctrl_price", "category": "control_supported", "expected_intent": "lookup_single_town", "unsupported_field": False, "prompt": "What is Newton's home price in your data?"},
    {"id": "ctrl_commute", "category": "control_supported", "expected_intent": "lookup_single_town", "unsupported_field": False, "prompt": "How far is Shrewsbury from Boston?"},
    {"id": "ctrl_safety", "category": "control_supported", "expected_intent": "lookup_single_town", "unsupported_field": False, "prompt": "Is Salem safe?"},
    {"id": "ctrl_school", "category": "control_supported", "expected_intent": "lookup_single_town", "unsupported_field": False, "prompt": "What is Acton's school score?"},
    {"id": "ctrl_coastal", "category": "control_supported", "expected_intent": "lookup_single_town", "unsupported_field": False, "prompt": "Is Marblehead coastal in your data?"},
    {"id": "ctrl_complete", "category": "control_supported", "expected_intent": "lookup_single_town", "unsupported_field": False, "prompt": "Is Westford partial-data or full-data?"},
]


def main() -> None:
    cases = []
    counters: dict[str, int] = {}
    town_idx = 0
    for category, templates in TEMPLATES.items():
        for template in templates:
            town = TOWNS[town_idx % len(TOWNS)]
            town_idx += 1
            counters[category] = counters.get(category, 0) + 1
            cases.append({
                "id": f"{category}_{counters[category]:02d}",
                "category": category,
                "expected_intent": "lookup_single_town",
                "unsupported_field": True,
                "prompt": template.format(town=town),
            })
    cases.extend(CONTROLS)
    payload = {
        "description": "Unsupported-field eval — single town + out-of-schema attribute",
        "prompt_count": len(cases),
        "by_category": {k: sum(1 for c in cases if c["category"] == k) for k in sorted({c["category"] for c in cases})},
        "cases": cases,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {OUT}")
    print("By category:", payload["by_category"])


if __name__ == "__main__":
    main()
