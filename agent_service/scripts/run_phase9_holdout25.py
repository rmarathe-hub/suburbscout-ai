#!/usr/bin/env python3
"""Phase 9 holdout 25 — brand-new prompts (round 2)."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICE_ROOT / "scripts"))

from eval_query_agent import run_query_agent_prompt  # noqa: E402

OUT = Path(__file__).resolve().parent / "phase9_holdout25_responses.json"

PROMPTS: list[tuple[str, str, str]] = [
    # A — commute rank + workplace phrasing
    ("A", "P1", "Office in Dedham — towns under 950k within 34 minutes, strong schools."),
    ("A", "P2", "Natick is my commute hub; safer suburbs max 28 min drive."),
    ("A", "P3", "Relocating for work in Marblehead; affordable coastal towns within 40 min."),
    ("A", "P4", "Accepted a role in Quincy — budget 825k, max commute 32 min."),
    ("A", "P5", "Company HQ in Salem; quieter towns under 38 minutes."),
    # B — shorthand
    ("B", "P6", "Dedham: 34 min cap, schools high priority."),
    ("B", "P7", "Marblehead hub, 40 min max, coastal only."),
    ("B", "P8", "Quincy 32 minute commute cap, under 825k."),
    ("B", "P9", "Salem workplace, 38 min, safety matters."),
    # C — compare + destination
    ("C", "P10", "Ipswich vs Gloucester if I work in Peabody."),
    ("C", "P11", "Boxford or Topsfield — better commute to Lowell?"),
    ("C", "P12", "Compare Braintree and Quincy on schools and price."),
    ("C", "P13", "Woburn versus Burlington for office in Waltham."),
    # D — unsupported destinations
    ("D", "P14", "Ipswich vs Gloucester for a job in Miami."),
    ("D", "P15", "Boxford or Topsfield commuting to Seattle."),
    ("D", "P16", "Braintree vs Quincy if workplace is in Austin TX."),
    # E — multi-town / lookup / membership
    ("E", "P17", "Compare Ipswich, Gloucester, and Beverly on commute and schools."),
    ("E", "P18", "What are Boxford's school score and safety score?"),
    ("E", "P19", "Pull up Marblehead."),
    ("E", "P20", "Would Ipswich be accepted as a town name?"),
    # F — semantic / refusals / special
    ("F", "P21", "Towns like Salem but less expensive."),
    ("F", "P22", "Any MLS listings in Dedham under 700k today?"),
    ("F", "P23", "Best area inside Newton for young families."),
    ("F", "P24", "Compare Newton, Needham, Wellesley, and Weston on price."),
    ("F", "P25", "We're fine with weaker schools if commute to Burlington is under 25 min."),
]

DEST: dict[str, str] = {
    "P1": "Dedham",
    "P2": "Natick",
    "P3": "Marblehead",
    "P4": "Quincy",
    "P5": "Salem",
    "P6": "Dedham",
    "P7": "Marblehead",
    "P8": "Quincy",
    "P9": "Salem",
    "P10": "Peabody",
    "P11": "Lowell",
    "P13": "Waltham",
    "P25": "Burlington",
}

CAP: dict[str, int] = {
    "P1": 34,
    "P2": 28,
    "P3": 40,
    "P4": 32,
    "P5": 38,
    "P6": 34,
    "P7": 40,
    "P8": 32,
    "P9": 38,
    "P25": 25,
}

BUDGET: dict[str, int] = {
    "P1": 950_000,
    "P4": 825_000,
    "P8": 825_000,
}


def _run_prompt(prompt: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        raw = asyncio.run(run_query_agent_prompt(prompt, save_searches=False))
        return {
            "http_status": 200,
            "latency_s": round(time.perf_counter() - started, 2),
            "raw": {
                "answer": (raw.get("response") or {}).get("final_recommendation"),
                "execution_status": raw.get("execution_status"),
                "trust_gate": raw.get("trust_gate"),
                "trust_gate_blocks": raw.get("trust_gate_blocks"),
                "plan": raw.get("plan"),
                "metadata": raw.get("metadata"),
                "top_matches": (raw.get("response") or {}).get("top_matches"),
            },
        }
    except Exception as exc:
        return {
            "http_status": 0,
            "latency_s": round(time.perf_counter() - started, 2),
            "raw": {"detail": str(exc)},
        }


def _plan_prefs(raw: dict) -> tuple[dict, dict, list[str], list[str]]:
    plan = raw.get("plan") or {}
    prefs: dict = {}
    compare_towns: list[str] = []
    for op in plan.get("ops") or []:
        if op.get("op") == "rank":
            prefs = op.get("preferences") or {}
        if op.get("op") == "compare":
            compare_towns = list(op.get("towns") or [])
    intent = plan.get("commute_intent") or {}
    ops = [o.get("op") for o in plan.get("ops") or []]
    return prefs, intent, ops, compare_towns


def _max_commute(prefs: dict, intent: dict) -> int | None:
    return prefs.get("max_commute_minutes") or intent.get("max_commute_minutes")


def _dest_ok(meta: dict, expected: str) -> bool:
    t = (meta.get("commute_destination_town") or "").lower()
    l = (meta.get("commute_destination") or "").lower()
    e = expected.lower()
    return e in t or e in l


def evaluate(section: str, cid: str, entry: dict[str, Any]) -> tuple[str, list[str]]:
    notes: list[str] = []
    http = entry.get("http_status")
    raw = entry.get("raw") or {}
    if http == 500:
        return "FAIL", ["HTTP 500"]
    if http != 200:
        return "FAIL", [f"HTTP {http}"]

    status = raw.get("execution_status")
    meta = raw.get("metadata") or {}
    prefs, intent, ops, compare_towns = _plan_prefs(raw)
    max_c = _max_commute(prefs, intent)
    gate = raw.get("trust_gate")

    if section == "A":
        if not _dest_ok(meta, DEST[cid]):
            notes.append(f"dest expected {DEST[cid]}")
        if max_c != CAP[cid]:
            notes.append(f"max_commute={max_c} expected {CAP[cid]}")
        if cid in BUDGET and prefs.get("budget_max") != BUDGET[cid]:
            notes.append(f"budget={prefs.get('budget_max')} expected {BUDGET[cid]}")
        if cid == "P3" and not prefs.get("requires_coastal"):
            notes.append("expected requires_coastal=true")
        if cid in CAP:
            for m in raw.get("top_matches") or []:
                d = m.get("data") or m
                mins = d.get("drive_minutes_to_destination")
                if mins is not None and mins > CAP[cid]:
                    notes.append(f"over_cap {d.get('name')}={mins}")
                    break

    elif section == "B":
        if not _dest_ok(meta, DEST[cid]):
            notes.append(f"dest expected {DEST[cid]}")
        if max_c != CAP[cid]:
            notes.append(f"max_commute={max_c} expected {CAP[cid]}")
        if cid == "P7" and not prefs.get("requires_coastal"):
            notes.append("expected requires_coastal=true")
        if cid in BUDGET and prefs.get("budget_max") != BUDGET[cid]:
            notes.append(f"budget={prefs.get('budget_max')} expected {BUDGET[cid]}")

    elif section == "C":
        if "compare" not in ops:
            notes.append(f"ops={ops}")
        if status not in ("ok", "partial"):
            notes.append(f"status={status}")
        if cid != "P12" and not _dest_ok(meta, DEST[cid]):
            notes.append(f"dest expected {DEST[cid]}")

    elif section == "D":
        if status not in ("blocked", "out_of_scope", "not_found") and not raw.get("trust_gate_blocks"):
            notes.append(f"expected refusal status={status}")
        if status == "ok" and raw.get("top_matches"):
            notes.append("top_matches on unsupported compare")

    elif section == "E":
        if cid == "P17":
            if "compare" not in ops:
                notes.append(f"expected compare ops={ops}")
            elif len(compare_towns) < 3:
                notes.append(f"expected 3-town compare got {compare_towns}")
        elif cid == "P18":
            if "lookup" not in ops and "compare" not in ops:
                notes.append(f"expected lookup/compare ops={ops}")
        elif cid == "P19":
            if status not in ("ok", "partial"):
                notes.append(f"lookup status={status}")
        elif cid == "P20":
            if "membership" not in ops:
                notes.append(f"expected membership ops={ops}")

    elif section == "F":
        if cid == "P21":
            if status == "error":
                notes.append("error status")
        elif cid in ("P22", "P23"):
            if status == "ok" and not gate:
                notes.append("should refuse or trust_gate")
            if status == "ok" and raw.get("top_matches"):
                notes.append("ranked on refusal prompt")
        elif cid == "P24":
            if "compare" not in ops:
                notes.append(f"expected compare ops={ops}")
            elif len(compare_towns) < 4:
                notes.append(f"expected 4-town compare got {compare_towns}")
        elif cid == "P25":
            if not _dest_ok(meta, DEST[cid]):
                notes.append(f"dest expected {DEST[cid]}")
            if max_c != CAP[cid]:
                notes.append(f"max_commute={max_c} expected {CAP[cid]}")
            if not (prefs.get("deprioritize_schools") or prefs.get("prefer_low_school")):
                if prefs.get("school_priority") == "high":
                    notes.append("should deprioritize schools")

    return ("PASS" if not notes else "FAIL"), notes


def main() -> int:
    print("=== Phase 9 HOLDOUT 25 (round 2) ===\n")
    results = []
    for i, (sec, cid, prompt) in enumerate(PROMPTS, 1):
        print(f"[{i}/25] {cid} ...", flush=True)
        entry = _run_prompt(prompt)
        verdict, notes = evaluate(sec, cid, entry)
        raw = entry.get("raw") or {}
        prefs, intent, ops, compare_towns = _plan_prefs(raw)
        meta = raw.get("metadata") or {}
        row = {
            "section": sec,
            "id": cid,
            "prompt": prompt,
            "verdict": verdict,
            "notes": notes,
            "http_status": entry.get("http_status"),
            "latency_s": entry.get("latency_s"),
            "execution_status": raw.get("execution_status"),
            "trust_gate": raw.get("trust_gate"),
            "ops": ops,
            "compare_towns": compare_towns,
            "max_commute_minutes": _max_commute(prefs, intent),
            "budget_max": prefs.get("budget_max"),
            "commute_destination": meta.get("commute_destination"),
            "answer_snip": (raw.get("answer") or "")[:180],
        }
        results.append(row)
        print(f"  [{verdict}] {cid} status={row['execution_status']} ops={ops} notes={notes}")

    passed = sum(1 for r in results if r["verdict"] == "PASS")
    report = {
        "summary": {
            "total": 25,
            "pass": passed,
            "fail": 25 - passed,
            "http_500": sum(1 for r in results if r.get("http_status") == 500),
            "by_section": {},
        },
        "results": results,
    }
    for r in results:
        sec = r["section"]
        report["summary"]["by_section"].setdefault(sec, {"pass": 0, "total": 0})
        report["summary"]["by_section"][sec]["total"] += 1
        if r["verdict"] == "PASS":
            report["summary"]["by_section"][sec]["pass"] += 1

    OUT.write_text(json.dumps(report, indent=2))
    print(f"\n{passed}/25 passed | saved {OUT}")
    if passed != 25:
        print("\nFailures:")
        for r in results:
            if r["verdict"] == "FAIL":
                print(f"  {r['id']}: {r['notes']}")
    return 0 if passed == 25 else 1


if __name__ == "__main__":
    raise SystemExit(main())
