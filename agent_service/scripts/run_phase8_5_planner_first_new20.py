#!/usr/bin/env python3
"""Phase 8.5 — 20 new planner-first prompts (not in fresh-40 set)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent / "phase8_5_planner_first_new20_responses.json"

PROMPTS: list[tuple[str, str, str]] = [
    ("A", "N1", "Rank towns under 750k within 32 minutes of Arlington with strong schools."),
    ("A", "N2", "Cheaper suburbs within 28 minutes of Medford, safety matters."),
    ("A", "N3", "Find family-friendly towns within 35 minutes of Framingham under 1.1M."),
    ("B", "N4", "Arlington max 30 min drive, good schools, budget 950k."),
    ("B", "N5", "Medford under 20 minutes, affordable options only."),
    ("B", "N6", "Framingham commute limit 35 min, safer towns preferred."),
    ("C", "N7", "Compare Concord and Carlisle for a commute to Lexington."),
    ("C", "N8", "Is Wayland or Sudbury better for driving to Waltham daily?"),
    ("C", "N9", "Marblehead versus Swampscott if my office is in Burlington."),
    ("D", "N10", "Compare Concord and Carlisle if I commute to Stamford."),
    ("D", "N11", "Wayland or Sudbury for driving to Albany?"),
    ("E", "N12", "Compare Concord and Carlisle on price and schools."),
    ("E", "N13", "How does Wayland compare to Sudbury on safety and commute to Boston?"),
    ("E", "N14", "Open Marblehead."),
    ("F", "N15", "I just got a job in Lexington and need affordable towns with decent schools."),
    ("F", "N16", "Daily commute to Waltham — show me safer suburbs under 850k."),
    ("G", "N17", "Towns like Arlington but with lower prices."),
    ("G", "N18", "Alternatives to Concord that are closer to Cambridge."),
    ("H", "N19", "Show me live Realtor.com listings in Wayland."),
    ("H", "N20", "What homes are for sale in Sudbury this week?"),
]


def post_query(prompt: str) -> dict[str, Any]:
    body = json.dumps({"prompt": prompt, "save_audit": False, "debug": True}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/query",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=360) as resp:
            return {
                "http_status": resp.status,
                "latency_s": round(time.perf_counter() - started, 2),
                "raw": json.loads(resp.read()),
            }
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read())
        except Exception:
            detail = {"detail": exc.reason}
        return {
            "http_status": exc.code,
            "latency_s": round(time.perf_counter() - started, 2),
            "raw": detail,
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "http_status": 0,
            "latency_s": round(time.perf_counter() - started, 2),
            "raw": {"detail": str(exc)},
            "error": str(exc),
        }


def _rank_prefs(plan: dict | None) -> dict[str, Any]:
    if not plan:
        return {}
    for op in plan.get("ops") or []:
        if op.get("op") == "rank":
            return op.get("preferences") or {}
    return {}


def _intent(plan: dict | None) -> dict[str, Any]:
    return (plan or {}).get("commute_intent") or {}


def inspect(entry: dict[str, Any]) -> dict[str, Any]:
    raw = entry.get("raw") or {}
    plan = raw.get("plan")
    prefs = _rank_prefs(plan)
    intent = _intent(plan)
    top = raw.get("top_matches") or []
    return {
        "http_status": entry.get("http_status"),
        "execution_status": raw.get("execution_status"),
        "trust_gate": raw.get("trust_gate"),
        "ops": [o.get("op") for o in (plan or {}).get("ops") or []],
        "commute_destination": (raw.get("metadata") or {}).get("commute_destination"),
        "commute_destination_is_default": (raw.get("metadata") or {}).get(
            "commute_destination_is_default"
        ),
        "commute_destination_town": (raw.get("metadata") or {}).get("commute_destination_town"),
        "max_commute_minutes": prefs.get("max_commute_minutes") or intent.get("max_commute_minutes"),
        "budget_max": prefs.get("budget_max"),
        "top_over_cap": [
            f"{(m.get('data') or m).get('name')}={(m.get('data') or m).get('drive_minutes_to_destination')}"
            for m in top
            if (m.get("data") or m).get("drive_minutes_to_destination") is not None
        ][:3],
    }


def evaluate(section: str, case_id: str, prompt: str, entry: dict[str, Any]) -> tuple[str, list[str]]:
    notes: list[str] = []
    http = entry.get("http_status")
    raw = entry.get("raw") or {}
    ins = inspect(entry)
    status = ins["execution_status"]
    ops = ins["ops"]

    if http == 500:
        return "FAIL", ["HTTP 500"]
    if http != 200:
        return "FAIL", [f"HTTP {http}"]

    if section == "A":
        if status not in ("ok", "partial", "no_rows"):
            notes.append(f"status={status}")
        if ins["max_commute_minutes"] is None:
            notes.append("missing max_commute_minutes")
        if ins["commute_destination_is_default"]:
            notes.append("unexpected default Boston")

    elif section == "B":
        if ins["max_commute_minutes"] is None:
            notes.append("missing max_commute_minutes")
        if ins["budget_max"] is not None and ins["budget_max"] <= 50_000:
            notes.append(f"budget_max={ins['budget_max']} minutes-as-dollars")

    elif section == "C":
        if "compare" not in ops:
            notes.append(f"ops={ops}")
        if ins["trust_gate"] == "multi_compare":
            notes.append("multi_compare")

    elif section == "D":
        if status not in ("blocked", "out_of_scope", "not_found") and not raw.get("trust_gate_blocks"):
            notes.append(f"expected refusal status={status}")

    elif section == "E":
        if case_id == "N12" and ins["commute_destination_is_default"] is not True:
            notes.append("plain compare should default Boston")
        if case_id == "N12" and "compare" not in ops:
            notes.append(f"expected compare ops={ops}")
        if case_id == "N14" and status not in ("ok", "partial"):
            notes.append(f"lookup status={status}")

    elif section == "F":
        if ins["commute_destination_is_default"]:
            notes.append("workplace should not default Boston only")
        if status not in ("ok", "partial", "no_rows"):
            notes.append(f"status={status}")

    elif section == "G":
        if "Traceback" in str(raw.get("answer") or ""):
            notes.append("stack trace")

    elif section == "H":
        if status == "ok" and not raw.get("trust_gate"):
            notes.append("listing should be refused")

    return ("PASS" if not notes else "FAIL"), notes


def main() -> int:
    results = []
    print(f"=== Phase 8.5 planner-first NEW 20 QA ===\n{BASE}\n")
    for i, (section, cid, prompt) in enumerate(PROMPTS, 1):
        print(f"[{i}/20] {cid} ...", flush=True)
        entry = post_query(prompt)
        verdict, notes = evaluate(section, cid, prompt, entry)
        row = {
            "section": section,
            "id": cid,
            "prompt": prompt,
            "verdict": verdict,
            "notes": notes,
            "inspection": inspect(entry),
            "latency_s": entry.get("latency_s"),
            "raw": entry.get("raw"),
        }
        results.append(row)
        print(f"  [{verdict}] {cid} {notes}")

    passed = sum(1 for r in results if r["verdict"] == "PASS")
    http_500 = sum(1 for r in results if r["inspection"].get("http_status") == 500)
    report = {
        "summary": {
            "total": 20,
            "pass": passed,
            "fail": 20 - passed,
            "http_500": http_500,
        },
        "results": results,
    }
    OUT.write_text(json.dumps(report, indent=2))
    print(f"\n{passed}/20 passed | saved {OUT}")
    return 0 if passed == 20 else 1


if __name__ == "__main__":
    raise SystemExit(main())
