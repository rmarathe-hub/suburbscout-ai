#!/usr/bin/env python3
"""Generate 100 planner-only eval cases with expected QueryPlan JSON fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

FIXTURES = SERVICE_ROOT / "tests" / "fixtures" / "planner_eval"
OUT_MANIFEST = SERVICE_ROOT / "app" / "evals" / "planner_eval_100.json"


def _case(
    case_id: str,
    category: str,
    prompt: str,
    plan: dict[str, Any],
    *,
    expect_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan_path = FIXTURES / f"{case_id}.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    expect: dict[str, Any] = {"ops": [op["op"] for op in plan["ops"]]}
    if expect_extra:
        expect.update(expect_extra)
    return {
        "id": case_id,
        "category": category,
        "prompt": prompt,
        "plan_file": f"tests/fixtures/planner_eval/{case_id}.json",
        "expect": expect,
    }


def build_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    # --- lookup (20) ---
    lookup_specs = [
        ("pl_lk_01", "Acton", "commute", "How long is the drive from Acton to Boston?"),
        ("pl_lk_02", "Newton", "price", "What is Newton's median home price in your data?"),
        ("pl_lk_03", "Maynard", "school", "Does Maynard have a school score saved?"),
        ("pl_lk_04", "Sharon", "safety", "What is Sharon's safety rating?"),
        ("pl_lk_05", "Gloucester", "coastal", "Is Gloucester marked as coastal?"),
        ("pl_lk_06", "Concord", "region", "What region is Concord in?"),
        ("pl_lk_07", "Framingham", "missing", "What fields are missing for Framingham?"),
        ("pl_lk_08", "Lexington", "tier", "Is Lexington full-data or partial?"),
        ("pl_lk_09", "Wellesley", "summary", "Give me a full summary for Wellesley."),
        ("pl_lk_10", "Brookline", "commute", "Commute time for Brookline to South Station?"),
        ("pl_lk_11", "Needham", "price", "How expensive is Needham?"),
        ("pl_lk_12", "Quincy", "safety", "Crime info for Quincy."),
        ("pl_lk_13", "Salem", "school", "School numbers for Salem."),
        ("pl_lk_14", "Burlington", "summary", "Pull up everything you know about Burlington."),
        ("pl_lk_15", "Natick", "commute", "How far is Natick from Boston?"),
        ("pl_lk_16", "Westford", "price", "Housing price for Westford."),
        ("pl_lk_17", "Hingham", "coastal", "Is Hingham coastal in your tags?"),
        ("pl_lk_18", "Reading", "safety", "Safety score for Reading."),
        ("pl_lk_19", "Melrose", "school", "What school metric do you have for Melrose?"),
        ("pl_lk_20", "Arlington", "commute", "Drive minutes from Arlington to Boston?"),
    ]
    for cid, town, field, prompt in lookup_specs:
        cases.append(
            _case(
                cid,
                "lookup",
                prompt,
                {"ops": [{"op": "lookup", "items": [{"town": town, "field": field}]}]},
                expect_extra={"lookup_items": [{"town": town, "field": field}]},
            )
        )

    # --- multi lookup (6) ---
    cases.append(
        _case(
            "pl_ml_01",
            "lookup",
            "What is commute from Maynard and housing cost in Newton?",
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [
                            {"town": "Maynard", "field": "commute"},
                            {"town": "Newton", "field": "price"},
                        ],
                    }
                ]
            },
            expect_extra={
                "lookup_items": [
                    {"town": "Maynard", "field": "commute"},
                    {"town": "Newton", "field": "price"},
                ],
            },
        )
    )
    cases.append(
        _case(
            "pl_ml_02",
            "lookup",
            "School score for Acton and safety for Concord.",
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [
                            {"town": "Acton", "field": "school"},
                            {"town": "Concord", "field": "safety"},
                        ],
                    }
                ]
            },
            expect_extra={
                "lookup_items": [
                    {"town": "Acton", "field": "school"},
                    {"town": "Concord", "field": "safety"},
                ],
            },
        )
    )

    # --- compare (14) ---
    compare_specs = [
        (
            "pl_cmp_01",
            ["Newton", "Needham"],
            ["latest_home_price"],
            "Compare Newton and Needham on price.",
        ),
        (
            "pl_cmp_02",
            ["Acton", "Concord"],
            ["drive_minutes_to_boston"],
            "Which is closer to Boston, Acton or Concord?",
        ),
        (
            "pl_cmp_03",
            ["Framingham", "Natick"],
            ["safety_score", "school_score"],
            "Framingham vs Natick for safety and schools.",
        ),
        (
            "pl_cmp_04",
            ["Lynn", "Revere"],
            None,
            "Compare Lynn and Revere.",
        ),
        (
            "pl_cmp_05",
            ["Lexington", "Winchester"],
            ["latest_home_price", "school_score"],
            "Lexington versus Winchester — price and schools.",
        ),
        (
            "pl_cmp_06",
            ["Rockport", "Gloucester"],
            ["is_coastal"],
            "Rockport and Gloucester coastal status.",
        ),
        (
            "pl_cmp_07",
            ["Brookline", "Newton"],
            ["safety_score"],
            "Compare crime in Brookline and Newton.",
        ),
        (
            "pl_cmp_08",
            ["Quincy", "Milton"],
            ["drive_minutes_to_boston"],
            "Quincy or Milton for a shorter Boston commute?",
        ),
        (
            "pl_cmp_09",
            ["Newton", "Needham", "Wellesley"],
            ["school_score"],
            "Compare Newton, Needham, and Wellesley on schools.",
        ),
        (
            "pl_cmp_10",
            ["Westford", "Sharon"],
            ["latest_home_price", "safety_score"],
            "Westford vs Sharon on price and safety.",
        ),
        (
            "pl_cmp_11",
            ["Cambridge", "Somerville"],
            ["latest_home_price"],
            "Cambridge vs Somerville on housing cost.",
        ),
        (
            "pl_cmp_12",
            ["Hingham", "Cohasset"],
            ["is_coastal", "latest_home_price"],
            "Compare Hingham and Cohasset.",
        ),
        (
            "pl_cmp_13",
            ["North Reading", "Reading"],
            ["school_score", "safety_score"],
            "North Reading versus Reading for schools and safety.",
        ),
        (
            "pl_cmp_14",
            ["Dedham", "Needham"],
            None,
            "Dedham or Needham — which is cheaper?",
        ),
    ]
    for cid, towns, cols, prompt in compare_specs:
        op: dict[str, Any] = {"op": "compare", "towns": towns}
        if cols:
            op["columns"] = cols
        expect: dict[str, Any] = {"compare_towns": towns}
        if cols:
            expect["compare_columns"] = cols
        cases.append(_case(cid, "compare", prompt, {"ops": [op]}, expect_extra=expect))

    # --- rank (16) ---
    rank_specs = [
        (
            "pl_rank_01",
            {"budget_max": 700000},
            "Towns under $700k with good schools.",
        ),
        (
            "pl_rank_02",
            {"max_commute_minutes": 45},
            "Suburbs within 45 minutes of Boston.",
        ),
        (
            "pl_rank_03",
            {"budget_max": 900000, "requires_coastal": True},
            "Affordable coastal towns under $900k.",
        ),
        (
            "pl_rank_04",
            {"exclude_towns": ["Sharon"]},
            "Best suburbs but not Sharon.",
        ),
        (
            "pl_rank_05",
            {"budget_max": 600000, "school_priority": "high"},
            "Cheap towns with strong schools.",
        ),
        (
            "pl_rank_06",
            {"max_commute_minutes": 35, "budget_max": 800000},
            "Under $800k and within 35 minutes of Boston.",
        ),
        (
            "pl_rank_07",
            {"safety_priority": "high"},
            "Safest suburbs in your dataset.",
        ),
        (
            "pl_rank_08",
            {"region_preference": "North Shore"},
            "Top North Shore towns.",
        ),
        (
            "pl_rank_09",
            {"budget_max": 750000, "commute_priority": "high"},
            "Affordable with a reasonable Boston commute.",
        ),
        (
            "pl_rank_10",
            {"affordability_priority": "high"},
            "Most affordable towns — top 5.",
            5,
        ),
        (
            "pl_rank_11",
            {"budget_max": 500000, "max_commute_minutes": 50},
            "Towns under $500k within 50 minutes of Boston.",
        ),
        (
            "pl_rank_12",
            {"requires_coastal": True},
            "Best coastal suburbs in the dataset.",
        ),
        (
            "pl_rank_13",
            {"budget_max": 850000, "safety_priority": "high"},
            "Safe suburbs under $850k.",
        ),
        (
            "pl_rank_14",
            {"county_preference": "Middlesex"},
            "Top Middlesex County towns.",
        ),
        (
            "pl_rank_15",
            {"min_commute_minutes": 20, "max_commute_minutes": 40},
            "Towns with a 20–40 minute Boston commute.",
        ),
        (
            "pl_rank_16",
            {
                "budget_max": 950000,
                "school_priority": "high",
                "commute_priority": "high",
            },
            "Good schools and commute under $950k.",
        ),
    ]
    for spec in rank_specs:
        if len(spec) == 4:
            cid, prefs, prompt, limit = spec
        else:
            cid, prefs, prompt = spec
            limit = 10
        op = {"op": "rank", "preferences": prefs, "limit": limit}
        cases.append(
            _case(
                cid,
                "rank",
                prompt,
                {"ops": [op]},
                expect_extra={"rank_preferences": prefs},
            )
        )

    # --- semantic (8) ---
    sem_specs = [
        ("pl_sem_01", "quiet family-friendly suburb near Boston"),
        ("pl_sem_02", "towns with a small-town New England feel"),
        ("pl_sem_03", "suburbs that feel suburban but not too remote"),
        ("pl_sem_04", "walkable downtown vibe near Boston"),
        ("pl_sem_05", "affordable starter-home suburbs"),
        ("pl_sem_06", "coastal community feel"),
        ("pl_sem_07", "good for young professionals commuting"),
        ("pl_sem_08", "sleepy residential neighborhoods"),
    ]
    for cid, q in sem_specs:
        cases.append(
            _case(
                cid,
                "semantic_search",
                f"Find suburbs that match: {q}",
                {"ops": [{"op": "semantic_search", "query_text": q, "top_k": 15}]},
            )
        )

    # --- semantic + rank (6) ---
    cases.append(
        _case(
            "pl_semrank_01",
            "semantic_rank",
            "Affordable family suburbs with a quiet vibe — show top matches.",
            {
                "ops": [
                    {
                        "op": "semantic_search",
                        "query_text": "quiet affordable family suburb",
                        "top_k": 15,
                    },
                    {
                        "op": "rank",
                        "preferences": {"budget_max": 800000},
                        "limit": 5,
                        "use_semantic_candidates": True,
                    },
                ]
            },
            expect_extra={
                "ops": ["semantic_search", "rank"],
                "use_semantic_candidates": True,
                "rank_preferences": {"budget_max": 800000},
            },
        )
    )
    for i, (budget,) in enumerate([(700000,), (900000,), (650000,), (550000,), (825000,)], start=2):
        cases.append(
            _case(
                f"pl_semrank_0{i}",
                "semantic_rank",
                f"Suburbs under ${budget // 1000}k that feel family-friendly.",
                {
                    "ops": [
                        {
                            "op": "semantic_search",
                            "query_text": "family-friendly suburb",
                            "top_k": 12,
                        },
                        {
                            "op": "rank",
                            "preferences": {"budget_max": budget},
                            "limit": 5,
                            "use_semantic_candidates": True,
                        },
                    ]
                },
                expect_extra={
                    "ops": ["semantic_search", "rank"],
                    "use_semantic_candidates": True,
                    "rank_preferences": {"budget_max": budget},
                },
            )
        )

    # --- unsupported / live / neighborhood (8) ---
    unsup_specs = [
        (
            "pl_unsup_01",
            "live_market",
            "Show me current Zillow listings in Newton right now.",
        ),
        (
            "pl_unsup_02",
            "live_market",
            "What are homes selling for in Acton today on MLS?",
        ),
        (
            "pl_unsup_03",
            "neighborhood",
            "Best neighborhoods in Brookline for families.",
        ),
        (
            "pl_unsup_04",
            "transit",
            "Which towns have the best MBTA access?",
        ),
        (
            "pl_unsup_05",
            "demographics",
            "Most diverse suburbs near Boston.",
        ),
        (
            "pl_unsup_06",
            "lifestyle",
            "Rank towns by nightlife.",
        ),
        (
            "pl_unsup_07",
            "school_detail",
            "Which elementary schools are best in Newton?",
        ),
        (
            "pl_unsup_08",
            "other",
            "Predict home prices in Wellesley next year.",
        ),
    ]
    for cid, cat, prompt in unsup_specs:
        cases.append(
            _case(
                cid,
                "unsupported",
                prompt,
                {
                    "ops": [
                        {
                            "op": "unsupported",
                            "category": cat,
                            "reason": f"Out of scope: {cat}",
                        }
                    ]
                },
                expect_extra={"unsupported_category": cat},
            )
        )

    # --- unsupported-field compare (8) — planner should use compare or unsupported ---
    field_prompts = [
        ("pl_unsf_01", "Which is more walkable, Newton or Needham?"),
        ("pl_unsf_02", "Compare Framingham and Quincy on diversity."),
        ("pl_unsf_03", "Is Salem more touristy than Plymouth?"),
        ("pl_unsf_04", "Newton vs Brookline for walkability."),
        ("pl_unsf_05", "Which has better nightlife, Cambridge or Somerville?"),
        ("pl_unsf_06", "Compare Acton and Concord on walk score."),
        ("pl_unsf_07", "Most walkable between Lexington and Winchester?"),
        ("pl_unsf_08", "Which is more diverse, Lynn or Revere?"),
    ]
    for cid, prompt in field_prompts:
        # Expected: compare with unsupported columns OR unsupported op
        cases.append(
            _case(
                cid,
                "unsupported_field",
                prompt,
                {
                    "ops": [
                        {
                            "op": "compare",
                            "towns": _towns_from_compare_prompt(prompt),
                            "columns": ["latest_home_price"],
                        }
                    ]
                },
                expect_extra={
                    "primary_op": "compare",
                    "ops_strict_order": False,
                },
            )
        )

    # --- commute destination (6) — expect unsupported or rank with Boston-only note ---
    dest_prompts = [
        ("pl_dest_01", "Towns within 30 minutes of Cambridge"),
        ("pl_dest_02", "I work in Burlington, find affordable towns"),
        ("pl_dest_03", "How far is Acton from Cambridge?"),
        ("pl_dest_04", "Commute to Kendall Square under 40 minutes"),
        ("pl_dest_05", "Find towns near Worcester with good schools"),
        ("pl_dest_06", "How far is Shrewsbury from Worcester?"),
    ]
    for cid, prompt in dest_prompts:
        if "How far" in prompt:
            plan = {
                "ops": [
                    {
                        "op": "unsupported",
                        "category": "transit",
                        "reason": "Non-Boston commute destination not in dataset.",
                    }
                ]
            }
            expect = {"unsupported_category": "transit", "ops": ["unsupported"]}
        else:
            plan = {
                "ops": [
                    {
                        "op": "unsupported",
                        "category": "transit",
                        "reason": "Cannot rank by non-Boston commute destination.",
                    }
                ]
            }
            expect = {"unsupported_category": "transit", "ops": ["unsupported"]}
        cases.append(_case(cid, "commute_destination", prompt, plan, expect_extra=expect))

    # --- typos / aliases (8) ---
    typo_specs = [
        ("pl_typo_01", "Worchester", "Is Worchester in your dataset?"),
        ("pl_typo_02", "Framinghan", "What is Framinghan's commute?"),
        ("pl_typo_03", "Westboro", "Compare Westboro and Natick on price."),
        ("pl_typo_04", "Lexinton", "School data for Lexinton."),
    ]
    for cid, typo, prompt in typo_specs:
        canonical = {
            "Worchester": "Worcester",
            "Framinghan": "Framingham",
            "Westboro": "Westborough",
            "Lexinton": "Lexington",
        }.get(typo, typo)
        if "Compare" in prompt:
            cases.append(
                _case(
                    cid,
                    "typo",
                    prompt,
                    {
                        "ops": [
                            {
                                "op": "compare",
                                "towns": [canonical, "Natick"],
                                "columns": ["latest_home_price"],
                            }
                        ]
                    },
                    expect_extra={"compare_towns": [canonical, "Natick"]},
                )
            )
        elif "dataset" in prompt:
            cases.append(
                _case(
                    cid,
                    "typo",
                    prompt,
                    {
                        "ops": [
                            {
                                "op": "lookup",
                                "items": [{"town": canonical, "field": "summary"}],
                            }
                        ]
                    },
                    expect_extra={"lookup_items": [{"town": canonical, "field": "summary"}]},
                )
            )
        else:
            cases.append(
                _case(
                    cid,
                    "typo",
                    prompt,
                    {
                        "ops": [
                            {
                                "op": "lookup",
                                "items": [{"town": canonical, "field": "commute"}],
                            }
                        ]
                    },
                    expect_extra={"lookup_items": [{"town": canonical, "field": "commute"}]},
                )
            )

    cases.append(
        _case(
            "pl_ml_03",
            "lookup",
            "Price in Wellesley, commute in Lexington, safety in Arlington.",
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [
                            {"town": "Wellesley", "field": "price"},
                            {"town": "Lexington", "field": "commute"},
                            {"town": "Arlington", "field": "safety"},
                        ],
                    }
                ]
            },
            expect_extra={
                "lookup_items": [
                    {"town": "Wellesley", "field": "price"},
                    {"town": "Lexington", "field": "commute"},
                    {"town": "Arlington", "field": "safety"},
                ],
            },
        )
    )
    cases.append(
        _case(
            "pl_ml_04",
            "lookup",
            "Is Providence in your 200-town dataset?",
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [{"town": "Providence", "field": "summary"}],
                    }
                ]
            },
            expect_extra={"lookup_items": [{"town": "Providence", "field": "summary"}]},
        )
    )

    alias_specs = [
        ("pl_alias_01", "Marlboro", "Marlborough", "Is Marlboro in the dataset?"),
        ("pl_alias_02", "Foxboro", "Foxborough", "Commute for Foxboro."),
        ("pl_alias_03", "Manchester-by-the-Sea", "Manchester-by-the-Sea", "Coastal status for Manchester-by-the-Sea."),
        ("pl_alias_04", "Manchester by the Sea", "Manchester-by-the-Sea", "Summarize Manchester by the Sea."),
        ("pl_alias_05", "Northboro", "Northborough", "School score for Northboro."),
        ("pl_alias_06", "Shrewsbry", "Shrewsbury", "Safety rating for Shrewsbry."),
    ]
    for cid, alias, canonical, prompt in alias_specs:
        cases.append(
            _case(
                cid,
                "alias",
                prompt,
                {
                    "ops": [
                        {
                            "op": "lookup",
                            "items": [{"town": canonical, "field": "summary"}],
                        }
                    ]
                },
                expect_extra={"lookup_items": [{"town": canonical, "field": "summary"}]},
            )
        )

    return cases[:100]


def _towns_from_compare_prompt(prompt: str) -> list[str]:
    """Best-effort town list for unsupported-field compare fixtures."""
    import re

    m = re.findall(
        r"\b(Newton|Needham|Framingham|Quincy|Salem|Plymouth|Brookline|Cambridge|Somerville|Acton|Concord|Lexington|Winchester|Lynn|Revere)\b",
        prompt,
    )
    return m[:2] if len(m) >= 2 else m


def main() -> None:
    cases = build_cases()
    if len(cases) != 100:
        raise SystemExit(f"Expected 100 cases, got {len(cases)}")

    by_cat: dict[str, int] = {}
    for c in cases:
        by_cat[c["category"]] = by_cat.get(c["category"], 0) + 1

    payload = {
        "description": "Planner-only eval — 100 NL prompts with expected QueryPlan JSON",
        "prompt_count": len(cases),
        "by_category": by_cat,
        "targets": {
            "operation_accuracy": 0.9,
            "town_extraction_accuracy": 0.9,
            "field_constraint_accuracy": 0.9,
        },
        "cases": cases,
    }
    OUT_MANIFEST.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {OUT_MANIFEST}")
    print("By category:", by_cat)


if __name__ == "__main__":
    main()
