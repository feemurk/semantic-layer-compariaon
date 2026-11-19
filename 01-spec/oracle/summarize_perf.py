#!/usr/bin/env python3
"""Merge per-engine oracle timings into perf/summary.csv and print the report tables.

Inputs: perf/*.json written by run_oracle.py --perf; files of the same engine are merged by query id.
Output: perf/summary.csv with one row per query and, per engine, first-run and warm-median seconds.
Standard library only.

    python summarize_perf.py perf/duckdb.json perf/spark.json
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import sys
from pathlib import Path

ORACLE = Path(__file__).resolve().parent


def classify(query_id: str, kind: str) -> tuple[str, str]:
    """(dataset, class) where class is the metric tier or the question type."""
    if kind == "metrics":
        dataset = "WWI" if query_id[2] == "W" or query_id.startswith("W-") else "NYC"
        tier = {"B": "Base", "S": "Simple", "M": "Medium", "C": "Complex"}[
            "B" if query_id.startswith("B-") else query_id[2]]
        return dataset, tier
    m = re.match(r"Q-([WN])-[SMC]\d-(P|D\d)$", query_id)
    if m:
        return ("WWI" if m.group(1) == "W" else "NYC"), m.group(2)
    n = int(query_id[3:])
    return ("WWI" if n <= 5 else "NYC"), "AH"


def main(paths: list[str]) -> None:
    engines = {}
    for p in paths:
        doc = json.loads(Path(p).read_text())
        engines.setdefault(doc["summary"]["engine"], {}).update({r["query_id"]: r for r in doc["results"]})
    names = list(engines)
    ids = sorted({q for e in engines.values() for q in e})
    out = ORACLE / "perf" / "summary.csv"
    rows = []
    for qid in ids:
        any_r = next(e[qid] for e in engines.values() if qid in e)
        dataset, klass = classify(qid, any_r["kind"])
        row = {"query_id": qid, "kind": any_r["kind"], "dataset": dataset, "class": klass, "rows": any_r["rows"]}
        for n in names:
            r = engines[n].get(qid, {})
            row[f"{n}_first_s"] = r.get("first_run_seconds")
            row[f"{n}_warm_median_s"] = r.get("warm_median_seconds")
            row[f"{n}_status"] = "error" if r.get("error") else ("mismatch" if r.get("mismatches") else "ok")
        rows.append(row)
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    def stat(sel, col):
        vals = [r[col] for r in rows if sel(r) and r[col] is not None]
        if not vals:
            return "—"
        return f"{statistics.median(vals):.3f} / {max(vals):.3f} / {sum(vals):.1f}"

    groups = [
        ("WWI metrics", lambda r: r["kind"] == "metrics" and r["dataset"] == "WWI"),
        ("NYC metrics", lambda r: r["kind"] == "metrics" and r["dataset"] == "NYC"),
        ("WWI questions", lambda r: r["kind"] == "questions" and r["dataset"] == "WWI"),
        ("NYC questions", lambda r: r["kind"] == "questions" and r["dataset"] == "NYC"),
        ("Predefined (P)", lambda r: r["class"] == "P"),
        ("Diagnostic (D1-D4)", lambda r: r["class"].startswith("D")),
        ("Ad hoc (AH)", lambda r: r["class"] == "AH"),
        ("All 92", lambda r: True),
    ]
    print("| Group | Queries | " + " | ".join(f"{n} warm median / max / total (s)" for n in names) + " |")
    print("|---|---|" + "---|" * len(names))
    for label, sel in groups:
        count = sum(1 for r in rows if sel(r))
        print(f"| {label} | {count} | " + " | ".join(stat(sel, f"{n}_warm_median_s") for n in names) + " |")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
