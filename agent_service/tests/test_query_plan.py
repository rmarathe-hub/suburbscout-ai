"""Phase 1 tests — query plan schema and validation."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.query_plan import (  # noqa: E402
    CompareOp,
    LookupOp,
    PlanValidationError,
    QueryPlan,
    RankOp,
    SemanticSearchOp,
    UnsupportedOp,
    normalize_lookup_field,
    parse_plan_json,
    plan_json_schema,
    validate_plan,
)


class TestQueryPlan(unittest.TestCase):
    def test_normalize_lookup_field_aliases(self) -> None:
        self.assertEqual(normalize_lookup_field("latest_home_price"), "price")
        self.assertEqual(normalize_lookup_field("drive_minutes_to_boston"), "commute")
        self.assertEqual(normalize_lookup_field("schools"), "school")

    def test_lookup_op_dedupes_items(self) -> None:
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [
                            {"town": "Maynard", "field": "school"},
                            {"town": "Maynard", "field": "school_score"},
                        ],
                    }
                ]
            }
        )
        op = plan.ops[0]
        assert isinstance(op, LookupOp)
        self.assertEqual(len(op.items), 1)
        self.assertEqual(op.items[0].field, "school")

    def test_compare_op_normalizes_columns(self) -> None:
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "compare",
                        "towns": ["Newton", "Brookline", "Newton"],
                        "columns": ["price", "commute", "latest_home_price"],
                    }
                ]
            }
        )
        op = plan.ops[0]
        assert isinstance(op, CompareOp)
        self.assertEqual(op.towns, ["Newton", "Brookline"])
        self.assertEqual(
            op.columns,
            ["latest_home_price", "drive_minutes_to_boston"],
        )

    def test_rank_and_semantic_ops(self) -> None:
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "semantic_search",
                        "query_text": "quiet coastal town",
                        "top_k": 8,
                    },
                    {
                        "op": "rank",
                        "preferences": {"max_commute_minutes": 45, "budget_max": 600000},
                        "limit": 5,
                    },
                ]
            }
        )
        self.assertIsInstance(plan.ops[0], SemanticSearchOp)
        self.assertIsInstance(plan.ops[1], RankOp)
        self.assertEqual(plan.ops[1].limit, 5)

    def test_unsupported_op(self) -> None:
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "unsupported",
                        "category": "live_market",
                        "reason": "User asked for current Zillow listings",
                    }
                ]
            }
        )
        self.assertIsInstance(plan.ops[0], UnsupportedOp)

    def test_rejects_unknown_lookup_field(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan(
                {
                    "ops": [
                        {
                            "op": "lookup",
                            "items": [{"town": "Acton", "field": "walk_score"}],
                        }
                    ]
                }
            )

    def test_rejects_compare_single_town(self) -> None:
        with self.assertRaises(ValidationError):
            validate_plan(
                {"ops": [{"op": "compare", "towns": ["Acton"]}]}
            )

    def test_rejects_too_many_lookup_items(self) -> None:
        items = [{"town": f"Town{i}", "field": "school"} for i in range(21)]
        with self.assertRaises(ValidationError):
            validate_plan({"ops": [{"op": "lookup", "items": items}]})

    def test_parse_plan_json_strips_fence(self) -> None:
        raw = """```json
{"ops": [{"op": "lookup", "items": [{"town": "Maynard", "field": "commute"}]}]}
```"""
        plan = parse_plan_json(raw)
        self.assertIsInstance(plan.ops[0], LookupOp)

    def test_plan_json_schema_exports(self) -> None:
        schema = plan_json_schema()
        defs = schema.get("$defs", {})
        self.assertIn("LookupOp", defs)
        self.assertIn("CompareOp", defs)
        self.assertEqual(schema.get("title"), "QueryPlan")

    def test_model_roundtrip(self) -> None:
        original = QueryPlan(
            ops=[
                LookupOp(items=[{"town": "Concord", "field": "price"}]),
            ],
            user_intent_summary="single town price",
        )
        data = json.loads(original.model_dump_json())
        restored = validate_plan(data)
        self.assertEqual(restored.ops[0].items[0].town, "Concord")


if __name__ == "__main__":
    unittest.main()
