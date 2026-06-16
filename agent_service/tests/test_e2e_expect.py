"""Tests for E2E expectation builder."""

from __future__ import annotations

from app.evals.e2e_expect import build_e2e_expect


def test_typo_membership_intent_accepts_membership_op() -> None:
    case = {
        "category": "typo",
        "expected_intent": "dataset_membership",
        "prompt": "Would Lexingtn resolve correctly?",
    }
    expect = build_e2e_expect(case)
    assert expect["plan_ops_contains"] == ["membership"]


def test_typo_lookup_intent_accepts_lookup_or_membership() -> None:
    case = {
        "category": "typo",
        "expected_intent": "lookup_single_town",
        "prompt": "Is Manchestr-by-the-Sea coastal?",
    }
    expect = build_e2e_expect(case)
    assert expect["plan_ops_contains_any"] == ["lookup", "membership"]


def test_typo_compare_expects_compare_op() -> None:
    case = {
        "category": "typo",
        "expected_intent": "compare_towns",
        "prompt": "Somervile versus Acton for safety.",
    }
    expect = build_e2e_expect(case)
    assert expect["plan_ops_contains"] == ["compare"]


def test_lookup_category_requires_lookup_op() -> None:
    case = {
        "category": "lookup",
        "expected_intent": "lookup_single_town",
        "prompt": "Is Wilmington a partial-data town?",
    }
    expect = build_e2e_expect(case)
    assert expect["plan_ops_contains"] == ["lookup"]
    assert "plan_ops_contains_any" not in expect
