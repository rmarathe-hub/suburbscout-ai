"""Layer 3 trust-gate eval cases (no live LLM)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

TRUST_EVAL = SERVICE_ROOT / "app" / "evals" / "trust_gate_plan_eval.json"


class TestTrustGateLayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not TRUST_EVAL.exists():
            raise unittest.SkipTest("trust_gate_plan_eval.json missing")
        cls.cases = json.loads(TRUST_EVAL.read_text(encoding="utf-8")).get("cases") or []

    def test_all_trust_gate_expectations(self) -> None:
        from app.plan_trust_gates import evaluate_plan_trust_gate
        from app.query_plan import validate_plan

        failures: list[str] = []
        for case in self.cases:
            plan = validate_plan(case["plan"])
            gate = evaluate_plan_trust_gate(case["prompt"], plan)
            actual = gate.gate_type if gate else None
            if actual != case.get("expect_gate"):
                failures.append(
                    f"{case['id']}: gate {actual!r} != {case.get('expect_gate')!r}"
                )
            if case.get("expect_blocks") and not (gate and gate.blocks_pipeline):
                failures.append(f"{case['id']}: expected blocks_pipeline")

        if failures:
            self.fail("\n".join(failures))

    def test_refusal_skips_answer_llm(self) -> None:
        import asyncio

        from app.query_agent import handle_query_v2
        from app.query_plan import validate_plan

        blocked = [c for c in self.cases if c.get("expect_blocks")][:3]
        for case in blocked:
            plan = validate_plan(case["plan"])

            async def _run() -> dict:
                with patch("app.query_agent.query_agent_available", return_value=True):
                    with patch("app.query_agent.plan_query_with_llm", return_value=plan):
                        return await handle_query_v2(case["prompt"], save_searches=False)

            payload = asyncio.run(_run())
            self.assertEqual(payload.get("execution_status"), "blocked")
            self.assertFalse(payload.get("used_answer_llm"))


if __name__ == "__main__":
    unittest.main()
