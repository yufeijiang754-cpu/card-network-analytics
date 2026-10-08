"""Render the dbt DAG (sources, seeds, models) from manifest.json as a Mermaid diagram in docs/LINEAGE.md."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STYLE = {
    "source": "fill:#fde2e2,stroke:#c0392b",
    "seed": "fill:#eeeeee,stroke:#7f8c8d",
    "staging": "fill:#e3f2fd,stroke:#1e88e5",
    "intermediate": "fill:#fff8e1,stroke:#f9a825",
    "marts": "fill:#e8f5e9,stroke:#43a047",
    "dq": "fill:#f3e5f5,stroke:#8e24aa",
}


def main() -> None:
    m = json.loads((ROOT / "dbt/target/manifest.json").read_text())
    nodes = {}
    for uid, s in m["sources"].items():
        nodes[uid] = (f"raw.{s['name']}", "source")
    for uid, n in m["nodes"].items():
        if n["resource_type"] == "seed":
            nodes[uid] = (n["name"], "seed")
        elif n["resource_type"] == "model":
            nodes[uid] = (n["name"], n["schema"])
    ids = {uid: f"n{i}" for i, uid in enumerate(sorted(nodes))}
    lines = ["flowchart LR"]
    for uid, (label, kind) in sorted(nodes.items()):
        lines.append(f'    {ids[uid]}["{label}"]:::{kind}')
    for uid, n in m["nodes"].items():
        if n["resource_type"] != "model":
            continue
        for parent in n["depends_on"]["nodes"]:
            if parent in ids:
                lines.append(f"    {ids[parent]} --> {ids[uid]}")
    for kind, style in STYLE.items():
        lines.append(f"    classDef {kind} {style}")
    body = "\n".join(lines)
    md = (
        "# Data Lineage\n\n"
        "Auto-generated from `dbt/target/manifest.json` by `scripts/export_lineage.py`. For the interactive\n"
        "version with column-level documentation run `make docs` (dbt docs serve).\n\n"
        "Colour key: red = raw sources, grey = reference seeds, blue = staging, yellow = intermediate,\n"
        "purple = data quality, green = marts.\n\n"
        f"```mermaid\n{body}\n```\n"
    )
    (ROOT / "docs/LINEAGE.md").write_text(md)
    print(f"docs/LINEAGE.md written ({len(nodes)} nodes)")


if __name__ == "__main__":
    main()
