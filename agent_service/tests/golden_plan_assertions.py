"""Shared assertion helpers for golden plan executor tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.plan_executor import ExecutionResult, ExecutionStatus, execute_plan
from app.query_plan import PlanValidationError, validate_plan

GOLDEN_ROOT = Path(__file__).resolve().parent / "fixtures" / "golden_plans"


def load_manifest() -> dict[str, Any]:
    path = GOLDEN_ROOT / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_plan_file(relative: str) -> dict[str, Any]:
    return json.loads((GOLDEN_ROOT / relative).read_text(encoding="utf-8"))


def run_golden_case(case: dict[str, Any]) -> ExecutionResult | None:
    """
    Run one manifest case.

    Returns None when expect_validation_error and validation failed as expected.
  """
    plan_data = load_plan_file(case["plan_file"])
    if case.get("expect_validation_error"):
        try:
            validate_plan(plan_data)
        except (PlanValidationError, Exception):
            return None
        raise AssertionError(f"{case['id']}: expected plan validation to fail")
    return execute_plan(plan_data)


def assert_golden_case(case: dict[str, Any], result: ExecutionResult | None) -> list[str]:
    """Return list of failure messages (empty if passed)."""
    failures: list[str] = []
    case_id = case.get("id", "?")

    if case.get("expect_validation_error"):
        if result is not None:
            failures.append(f"{case_id}: expected validation error but plan executed")
        return failures

    assert result is not None
    expected_status = case.get("expect_status")
    allowed_statuses = case.get("expect_status_in")
    if allowed_statuses:
        if result.status.value not in allowed_statuses:
            failures.append(
                f"{case_id}: status {result.status.value} not in {allowed_statuses}"
            )
    elif expected_status and result.status.value != expected_status:
        failures.append(
            f"{case_id}: status {result.status.value} != expected {expected_status}"
        )

    expected_code = case.get("message_code")
    if expected_code and result.message_code != expected_code:
        failures.append(
            f"{case_id}: message_code {result.message_code} != expected {expected_code}"
        )

    for op_result in result.ops_results:
        if op_result.op == "lookup":
            items = op_result.data.get("items") or []
            found = [i for i in items if i.get("found")]
            min_found = case.get("lookup_items_found_min")
            if min_found is not None and len(found) < min_found:
                failures.append(
                    f"{case_id}: lookup found {len(found)} items, need >= {min_found}"
                )
            required_towns = case.get("lookup_towns_found") or []
            found_names = {i.get("town", "").lower() for i in found}
            for town in required_towns:
                if town.lower() not in found_names:
                    failures.append(f"{case_id}: missing found town {town}")

        if op_result.op == "compare":
            rows = op_result.data.get("comparison_table") or []
            min_rows = case.get("compare_rows_min")
            if min_rows is not None and len(rows) < min_rows:
                failures.append(
                    f"{case_id}: compare rows {len(rows)} < {min_rows}"
                )
            required = case.get("compare_towns") or []
            row_names = {r.get("town", "").lower() for r in rows}
            for town in required:
                if town.lower() not in row_names:
                    failures.append(f"{case_id}: compare missing town {town}")

        if op_result.op == "rank":
            matches = op_result.data.get("top_matches") or []
            min_m = case.get("rank_matches_min")
            if min_m is not None and len(matches) < min_m:
                failures.append(f"{case_id}: rank matches {len(matches)} < {min_m}")
            exclude = case.get("rank_excludes_town")
            if exclude:
                names = {m.get("name", "").lower() for m in matches if m.get("name")}
                if exclude.lower() in names:
                    failures.append(f"{case_id}: rank included excluded town {exclude}")

        if op_result.op == "semantic_search":
            min_c = case.get("semantic_candidates_min")
            names = op_result.data.get("candidate_town_names") or []
            if min_c is not None and len(names) < min_c:
                failures.append(
                    f"{case_id}: semantic candidates {len(names)} < {min_c}"
                )

    snippets_blob = json.dumps(result.answer_context).lower()
    for token in case.get("snippets_contain") or []:
        if token.lower() not in snippets_blob:
            failures.append(f"{case_id}: answer_context missing token '{token}'")

    return failures
