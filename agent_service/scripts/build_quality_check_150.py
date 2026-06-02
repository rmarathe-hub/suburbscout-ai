#!/usr/bin/env python3
"""Generate app/evals/quality_check_150_prompts.json from the curated prompt list."""

from __future__ import annotations

import json
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
OUT = SERVICE_ROOT / "app" / "evals" / "quality_check_150_prompts.json"

PROMPTS: dict[str, list[str]] = {
    "A_lookup": [
        "What is the commute from Gardner to Boston?",
        "How long is the commute from Shrewsbury to Boston?",
        "What is the commute time for Walpole?",
        "Give me the commute and distance for Acton.",
        "What is the home price for Burlington in your dataset?",
        "What is the crime rate in Shrewsbury?",
        "Is Walpole safer than Shrewsbury?",
        "What is the school score for Sharon?",
        "Tell me the safety score and crime rate for Framingham.",
        "What data do you have for Westford?",
        "Is Gardner in your dataset?",
        "Is Charlton in your dataset?",
        "Is Westborough in the town list?",
        "What fields are missing for Freetown?",
        "Why is Worcester partial data?",
        "What is the data quality tier for Grafton?",
        "What region is Marblehead in?",
        "What county is Lexington in?",
        "What is the affordability score for Newton?",
        "Give me a quick factual summary of Burlington.",
    ],
    "B_typo": [
        "Compare Shrevsbury and Walpole.",
        "What is the commute from Worecster?",
        "Is Westboro in your dataset?",
        "Compare Lexinton and Acton.",
        "How safe is Framingam?",
        "Commute for Marlbrough.",
        "Compare Newburyport and Newbury.",
        "Is Manchester by the Sea coastal?",
        "Tell me about Manchester-by-the-sea.",
        "Compare North Andover and Andover.",
        "Is Brookline different from Brooklyn?",
        "Compare Medford and Milford.",
        "What is the school score for Needham MA?",
        "Is Haverhill in the dataset?",
        "What is the commute from Chelsae?",
    ],
    "C_compare": [
        "Compare Acton and Framingham.",
        "Compare Sharon and Westford.",
        "Compare Walpole and Shrewsbury.",
        "Compare Burlington and Waltham.",
        "Compare Cambridge and Somerville.",
        "Compare Newton and Wellesley.",
        "Compare Lexington and Winchester.",
        "Compare Salem and Beverly.",
        "Compare Marblehead and Swampscott.",
        "Compare Lynn and Revere.",
        "Compare Worcester and Shrewsbury.",
        "Compare Grafton and Westborough.",
        "Compare Quincy and Milton.",
        "Compare Concord and Acton.",
        "Compare Chelsea and Brookline.",
        "Which is safer, Burlington or Framingham?",
        "Which has better schools, Sharon or Westford?",
        "Which is cheaper, Newton or Waltham?",
        "Which has a shorter commute, Arlington or Lexington?",
        "Which is better for a family, Acton or Worcester?",
    ],
    "D_recommend_basic": [
        "Find me a safe suburb under $900k with good schools.",
        "Recommend towns under $750k with strong schools.",
        "Best family-friendly suburbs under $850k.",
        "Affordable suburbs with decent schools and low crime.",
        "Good suburbs for a family with a $700k budget.",
        "Best towns if I care most about safety.",
        "Best towns if I care most about schools.",
        "Best towns if affordability matters more than commute.",
        "Recommend places with good schools but not crazy expensive.",
        "Find me balanced suburbs with safety, schools, and affordability.",
        "Give me top 5 towns under $800k.",
        "Give me top 10 suburbs for families.",
        "Find safe towns with lower home prices.",
        "Good towns for first-time homebuyers near Boston.",
        "Best value towns with decent commute and good safety.",
    ],
    "E_budget_hard": [
        "Find towns under $600k with good schools.",
        "Find towns under $500k with low crime.",
        "Best suburbs under $650k and under 40 minutes to Boston.",
        "Give me towns under $900k but exclude anything with missing price data.",
        "Recommend towns under $750k, and do not include partial housing data.",
        "Find me the best towns under $700k even if schools are only average.",
        "What are the tradeoffs for towns under $550k?",
        "Find me towns under $1 million with elite schools.",
        "Find me affordable towns under $600k with decent safety.",
        "I only have $500k. Be honest about what I can get.",
        "Show me the best options under $400k.",
        "Find towns under $800k and close to Boston.",
        "Find towns under $800k but prioritize school over commute.",
        "Find towns under $700k and rank by safety.",
        "Find towns under $650k that are not too far from Boston.",
    ],
    "F_commute_hard": [
        "Find suburbs under 30 minutes to Boston with good safety.",
        "Safe coastal suburbs under 30 minutes to Boston.",
        "Best towns within 45 minutes of Boston.",
        "Best towns over 45 minutes away from Boston.",
        "I want to be at least 50 minutes away from Boston.",
        "Find towns between 30 and 45 minutes from Boston.",
        "I don't care about commute; find the best schools under $900k.",
        "I care a lot about commute and safety, less about schools.",
        "Find affordable towns with a commute under 35 minutes.",
        "Find towns with long commute but excellent schools.",
        "Which towns are far from Boston but still strong for families?",
        "Give me towns close to Boston but not extremely expensive.",
        "Find suburbs under 25 minutes to Boston and under $900k.",
        "What are the safest towns within 40 minutes?",
        "Find towns farther than 45 minutes but under $700k.",
    ],
    "G_coastal_region": [
        "Find me a coastal suburb under $900k.",
        "Find a safe coastal suburb with good schools.",
        "Quiet coastal town with strong schools.",
        "Coastal town under $800k with decent commute.",
        "North Shore family-friendly suburb with strong schools.",
        "South Shore suburb under $850k with good safety.",
        "Find a North Shore town under $750k.",
        "Find a coastal town under $500k with low crime.",
        "Find me coastal towns only; do not include inland towns.",
        "Is Reading coastal?",
        "Is Boxford coastal?",
        "Is Marblehead coastal?",
        "Find a coastal town like Marblehead but cheaper.",
        "Find a North Shore suburb with a walkable feel.",
        "Find South Shore towns with good schools and lower prices.",
    ],
    "H_semantic_vibe": [
        "I want somewhere quiet, family-oriented, and not too urban.",
        "Find me a town that feels like Acton but cheaper.",
        "Find me something like Lexington but under $750k.",
        "I want a town like Wellesley but less expensive.",
        "Find somewhere like Cambridge but safer and cheaper.",
        "I want a walkable downtown feel under $800k.",
        "Recommend a suburb with a charming old-town feel.",
        "I want a quiet North Shore vibe with good schools.",
        "Find me a suburb with a coastal feel but not too expensive.",
        "I want a town that feels educated, safe, and family-focused.",
        "Find a suburb that is not too dense but still has amenities.",
        "Give me towns with a suburban but not rural feel.",
        "Find towns similar to Sharon but with a shorter commute.",
        "Find towns similar to Burlington but safer.",
        "Find towns like Newton but cheaper and less urban.",
    ],
    "I_inverted": [
        "Find me a high-crime suburb that is affordable and close to Boston.",
        "Which towns have worse safety but cheaper prices?",
        "Show me cheaper towns even if crime is higher.",
        "I don't care about schools; I only care about price and commute.",
        "I don't care about safety; find the cheapest towns close to Boston.",
        "Find towns with average schools but excellent commute.",
        "Find towns with weak schools but low prices.",
        "Find towns with high crime rates, but explain why someone might still consider them.",
        "Show me risky but affordable options near Boston.",
        "Find towns where affordability is the main upside and safety is the downside.",
    ],
    "J_limitations": [
        "Compare Charlton and Shrewsbury.",
        "What is the commute from Charlton to Boston?",
        "Find me live Zillow prices for Acton today.",
        "Give me the 2026 crime rate for Sharon.",
        "Do you have live Redfin data for Wellesley?",
        "I work in Westborough; rank towns by commute to Westborough.",
        "I commute to Burlington, not Boston. What should I consider?",
        "Find coastal towns under $400k with elite schools and low crime.",
        "Find a town under $500k, under 20 minutes to Boston, coastal, with elite schools.",
        "Recommend towns outside your 200-town list if they are better.",
    ],
}

CATEGORY_LABELS = {
    "A_lookup": "A. Direct single-town factual lookup",
    "B_typo": "B. Typo and town normalization",
    "C_compare": "C. Two-town comparison",
    "D_recommend_basic": "D. Basic recommendation prompts",
    "E_budget_hard": "E. Budget hard-constraint tests",
    "F_commute_hard": "F. Commute hard-constraint tests",
    "G_coastal_region": "G. Coastal and region hard-filter tests",
    "H_semantic_vibe": "H. Semantic / vibe prompts",
    "I_inverted": "I. Inverted / unusual preference tests",
    "J_limitations": "J. Unknown-town, limitation, and no-match tests",
}


def main() -> None:
    cases: list[dict] = []
    for category, prompts in PROMPTS.items():
        for idx, prompt in enumerate(prompts, start=1):
            cases.append({
                "id": f"{category}_{idx:02d}",
                "category": category,
                "category_label": CATEGORY_LABELS[category],
                "prompt": prompt,
            })

    payload = {
        "version": "quality_check_150",
        "description": "150 SuburbScout manual quality-test prompts (response review)",
        "total_cases": len(cases),
        "cases": cases,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases)} prompts to {OUT}")


if __name__ == "__main__":
    main()
