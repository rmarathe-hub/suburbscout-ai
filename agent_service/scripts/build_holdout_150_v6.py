#!/usr/bin/env python3
"""Generate app/evals/holdout_150_v6_prompts.json — Holdout Set #6."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT / "scripts"))

from estimate_holdout_v6 import CASES  # noqa: E402

OUT = SERVICE_ROOT / "app" / "evals" / "holdout_150_v6_prompts.json"

LABELS = {
    "A_lookup": "A. Lookup / single-town facts",
    "B_membership": "B. Membership / scope / aliases",
    "C_typo": "C. Typos / fuzzy town names",
    "D_compare": "D. Natural comparison questions",
    "E_budget": "E. Budget / affordability constraints",
    "F_commute": "F. Commute / distance constraints",
    "G_coastal": "G. Coastal / region filters",
    "H_semantic": "H. Semantic / vibe prompts",
    "I_inverted": "I. Inverted / tradeoff-heavy prompts",
}


def main() -> None:
    counters: dict[str, int] = {}
    cases = []
    for cat, intent, prompt in CASES:
        counters[cat] = counters.get(cat, 0) + 1
        cases.append({
            "id": f"{cat}_{counters[cat]:02d}",
            "category": cat,
            "category_label": LABELS[cat],
            "expected_intent": intent,
            "prompt": prompt,
        })
    payload = {
        "description": "Holdout Set #6 — fresh 150 prompts (sixth phrasing variant)",
        "prompt_count": len(cases),
        "cases": cases,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {OUT}")


if __name__ == "__main__":
    main()
