#!/usr/bin/env python3
"""Phase 8.5 diverse regression — 40 prompts, save raw JSON responses."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent / "phase8_5_diverse_regression_responses.json"

PROMPTS: list[tuple[str, str]] = [
    ("A", "Find towns like Westford but cheaper."),
    ("A", "Show me suburbs similar to Sharon with lower home prices."),
    ("A", "What towns are comparable to Acton but more affordable?"),
    ("A", "Find places similar to Lexington but not as expensive."),
    ("A", "Recommend alternatives to Wayland with better affordability."),
    ("B", "Compare Westford and Reading for commute to Cambridge."),
    ("B", "Compare Sharon and Milton for commute to Newton."),
    ("B", "Compare Bedford and Lexington for commute to Waltham."),
    ("B", "Compare Wayland and Sudbury for commute to Framingham."),
    ("B", "Compare Melrose and Stoneham for commute to Burlington."),
    ("C", "Open Westford."),
    ("C", "Tell me about Sharon."),
    ("C", "Compare Lexington and Newton."),
    ("C", "Show details for Milton."),
    ("C", "What is the home price and school score for Bedford?"),
    ("D", "Find safe towns within 28 minutes of Lexington."),
    ("D", "Find towns under 850k within 32 minutes of Somerville."),
    ("D", "Find good school towns within 25 minutes of Brookline."),
    ("D", "Find affordable suburbs within 30 minutes of Quincy."),
    ("D", "Find low-crime towns within 35 minutes of Salem."),
    ("E", "Find affordable suburbs with good schools near Boston."),
    ("E", "Which safe towns under 800k have a reasonable Boston commute?"),
    ("E", "Compare Sharon and Reading."),
    ("E", "What is the commute from Bedford to Boston?"),
    ("E", "Open Burlington."),
    ("F", "What is the commute from Acton to Providence?"),
    ("F", "Find towns within 30 minutes of Manhattan."),
    ("F", "Compare Reading and Waltham for commute to Hartford."),
    ("F", "Find safe suburbs within 25 minutes of downtown Boston office."),
    ("F", "How long is the drive from Maynard to Logan Airport?"),
    ("G", "Show active Redfin listings under 900k in Waltham."),
    ("G", "Can you find current homes for sale in Lexington?"),
    ("G", "Give me Zillow houses in Brookline under 1.2M."),
    ("G", "MLS listings near Cambridge with good schools."),
    ("G", "Which houses are on the market in Newton right now?"),
    ("H", "I work in Cambridge and want safe towns under 900k."),
    ("H", "My office is in Waltham. Find towns with strong schools under 1M."),
    ("H", "I need to commute to Burlington from a cheaper town with good schools."),
    ("H", "Best suburbs if I care about commute to Newton more than schools."),
    ("H", "Find towns where Cambridge commute is under 35 minutes and schools are decent."),
]


def post_query(prompt: str) -> dict[str, Any]:
    body = json.dumps({"prompt": prompt, "save_audit": False, "debug": False}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/query",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = json.loads(resp.read())
            return {"http_status": resp.status, "raw": raw}
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read())
        except Exception:
            detail = {"detail": exc.reason}
        return {"http_status": exc.code, "raw": detail, "error": str(exc)}


def _pick_data(m: dict[str, Any]) -> dict[str, Any]:
    data = m.get("data") or m
    return data if isinstance(data, dict) else {}


def summarize_match(m: dict[str, Any]) -> dict[str, Any]:
    data = _pick_data(m)
    return {
        "name": m.get("name") or data.get("name"),
        "latest_home_price": data.get("latest_home_price"),
        "drive_minutes_to_destination": data.get("drive_minutes_to_destination"),
        "commute_destination_label": data.get("commute_destination_label"),
        "drive_minutes_to_boston": data.get("drive_minutes_to_boston"),
    }


def max_minutes_from_prompt(prompt: str) -> int | None:
    m = re.search(r"\bwithin\s+(\d+)\s+minutes?\b", prompt, re.I)
    return int(m.group(1)) if m else None


def evaluate(section: str, prompt: str, entry: dict[str, Any]) -> tuple[str, str]:
    http = entry.get("http_status")
    raw = entry.get("raw") or {}
    status = raw.get("execution_status")
    gate = raw.get("trust_gate")
    meta = raw.get("metadata") or {}
    dest = meta.get("commute_destination")
    is_default = meta.get("commute_destination_is_default")
    dest_town = meta.get("commute_destination_town")
    top = raw.get("top_matches") or []
    answer = str(raw.get("answer") or "")

    if http == 500:
        return "FAIL", "HTTP 500"
    if http != 200:
        return "FAIL", f"HTTP {http}"

    if section == "A":
        if "Traceback" in answer or "exception" in answer.lower():
            return "FAIL", "raw exception in answer"
        if status in ("ok", "no_rows", "partial", "out_of_scope"):
            return "PASS", status or "ok"
        return "WARN", status or "?"

    if section == "B":
        if gate == "multi_compare":
            return "FAIL", "multi_compare block"
        if status != "ok":
            return "FAIL", f"status={status}"
        m = re.search(r"commute to (\w+)", prompt, re.I)
        expected = m.group(1) if m else None
        if expected and dest and expected.lower() not in str(dest).lower():
            return "FAIL", f"dest={dest}"
        return "PASS", f"dest={dest}"

    if section == "C":
        if is_default is not True:
            return "FAIL", f"is_default={is_default}"
        if dest_town is not None:
            return "FAIL", f"dest_town={dest_town}"
        if status != "ok":
            return "FAIL", status or "?"
        return "PASS", "Boston default"

    if section == "D":
        m = re.search(r"minutes of ([A-Za-z ]+?)\.", prompt)
        if not m:
            m = re.search(r"minutes of ([A-Za-z ]+)$", prompt)
        expected = (m.group(1).strip() if m else "").split()[-1]
        if is_default is not False:
            return "FAIL", f"default={is_default}"
        if expected and dest and expected.lower() not in str(dest).lower():
            return "FAIL", f"dest={dest}"
        limit = max_minutes_from_prompt(prompt)
        if limit and top:
            over = []
            for row in top:
                d = _pick_data(row)
                mins = d.get("drive_minutes_to_destination")
                if mins is not None and mins > limit:
                    over.append((row.get("name"), mins))
            if over:
                return "FAIL", f"over limit: {over[:2]}"
        if status != "ok":
            return "FAIL", status or "?"
        return "PASS", f"{len(top)} matches"

    if section == "E":
        if status not in ("ok", "partial"):
            return "FAIL", status or "?"
        if "commute from Bedford to Boston" in prompt:
            if "41.7" not in answer and "41" not in answer:
                return "WARN", "Boston minutes not in answer"
            return "PASS", "Boston commute"
        if is_default is not True:
            return "FAIL", f"is_default={is_default}"
        if dest_town is not None:
            return "FAIL", f"dest_town={dest_town}"
        return "PASS", "Boston default"

    if section == "F":
        if status == "ok" and re.search(r"\b\d+\s*(?:min|minute)", answer, re.I):
            if any(x in prompt for x in ("Providence", "Manhattan", "Hartford", "Logan")):
                return "FAIL", "invented commute minutes"
        if status in ("blocked", "out_of_scope", "no_rows"):
            return "PASS", status
        if "office" in prompt.lower() and status == "ok":
            return "PASS", "Boston default fallback"
        if status == "ok" and not re.search(r"\b\d+\s*(?:min|minute)", answer, re.I):
            return "PASS", "ok without invented minutes"
        return "WARN", status or "?"

    if section == "G":
        if status == "out_of_scope" or gate:
            return "PASS", status or gate or "refused"
        if "listing" in answer.lower() or "zillow" in answer.lower() or "mls" in answer.lower():
            if status == "ok":
                return "FAIL", "accepted listing query"
        if status in ("blocked", "out_of_scope"):
            return "PASS", status
        if is_default is not True and dest_town:
            return "FAIL", f"wrong dest_town={dest_town}"
        return "WARN", status or "?"

    if section == "H":
        if http != 200:
            return "FAIL", f"HTTP {http}"
        if gate in ("commute_destination_rank", "commute_destination_lookup"):
            return "FAIL", gate
        if status not in ("ok", "partial", "no_rows"):
            return "FAIL", status or "?"
        if is_default is False and not dest:
            return "FAIL", "missing destination"
        return "PASS", f"dest={dest}"

    return "PASS", status or "ok"


def main() -> None:
    results: list[dict[str, Any]] = []
    print(f"Running {len(PROMPTS)} prompts against {BASE} ...\n")

    for i, (section, prompt) in enumerate(PROMPTS, 1):
        print(f"[{i}/{len(PROMPTS)}] ({section}) {prompt[:70]}...", flush=True)
        t0 = time.perf_counter()
        entry = post_query(prompt)
        elapsed = round(time.perf_counter() - t0, 1)
        raw = entry.get("raw") or {}
        meta = raw.get("metadata") or {}
        top = raw.get("top_matches") or []
        result, notes = evaluate(section, prompt, entry)
        record = {
            "index": i,
            "section": section,
            "prompt": prompt,
            "latency_s": elapsed,
            "http_status": entry.get("http_status"),
            "execution_status": raw.get("execution_status"),
            "trust_gate": raw.get("trust_gate"),
            "source": raw.get("source"),
            "answer": raw.get("answer"),
            "error": raw.get("error") or entry.get("error"),
            "metadata": meta,
            "top_matches_count": len(top),
            "top_matches_sample": [summarize_match(m) for m in top[:3]],
            "comparison": raw.get("comparison"),
            "evaluation_result": result,
            "evaluation_notes": notes,
            "raw_response": raw,
        }
        results.append(record)

    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
