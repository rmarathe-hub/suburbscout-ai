"""Aggregate confusion matrices for query-agent E2E eval rows."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def build_confusion_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    expected_to_first_op: Counter[str] = Counter()
    semantic_failures: Counter[str] = Counter()
    typo_failures: Counter[str] = Counter()
    membership_failures: Counter[str] = Counter()
    trust_failures: Counter[str] = Counter()

    for row in rows:
        if row.get("passed"):
            continue
        cat = row.get("category", "?")
        ops = row.get("plan_ops") or []
        first_op = ops[0] if ops else "(none)"
        expected_to_first_op[f"{cat} → {first_op}"] += 1

        for reason in row.get("failure_reasons") or []:
            r = str(reason)
            if cat == "semantic" or "semantic" in r.lower():
                if "missing use_semantic" in r:
                    semantic_failures["rank_missing_semantic_candidates"] += 1
                elif "semantic_search" in r:
                    semantic_failures["missing_semantic_search_op"] += 1
                elif "hallucination" in r:
                    semantic_failures["answer_hallucination"] += 1
                else:
                    semantic_failures[r[:80]] += 1
            elif cat in ("typo", "membership_typo") or cat == "membership":
                typo_failures[r[:80]] += 1
            elif "trust_gate" in r:
                trust_failures[r[:80]] += 1
            elif cat == "membership":
                membership_failures[r[:80]] += 1

    return {
        "expected_category_to_actual_first_op": dict(
            expected_to_first_op.most_common(30)
        ),
        "semantic_failures_by_type": dict(semantic_failures.most_common(20)),
        "typo_failures_by_type": dict(typo_failures.most_common(20)),
        "membership_failures_by_type": dict(membership_failures.most_common(20)),
        "trust_gate_failures_by_type": dict(trust_failures.most_common(20)),
    }
