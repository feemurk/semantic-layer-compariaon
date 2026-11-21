"""E1 reconciliation and sequential E3 timings for the S2 semantic models (SPEC § 8, § 9.2, § 9.3).

Runs queries/metrics/*.dax (22 metrics at the oracle grains) and queries/questions/*.dax (70 questions) against a
deployed model and compares each result with 01-spec/oracle/expected/<kind>/<id>.csv.

Transports
  rest  Power BI REST executeQueries. One query per call, at most 100,000 rows / 1,000,000 values, 120 calls per
        minute per user; service principals are refused for models with RLS roles, so this transport needs a user
        token (or a model without roles).
  xmla  deploy/XmlaQuery (ADOMD.NET over the XMLA endpoint, service principal connection string in
        SLC_XMLA_CONNECTION_STRING). This is the CI transport: it works with service principals on RLS models.

Comparison (SPEC § 5.3 rule 7, § 9.3)
  metrics    keyed on (grain, measure, member_1..member_3); an absent row equals a row whose value is NULL.
  questions  row multiset: every expected row must be matched by one actual row; an expected row may be absent only
             when all of its non-text values are NULL.
  Values use the oracle tolerances: integers exact, money (at most two decimals in the expected text) +/-0.005,
  other decimals +/-1e-6, NULL only matches NULL. Midnight datetimes compare as dates.

    python reconcile.py --transport xmla --dataset SLC_WWI_Import --select 'Q-W-*' --repeat 4 --out results.json

Exit status: 1 when any query errors, or with --fail-on-mismatch when any result differs.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import fnmatch
import json
import os
import re
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
STACK = HERE.parent
REPO = STACK.parents[1]
EXPECTED = REPO / "01-spec" / "oracle" / "expected"
QUERIES = STACK / "queries"
METRIC_KEY = 5
MONEY = Decimal("0.005")
RATIO = 1e-6
MIDNIGHT = re.compile(r"^(\d{4}-\d{2}-\d{2})T00:00:00(?:\.0+)?(?:Z)?$")


# --------------------------------------------------------------------------- values


def normalize(value):
    """JSON/ADOMD value -> comparable Python value (dates as ISO text, numbers as int/Decimal/float)."""
    if isinstance(value, str):
        m = MIDNIGHT.match(value)
        return m.group(1) if m else value
    return value


def to_text(value) -> str:
    value = normalize(value)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def values_match(actual, expected: str) -> bool:
    actual = normalize(actual)
    if actual is None or expected == "":
        return actual is None and expected == ""
    if isinstance(actual, bool):
        return to_text(actual) == expected.lower()
    if isinstance(actual, (int, float, Decimal)):
        try:
            want = Decimal(expected)
        except InvalidOperation:
            return False
        have = Decimal(str(actual))
        if want == want.to_integral_value() and "." not in expected and isinstance(actual, int):
            return have == want
        places = len(expected.split(".")[1]) if "." in expected else 0
        if places <= 2:
            return abs(have - want) <= MONEY
        return abs(float(have) - float(want)) <= RATIO
    return to_text(actual) == expected


def is_text(expected: str) -> bool:
    try:
        Decimal(expected)
        return False
    except InvalidOperation:
        return expected.lower() not in {"true", "false"}


# --------------------------------------------------------------------------- comparison


@dataclass
class Outcome:
    query_id: str
    kind: str
    rows: int = 0
    seconds: list[float] = field(default_factory=list)
    error: str | None = None
    missing: int = 0
    extra: int = 0
    different: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def matches(self) -> bool:
        return self.error is None and not (self.missing or self.extra or self.different or self.problems)

    def timings(self) -> tuple[float | None, float | None]:
        if not self.seconds:
            return None, None
        warm = self.seconds[1:] or self.seconds
        return round(self.seconds[0], 4), round(statistics.median(warm), 4)


def read_expected(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    return rows[0], rows[1:]


def compare_metric(columns: list[str], rows: list[list], expected: Path, out: Outcome) -> None:
    header, want_rows = read_expected(expected)
    if [c.lower() for c in columns] != [h.lower() for h in header]:
        out.problems.append(f"columns {columns} != expected {header}")
        return
    want = {tuple(r[:METRIC_KEY]): r[METRIC_KEY] for r in want_rows}
    got = {tuple(to_text(v) for v in r[:METRIC_KEY]): r[METRIC_KEY] for r in rows}
    if len(got) != len(rows):
        out.problems.append(f"{len(rows) - len(got)} duplicate keys in result")
    for key in want.keys() - got.keys():
        if want[key] != "":  # rule 7: absent == NULL
            out.missing += 1
            out.problems.append(f"missing {key} expected {want[key]!r}")
    for key in got.keys() - want.keys():
        if normalize(got[key]) is not None:
            out.extra += 1
            out.problems.append(f"extra {key} value {to_text(got[key])!r}")
    for key in want.keys() & got.keys():
        if not values_match(got[key], want[key]):
            out.different += 1
            out.problems.append(f"{key}: {to_text(got[key])!r} != expected {want[key]!r}")
    del out.problems[25:]


def compare_question(columns: list[str], rows: list[list], expected: Path, out: Outcome) -> None:
    header, want_rows = read_expected(expected)
    if [c.lower() for c in columns] != [h.lower() for h in header]:
        out.problems.append(f"columns {columns} != expected {header}")
        return
    unmatched = list(range(len(rows)))
    for exp in want_rows:
        hit = next((i for i in unmatched if all(values_match(a, e) for a, e in zip(rows[i], exp))), None)
        if hit is not None:
            unmatched.remove(hit)
            continue
        if all(e == "" or is_text(e) for e in exp) and any(e == "" for e in exp):
            continue  # rule 7: a row whose values are all NULL may be absent
        out.missing += 1
        out.problems.append(f"missing row {exp}")
    for i in unmatched:
        out.extra += 1
        out.problems.append(f"extra row {[to_text(v) for v in rows[i]]}")
    del out.problems[25:]


# --------------------------------------------------------------------------- transports


class RestTransport:
    """Power BI REST executeQueries (POST /groups/{ws}/datasets/{id}/executeQueries)."""

    def __init__(self, workspace_id: str, dataset_id: str, impersonate: str | None):
        import requests
        from azure.identity import DefaultAzureCredential

        token = DefaultAzureCredential().get_token("https://analysis.windows.net/powerbi/api/.default").token
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/datasets/{dataset_id}/executeQueries"
        self.impersonate = impersonate

    def execute(self, dax: str) -> tuple[list[str], list[list]]:
        body = {"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}}
        if self.impersonate:
            body["impersonatedUserName"] = self.impersonate
        r = self.session.post(self.url, json=body, timeout=600)
        if r.status_code != 200:
            raise RuntimeError(f"executeQueries {r.status_code}: {r.text[:400]}")
        result = r.json()["results"][0]
        if "error" in result:
            raise RuntimeError(json.dumps(result["error"])[:400])
        table = result["tables"][0]
        rows = table.get("rows", [])
        columns = [c.strip("[]").split("[")[-1].rstrip("]") for c in (rows[0].keys() if rows else [])]
        if not rows:
            columns = []
        return columns, [list(r.values()) for r in rows]


class XmlaTransport:
    """deploy/XmlaQuery, built once with `dotnet build -c Release`."""

    def __init__(self) -> None:
        if not os.environ.get("SLC_XMLA_CONNECTION_STRING"):
            raise SystemExit("SLC_XMLA_CONNECTION_STRING is not set")
        dll = HERE / "XmlaQuery" / "bin" / "Release" / "net8.0" / "XmlaQuery.dll"
        if not dll.exists():
            subprocess.run(["dotnet", "build", "-c", "Release", str(HERE / "XmlaQuery")], check=True)
        self.dll = dll

    def execute(self, dax: str) -> tuple[list[str], list[list]]:
        tmp = HERE / ".query.dax"
        tmp.write_text(dax)
        try:
            p = subprocess.run(["dotnet", str(self.dll), str(tmp)], capture_output=True, text=True, timeout=900)
        finally:
            tmp.unlink(missing_ok=True)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.strip()[:400])
        doc = json.loads(p.stdout, parse_float=Decimal)
        return [c.strip("[]") for c in doc["columns"]], doc["rows"]


# --------------------------------------------------------------------------- run


def load_queries(dataset: str, select: str) -> list[tuple[str, str, str]]:
    sys.path.insert(0, str(STACK))
    from lint_model import model_for_query

    out = []
    for kind in ("metrics", "questions"):
        for path in sorted((QUERIES / kind).glob("*.dax")):
            if fnmatch.fnmatch(path.stem, select) and model_for_query(path) == dataset:
                out.append((path.stem, kind, path.read_text(encoding="utf-8")))
    return out


def run(transport, queries: list[tuple[str, str, str]], repeat: int) -> list[Outcome]:
    results = []
    for qid, kind, dax in queries:
        out = Outcome(qid, kind)
        try:
            columns, rows = [], []
            for _ in range(max(1, repeat)):
                t0 = time.perf_counter()
                columns, rows = transport.execute(dax)
                out.seconds.append(time.perf_counter() - t0)
            out.rows = len(rows)
            expected = EXPECTED / kind / f"{qid}.csv"
            (compare_metric if kind == "metrics" else compare_question)(columns, rows, expected, out)
        except Exception as exc:  # recorded per query; the run continues
            out.error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:400]}"
        cold, warm = out.timings()
        status = "ERROR" if out.error else ("ok" if out.matches else "DIFF")
        print(f"{status:5} {qid:14} rows={out.rows:<7} cold={cold or 0:8.3f}s warm={warm or 0:8.3f}s "
              f"missing={out.missing} extra={out.extra} different={out.different} {out.error or ''}", flush=True)
        for problem in out.problems[:5]:
            print(f"        {problem}")
        results.append(out)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", required=True, choices=["rest", "xmla"])
    parser.add_argument("--dataset", required=True, help="model name, e.g. SLC_WWI_Import")
    parser.add_argument("--workspace-id", help="rest transport")
    parser.add_argument("--dataset-id", help="rest transport")
    parser.add_argument("--impersonate", help="rest transport: impersonatedUserName (RLS checks, E8)")
    parser.add_argument("--select", default="*")
    parser.add_argument("--repeat", type=int, default=4, help="runs per query; the first is reported as cold")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--fail-on-mismatch", action="store_true")
    args = parser.parse_args()

    dataset = "WWI" if "_WWI_" in args.dataset else "NYC"
    if args.transport == "rest":
        if not (args.workspace_id and args.dataset_id):
            raise SystemExit("--workspace-id and --dataset-id are required for the rest transport")
        transport = RestTransport(args.workspace_id, args.dataset_id, args.impersonate)
    else:
        transport = XmlaTransport()
    run_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    results = run(transport, load_queries(dataset, args.select), args.repeat)
    errors = [r for r in results if r.error]
    diffs = [r for r in results if not r.error and not r.matches]
    summary = {"stack": "powerbi-tabular", "dataset": args.dataset, "transport": args.transport, "queries": len(results),
               "errors": len(errors), "mismatched": len(diffs), "matched": len(results) - len(errors) - len(diffs),
               "repeat": args.repeat, "run_at_utc": run_at}
    print(json.dumps(summary))
    if args.out:
        args.out.write_text(json.dumps({"summary": summary, "results": [
            {"query_id": r.query_id, "kind": r.kind, "rows": r.rows, "cold_seconds": r.timings()[0],
             "warm_median_seconds": r.timings()[1], "error": r.error, "missing": r.missing, "extra": r.extra,
             "different": r.different, "problems": r.problems} for r in results]}, indent=1))
    if errors or (args.fail_on_mismatch and diffs):
        sys.exit(1)


if __name__ == "__main__":
    main()
