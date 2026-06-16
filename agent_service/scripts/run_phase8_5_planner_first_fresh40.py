#!/usr/bin/env python3
"""Phase 8.5 planner-first fresh 40-prompt QA via POST /api/query?debug=true."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent / "phase8_5_planner_first_fresh40_responses.json"

PROMPTS: list[tuple[str, str, str]] = [
    # section, id, prompt
    ("A", "A1", "Find towns under 900k within 35 minutes of Cambridge with strong schools."),
    ("A", "A2", "I want safe towns below 800k within 30 minutes of Waltham."),
    ("A", "A3", "Show me good-school suburbs within 25 minutes of Burlington."),
    ("A", "A4", "Find lower-crime towns within 40 minutes of Newton and under 950k."),
    ("A", "A5", "I need towns within 30 minutes of Somerville, but homes should be under 850k."),
    ("B", "B6", "Cambridge under 30 minutes, safe, decent schools, under 1M."),
    ("B", "B7", "Waltham below 25 min commute and affordable."),
    ("B", "B8", "Burlington under 35 min drive, good schools preferred."),
    ("B", "B9", "Newton 30 minute commute max, safer towns only."),
    ("B", "B10", "Somerville commute cap 30 minutes, homes below 900k."),
    ("C", "C11", "Compare Lexington and Bedford if I commute to Waltham."),
    ("C", "C12", "Which is better, Sharon or Milton, for driving to Brookline?"),
    ("C", "C13", "Acton versus Reading if my job is in Cambridge."),
    ("C", "C14", "Would Melrose or Stoneham be better for commuting into Burlington?"),
    ("C", "C15", "Compare Wellesley and Newton if I need to get to Somerville."),
    ("D", "D16", "Compare Lexington and Bedford if I commute to Providence."),
    ("D", "D17", "Sharon or Milton for driving to Hartford?"),
    ("D", "D18", "Acton versus Reading if my job is in Manhattan."),
    ("D", "D19", "Would Melrose or Stoneham be better for commuting into New Haven?"),
    ("D", "D20", "Compare Wellesley and Newton if I need to get to Logan Airport."),
    ("E", "E21", "Compare Lexington and Bedford on schools, safety, and price."),
    ("E", "E22", "Compare Sharon and Milton by home price and school score."),
    ("E", "E23", "Tell me about Waltham."),
    ("E", "E24", "Open Burlington."),
    ("E", "E25", "What is the safety score for Newton?"),
    ("F", "F26", "I'm starting work in Cambridge and want towns with good schools under 950k."),
    ("F", "F27", "My new office is Waltham; suggest safer suburbs with reasonable prices."),
    ("F", "F28", "I'll be commuting to Burlington most days and want a cheaper town."),
    ("F", "F29", "My daily drive is to Newton, but I care more about low crime than schools."),
    ("F", "F30", "I work near Somerville and need something under 900k."),
    ("G", "G31", "Find towns similar to Belmont but less expensive."),
    ("G", "G32", "What are good alternatives to Wellesley with lower home prices?"),
    ("G", "G33", "Suggest suburbs like Brookline but safer and cheaper."),
    ("G", "G34", "Find places comparable to Lexington but closer to Cambridge."),
    ("G", "G35", "What towns feel like Newton but offer better value?"),
    ("H", "H36", "Show me current Zillow homes in Lexington under 1M."),
    ("H", "H37", "Pull Redfin listings for Waltham with good schools."),
    ("H", "H38", "Find MLS homes for sale in Burlington right now."),
    ("H", "H39", "What houses are listed today in Cambridge?"),
    ("H", "H40", "Show active properties in Newton under 900k."),
]

DEST_FROM_PROMPT: dict[str, str] = {
    "A1": "Cambridge",
    "A2": "Waltham",
    "A3": "Burlington",
    "A4": "Newton",
    "A5": "Somerville",
    "B6": "Cambridge",
    "B7": "Waltham",
    "B8": "Burlington",
    "B9": "Newton",
    "B10": "Somerville",
    "C11": "Waltham",
    "C12": "Brookline",
    "C13": "Cambridge",
    "C14": "Burlington",
    "C15": "Somerville",
    "F26": "Cambridge",
    "F27": "Waltham",
    "F28": "Burlington",
    "F29": "Newton",
    "F30": "Somerville",
}

BUDGET_FROM_PROMPT: dict[str, int] = {
    "A1": 900_000,
    "A2": 800_000,
    "A4": 950_000,
    "A5": 850_000,
    "B6": 1_000_000,
    "B10": 900_000,
    "F26": 950_000,
    "F30": 900_000,
}

COMMUTE_CAP_FROM_PROMPT: dict[str, int] = {
    "A1": 35,
    "A2": 30,
    "A3": 25,
    "A4": 40,
    "A5": 30,
    "B6": 30,
    "B7": 25,
    "B8": 35,
    "B9": 30,
    "B10": 30,
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
            raw = json.loads(resp.read())
            return {
                "http_status": resp.status,
                "latency_s": round(time.perf_counter() - started, 2),
                "raw": raw,
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


def _rank_prefs(plan: dict[str, Any] | None) -> dict[str, Any]:
    if not plan:
        return {}
    for op in plan.get("ops") or []:
        if op.get("op") == "rank":
            return op.get("preferences") or {}
    return {}


def _extract_inspection(entry: dict[str, Any]) -> dict[str, Any]:
    raw = entry.get("raw") or {}
    meta = raw.get("metadata") or {}
    plan = raw.get("plan")
    prefs = _rank_prefs(plan)
    top = raw.get("top_matches") or []
    return {
        "http_status": entry.get("http_status"),
        "execution_status": raw.get("execution_status"),
        "trust_gate": raw.get("trust_gate"),
        "trust_gate_blocks": raw.get("trust_gate_blocks"),
        "commute_destination": meta.get("commute_destination"),
        "commute_destination_is_default": meta.get("commute_destination_is_default"),
        "commute_destination_town": meta.get("commute_destination_town"),
        "max_commute_minutes": prefs.get("max_commute_minutes"),
        "budget_max": prefs.get("budget_max"),
        "top_match_count": len(top),
        "top_matches_summary": [
            {
                "name": (m.get("name") or (m.get("data") or {}).get("name")),
                "drive_minutes_to_destination": (m.get("data") or m).get("drive_minutes_to_destination"),
                "drive_minutes_to_boston": (m.get("data") or m).get("drive_minutes_to_boston"),
                "latest_home_price": (m.get("data") or m).get("latest_home_price"),
            }
            for m in top[:5]
        ],
        "comparison_present": bool(raw.get("comparison")),
        "answer_snip": (raw.get("answer") or "")[:200],
    }


def _dest_in_meta(meta: dict[str, Any], expected: str) -> bool:
    town = (meta.get("commute_destination_town") or "").lower()
    label = (meta.get("commute_destination") or "").lower()
    exp = expected.lower()
    return exp in town or exp in label


def _over_commute_cap(top: list[dict[str, Any]], cap: int) -> list[str]:
    over: list[str] = []
    for m in top:
        data = m.get("data") or m
        name = m.get("name") or data.get("name")
        mins = data.get("drive_minutes_to_destination")
        if mins is not None and mins > cap:
            over.append(f"{name}={mins}")
    return over


def _has_invented_commute_minutes(answer: str, status: str) -> bool:
    if status in ("blocked", "out_of_scope", "not_found"):
        return False
    return bool(re.search(r"\b\d{1,3}\s*(?:min|minute)", answer, re.I))


def evaluate(section: str, case_id: str, prompt: str, entry: dict[str, Any]) -> tuple[str, list[str]]:
    notes: list[str] = []
    http = entry.get("http_status")
    raw = entry.get("raw") or {}
    status = raw.get("execution_status")
    gate = raw.get("trust_gate")
    meta = raw.get("metadata") or {}
    plan = raw.get("plan") or {}
    prefs = _rank_prefs(plan)
    top = raw.get("top_matches") or []
    answer = str(raw.get("answer") or "")

    if http == 500:
        return "FAIL", ["HTTP 500"]
    if http != 200:
        return "FAIL", [f"HTTP {http}"]

    if section == "A":
        exp_dest = DEST_FROM_PROMPT[case_id]
        cap = COMMUTE_CAP_FROM_PROMPT[case_id]
        if not _dest_in_meta(meta, exp_dest):
            notes.append(f"dest expected {exp_dest}, got town={meta.get('commute_destination_town')} label={meta.get('commute_destination')}")
        if prefs.get("max_commute_minutes") != cap:
            notes.append(f"max_commute_minutes={prefs.get('max_commute_minutes')} expected {cap}")
        if case_id in BUDGET_FROM_PROMPT and prefs.get("budget_max") != BUDGET_FROM_PROMPT[case_id]:
            notes.append(f"budget_max={prefs.get('budget_max')} expected {BUDGET_FROM_PROMPT[case_id]}")
        over = _over_commute_cap(top, cap)
        if over and status == "ok":
            notes.append(f"top_matches exceed cap: {over}")

    elif section == "B":
        exp_dest = DEST_FROM_PROMPT[case_id]
        cap = COMMUTE_CAP_FROM_PROMPT[case_id]
        if not _dest_in_meta(meta, exp_dest):
            notes.append(f"dest expected {exp_dest}")
        if prefs.get("max_commute_minutes") != cap:
            notes.append(f"max_commute_minutes={prefs.get('max_commute_minutes')} expected {cap}")
        budget = prefs.get("budget_max")
        if budget is not None and budget <= 50_000 and case_id not in ("B7", "B8", "B9"):
            notes.append(f"budget_max={budget} looks like minutes-as-dollars")
        if case_id == "B6" and budget != 1_000_000:
            notes.append(f"budget_max={budget} expected 1000000")
        if case_id == "B10" and budget != 900_000:
            notes.append(f"budget_max={budget} expected 900000")

    elif section == "C":
        exp_dest = DEST_FROM_PROMPT[case_id]
        if gate == "multi_compare":
            notes.append("multi_compare trust gate")
        if status not in ("ok", "partial"):
            notes.append(f"status={status}")
        compare_ops = [o for o in (plan.get("ops") or []) if o.get("op") == "compare"]
        if compare_ops:
            towns = compare_ops[0].get("towns") or []
            if len(towns) != 2:
                notes.append(f"compare towns count={len(towns)}")
        if not _dest_in_meta(meta, exp_dest):
            notes.append(f"dest expected {exp_dest}")

    elif section == "D":
        if status not in ("blocked", "out_of_scope", "not_found") and not raw.get("trust_gate_blocks"):
            notes.append(f"expected refusal, status={status} gate={gate}")
        if _has_invented_commute_minutes(answer, status or ""):
            notes.append("invented commute minutes in answer")
        if status == "ok" and top:
            notes.append("got top_matches on unsupported compare")

    elif section == "E":
        if meta.get("commute_destination_is_default") is not True:
            notes.append(f"expected default Boston, is_default={meta.get('commute_destination_is_default')}")
        if meta.get("commute_destination_town"):
            notes.append(f"unexpected commute_destination_town={meta.get('commute_destination_town')}")
        dest_label = (meta.get("commute_destination") or "").lower()
        if "that place" in dest_label:
            notes.append("that place metadata")

    elif section == "F":
        exp_dest = DEST_FROM_PROMPT[case_id]
        if not _dest_in_meta(meta, exp_dest):
            notes.append(f"dest expected {exp_dest}, got {meta.get('commute_destination_town')}")
        if meta.get("commute_destination_is_default") is True:
            notes.append("false default to Boston")
        if status not in ("ok", "partial", "no_rows"):
            notes.append(f"status={status}")

    elif section == "G":
        if "Traceback" in answer or "stack trace" in answer.lower():
            notes.append("stack trace in answer")
        if status == "error":
            notes.append("execution_status=error")

    elif section == "H":
        if status == "ok" and not gate:
            notes.append(f"expected refusal, status=ok")
        if re.search(r"\b(?:listing|zillow|redfin|mls|for sale|on the market)\b", answer, re.I) and status == "ok":
            if not gate:
                notes.append("invented listing details")
        listing_town = re.search(
            r"\b(Lexington|Waltham|Burlington|Cambridge|Newton)\b", prompt, re.I
        )
        if listing_town and meta.get("commute_destination_town") and _dest_in_meta(
            meta, listing_town.group(1)
        ):
            if "commute" not in prompt.lower() and "drive" not in prompt.lower():
                notes.append("listing town became commute destination")

    return ("PASS" if not notes else "FAIL"), notes


def main() -> int:
    results: list[dict[str, Any]] = []
    section_stats: dict[str, dict[str, int]] = {}

    print(f"=== Phase 8.5 planner-first fresh 40 QA ===\nBase: {BASE}\n")

    for i, (section, case_id, prompt) in enumerate(PROMPTS, 1):
        print(f"[{i}/40] {case_id} ...", flush=True)
        entry = post_query(prompt)
        verdict, notes = evaluate(section, case_id, prompt, entry)
        inspection = _extract_inspection(entry)
        row = {
            "section": section,
            "id": case_id,
            "prompt": prompt,
            "verdict": verdict,
            "notes": notes,
            "inspection": inspection,
            "http_status": entry.get("http_status"),
            "latency_s": entry.get("latency_s"),
            "raw": entry.get("raw"),
        }
        results.append(row)
        sec = section_stats.setdefault(section, {"pass": 0, "fail": 0})
        sec["pass" if verdict == "PASS" else "fail"] += 1
        mark = "PASS" if verdict == "PASS" else "FAIL"
        print(f"  [{mark}] {case_id} http={inspection['http_status']} status={inspection['execution_status']} notes={notes}")

    http_500 = sum(1 for r in results if r.get("http_status") == 500)
    http_non200 = sum(1 for r in results if r.get("http_status") != 200)
    ok_count = sum(1 for r in results if (r.get("inspection") or {}).get("execution_status") == "ok")
    blocked = sum(
        1
        for r in results
        if (r.get("inspection") or {}).get("execution_status") in ("blocked", "out_of_scope", "not_found")
        or (r.get("inspection") or {}).get("trust_gate_blocks")
    )
    no_rows = sum(1 for r in results if (r.get("inspection") or {}).get("execution_status") == "no_rows")

    category_failures = {
        "dynamic_commute_cap": section_stats.get("A", {}).get("fail", 0),
        "shorthand_commute": section_stats.get("B", {}).get("fail", 0),
        "valid_compare_destination": section_stats.get("C", {}).get("fail", 0),
        "unsupported_compare_destination": section_stats.get("D", {}).get("fail", 0),
        "metadata_cleanup": section_stats.get("E", {}).get("fail", 0),
        "workplace_destination": section_stats.get("F", {}).get("fail", 0),
        "semantic_500": section_stats.get("G", {}).get("fail", 0),
        "listing_trust_gate": section_stats.get("H", {}).get("fail", 0),
    }

    total_fail = sum(1 for r in results if r["verdict"] == "FAIL")
    safe = total_fail == 0 and http_500 == 0

    report = {
        "summary": {
            "total_prompts": len(results),
            "http_500_count": http_500,
            "http_non_200_count": http_non200,
            "ok_count": ok_count,
            "blocked_refusal_count": blocked,
            "no_rows_fallback_count": no_rows,
            "verdict_pass": len(results) - total_fail,
            "verdict_fail": total_fail,
            "category_failures": category_failures,
            "safe_to_commit_manually": safe,
        },
        "results": results,
    }

    OUT.write_text(json.dumps(report, indent=2))
    print("\n=== Final report ===")
    for k, v in report["summary"].items():
        print(f"  {k}: {v}")
    print(f"\nSaved: {OUT}")
    return 0 if safe else 1


if __name__ == "__main__":
    raise SystemExit(main())
