#!/usr/bin/env python3
"""End-to-end offline demo: define -> compile -> govern -> cache -> lineage.

    python examples/run_demo.py

Compiles revenue by region from the default semantic model, runs it
against the deterministic synthetic dataset, shows the repeat query
served from cache, prints lineage and governance, and shows the
draft / deprecated / fan-out gates refusing unsafe queries.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from semantic_layer.demo import run_demo  # noqa: E402


def main() -> int:
    report = run_demo()
    print(json.dumps(report, indent=2, default=str))
    ok = (report["second_query_from_cache"] and report["governance_ok"]
          and report["revenue_by_region"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
