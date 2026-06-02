"""E2E expectation blocks for query-agent holdout evals."""

from __future__ import annotations

import re
from typing import Any

from app.query_patterns import is_dataset_membership_query


def _is_compare_prompt(prompt: str) -> bool:
    lower = prompt.lower()
    if re.search(r"\b(?:versus|vs\.?)\b", lower):
        return True
    if re.search(r"\bcompare\b.+\b(?:and|on|for)\b", lower):
        return True
    if re.search(r"\bwhich (?:is|has|town)\b.+\b(?:or|than)\b", lower):
        return True
    return False


def build_e2e_expect(case: dict[str, Any]) -> dict[str, Any]:
    """Build expect dict from category + prompt heuristics."""
    cat = case.get("category", "")
    prompt = case.get("prompt", "")
    expect: dict[str, Any] = {
        "forbid_hallucinated_facts": True,
        "forbid_wrong_commute_rank": True,
    }

    if cat == "unsupported":
        expect["execution_status_in"] = ["blocked", "out_of_scope"]
        expect["expect_used_answer_llm"] = False
        return expect

    if cat == "pullup_lookup":
        expect["plan_ops_contains"] = ["lookup"]
        expect["execution_status_in"] = ["ok", "partial", "not_found"]
        return expect

    if cat == "inverted_crime":
        expect["plan_ops_contains"] = ["rank"]
        expect["execution_status_in"] = ["ok", "partial", "no_rows", "blocked"]
        return expect

    if cat == "neighborhood":
        expect["execution_status_in"] = ["blocked", "out_of_scope"]
        expect["expect_used_answer_llm"] = False
        return expect

    if cat == "semantic_lifestyle":
        expect["plan_ops_contains"] = ["semantic_search"]
        expect["require_semantic_rank_limited"] = True
        expect["execution_status_in"] = ["ok", "partial", "no_rows"]
        return expect

    if cat in ("membership", "membership_typo") or is_dataset_membership_query(prompt):
        expect["plan_ops_contains"] = ["membership"]
        expect["plan_ops_max"] = 1
        expect["execution_status_in"] = ["ok", "not_found", "out_of_scope", "blocked"]
        return expect

    if cat == "semantic" or (
        re.search(r"\b(?:vibe|feel|similar to|[- ]like)\b", prompt, re.I)
        and not is_dataset_membership_query(prompt)
    ):
        expect["plan_ops_contains"] = ["semantic_search"]
        expect["require_semantic_rank_limited"] = True
        expect["execution_status_in"] = ["ok", "partial", "no_rows"]
        return expect

    if cat == "compare" or (cat == "typo" and _is_compare_prompt(prompt)):
        expect["plan_ops_contains"] = ["compare"]
        expect["execution_status_in"] = ["ok", "partial", "blocked"]
        return expect

    if cat == "lookup" or (cat == "typo" and not _is_compare_prompt(prompt)):
        expect["plan_ops_contains"] = ["lookup"]
        expect["execution_status_in"] = ["ok", "partial", "not_found"]
        return expect

    if cat in ("budget", "commute", "coastal", "inverted"):
        expect["plan_ops_contains_any"] = ["rank", "semantic_search"]
        expect["execution_status_in"] = ["ok", "partial", "no_rows", "blocked"]
        if cat == "coastal":
            expect["rank_requires_coastal"] = True
        return expect

    expect["execution_status_in"] = [
        "ok",
        "partial",
        "not_found",
        "no_rows",
        "blocked",
        "out_of_scope",
    ]
    return expect
