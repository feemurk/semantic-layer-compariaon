#!/usr/bin/env python3
"""Compare flattened S1 results (CSV written by scripts/reconcile.ps1) with the oracle (SPEC § 9.2, § 9.3).

Metrics (oracle contract grain, measure, member_1..3, value) are compared keyed on the first five columns. SPEC § 5.3
rule 7 and § 9.3: an absent row equals a NULL value, and the member labels NULL, blank and "Unknown" are equivalent.
Questions are compared as multisets of rows under the oracle tolerances (run_oracle.values_match): every actual row
must match a distinct expected row, an unmatched expected row is tolerated only when all its values are NULL.

    python3 tools/compare.py --actual out/        # out/metrics/*.csv, out/questions/*.csv; exit 1 on any difference
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ORACLE = HERE.parents[1] / "01-spec" / "oracle"
sys.path.insert(0, str(ORACLE))

import run_oracle  # noqa: E402

KEY = ["grain", "measure", "member_1", "member_2", "member_3"]
NULL_LABELS = {"", "Unknown"}


@dataclass
class Outcome:
    query_id: str
    kind: str
    missing: int = 0
    extra: int = 0
    different: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def matches(self) -> bool:
        return not (self.missing or self.extra or self.different or self.problems)


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    return rows[0], rows[1:]


def text_match(actual: str, expected: str) -> bool:
    """Values arrive as text from the flattened CSV; numbers compare under the oracle tolerances."""
    if actual == "" or expected == "":
        return actual == expected
    try:
        a, e = float(actual), float(expected)
    except ValueError:
        return actual == expected
    if "." not in expected and "." not in actual and "e" not in expected.lower():
        return int(a) == int(e) and a == e
    tolerance = float(run_oracle.MONEY_TOLERANCE) if len(expected.split(".")[-1]) <= 2 else run_oracle.RATIO_TOLERANCE
    return abs(a - e) <= tolerance


def label(value: str) -> str:
    return "" if value in NULL_LABELS else value


def compare_metric(actual: Path, expected: Path, query_id: str) -> Outcome:
    out = Outcome(query_id, "metrics")
    a_head, a_rows = read_csv(actual)
    e_head, e_rows = read_csv(expected)
    if a_head != e_head or e_head[:5] != KEY:
        out.problems.append(f"header {a_head} != {e_head}")
        return out
    want = {tuple(label(v) if i > 1 else v for i, v in enumerate(r[:5])): r[5] for r in e_rows}
    got: dict[tuple, str] = {}
    for r in a_rows:
        key = tuple(label(v) if i > 1 else v for i, v in enumerate(r[:5]))
        if key in got:
            out.problems.append(f"duplicate key {key}")
        got[key] = r[5]
    for key in want.keys() - got.keys():
        if want[key] != "":
            out.missing += 1
            if len(out.problems) < 25:
                out.problems.append(f"missing {key} expected {want[key]!r}")
    for key in got.keys() - want.keys():
        if got[key] != "":
            out.extra += 1
            if len(out.problems) < 25:
                out.problems.append(f"extra {key} value {got[key]!r}")
    for key in want.keys() & got.keys():
        if not text_match(got[key], want[key]):
            out.different += 1
            if len(out.problems) < 25:
                out.problems.append(f"{key}: {got[key]!r} != expected {want[key]!r}")
    return out


def compare_question(actual: Path, expected: Path, query_id: str) -> Outcome:
    out = Outcome(query_id, "questions")
    a_head, a_rows = read_csv(actual)
    e_head, e_rows = read_csv(expected)
    if a_head != e_head:
        out.problems.append(f"header {a_head} != {e_head}")
        return out
    used: set[int] = set()
    for row in a_rows:
        norm = [label(v) for v in row]
        match = next((i for i, e in enumerate(e_rows) if i not in used
                      and all(text_match(a, label(w)) for a, w in zip(norm, e))), None)
        if match is None:
            out.extra += 1
            if len(out.problems) < 25:
                out.problems.append(f"row {row} not in the oracle answer")
        else:
            used.add(match)
    for i, e in enumerate(e_rows):
        if i not in used:
            out.missing += 1
            if len(out.problems) < 25:
                out.problems.append(f"expected row {e} not returned")
    return out


def compare_dir(actual_dir: Path, select: str = "*") -> list[Outcome]:
    outcomes = []
    for kind, fn in (("metrics", compare_metric), ("questions", compare_question)):
        for expected in sorted((ORACLE / "expected" / kind).glob("*.csv")):
            if not fnmatch.fnmatch(expected.stem, select):
                continue
            actual = actual_dir / kind / expected.name
            if not actual.exists():
                o = Outcome(expected.stem, kind)
                o.problems.append(f"missing result file {actual}")
                outcomes.append(o)
            else:
                outcomes.append(fn(actual, expected, expected.stem))
    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--select", default="*", help="glob over query ids")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    outcomes = compare_dir(args.actual, args.select)
    for o in outcomes:
        status = "ok" if o.matches else "DIFF"
        print(f"{status:4} {o.kind:9} {o.query_id:12} missing={o.missing} extra={o.extra} different={o.different}")
        for p in o.problems[:5]:
            print(f"       {p}")
    summary = {"queries": len(outcomes), "matched": sum(o.matches for o in outcomes),
               "mismatched": sum(not o.matches for o in outcomes)}
    print(json.dumps(summary))
    if args.report:
        args.report.write_text(json.dumps({"summary": summary, "results": [o.__dict__ for o in outcomes]}, indent=1))
    if summary["mismatched"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
