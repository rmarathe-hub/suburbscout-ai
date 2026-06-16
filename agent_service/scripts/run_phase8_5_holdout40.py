#!/usr/bin/env python3
"""Phase 8.5 holdout 40 — brand-new prompts (not in fresh-40 or new-20)."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent / "phase8_5_holdout40_responses.json"

# All-new towns/phrasing — holdout generalization set
PROMPTS: list[tuple[str, str, str]] = [
    # A — dynamic commute ranking
    ("A", "H1", "We're relocating for work in Needham — suburbs within 38 minutes, strong schools, homes under 1.2M."),
    ("A", "H2", "Natick is my commute anchor; what towns are under 900k within 27 minutes by car?"),
    ("A", "H3", "Peabody hub, 33 minute commute max, family-friendly towns around 800k."),
    ("A", "H4", "Cheaper options than Westford but still within 45 minutes of Chelmsford."),
    ("A", "H5", "Low crime suburbs under 950k, max 30 minutes drive to Watertown for office."),
    # B — shorthand commute phrasing
    ("B", "H6", "Needham: 30 min cap, schools matter, 1M ceiling."),
    ("B", "H7", "Natick drive max 22 min, safer towns only."),
    ("B", "H8", "Peabody hub, commute below 35, affordable suburbs."),
    ("B", "H9", "Winchester 25 minute max commute, good schools."),
    ("B", "H10", "Chelmsford workplace, under 40 min drive, homes below 750k."),
    # C — valid compare + destination
    ("C", "H11", "Hingham vs Cohasset if my workplace is Needham."),
    ("C", "H12", "North Andover or Andover — better commute to Lowell?"),
    ("C", "H13", "Compare Westborough and Hopkinton for a daily commute to Natick."),
    ("C", "H14", "Gloucester or Beverly — which works better for a Peabody commute?"),
    ("C", "H15", "Malden versus Revere if I'm working in Watertown."),
    # D — unsupported compare destinations
    ("D", "H16", "Hingham vs Cohasset if I commute to Brooklyn."),
    ("D", "H17", "North Andover or Andover for a job in Philadelphia?"),
    ("D", "H18", "Westborough vs Hopkinton for commuting into JFK Airport."),
    ("D", "H19", "Gloucester or Beverly for work in Portland Maine?"),
    ("D", "H20", "Malden or Revere if my office is in Newark NJ?"),
    # E — plain compare / lookup / membership
    ("E", "H21", "Compare Andover and North Andover on safety, schools, and price."),
    ("E", "H22", "How do Hingham and Cohasset compare on home prices and schools?"),
    ("E", "H23", "Pull up Westborough."),
    ("E", "H24", "What is the commute from Maynard to Boston?"),
    ("E", "H25", "Would Topsfield be accepted as a town name in your dataset?"),
    # F — workplace natural language
    ("F", "H26", "Just accepted an offer in Needham — suburbs with strong schools, budget 1.1M."),
    ("F", "H27", "Office moving to Lowell; affordable towns with okay schools."),
    ("F", "H28", "I'll be in Natick five days a week — short commute beats schools."),
    ("F", "H29", "New role in Peabody; we care about safety and have 900k."),
    ("F", "H30", "Chelmsford is my workplace — cheaper town with reasonable crime stats."),
    # G — semantic / similar (no 500)
    ("G", "H31", "Suburbs like Winchester but less expensive."),
    ("G", "H32", "Places similar to Hingham but closer to Boston."),
    ("G", "H33", "What feels like Westford but has better schools and lower price?"),
    ("G", "H34", "Comparable towns to Andover but safer."),
    ("G", "H35", "Alternatives to Needham with more affordable housing."),
    # H — listing trust gates
    ("H", "H36", "Any Trulia listings in Andover under 800k right now?"),
    ("H", "H37", "Show open houses in Winchester this weekend."),
    ("H", "H38", "Homes actively listed in Natick today?"),
    ("H", "H39", "What's on the market in Hingham currently?"),
    ("H", "H40", "Real-time property listings near Peabody with good schools."),
]

DEST: dict[str, str] = {
    "H1": "Needham",
    "H2": "Natick",
    "H3": "Peabody",
    "H4": "Chelmsford",
    "H5": "Watertown",
    "H6": "Needham",
    "H7": "Natick",
    "H8": "Peabody",
    "H9": "Winchester",
    "H10": "Chelmsford",
    "H11": "Needham",
    "H12": "Lowell",
    "H13": "Natick",
    "H14": "Peabody",
    "H15": "Watertown",
    "H26": "Needham",
    "H27": "Lowell",
    "H28": "Natick",
    "H29": "Peabody",
    "H30": "Chelmsford",
}

CAP: dict[str, int] = {
    "H1": 38,
    "H2": 27,
    "H3": 33,
    "H4": 45,
    "H5": 30,
    "H6": 30,
    "H7": 22,
    "H8": 35,
    "H9": 25,
    "H10": 40,
}

BUDGET: dict[str, int] = {
    "H1": 1_200_000,
    "H2": 900_000,
    "H3": 800_000,
    "H5": 950_000,
    "H6": 1_000_000,
    "H10": 750_000,
    "H26": 1_100_000,
    "H29": 900_000,
}


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
        return {"http_status": exc.code, "latency_s": round(time.perf_counter() - started, 2), "raw": detail}
    except Exception as exc:
        return {"http_status": 0, "latency_s": round(time.perf_counter() - started, 2), "raw": {"detail": str(exc)}}


def _plan_prefs(raw: dict) -> tuple[dict, dict, list[str]]:
    plan = raw.get("plan") or {}
    prefs: dict = {}
    for op in plan.get("ops") or []:
        if op.get("op") == "rank":
            prefs = op.get("preferences") or {}
    intent = plan.get("commute_intent") or {}
    ops = [o.get("op") for o in plan.get("ops") or []]
    return prefs, intent, ops


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
    prefs, intent, ops = _plan_prefs(raw)
    max_c = _max_commute(prefs, intent)
    answer = str(raw.get("answer") or "")

    if section == "A":
        if not _dest_ok(meta, DEST[cid]):
            notes.append(f"dest expected {DEST[cid]}")
        if max_c != CAP[cid]:
            notes.append(f"max_commute={max_c} expected {CAP[cid]}")
        if cid in BUDGET and prefs.get("budget_max") != BUDGET[cid]:
            notes.append(f"budget={prefs.get('budget_max')} expected {BUDGET[cid]}")
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
        if not _dest_ok(meta, DEST[cid]):
            notes.append(f"dest expected {DEST[cid]}")

    elif section == "D":
        if status not in ("blocked", "out_of_scope", "not_found") and not raw.get("trust_gate_blocks"):
            notes.append(f"expected refusal status={status}")
        if status == "ok" and raw.get("top_matches"):
            notes.append("top_matches on unsupported compare")

    elif section == "E":
        if cid == "H21":
            if "compare" not in ops:
                notes.append(f"expected compare ops={ops}")
            if meta.get("commute_destination_is_default") is not True:
                notes.append("plain compare needs default Boston")
        elif cid == "H22":
            if "compare" not in ops:
                notes.append(f"expected compare ops={ops}")
        elif cid == "H23":
            if status not in ("ok", "partial"):
                notes.append(f"lookup status={status}")
        elif cid == "H24":
            if status not in ("ok", "partial"):
                notes.append(f"commute lookup status={status}")
        elif cid == "H25":
            if status not in ("ok", "partial", "blocked"):
                notes.append(f"membership status={status}")

    elif section == "F":
        if not _dest_ok(meta, DEST[cid]):
            notes.append(f"dest expected {DEST[cid]}")
        if meta.get("commute_destination_is_default"):
            notes.append("should not be Boston-only default")
        if status not in ("ok", "partial", "no_rows"):
            notes.append(f"status={status}")

    elif section == "G":
        if "Traceback" in answer:
            notes.append("stack trace")
        if status == "error":
            notes.append("error status")

    elif section == "H":
        if status == "ok" and not raw.get("trust_gate"):
            notes.append("listing should refuse")

    return ("PASS" if not notes else "FAIL"), notes


def main() -> int:
    print(f"=== Phase 8.5 HOLDOUT 40 (all-new prompts) ===\n{BASE}\n")
    results = []
    for i, (sec, cid, prompt) in enumerate(PROMPTS, 1):
        print(f"[{i}/40] {cid} ...", flush=True)
        entry = post_query(prompt)
        verdict, notes = evaluate(sec, cid, entry)
        raw = entry.get("raw") or {}
        prefs, intent, ops = _plan_prefs(raw)
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
            "ops": ops,
            "max_commute_minutes": _max_commute(prefs, intent),
            "budget_max": prefs.get("budget_max"),
            "commute_destination": meta.get("commute_destination"),
            "answer_snip": (raw.get("answer") or "")[:180],
            "raw": raw,
        }
        results.append(row)
        print(f"  [{verdict}] {cid} status={row['execution_status']} ops={ops} notes={notes}")

    passed = sum(1 for r in results if r["verdict"] == "PASS")
    report = {
        "summary": {
            "total": 40,
            "pass": passed,
            "fail": 40 - passed,
            "http_500": sum(1 for r in results if r.get("http_status") == 500),
            "deploy_ready_holdout": passed == 40,
        },
        "results": results,
    }
    OUT.write_text(json.dumps(report, indent=2))
    print(f"\n{passed}/40 passed | saved {OUT}")
    return 0 if passed == 40 else 1


if __name__ == "__main__":
    raise SystemExit(main())
