#!/usr/bin/env python3
"""Phase 2 test suite: S3 Tableau published data sources and VizQL Data Service queries (02-implementations/bi-layer).

Layers
  1. Structure: required files; vendored official schemas match their recorded checksums; guide sections, links,
     documentation sources; generated artifacts in sync with build_tableau.py; CI workflow; pinned requirements.
  2. Data sources: every .tds validates against Tableau's official 2026.3 document schema; calculations, filters,
     relationships and column maps cross-reference; glossary coverage and agent descriptions; row-level security per
     SPEC § 10; multi-fact structure; the closing-stock period end excludes every non-date dimension.
  3. Queries: every VDS query validates against the VizQL Data Service OpenAPI 20263.0 schema and resolves against
     its data source; 22 metric and 70 question specs cover the oracle exactly; metric grains equal the oracle's;
     every question's assembly produces the oracle's header.
  4. Deployment: connection binding, extract refresh settings (XSD-valid), refresh plan, publish dry run.
  5. Negative: malformed and schema-invalid .tds, undefined references, malformed LOD, invalid VDS queries
     (undefined field, bad filter type, extra property, AGG misuse, unknown parameter), broken assemblies.
  6. Emulation on the oracle fixtures (DuckDB): all 92 query plans and assemblies reproduce the oracle's answers on the
     fixtures through tools/vds_emulator.py; tampered assemblies are detected.
  7. Comparator: oracle tolerances, NULL-equals-absent (SPEC § 5.3 rule 7), missing/extra/different counts.

No Tableau site is contacted. Requires 02-implementations/bi-layer/requirements.txt. Exits non-zero on failure.

    python3 scripts/test_tableau.py
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
S3 = REPO / "02-implementations" / "bi-layer"
ORACLE = REPO / "01-spec" / "oracle"
GUIDE = S3 / "TABLEAU_GUIDE.md"
WORKFLOW = REPO / ".github" / "workflows" / "s3-tableau.yml"
for p in (S3, S3 / "jobs", S3 / "tools", ORACLE):
    sys.path.insert(0, str(p))

try:
    import duckdb  # noqa: F401
    import jsonschema  # noqa: F401
    import xmlschema  # noqa: F401
    import yaml
except ImportError as exc:  # pinned deps are mandatory, never a silent skip
    sys.exit(f"missing test dependency ({exc}); pip install -r 02-implementations/bi-layer/requirements.txt")

import build_tableau as bt  # noqa: E402
import lint_tableau as lint  # noqa: E402
import model  # noqa: E402
import publish  # noqa: E402
import reconcile  # noqa: E402
import refresh  # noqa: E402
import run_oracle as ro  # noqa: E402
import vds_emulator  # noqa: E402

METRICS = lint.load("metrics")
QUESTIONS = lint.load("questions")
TDS = {ds.key: (S3 / "datasources" / ds.file).read_text() for ds in model.DATASOURCES}


def expected(kind: str, qid: str) -> tuple[list[str], list[list[str]]]:
    with (ORACLE / "expected" / kind / f"{qid}.csv").open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    return rows[0], rows[1:]


def oracle_ids(kind: str) -> list[str]:
    return sorted(p.stem for p in (ORACLE / kind).glob("*.sql"))


# ================================================================== 1. structure

class StructureTests(unittest.TestCase):
    def test_required_files(self):
        required = ["TABLEAU_GUIDE.md", "model.py", "vds.py", "build_tableau.py", "question_specs.py", "lint_tableau.py",
                    "requirements.txt", "jobs/publish.py", "jobs/refresh.py", "jobs/reconcile.py",
                    "tools/vds_emulator.py", "schemas/tds.xsd", "schemas/tableau_user_namespace.xsd",
                    "schemas/vendor/NOTICE.md", "schemas/vendor/twb_2026.3.0.xsd",
                    "schemas/vendor/VizQLDataServiceOpenAPISchema_20263.0.json",
                    "schemas/vendor/LICENSE-tableau-document-schemas.txt",
                    "schemas/vendor/LICENSE-VizQL-Data-Service.txt", "datasources/field_catalog.json"]
        self.assertEqual([r for r in required if not (S3 / r).is_file()], [])
        self.assertTrue(WORKFLOW.is_file())
        for ds in model.DATASOURCES:
            self.assertTrue((S3 / "datasources" / ds.file).is_file())

    def test_vendored_schemas_match_recorded_checksums(self):
        notice = (S3 / "schemas" / "vendor" / "NOTICE.md").read_text()
        for name, digest in re.findall(r"\| `([^`]+)` \|[^|]+\|[^|]+\| `([0-9a-f]{64})` \|", notice):
            actual = hashlib.sha256((S3 / "schemas" / "vendor" / name).read_bytes()).hexdigest()
            self.assertEqual(actual, digest, name)
        self.assertEqual(len(re.findall(r"`[0-9a-f]{64}`", notice)), 2)

    def test_generated_artifacts_in_sync(self):
        stale = [str(p.relative_to(S3)) for p, t in bt.outputs().items() if not p.exists() or p.read_text() != t]
        self.assertEqual(stale, [])

    def test_guide(self):
        text = GUIDE.read_text()
        for section in ("Model structure", "Calculation semantics", "Security model", "Performance behavior",
                        "Limitations"):
            self.assertRegex(text, rf"(?m)^## \d+\. {section}")
        self.assertIn("https://raw.githubusercontent.com/tableau/VizQL-Data-Service/main/VizQLDataServiceOpenAPISchema.json",
                      text)
        self.assertIn("twb_2026.3.0.xsd", text)
        self.assertRegex(text, r"checked 2026-\d\d-\d\d")
        links = [l for l in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text) if not l.startswith("http")]
        self.assertGreater(len(links), 15)
        self.assertEqual([l for l in links if not (GUIDE.parent / l).resolve().exists()], [])
        for block in re.findall(r"```[a-z]*\n(.*?)```", text, re.S):
            self.assertNotRegex(block, r"\.\.\.|TODO|<placeholder>")

    def test_requirements_pinned(self):
        lines = [l for l in (S3 / "requirements.txt").read_text().splitlines() if l and not l.startswith("#")]
        self.assertTrue(lines)
        for line in lines:
            self.assertRegex(line, r"^[A-Za-z0-9_.-]+==\d[\w.]*$")

    def test_workflow(self):
        wf = yaml.safe_load(WORKFLOW.read_text())
        self.assertEqual(list(wf["jobs"]), ["lint", "test", "promote"])
        self.assertEqual(wf["jobs"]["test"]["needs"], "lint")
        self.assertEqual(wf["jobs"]["promote"]["needs"], "test")
        lint_runs = " ".join(s.get("run", "") for s in wf["jobs"]["lint"]["steps"])
        self.assertIn("scripts/test_tableau.py", lint_runs)
        self.assertIn("build_tableau.py --check", lint_runs)
        for job in ("test", "promote"):
            runs = " ".join(s.get("run", "") for s in wf["jobs"][job]["steps"])
            self.assertIn("jobs/publish.py", runs)
            self.assertIn("jobs/reconcile.py", runs)
            self.assertIn("--fail-on-mismatch", runs)
        self.assertNotRegex(WORKFLOW.read_text(), r"(?i)password\s*:|dapi[0-9a-f]{8}")


# ================================================================== 2. data sources

class DataSourceTests(unittest.TestCase):
    def test_tds_validate_against_official_schema(self):
        for key, text in TDS.items():
            self.assertEqual(lint.validate_tds(text), [], key)

    def test_tds_cross_references(self):
        for key, text in TDS.items():
            self.assertEqual(lint.lint_tds(text), [], key)

    def test_every_glossary_metric_has_a_calculation(self):
        covered = {c.metric_id for ds in model.DATASOURCES for c in ds.calcs if c.metric_id}
        self.assertEqual(covered, set(model.METRICS))
        for ds in model.DATASOURCES:
            for c in ds.calcs:
                if c.metric_id and c.metric_id not in {"N-C1"}:
                    self.assertEqual(c.caption, model.METRICS[c.metric_id]["display_name"], c.name)

    def test_visible_fields_carry_descriptions(self):
        catalog = json.loads((S3 / "datasources" / "field_catalog.json").read_text())
        for name, ds in catalog.items():
            for caption, f in ds["fields"].items():
                if f["kind"] == "calculation" and not f["hidden"]:
                    self.assertTrue(f["description"], f"{name}: {caption}")
            for ds_model in model.DATASOURCES:
                for c in ds_model.calcs:
                    if c.metric_id:
                        syn = model.METRICS[c.metric_id].get("synonyms", [])
                        self.assertTrue(all(s in c.desc for s in syn), c.name)

    def test_row_level_security_matches_spec(self):
        rls = {ds.key: ds.rls for ds in model.DATASOURCES}
        self.assertEqual({k: [f.logical_table_scoped for f in v] for k, v in rls.items()},
                         {"slc_wwi_sales_orders": [False], "slc_wwi_stock": [True], "slc_nyc_trips": [True]})
        calcs = {ds.key: {c.name: c for c in ds.calcs} for ds in model.DATASOURCES}
        self.assertIn("ISMEMBEROF('slc_territory_southeast')", calcs["slc_wwi_sales_orders"]["rls_wwi_territory"].formula)
        self.assertIn("'Southeast'", calcs["slc_wwi_sales_orders"]["rls_wwi_territory"].formula)
        self.assertIn("ISMEMBEROF('slc_territory_southeast')", calcs["slc_wwi_stock"]["rls_wwi_inventory"].formula)
        self.assertNotIn(" OR ", calcs["slc_wwi_stock"]["rls_wwi_inventory"].formula)
        self.assertIn("ISMEMBEROF('slc_pickup_manhattan')", calcs["slc_nyc_trips"]["rls_nyc_pickup"].formula)
        self.assertIn("'Manhattan'", calcs["slc_nyc_trips"]["rls_nyc_pickup"].formula)
        for key, text in TDS.items():
            filters = lint.ET.fromstring(text.encode()).findall("filter")
            self.assertEqual(len(filters), 1, key)
            self.assertEqual(filters[0].get("logical-table-scoped") == "true", rls[key][0].logical_table_scoped)
        nyc = model.BY_KEY["slc_nyc_trips"]
        trips_cols = {c.name for c in nyc.tables[0].cols}
        self.assertIn("trip_rls_pickup_borough", trips_cols)  # scoped filter only references the Trips table

    def test_multi_fact_model(self):
        ws = model.BY_KEY["slc_wwi_sales_orders"]
        dims_of = {}
        for r in ws.rels:
            dims_of.setdefault(r.first, set()).add(r.second)
        shared = dims_of["sales"] & dims_of["orders"]
        self.assertEqual(shared, {"date", "customer", "city", "stock_item", "salesperson"})
        self.assertNotIn("stock_daily", {t.id for t in ws.tables})

    def test_closing_stock_period_end_excludes_every_non_date_dimension(self):
        stock = model.BY_KEY["slc_wwi_stock"]
        visible_dims = {c.name for t in stock.tables if t.id != "date" for c in t.cols
                        if c.role == "dimension" and not c.hidden and c.name != "stk_snapshot_date"}
        self.assertEqual(visible_dims, set(model.STOCK_NON_DATE_DIMS))

    def test_custom_sql_reads_only_canonical_tables(self):
        for ds in model.DATASOURCES:
            for t in ds.tables:
                for ref in re.findall(r"\bslc\.(\w+)\.(\w+)", t.sql):
                    self.assertIn(ref[0], {"wwi", "nyctaxi"}, t.id)
                    self.assertNotIn(ref[1], {"stock_holding_current", "fact_trip_quarantine"}, t.id)


# ================================================================== 3. queries

class QueryTests(unittest.TestCase):
    def test_coverage_matches_oracle(self):
        self.assertEqual(sorted(METRICS), oracle_ids("metrics"))
        self.assertEqual(sorted(QUESTIONS), oracle_ids("questions"))

    def test_metric_specs_validate(self):
        self.assertEqual([p for s in METRICS.values() for p in lint.lint_metric(s)], [])

    def test_question_specs_validate(self):
        self.assertEqual([p for s in QUESTIONS.values() for p in lint.lint_question(s)], [])

    def test_metric_grains_equal_oracle_grains(self):
        for mid, spec in METRICS.items():
            _, rows = expected("metrics", mid)
            want = {(r[0], r[1]) for r in rows}
            got = {(b["grain"], label) for b in spec["branches"] for label in b["values"]}
            self.assertEqual(got, want, mid)

    def test_question_headers_equal_oracle(self):
        wrong = {q: lint.assemble_columns(s) for q, s in QUESTIONS.items()
                 if lint.assemble_columns(s) != expected("questions", q)[0]}
        self.assertEqual(wrong, {})

    def test_period_to_date_anchors(self):
        for mid in ("N-C1", "N-C2"):
            by_grain = {b["grain"]: b for b in METRICS[mid]["branches"]}
            self.assertEqual(len(by_grain["day"]["anchors"]), 731)
            self.assertEqual(len(by_grain["month"]["anchors"]), 24)
            self.assertEqual(by_grain["month"]["anchors"][1], ["2023-02-28", "2023-02-01"])
            self.assertEqual(by_grain["month"]["anchors"][13], ["2024-02-29", "2024-02-01"])
            self.assertEqual(by_grain["total"]["anchors"], [["2024-12-31", None]])

    def test_fact_driven_queries_carry_presence(self):
        presence = {"lines", "order_lines", "snap_rows", "trips"}
        for qid, spec in QUESTIONS.items():
            for name, q in spec["queries"].items():
                aliases = set(q["output"])
                measures = [f for f in q["query"]["fields"] if f.get("function") == "AGG"]
                uses_presence = aliases & presence and re.search(rf"\b({'|'.join(aliases & presence)})\b",
                                                                 spec["assemble"])
                if measures and aliases & presence:
                    self.assertTrue(uses_presence, f"{qid}/{name}: presence measure fetched but unused")


# ================================================================== 4. deployment

EXTRACT_BLOCK = ("<extract count='-1' enabled='true' object-id='' units='records'>"
                 "<connection class='hyper' dbname='Data/Extracts/slc_nyc_trips.hyper' schema='Extract' "
                 "tablename='Extract'><relation name='Extract' table='[Extract].[Extract]' type='table' />"
                 "</connection></extract>")


def with_extract(text: str) -> str:
    return text.replace("<object-graph>", EXTRACT_BLOCK + "<object-graph>", 1)


class DeploymentTests(unittest.TestCase):
    def test_bind_connection(self):
        out = publish.bind_connection(TDS["slc_nyc_trips"], "adb-1.azuredatabricks.net", "/sql/1.0/warehouses/abc")
        conn = lint.ET.fromstring(out.encode()).find("connection/named-connections/named-connection/connection")
        self.assertEqual((conn.get("server"), conn.get("v-http-path")),
                         ("adb-1.azuredatabricks.net", "/sql/1.0/warehouses/abc"))
        self.assertEqual(lint.validate_tds(out), [])
        with self.assertRaises(ValueError):
            publish.bind_connection(TDS["slc_nyc_trips"], "", "/sql/1.0/warehouses/abc")

    def test_extract_settings(self):
        ds = model.BY_KEY["slc_nyc_trips"]
        doc = with_extract(TDS["slc_nyc_trips"])
        self.assertEqual(lint.validate_tds(doc), [])
        out = publish.patch_extract(doc, ds, "2024-12-31")
        self.assertEqual(lint.validate_tds(out), [])
        root = lint.ET.fromstring(out.encode())
        self.assertEqual(root.find("extract/connection/refresh").get("increment-key"), "[trip_pickup_ts]")
        flt = root.find("extract/filter")
        self.assertEqual((flt.get("first-period"), flt.get("period-type-v2"), flt.get("period-anchor")),
                         ("-23", "month", "#2024-12-31#"))
        wwi = publish.patch_extract(with_extract(TDS["slc_wwi_stock"]), model.BY_KEY["slc_wwi_stock"], "2024-12-31")
        self.assertIsNone(lint.ET.fromstring(wwi.encode()).find("extract/connection/refresh"))

    def test_extract_settings_require_an_extract(self):
        with self.assertRaises(ValueError):
            publish.patch_extract(TDS["slc_nyc_trips"], model.BY_KEY["slc_nyc_trips"], "2024-12-31")

    def test_refresh_plan(self):
        self.assertEqual(refresh.plan("incremental"),
                         [("SLC WWI Sales and Orders (Extract)", False), ("SLC WWI Stock (Extract)", False),
                          ("SLC NYC Trips (Extract)", True)])
        self.assertTrue(all(not inc for _, inc in refresh.plan("rollover")))
        with self.assertRaises(ValueError):
            refresh.plan("weekly")

    def test_publish_dry_run(self):
        env = {"DATABRICKS_SERVER_HOSTNAME": "adb-1.azuredatabricks.net", "DATABRICKS_HTTP_PATH": "/sql/1.0/warehouses/a",
               "PATH": "/usr/bin:/bin"}
        out = subprocess.run([sys.executable, str(S3 / "jobs" / "publish.py"), "--dry-run"], env=env,
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.count("publish "), 3)


# ================================================================== 5. negative

class NegativeTests(unittest.TestCase):
    def test_malformed_tds(self):
        self.assertTrue(lint.validate_tds(TDS["slc_wwi_stock"][:-40])[0].startswith("not well-formed"))

    def test_schema_invalid_tds(self):
        bad = TDS["slc_wwi_stock"].replace(' role="measure"', "", 1)
        self.assertTrue(any("role" in p for p in lint.validate_tds(bad)))
        bad = TDS["slc_wwi_stock"].replace("<object-graph>", "<object-graf>", 1).replace("</object-graph>",
                                                                                          "</object-graf>", 1)
        self.assertTrue(lint.validate_tds(bad))

    def test_undefined_reference_in_calculation(self):
        bad = TDS["slc_nyc_trips"].replace("SUM([trip_total_amount])", "SUM([trip_total])", 1)
        self.assertTrue(any("does not resolve" in p for p in lint.lint_tds(bad)))

    def test_malformed_lod(self):
        bad = TDS["slc_wwi_stock"].replace("{EXCLUDE", "{EXCLUDES", 1)
        self.assertTrue(any("level-of-detail" in p for p in lint.lint_tds(bad)))

    def test_filter_on_undefined_field(self):
        bad = TDS["slc_nyc_trips"].replace('column="[rls_nyc_pickup]"', 'column="[rls_missing]"', 1)
        self.assertTrue(any("undefined field" in p for p in lint.lint_tds(bad)))

    def test_vds_query_with_undefined_field(self):
        spec = copy.deepcopy(QUESTIONS["Q-N-S1-P"]["queries"]["q"])
        spec["query"]["fields"][0]["fieldCaption"] = "Pickup Borrough"
        self.assertTrue(any("not defined" in p for p in lint.validate_query(spec)))

    def test_vds_query_schema_violations(self):
        base = QUESTIONS["Q-N-S1-P"]["queries"]["q"]
        cases = []
        s = copy.deepcopy(base)
        s["query"]["filters"][0]["filterType"] = "EQUALS"
        cases.append((s, "not one of"))
        s = copy.deepcopy(base)
        s["query"]["filters"][0]["include"] = True
        cases.append((s, "not defined for SetFilter"))
        s = copy.deepcopy(base)
        s["query"]["fields"][2]["function"] = "TOTAL"
        cases.append((s, "not valid under any"))
        s = copy.deepcopy(base)
        del s["query"]["fields"]
        cases.append((s, "required"))
        for spec, pattern in cases:
            self.assertTrue(any(pattern in p for p in lint.validate_query(spec)), pattern)

    def test_agg_misuse_and_unknown_parameter(self):
        s = copy.deepcopy(QUESTIONS["Q-N-S1-P"]["queries"]["q"])
        s["query"]["fields"][0]["function"] = "AGG"
        self.assertTrue(any("not an aggregate calculation" in p for p in lint.validate_query(s)))
        s = copy.deepcopy(QUESTIONS["Q-N-S1-P"]["queries"]["q"])
        del s["query"]["fields"][2]["function"]
        self.assertTrue(any("without function AGG" in p for p in lint.validate_query(s)))
        s = copy.deepcopy(QUESTIONS["Q-N-C1-D3"]["queries"]["q"])
        s["query"]["parameters"][0]["parameterCaption"] = "Anchor"
        self.assertTrue(any("parameter 'Anchor'" in p for p in lint.validate_query(s)))

    def test_broken_assemblies(self):
        s = copy.deepcopy(QUESTIONS["Q-N-S1-P"])
        s["assemble"] = s["assemble"].replace("FROM q", "FROM slc.nyctaxi.fact_trip")
        self.assertTrue(any("physical tables" in p for p in lint.lint_question(s)))
        s = copy.deepcopy(QUESTIONS["Q-N-S1-P"])
        s["assemble"] = s["assemble"].replace("FROM q", "FROM trips_raw")
        self.assertTrue(any("neither a query result" in p or "does not run" in p for p in lint.lint_question(s)))
        s = copy.deepcopy(QUESTIONS["Q-N-S1-P"])
        s["assemble"] = s["assemble"].replace("revenue FROM", "revenue AS gross FROM")
        self.assertNotEqual(lint.assemble_columns(s), expected("questions", "Q-N-S1-P")[0])

    def test_metric_spec_with_unknown_member_alias(self):
        s = copy.deepcopy(METRICS["W-S1"])
        s["branches"][1]["members"] = ["nope"]
        self.assertTrue(any("member alias" in p for p in lint.lint_metric(s)))


# ================================================================== 6. emulation on fixtures

class FixtureEmulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine, con = vds_emulator.fixture_connection()
        cls.emu = vds_emulator.Emulator(con)
        cls.tmp = Path(tempfile.mkdtemp(prefix="slc-s3-oracle-"))
        oracle = {q.query_id: q for q in ro.load_queries()}
        for kind in ("metrics", "questions"):
            for qid in oracle_ids(kind):
                cols, rows = cls.engine.execute(oracle[qid].sql)
                ro.write_csv(cols, rows, cls.tmp / kind / f"{qid}.csv")

    @classmethod
    def tearDownClass(cls):
        cls.engine.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_spec(self, kind, spec):
        return reconcile.run_one(kind, spec, self.emu, 1, self.tmp)

    def test_all_metric_plans_reproduce_the_oracle_on_fixtures(self):
        failures = {}
        for mid, spec in METRICS.items():
            out = self.run_spec("metrics", spec)
            if not out.matches:
                failures[mid] = out.error or out.problems[:3]
        self.assertEqual(failures, {})

    def test_all_question_plans_reproduce_the_oracle_on_fixtures(self):
        failures = {}
        for qid, spec in QUESTIONS.items():
            out = self.run_spec("questions", spec)
            if not out.matches:
                failures[qid] = out.error or out.problems[:3]
        self.assertEqual(failures, {})

    def test_tampered_plans_are_detected(self):
        s = copy.deepcopy(QUESTIONS["Q-W-S1-D2"])
        s["assemble"] = s["assemble"].replace("ORDER BY i.revenue DESC", "ORDER BY i.revenue ASC")
        self.assertFalse(self.run_spec("questions", s).matches)
        s = copy.deepcopy(QUESTIONS["Q-N-S2-D4"])
        s["assemble"] = s["assemble"].replace("FROM codes c LEFT JOIN q", "FROM codes c JOIN q")
        self.assertFalse(self.run_spec("questions", s).matches)
        s = copy.deepcopy(METRICS["W-C1"])
        for b in s["branches"]:
            b["values"] = {"W-C1": b["output"] and next(iter(b["values"].values()))}
            b["query"]["fields"] = [f if f.get("fieldCaption") != "Stock Group Revenue Share"
                                    else {**f, "fieldCaption": "Revenue (Excl. Tax)"} for f in b["query"]["fields"]]
        self.assertFalse(self.run_spec("metrics", s).matches)


# ================================================================== 7. comparator

class ComparatorTests(unittest.TestCase):
    def compare(self, rows, qid="W-M1"):
        out = reconcile.Outcome(qid, "metrics")
        reconcile.compare_metric(rows, ORACLE / "expected" / "metrics" / f"{qid}.csv", out)
        return out

    def typed(self, qid="W-M1"):
        _, rows = expected("metrics", qid)
        return [tuple(None if v == "" else v for v in r[:5]) + (float(r[5]) if r[5] else None,) for r in rows]

    def test_exact_and_reordered(self):
        rows = self.typed()
        self.assertTrue(self.compare(rows).matches)
        self.assertTrue(self.compare(list(reversed(rows))).matches)

    def test_null_equals_absent(self):
        rows = self.typed() + [("year", "W-M1", "1999", None, None, None)]
        self.assertTrue(self.compare(rows).matches)

    def test_counts(self):
        rows = self.typed()
        rows = rows[1:] + [("year", "W-M1", "1999", None, None, 0.5)]
        rows[0] = rows[0][:5] + ((rows[0][5] or 0) + 0.01,)
        out = self.compare(rows)
        self.assertEqual((out.missing, out.extra, out.different), (1, 1, 1))

    def test_money_and_ratio_tolerances(self):
        rows = self.typed("W-S1")
        base = rows[0][5]
        rows[0] = rows[0][:5] + (reconcile.typed(base + 0.0049, "money"),)
        self.assertTrue(self.compare(rows, "W-S1").matches)
        rows[0] = rows[0][:5] + (reconcile.typed(base + 0.01, "money"),)
        self.assertFalse(self.compare(rows, "W-S1").matches)
        ratios = self.typed("W-M1")
        ratios[0] = ratios[0][:5] + (reconcile.typed(ratios[0][5] + 1e-5, "ratio"),)
        self.assertFalse(self.compare(ratios).matches)
        self.assertEqual(reconcile.typed(12.0, "count"), 12)

    def test_value_kinds_follow_formats(self):
        kinds = {b["grain"]: b["value_kinds"] for b in METRICS["W-C2"]["branches"]}
        self.assertEqual(kinds["total"], {"W-C2": "ratio", "W-C2:closing_units": "count",
                                          "W-C2:units_sold_91d": "count"})
        self.assertEqual(METRICS["N-S1"]["branches"][0]["value_kinds"], {"N-S1": "money"})
        self.assertEqual(METRICS["B-W4"]["branches"][0]["value_kinds"], {"B-W4": "count"})


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if result.wasSuccessful() else 1)
