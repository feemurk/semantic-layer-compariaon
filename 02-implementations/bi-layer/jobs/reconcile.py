#!/usr/bin/env python3
"""E1 reconciliation and E3 sequential timings for stack S3 through the VizQL Data Service (SPEC § 8, § 9.2, § 9.3).

For each queries/metrics/<ID>.json branch (and each anchor of an As-of Date branch) the runner issues one VDS query,
maps the result to the oracle contract (grain, measure, member_1..3, value) and compares it keyed on the grouping
columns with 01-spec/oracle/expected/metrics/<ID>.csv. For each queries/questions/<ID>.json it issues every VDS query,
loads the results into typed DuckDB tables, runs the assembly and compares the rows positionally with
01-spec/oracle/expected/questions/<ID>.csv. Tolerances are the oracle's own (run_oracle.values_match); a NULL value and
an absent row are equivalent (SPEC § 5.3 rule 7).

Environment for a live run: TABLEAU_SERVER, TABLEAU_SITE, TABLEAU_PAT_NAME, TABLEAU_PAT_SECRET (an identity with View,
Connect and API Access on the published data sources). Results are written as JSON to --out.

    python3 jobs/reconcile.py --select 'Q-*-P' --fail-on-mismatch --out results/reconcile.json
"""

from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import fnmatch
import json
import os
import statistics
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[1]
ORACLE = REPO / "01-spec" / "oracle"
for p in (HERE, ORACLE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import run_oracle  # noqa: E402

KEY = ["grain", "measure", "member_1", "member_2", "member_3"]


# --------------------------------------------------------------------------- executors

def convert(value, duck_type: str):
    """A VDS JSON value to the Python value of its declared output type."""
    if value is None:
        return None
    if duck_type == "DATE":
        return dt.date.fromisoformat(str(value)[:10])
    if duck_type == "TIMESTAMP":
        return dt.datetime.fromisoformat(str(value).replace("Z", ""))
    if duck_type == "BOOLEAN":
        return value if isinstance(value, bool) else str(value).lower() == "true"
    if duck_type == "BIGINT":
        return int(round(float(value)))
    if duck_type == "DOUBLE":
        return float(value)
    return str(value)


class VdsExecutor:
    """Live executor: Tableau REST sign-in (personal access token) plus VizQL Data Service query-datasource."""

    def __init__(self):
        import tableauserverclient as TSC

        self.server = TSC.Server(os.environ["TABLEAU_SERVER"], use_server_version=True)
        auth = TSC.PersonalAccessTokenAuth(os.environ["TABLEAU_PAT_NAME"], os.environ["TABLEAU_PAT_SECRET"],
                                           site_id=os.environ.get("TABLEAU_SITE", ""))
        self.server.auth.sign_in(auth)
        self.url = os.environ["TABLEAU_SERVER"].rstrip("/") + "/api/v1/vizql-data-service/query-datasource"
        self._luids: dict[str, str] = {}

    def luid(self, name: str) -> str:
        if name not in self._luids:
            import tableauserverclient as TSC

            opts = TSC.RequestOptions()
            opts.filter.add(TSC.Filter(TSC.RequestOptions.Field.Name, TSC.RequestOptions.Operator.Equals, name))
            items, _ = self.server.datasources.get(opts)
            if len(items) != 1:
                raise LookupError(f"expected one published data source named {name!r}, found {len(items)}")
            self._luids[name] = items[0].id
        return self._luids[name]

    def execute(self, spec: dict) -> tuple[list[str], list[tuple]]:
        body = {"datasource": {"datasourceLuid": self.luid(spec["datasource"])}, "query": spec["query"],
                "options": {"returnFormat": "OBJECTS", "disaggregate": False}}
        req = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "Accept": "application/json",
                                              "X-Tableau-Auth": self.server.auth_token})
        with urllib.request.urlopen(req, timeout=600) as resp:
            payload = json.loads(resp.read())
        if payload.get("error"):
            raise RuntimeError(f"VDS error: {payload['error']}")
        cols = list(spec["output"])
        rows = [tuple(convert(obj.get(c), spec["output"][c]) for c in cols) for obj in payload.get("data", [])]
        return cols, rows

    def close(self) -> None:
        self.server.auth.sign_out()


# --------------------------------------------------------------------------- results

@dataclass
class Outcome:
    query_id: str
    kind: str
    rows: int = 0
    vds_calls: int = 0
    seconds: list[float] = field(default_factory=list)
    error: str | None = None
    missing: int = 0
    extra: int = 0
    different: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def matches(self) -> bool:
        return self.error is None and not (self.missing or self.extra or self.different or self.problems)

    def as_dict(self) -> dict:
        warm = self.seconds[1:] or self.seconds
        return {"query_id": self.query_id, "kind": self.kind, "rows": self.rows, "vds_calls": self.vds_calls,
                "cold_seconds": round(self.seconds[0], 4) if self.seconds else None,
                "warm_median_seconds": round(statistics.median(warm), 4) if warm else None,
                "error": self.error, "missing": self.missing, "extra": self.extra, "different": self.different,
                "problems": self.problems[:25], "matches_oracle": self.matches}


def typed(value, kind: str):
    """Python type that selects the SPEC § 9.3 tolerance in run_oracle.values_match."""
    if value is None:
        return None
    if kind == "money":
        return Decimal(str(round(float(value), 6)))
    if kind == "count":
        return int(round(float(value)))
    return float(value)


def metric_rows(spec: dict, executor) -> tuple[list[tuple], int]:
    """Contract rows of one metric spec and the number of VDS calls issued."""
    out, calls = [], 0
    for b in spec["branches"]:
        runs = b.get("anchors") or [[None, None]]
        for anchor, label in runs:
            q = copy.deepcopy(b)
            if anchor is not None:
                q["query"]["parameters"] = [{"parameterCaption": b["anchor_parameter"], "value": anchor}]
            cols, rows = executor.execute(q)
            calls += 1
            idx = {c: i for i, c in enumerate(cols)}
            for r in rows:
                if b.get("presence") and not r[idx[b["presence"]]]:
                    continue
                members = [label if m == "@anchor" else run_oracle.to_text(r[idx[m]]) for m in b["members"]]
                members = [None if m in ("", None) else m for m in members] + [None] * (3 - len(b["members"]))
                for measure, alias in b["values"].items():
                    out.append((b["grain"], measure, *members, typed(r[idx[alias]], b["value_kinds"][measure])))
    return out, calls


def compare_metric(rows: list[tuple], expected_path: Path, out: Outcome) -> None:
    with expected_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        expected = list(reader)
    if header[:5] != KEY:
        out.problems.append(f"unexpected expected header {header}")
        return
    want = {tuple(r[:5]): r[5] for r in expected}
    got: dict[tuple, object] = {}
    for r in rows:
        key = tuple("" if v is None else str(v) for v in r[:5])
        if key in got:
            out.problems.append(f"duplicate key {key}")
        got[key] = r[5]
    for key in want.keys() - got.keys():
        if want[key] != "":  # rule 7: an absent row equals NULL
            out.missing += 1
            if len(out.problems) < 25:
                out.problems.append(f"missing {key} expected {want[key]!r}")
    for key in got.keys() - want.keys():
        if got[key] is not None:
            out.extra += 1
            if len(out.problems) < 25:
                out.problems.append(f"extra {key} value {run_oracle.to_text(got[key])!r}")
    for key in want.keys() & got.keys():
        if not run_oracle.values_match(got[key], want[key]):
            out.different += 1
            if len(out.problems) < 25:
                out.problems.append(f"{key}: {run_oracle.to_text(got[key])!r} != expected {want[key]!r}")


def question_result(spec: dict, executor) -> tuple[list[str], list[tuple], int]:
    import duckdb

    con = duckdb.connect()
    try:
        con.execute("SET default_null_order = 'nulls_first_on_asc_last_on_desc'")
        for name, q in spec["queries"].items():
            cols, rows = executor.execute(q)
            types = q["output"]
            con.execute(f'CREATE TABLE "{name}" ({", ".join(f"{chr(34)}{c}{chr(34)} {types[c]}" for c in cols)})')
            if rows:
                con.executemany(f'INSERT INTO "{name}" VALUES ({", ".join("?" for _ in cols)})', rows)
        cur = con.execute(spec["assemble"])
        return [d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()], len(spec["queries"])
    finally:
        con.close()


def run_one(kind: str, spec: dict, executor, repeat: int, expected_dir: Path) -> Outcome:
    qid = spec["metric"] if kind == "metrics" else spec["question"]
    out = Outcome(qid, kind)
    try:
        for _ in range(max(1, repeat)):
            t0 = time.perf_counter()
            if kind == "metrics":
                rows, out.vds_calls = metric_rows(spec, executor)
                cols = None
            else:
                cols, rows, out.vds_calls = question_result(spec, executor)
            out.seconds.append(time.perf_counter() - t0)
        out.rows = len(rows)
        expected = expected_dir / kind / f"{qid}.csv"
        if kind == "metrics":
            compare_metric(rows, expected, out)
        else:
            out.problems = run_oracle.compare(cols, rows, expected)
            out.different = len(out.problems)
    except Exception as exc:  # recorded per query; the run continues
        out.error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:400] if str(exc) else ''}"
    return out


def load(kind: str, select: str = "*") -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((HERE / "queries" / kind).glob("*.json"))
            if fnmatch.fnmatch(p.stem, select)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--select", default="*", help="glob over metric and question ids")
    parser.add_argument("--repeat", type=int, default=4, help="runs per id; the first is the cold run")
    parser.add_argument("--fail-on-mismatch", action="store_true")
    parser.add_argument("--out", type=Path, default=HERE / "results" / "reconcile.json")
    args = parser.parse_args()

    executor = VdsExecutor()
    results = []
    try:
        for kind in ("metrics", "questions"):
            for spec in load(kind, args.select):
                res = run_one(kind, spec, executor, args.repeat, ORACLE / "expected")
                results.append(res)
                status = "ERROR" if res.error else ("ok" if res.matches else "DIFF")
                print(f"{status:5} {res.query_id:12} rows={res.rows:<6} calls={res.vds_calls:<5} "
                      f"missing={res.missing} extra={res.extra} different={res.different} {res.error or ''}", flush=True)
    finally:
        executor.close()
    errors = [r for r in results if r.error]
    diffs = [r for r in results if not r.error and not r.matches]
    summary = {"stack": "tableau", "queries": len(results), "errors": len(errors), "mismatched": len(diffs),
               "run_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"summary": summary, "results": [r.as_dict() for r in results]}, indent=1))
    print(json.dumps(summary))
    if errors or (args.fail_on_mismatch and diffs):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
