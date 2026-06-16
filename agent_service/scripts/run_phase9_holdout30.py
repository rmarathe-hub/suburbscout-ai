#!/usr/bin/env python3
"""Phase 9 holdout 30 — brand-new prompts (post plan-only pipeline)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICE_ROOT / "scripts"))

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent / "phase9_holdout30_responses.json"

PROMPTS: list[tuple[str, str, str]] = [
    # A — dynamic commute ranking
    ("A", "N1", "Job in Framingham — safe suburbs under 1M within 32 minutes."),
    ("A", "N2", "Daily drive to Sudbury; budget 850k max; good schools."),
    ("A", "N3", "Affordable towns within 28 minutes of Lexington for my office."),
    ("A", "N4", "Commute anchor Bedford; max 35 min; prefer coastal towns."),
    ("A", "N5", "Wellesley workplace; quieter towns under 40 min; homes below 1.15M."),
    # B — shorthand commute
    ("B", "N6", "Framingham: 32 min cap, schools matter."),
    ("B", "N7", "Sudbury drive max 25, affordable only."),
    ("B", "N8", "Lexington hub, commute below 30."),
    ("B", "N9", "Bedford 35 minute max, safer towns."),
    ("B", "N10", "Wellesley 40 min, budget 1.1M."),
    # C — valid compare + destination
    ("C", "N11", "Concord vs Lexington if I work in Burlington."),
    ("C", "N12", "Acton or Bedford — better for a Framingham commute?"),
    ("C", "N13", "Compare Sharon and Newton on schools and price."),
    ("C", "N14", "Melrose versus Medford for a commute to Watertown."),
    ("C", "N15", "Arlington vs Belmont for office in Cambridge."),
    # D — unsupported compare destinations
    ("D", "N16", "Concord vs Lexington for a job in Chicago."),
    ("D", "N17", "Acton or Bedford commuting to Manhattan."),
    ("D", "N18", "Sharon vs Newton if workplace is in Hartford CT."),
    ("D", "N19", "Melrose or Medford for work in Providence RI."),
    ("D", "N20", "Arlington vs Belmont for a San Francisco job."),
    # E — compare table / lookup / membership
    ("E", "N21", "Compare Concord, Lexington, and Bedford on schools and commute."),
    ("E", "N22", "What is Medford's home price and school score?"),
    ("E", "N23", "Open Arlington."),
    ("E", "N24", "Commute from Gardner to Boston?"),
    ("E", "N25", "Is Boxford in your dataset?"),
    # F — workplace / semantic / refusals / inverted prefs
    ("F", "N26", "Starting at a company in Burlington next month — towns under 900k, 30 min max."),
    ("F", "N27", "Suburbs like Concord but cheaper."),
    ("F", "N28", "Current Redfin listings in Newton under 1M?"),
    ("F", "N29", "Which neighborhood in Wellesley is safest?"),
    ("F", "N30", "Crime can be higher if homes are cheap."),
]

DEST: dict[str, str] = {
    "N1": "Framingham",
    "N2": "Sudbury",
    "N3": "Lexington",
    "N4": "Bedford",
    "N5": "Wellesley",
    "N6": "Framingham",
    "N7": "Sudbury",
    "N8": "Lexington",
    "N9": "Bedford",
    "N10": "Wellesley",
    "N11": "Burlington",
    "N12": "Framingham",
    "N14": "Watertown",
    "N15": "Cambridge",
    "N26": "Burlington",
}

CAP: dict[str, int] = {
    "N1": 32,
    "N3": 28,
    "N4": 35,
    "N5": 40,
    "N6": 32,
    "N7": 25,
    "N8": 30,
    "N9": 35,
    "N10": 40,
    "N26": 30,
}

BUDGET: dict[str, int] = {
    "N1": 1_000_000,
    "N2": 850_000,
    "N5": 1_150_000,
    "N10": 1_100_000,
    "N26": 900_000,
}

PLAIN_COMPARE = frozenset({"N13", "N21", "N22"})


def post_query(prompt: str) -> dict[str, Any]:
    """Prefer in-process query agent (always uses latest code)."""
    import asyncio

    from eval_query_agent import run_query_agent_prompt

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


def _post_query_http(prompt: str) -> dict[str, Any]:
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
        return {"http_status": exc.code, "latency_s": round(time.perf_counter() - started, 2), "raw": detail}
    except Exception as exc:
        return {"http_status": 0, "latency_s": round(time.perf_counter() - started, 2), "raw": {"detail": str(exc)}}


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
    answer = str(raw.get("answer") or "")
    gate = raw.get("trust_gate")

    if section == "A":
        if cid in DEST and not _dest_ok(meta, DEST[cid]):
            notes.append(f"dest expected {DEST[cid]}")
        if cid in CAP and max_c != CAP[cid]:
            notes.append(f"max_commute={max_c} expected {CAP[cid]}")
        if cid in BUDGET and prefs.get("budget_max") != BUDGET[cid]:
            notes.append(f"budget={prefs.get('budget_max')} expected {BUDGET[cid]}")
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
        b = prefs.get("budget_max")
        if b is not None and b <= 50_000:
            notes.append(f"budget_as_minutes={b}")
        if cid in BUDGET and b != BUDGET[cid]:
            notes.append(f"budget={b} expected {BUDGET[cid]}")

    elif section == "C":
        if "compare" not in ops:
            notes.append(f"ops={ops}")
        if status not in ("ok", "partial"):
            notes.append(f"status={status}")
        if cid != "N13" and not _dest_ok(meta, DEST[cid]):
            notes.append(f"dest expected {DEST[cid]}")

    elif section == "D":
        if status not in ("blocked", "out_of_scope", "not_found") and not raw.get("trust_gate_blocks"):
            notes.append(f"expected refusal status={status}")
        if status == "ok" and raw.get("top_matches"):
            notes.append("top_matches on unsupported compare")

    elif section == "E":
        if cid == "N21":
            if "compare" not in ops:
                notes.append(f"expected compare ops={ops}")
            elif len(compare_towns) < 3:
                notes.append(f"expected 3-town compare got {compare_towns}")
        elif cid == "N22":
            if "lookup" not in ops and "compare" not in ops:
                notes.append(f"expected lookup/compare ops={ops}")
        elif cid == "N23":
            if status not in ("ok", "partial"):
                notes.append(f"lookup status={status}")
        elif cid == "N24":
            if status not in ("ok", "partial"):
                notes.append(f"commute status={status}")
        elif cid == "N25":
            if "membership" not in ops:
                notes.append(f"expected membership ops={ops}")

    elif section == "F":
        if cid == "N26":
            if not _dest_ok(meta, DEST[cid]):
                notes.append(f"dest expected {DEST[cid]}")
            if max_c != CAP[cid]:
                notes.append(f"max_commute={max_c} expected {CAP[cid]}")
            if prefs.get("budget_max") != BUDGET[cid]:
                notes.append(f"budget={prefs.get('budget_max')} expected {BUDGET[cid]}")
        elif cid == "N27":
            if "Traceback" in answer:
                notes.append("stack trace")
            if status == "error":
                notes.append("error status")
        elif cid in ("N28", "N29"):
            if status == "ok" and not gate:
                notes.append("should refuse or trust_gate")
            if status == "ok" and raw.get("top_matches"):
                notes.append("ranked on refusal prompt")
        elif cid == "N30":
            if "rank" not in ops:
                notes.append(f"expected rank ops={ops}")
            if not (prefs.get("allow_low_safety") or prefs.get("prefer_high_crime")):
                notes.append("expected inverted crime prefs")

    return ("PASS" if not notes else "FAIL"), notes


def main() -> int:
    print(f"=== Phase 9 HOLDOUT 30 (in-process query agent) ===\n")
    results = []
    for i, (sec, cid, prompt) in enumerate(PROMPTS, 1):
        print(f"[{i}/30] {cid} ...", flush=True)
        entry = post_query(prompt)
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
            "total": 30,
            "pass": passed,
            "fail": 30 - passed,
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
    print(f"\n{passed}/30 passed | saved {OUT}")
    return 0 if passed == 30 else 1


if __name__ == "__main__":
    raise SystemExit(main())
