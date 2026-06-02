#!/usr/bin/env python3
"""Quick smoke test for ranking without LLM."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.ranking import parse_preferences_from_query, rank_suburbs  # noqa: E402


def main() -> None:
    queries = [
        "Find me a safe Boston suburb under 900k with good schools.",
        "I want an affordable suburb with strong schools and decent commute.",
        "Which towns are best for a family under 750k?",
    ]
    for q in queries:
        prefs = parse_preferences_from_query(q)
        results = rank_suburbs(prefs, top_n=5)
        print("\n" + "=" * 60)
        print("Query:", q)
        print("Preferences:", prefs.model_dump(exclude_none=True))
        print("Top matches:")
        for r in results:
            print(f"  #{r['rank']} {r['name']} — score {r['score']}")
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
