"""Fail if any model/seed column in the warehouse catalog lacks a business definition in dbt YAML."""

from __future__ import annotations

import json
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "dbt" / "target"


def main() -> int:
    manifest = json.loads((TARGET / "manifest.json").read_text())
    catalog = json.loads((TARGET / "catalog.json").read_text())
    missing, total = [], 0
    for uid, node in manifest["nodes"].items():
        if node["resource_type"] not in ("model", "seed"):
            continue
        if not node.get("description"):
            missing.append(f"{uid} (model description)")
        documented = {c.lower() for c, v in node["columns"].items() if v.get("description")}
        for col in catalog["nodes"].get(uid, {}).get("columns", {}):
            total += 1
            if col.lower() not in documented:
                missing.append(f"{uid}.{col}")
    print(f"Documented columns: {total - len([m for m in missing if 'model description' not in m])}/{total}")
    for m in missing:
        print("  MISSING:", m)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
