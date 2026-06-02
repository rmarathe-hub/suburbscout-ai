#!/usr/bin/env python3
"""Day 2 Step 1 verification: dependencies and config env vars."""

from __future__ import annotations

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


def main() -> None:
    print("=== Day 2 Step 1: Dependencies & Config ===\n")

    # 1. Package imports
    packages = [
        ("agent_framework", "agent-framework"),
        ("agent_framework.foundry", "agent-framework-foundry"),
        ("agent_framework.openai", "agent-framework-openai"),
    ]
    for module, label in packages:
        try:
            __import__(module)
            print(f"  PASS: import {module} ({label})")
        except ImportError as exc:
            print(f"  FAIL: import {module} — {exc}")
            sys.exit(1)

    # 2. Config / dotenv
    from app import config

    checks = [
        ("FOUNDRY_PROJECT_ENDPOINT", config.FOUNDRY_PROJECT_ENDPOINT),
        ("AZURE_OPENAI_API_KEY", config.AZURE_OPENAI_API_KEY),
        ("AZURE_OPENAI_DEPLOYMENT_NAME", config.AZURE_OPENAI_DEPLOYMENT_NAME),
        ("AZURE_OPENAI_ENDPOINT (fallback)", config.AZURE_OPENAI_ENDPOINT),
    ]
    print()
    for label, value in checks:
        if value:
            masked = value[:20] + "..." if label.endswith("KEY") and len(value) > 20 else value
            print(f"  PASS: {label} is set ({masked})")
        else:
            print(f"  FAIL: {label} is empty — check agent_service/.env")
            sys.exit(1)

    print(f"\n  Agent name constant: {config.AGENT_NAME}")
    print("\nStep 1 verification: PASSED")
    print("Next: Step 2 — app/tools.py (five core tools)")


if __name__ == "__main__":
    main()
