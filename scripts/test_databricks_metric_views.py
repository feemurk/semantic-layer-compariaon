#!/usr/bin/env python3
"""Phase 2 test suite: S4 Databricks Unity Catalog metric views (02-implementations/databricks-metric-views).

Layers
  1. Structure: required files; guide links resolve; doc URL and specification version recorded; generated YAML, DDL
     and reconciliation queries in sync with their builders; bundle, jobs and CI workflow cross-references.
  2. Definitions: every view passes lint_metric_views (YAML 1.1 grammar, MEASURE() resolution, joins, windows,
     agent metadata, materialization rules); DDL wraps the YAML in CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE
     YAML; CLAUDE.md § 5 coverage; glossary parity; profile separation (B-01).
  3. Queries: 22 metric and 70 question queries cover the oracle exactly, read only slc.semantic views, name only
     defined measures, and parse with the Spark 4.3 SQL parser.
  4. Security and deployment: ABAC policy, tag, function and grant coverage of SPEC § 10; statement splitting and
     the deploy plan order of both profiles; the keyed reconciliation comparator.
  5. Negative: malformed YAML, MEASURE() of an undefined measure, and every other lint rule reject bad input.
  6. Emulation on the oracle fixtures (Spark): all 92 queries resolve against the canonical schema with the oracle's
     output columns; every query without a window measure returns the oracle's answer on the fixtures.
  7. Real data (opt-in): SLC_LOCAL_B0=<platform local B0 dir> runs every query without a window measure on the
     real-data B0 through the emulator and compares it to the committed expected answers.

Requires scripts/requirements-test.txt and Java 17+. Exits non-zero on failure.

    python3 scripts/test_databricks_metric_views.py
"""

from __future__ import annotations

import copy
import csv
import os
import re
import shutil
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MV = REPO / "02-implementations" / "databricks-metric-views"
ORACLE = REPO / "01-spec" / "oracle"
GLOSSARY = REPO / "01-spec" / "glossary.yaml"
GUIDE = MV / "METRIC_VIEWS_GUIDE.md"
WORKFLOW = REPO / ".github" / "workflows" / "s4-metric-views.yml"
for p in (MV, MV / "jobs", MV / "tools", ORACLE):
    sys.path.insert(0, str(p))

try:
    import yaml
    from pyspark.sql import SparkSession
except ImportError as exc:  # pinned deps are mandatory, never a silent skip
    sys.exit(f"missing test dependency ({exc}); pip install -r scripts/requirements-test.txt")

import build_metric_views as bmv  # noqa: E402
import build_reconciliation_queries as brq  # noqa: E402
import deploy  # noqa: E402
import lint_metric_views as lint  # noqa: E402
import local_emulator  # noqa: E402
import reconcile  # noqa: E402
import run_oracle as ro  # noqa: E402

VIEWS = lint.load_views()
DOCS_URL = "https://docs.databricks.com/aws/en/uc-semantics/metric-views/yaml-reference"
DDL_RE = re.compile(r"^CREATE OR REPLACE VIEW slc\.semantic\.(\w+)\nWITH METRICS\nLANGUAGE YAML\nAS \$\$\n(.*)\$\$;\n$", re.S)
SPARK: SparkSession | None = None


def spark() -> SparkSession:
    global SPARK
    if SPARK is None:
        tmp = Path(tempfile.mkdtemp(prefix="slc-mv-test-"))
        SPARK = (SparkSession.builder.master("local[2]").appName("slc-mv-test")
                 .config("spark.ui.enabled", "false").config("spark.sql.session.timeZone", "UTC")
                 .config("spark.sql.shuffle.partitions", "4").config("spark.driver.memory", "4g")
                 .config("spark.ui.showConsoleProgress", "false")
                 .config("spark.sql.warehouse.dir", str(tmp / "warehouse")).getOrCreate())
        SPARK.sparkContext.setLogLevel("ERROR")
    return SPARK


def ddl_parts(path: Path) -> tuple[str, dict]:
    code = "\n".join(l for l in path.read_text().splitlines() if not l.startswith("-- ")) + "\n"
    m = DDL_RE.match(code)
    if not m:
        raise AssertionError(f"{path.name}: not CREATE OR REPLACE VIEW slc.semantic.<view> WITH METRICS LANGUAGE YAML")
    return m.group(1), yaml.safe_load(m.group(2))


def oracle_ids(kind: str) -> list[str]:
    return sorted(p.stem for p in (ORACLE / kind).glob("*.sql"))


def stack_ids(kind: str) -> list[str]:
    return sorted(p.stem for p in (MV / "queries" / kind).glob("*.sql"))


def expected_rows(kind: str, qid: str) -> tuple[list[str], list[list[str]]]:
    with (ORACLE / "expected" / kind / f"{qid}.csv").open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    return rows[0], rows[1:]


# Documented divergences from the oracle (METRIC_VIEWS_GUIDE.md § 3.5, SPEC B-08). A divergent result must still be an
# exact subset of the oracle's rows: only absent members are tolerated, never a different value.
# Value: (reason, observed on the real-data B0). On the sparse fixtures any of them may appear.
KNOWN_DIVERGENCES = {
    "Q-N-S2-D4": ("B-08: payment codes without 2024 trips are not reachable through nyc_trips", True),
    "Q-W-S2-P": ("B-08: the shared month axis comes from order and sale rows, not the calendar; every 2015 month has "
                 "both facts on B0", False),
}


def subset_of_expected(columns: list[str], rows: list[tuple], expected_path: Path) -> list[str]:
    """Problems unless every returned row equals some expected row (oracle tolerances) and none repeats."""
    with expected_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        expected = list(reader)
    if [c.lower() for c in columns] != [h.lower() for h in header]:
        return [f"columns {columns} != {header}"]
    problems, used = [], set()
    for row in rows:
        match = next((i for i, e in enumerate(expected) if i not in used
                      and all(ro.values_match(a, w) for a, w in zip(row, e))), None)
        if match is None:
            problems.append(f"row {row} not in the oracle answer")
        else:
            used.add(match)
    return problems


def check_against(columns, rows, expected: Path, query: ro.Query) -> tuple[bool, list[str]]:
    """(diverged, problems): problems are failures; a known divergence passes only as a strict row subset."""
    out = reconcile.Outcome(query.query_id, query.kind)
    if query.kind == "metrics":
        reconcile.compare_keyed(columns, rows, expected, out)
    else:
        out.problems = ro.compare(columns, rows, expected)
    if out.matches:
        return False, []
    if query.query_id in KNOWN_DIVERGENCES:
        return True, subset_of_expected(columns, rows, expected)
    return False, out.problems[:3] or ["mismatch"]


def valid_view() -> dict:
    return copy.deepcopy(VIEWS["nyc_trips"])


# ================================================================== 1. structure

class StructureTests(unittest.TestCase):
    def test_required_files_exist(self):
        required = [
            "METRIC_VIEWS_GUIDE.md", "build_metric_views.py", "build_reconciliation_queries.py", "lint_metric_views.py",
            "databricks.yml", "resources/jobs.yml", "jobs/deploy.py", "jobs/reconcile.py", "tools/local_emulator.py",
            "security/01_row_filter_functions.sql", "security/02_tags.sql", "security/03_policies.sql",
            "security/04_grants.sql", "security/90_drop_policies.sql",
        ]
        missing = [r for r in required if not (MV / r).is_file()]
        self.assertEqual(missing, [])
        self.assertTrue(WORKFLOW.is_file())

    def test_seven_views_in_every_format(self):
        names = sorted(VIEWS)
        self.assertEqual(names, sorted(deploy.VIEW_ORDER))
        for profile in ("governed", "accelerated"):
            self.assertEqual(sorted(p.stem for p in (MV / "sql" / profile).glob("*.sql")), names)

    def test_guide_links_resolve_and_code_is_not_duplicated(self):
        text = GUIDE.read_text()
        links = re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text)
        local = [l for l in links if not l.startswith("http")]
        self.assertGreater(len(local), 15)
        broken = [l for l in local if not (GUIDE.parent / l).resolve().exists()]
        self.assertEqual(broken, [])
        # Guides link to code files; no full YAML listing of a view is copied into the guide.
        self.assertNotIn("measures:\n- name: trip_count", text)

    def test_guide_records_documentation_and_version(self):
        text = GUIDE.read_text()
        self.assertIn(DOCS_URL, text)
        self.assertRegex(text, r"YAML specification 1\.1")
        self.assertRegex(text, r"checked 2026-\d\d-\d\d")
        for section in ("Model structure", "Calculation semantics", "Security model", "Performance behavior",
                        "Limitations"):
            self.assertRegex(text, rf"(?m)^## \d+\. {section}")

    def test_guide_has_no_placeholders(self):
        text = GUIDE.read_text()
        for block in re.findall(r"```[a-z]*\n(.*?)```", text, re.S):
            self.assertNotRegex(block, r"\.\.\.|TODO|<placeholder>")

    def test_generated_views_in_sync(self):
        stale = [str(p.relative_to(MV)) for p, t in bmv.outputs().items() if not p.exists() or p.read_text() != t]
        self.assertEqual(stale, [])

    def test_generated_reconciliation_queries_in_sync(self):
        stale = [m for m in brq.ALL_METRICS if (brq.OUT / f"{m}.sql").read_text() != brq.render(m)]
        self.assertEqual(stale, [])

    def test_bundle_references(self):
        bundle = yaml.safe_load((MV / "databricks.yml").read_text())
        self.assertEqual(set(bundle["targets"]), {"governed", "accelerated"})
        self.assertTrue(bundle["targets"]["governed"].get("default"))
        for target, conf in bundle["targets"].items():
            self.assertEqual(conf["variables"]["profile"], target)
        for path in bundle["sync"]["paths"]:
            self.assertTrue((MV / path).resolve().is_dir(), path)
        self.assertIn("../../01-spec/oracle", bundle["sync"]["paths"])
        jobs = yaml.safe_load((MV / "resources" / "jobs.yml").read_text())["resources"]["jobs"]
        self.assertEqual(set(jobs), {"slc_metric_views_deploy", "slc_metric_views_reconcile", "slc_metric_views_gate"})
        for job in jobs.values():
            self.assertEqual(job["environments"][0]["spec"]["environment_version"], "6")
            for task in job["tasks"]:
                self.assertTrue((MV / "resources" / task["spark_python_task"]["python_file"]).resolve().is_file())
                self.assertIn("--profile", task["spark_python_task"]["parameters"])

    def test_gate_selects_the_p_questions(self):
        jobs = yaml.safe_load((MV / "resources" / "jobs.yml").read_text())["resources"]["jobs"]
        params = jobs["slc_metric_views_gate"]["tasks"][0]["spark_python_task"]["parameters"]
        self.assertIn("--fail-on-mismatch", params)
        selected = [q for q in reconcile.load_queries(params[params.index("--select") + 1])]
        self.assertEqual(sorted(q.query_id for q in selected), [q for q in oracle_ids("questions") if q.endswith("-P")])
        self.assertEqual(len(selected), 12)

    def test_ci_workflow_runs_lint_test_promote(self):
        wf = yaml.safe_load(WORKFLOW.read_text())
        self.assertEqual(list(wf["jobs"]), ["lint", "test", "promote"])
        self.assertEqual(wf["jobs"]["test"]["needs"], "lint")
        self.assertEqual(wf["jobs"]["promote"]["needs"], "test")
        self.assertEqual(wf["permissions"]["id-token"], "write")
        lint_runs = " ".join(s.get("run", "") for s in wf["jobs"]["lint"]["steps"])
        self.assertIn("scripts/test_databricks_metric_views.py", lint_runs)
        for job in ("test", "promote"):
            runs = [s.get("run", "") for s in wf["jobs"][job]["steps"]]
            self.assertIn("databricks bundle deploy", runs)
            self.assertIn("databricks bundle run slc_metric_views_gate", runs)
            self.assertEqual(wf["jobs"][job]["env"]["DATABRICKS_AUTH_TYPE"], "github-oidc")
        self.assertNotRegex(WORKFLOW.read_text(), r"(?i)dapi[0-9a-f]{8}|password\s*:")

    def test_status_row(self):
        rows = [l for l in (REPO / "STATUS.md").read_text().splitlines() if "databricks-metric-views" in l]
        self.assertEqual(len(rows), 1)
        self.assertRegex(rows[0], r"\| (Not Started|In Progress|Complete|Blocked) \| \d{4}-\d\d-\d\d \|")


# ================================================================== 2. definitions

class DefinitionTests(unittest.TestCase):
    def test_every_view_passes_lint(self):
        problems = [p for v, d in VIEWS.items() for p in lint.lint_view(d, v)]
        self.assertEqual(problems, [])

    def test_every_ddl_wraps_its_yaml(self):
        for profile in ("governed", "accelerated"):
            for path in sorted((MV / "sql" / profile).glob("*.sql")):
                view, doc = ddl_parts(path)
                self.assertEqual(view, path.stem)
                self.assertEqual(lint.lint_view(doc, f"{profile}/{view}"), [])
                expected = dict(VIEWS[view])
                if profile == "accelerated" and view in bmv.MATERIALIZATION:
                    expected["materialization"] = bmv.MATERIALIZATION[view]
                self.assertEqual(doc, expected, path.name)

    def test_version_is_numeric_1_1(self):
        for path in sorted((MV / "metric_views").glob("*.yaml")):
            self.assertRegex(path.read_text(), r"(?m)^version: 1\.1$")

    def test_no_yaml_aliases_or_sql_comments_inside_definitions(self):
        for path in list((MV / "metric_views").glob("*.yaml")) + list((MV / "sql").glob("*/*.sql")):
            text = path.read_text()
            body = text.split("$$")[1] if "$$" in text else text
            self.assertNotRegex(body, r"(?m)(:\s*[&*]id\d+|^\s*- [&*]id\d+)", path.name)
            self.assertNotRegex(body, r"(?m)^\s*--", path.name)

    def test_claude_md_section_5_coverage(self):
        windows = [w for d in VIEWS.values() for m in d["measures"] for w in m.get("window", [])]
        self.assertTrue(any(w["range"] == "cumulative" for w in windows))
        self.assertTrue(any(w["range"].startswith("trailing") for w in windows))
        self.assertTrue(any(w["range"] == "all" for w in windows))
        self.assertTrue(any(w.get("semiadditive") == "last" for w in windows))
        self.assertTrue(any(w.get("offset") == "-1 year" for w in windows))
        composed = [m for d in VIEWS.values() for m in d["measures"] if "MEASURE(" in m["expr"]]
        self.assertGreaterEqual(len(composed), 6)
        self.assertEqual(set(bmv.MATERIALIZATION), {"nyc_trips", "wwi_sales"})
        for d in VIEWS.values():
            for item in d.get("fields", []) + d["measures"]:
                self.assertIn("display_name", item, item["name"])
            for m in d["measures"]:
                self.assertIn("comment", m, m["name"])
                self.assertIn("format", m, m["name"])

    def test_glossary_parity(self):
        glossary = yaml.safe_load(GLOSSARY.read_text())
        by_display = {m["display_name"]: m for d in VIEWS.values() for m in d["measures"]}
        for metric in glossary["metrics"]:
            if metric["id"] in {"W-C2", "N-C1", "N-C2", "W-C1"}:
                continue  # composite KPIs: parity is checked on their component measures below
            self.assertIn(metric["display_name"], by_display, metric["id"])
            fmt = glossary["formats"][metric["format"]]
            self.assertEqual(by_display[metric["display_name"]]["format"]["type"], fmt["type"], metric["id"])
        for display in ("Revenue YTD", "Revenue YoY % vs STLY", "MTD-to-YTD Daily Pace Index", "Days of Supply"):
            self.assertIn(display, by_display)

    def test_synonyms_are_unambiguous_within_a_view(self):
        for view, d in VIEWS.items():
            members = d.get("fields", []) + d["measures"]
            names = {k.lower().replace("_", " "): m["name"] for m in members for k in (m["name"], m["display_name"])}
            seen = {}
            for m in members:
                for s in m.get("synonyms", []):
                    key = s.lower().replace("_", " ")
                    self.assertEqual(names.get(key, m["name"]), m["name"], f"{view}: {s} names another member")
                    self.assertNotIn(key, seen, f"{view}: {s} on {seen.get(key)} and {m['name']}")
                    seen[key] = m["name"]
            displays = [m["display_name"] for m in members]
            self.assertEqual(len(displays), len(set(displays)), view)

    def test_no_one_to_many_joins(self):
        # B-02/B-03 are handled in SQL sources (bridge expansion, pre-aggregated second fact), not one_to_many joins.
        def walk(joins):
            for j in joins or []:
                yield j
                yield from walk(j.get("joins"))
        for view, d in VIEWS.items():
            self.assertEqual([j["name"] for j in walk(d.get("joins")) if j.get("cardinality") == "one_to_many"], [], view)

    def test_profiles_separate_materialization_from_abac(self):
        for path in (MV / "sql" / "governed").glob("*.sql"):
            self.assertNotIn("materialization", ddl_parts(path)[1])
        materialized = deploy.materialized_views(MV / "sql" / "accelerated")
        self.assertEqual(sorted(materialized), sorted(bmv.MATERIALIZATION))

    def test_materialized_measures_are_not_window_measures(self):
        for view, mat in bmv.MATERIALIZATION.items():
            windowed = {m["name"] for m in VIEWS[view]["measures"] if m.get("window")}
            for mv in mat["materialized_views"]:
                self.assertEqual(set(mv.get("measures", [])) & windowed, set())

    def test_stock_snapshot_keeps_null_sales(self):
        # DOS denominators must stay NULL on days without sales, as in the oracle (no COALESCE to 0).
        self.assertNotIn("COALESCE", VIEWS["wwi_stock"]["source"].upper())


# ================================================================== 3. queries

class QueryTests(unittest.TestCase):
    def test_metric_and_question_coverage_matches_oracle(self):
        self.assertEqual(stack_ids("metrics"), oracle_ids("metrics"))
        self.assertEqual(stack_ids("questions"), oracle_ids("questions"))
        self.assertEqual(len(stack_ids("metrics")), 22)
        self.assertEqual(len(stack_ids("questions")), 70)

    def test_queries_pass_lint(self):
        problems = [p for path in sorted((MV / "queries").glob("*/*.sql"))
                    for p in lint.lint_query(path.read_text(), VIEWS, path.stem)]
        self.assertEqual(problems, [])

    def test_multi_row_queries_are_ordered(self):
        unordered = []
        for q in reconcile.load_queries():
            _, rows = expected_rows(q.kind, q.query_id)
            if len(rows) > 1 and not re.search(r"\bORDER\s+BY\b", q.sql, re.I):
                unordered.append(q.query_id)
        self.assertEqual(unordered, [])

    def test_window_queries_filter_outside_the_window(self):
        # A WHERE on a time field inside a query that uses a window reaching beyond the anchor (cumulative, trailing,
        # leading or offset) would truncate the window (guide § 3.4). current and all frames are not affected.
        reaching = {m["name"] for d in VIEWS.values() for m in d["measures"]
                    if any(w["range"] not in {"current", "all"} or "offset" in w for w in m.get("window", []))}
        composed = {m["name"]: set(lint.MEASURE_CALL.findall(m["expr"])) for d in VIEWS.values() for m in d["measures"]}
        grew = True
        while grew:
            extra = {n for n, refs in composed.items() if refs & reaching} - reaching
            reaching |= extra
            grew = bool(extra)
        self.assertGreaterEqual(len(reaching), 8)
        checked = 0
        for path in sorted((MV / "queries" / "questions").glob("*.sql")):
            sql = path.read_text()
            if not set(lint.MEASURE_CALL.findall(sql)) & reaching:
                continue
            checked += 1
            for select in re.findall(r"MEASURE\([^)]*\).*?FROM\s+slc\.semantic\.\w+(.*?)(?:\)|$)", sql, re.S | re.I):
                where = re.search(r"\bWHERE\b(.*?)(\bGROUP\b|$)", select, re.S | re.I)
                if where:
                    self.assertNotRegex(where.group(1), r"\b(pickup_\w+|snapshot_\w+|calendar_\w+|fiscal_\w+)\b",
                                        path.stem)
        self.assertEqual(checked, 13)  # Q-N-C1 (4), Q-N-C2 (5), Q-W-C2 (4)

    def test_spark_parser_accepts_queries_and_ddl(self):
        parser = spark()._jsparkSession.sessionState().sqlParser()
        for q in reconcile.load_queries():
            parser.parsePlan(q.sql)
        for path in sorted((MV / "sql").glob("*/*.sql")):
            code = "\n".join(l for l in path.read_text().splitlines() if not l.startswith("-- ")).rstrip().rstrip(";")
            self.assertEqual(parser.parsePlan(code).getClass().getSimpleName(), "CreateMetricView", path.name)


# ================================================================== 4. security and deployment

class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.functions = (MV / "security" / "01_row_filter_functions.sql").read_text()
        self.tags = (MV / "security" / "02_tags.sql").read_text()
        self.policies = (MV / "security" / "03_policies.sql").read_text()
        self.grants = (MV / "security" / "04_grants.sql").read_text()
        self.drops = (MV / "security" / "90_drop_policies.sql").read_text()

    def test_policies_cover_spec_roles(self):
        principals = set(re.findall(r"\bTO `([^`]+)`", self.policies))
        self.assertEqual(principals, {"slc_territory_southeast", "slc_pickup_manhattan"})
        self.assertIn("sales_territory = 'Southeast'", self.functions)
        self.assertIn("borough = 'Manhattan'", self.functions)

    def test_policy_references_resolve(self):
        created = set(re.findall(r"CREATE OR REPLACE FUNCTION (slc\.security\.\w+)", self.functions))
        used = set(re.findall(r"ROW FILTER (slc\.security\.\w+)", self.policies))
        self.assertTrue(used and used <= created)
        tag_values = set(re.findall(r"SET TAG ON (?:TABLE|COLUMN) [\w.]+ (\w+) = (\w+)", self.tags))
        for key, value in re.findall(r"has_tag_value\('(\w+)', '(\w+)'\)", self.policies):
            self.assertIn((key, value), tag_values)

    def test_every_policy_is_dropped_in_the_accelerated_profile(self):
        created = set(re.findall(r"CREATE OR REPLACE POLICY (\w+)\s+ON SCHEMA ([\w.]+)", self.policies))
        dropped = set(re.findall(r"DROP POLICY (\w+) ON SCHEMA ([\w.]+)", self.drops))
        self.assertEqual(created, dropped)

    def test_grants_cover_policy_principals_on_semantic_schema_only(self):
        principals = set(re.findall(r"\bTO `([^`]+)`", self.policies))
        self.assertEqual(set(re.findall(r"ON SCHEMA slc\.semantic TO `([^`]+)`", self.grants)), principals)
        self.assertNotRegex(self.grants, r"ON (SCHEMA|TABLE) slc\.(wwi|nyctaxi)")

    def test_inventory_is_denied_and_stock_views_read_inventory_tables(self):
        self.assertIn("RETURN FALSE", self.functions)
        self.assertIn("slc_rls_scope = inventory", self.tags)
        self.assertIn("fact_stock_holding_daily", VIEWS["wwi_stock"]["source"])


class DeployTests(unittest.TestCase):
    def test_split_respects_dollar_blocks_quotes_and_comments(self):
        script = ("-- header; not a statement\nSELECT 'a;b' AS x;\n"
                  "CREATE VIEW v WITH METRICS LANGUAGE YAML AS $$\nversion: 1.1\ncomment: a; b\n$$;\n"
                  "SELECT `c;d` FROM t -- trailing; comment\n;\n-- only a comment;\n")
        stmts = deploy.split_statements(script)
        self.assertEqual(len(stmts), 3)
        self.assertIn("comment: a; b", stmts[1])
        self.assertTrue(deploy.code_of(stmts[2]).startswith("SELECT `c;d`"))

    def test_split_rejects_unterminated_dollar_block(self):
        with self.assertRaises(ValueError):
            deploy.split_statements("CREATE VIEW v WITH METRICS LANGUAGE YAML AS $$\nversion: 1.1\n;")

    def test_every_ddl_is_one_statement(self):
        for path in (MV / "sql").glob("*/*.sql"):
            self.assertEqual(len(deploy.split_statements(path.read_text())), 1, path.name)

    def test_governed_plan(self):
        steps = [deploy.code_of(s) for _, s in deploy.plan("governed")]
        first_policy = next(i for i, s in enumerate(steps) if s.startswith("CREATE OR REPLACE POLICY"))
        last_view = max(i for i, s in enumerate(steps) if s.startswith("CREATE OR REPLACE VIEW"))
        self.assertLess(last_view, first_policy)
        self.assertFalse(any(s.startswith(("REFRESH", "DROP POLICY")) for s in steps))
        self.assertEqual(sum(s.startswith("CREATE OR REPLACE VIEW") for s in steps), 7)
        self.assertEqual(sum(s.startswith("CREATE OR REPLACE POLICY") for s in steps), 3)

    def test_accelerated_plan(self):
        steps = [deploy.code_of(s) for _, s in deploy.plan("accelerated")]
        last_drop = max(i for i, s in enumerate(steps) if s.startswith("DROP POLICY"))
        first_view = next(i for i, s in enumerate(steps) if s.startswith("CREATE OR REPLACE VIEW"))
        self.assertLess(last_drop, first_view)
        self.assertFalse(any(s.startswith("CREATE OR REPLACE POLICY") for s in steps))
        refreshes = [s for s in steps if s.startswith("REFRESH MATERIALIZED VIEW")]
        self.assertEqual(sorted(refreshes), sorted(f"REFRESH MATERIALIZED VIEW slc.semantic.{v}" for v in bmv.MATERIALIZATION))
        self.assertGreater(steps.index(refreshes[0]), max(i for i, s in enumerate(steps) if s.startswith("CREATE OR REPLACE VIEW")))


class DivergenceRuleTests(unittest.TestCase):
    def test_known_divergence_must_be_a_strict_subset(self):
        query = next(q for q in reconcile.load_queries() if q.query_id == "Q-N-S2-D4")
        expected = ORACLE / "expected" / "questions" / "Q-N-S2-D4.csv"
        header, rows = expected_rows("questions", "Q-N-S2-D4")
        typed = [tuple(None if v == "" else v for v in r) for r in rows]
        self.assertEqual(check_against(header, typed, expected, query), (False, []))
        self.assertEqual(check_against(header, typed[:-2], expected, query), (True, []))
        tampered = [typed[0][:-1] + ("1.00",)] + typed[1:-2] if typed[0][-1] != "1.00" else [typed[0][:-1] + ("2.00",)]
        diverged, problems = check_against(header, tampered, expected, query)
        self.assertTrue(diverged and problems)

    def test_unknown_divergence_fails(self):
        query = next(q for q in reconcile.load_queries() if q.query_id == "Q-W-S1-P")
        header, rows = expected_rows("questions", "Q-W-S1-P")
        typed = [tuple(None if v == "" else v for v in r) for r in rows]
        diverged, problems = check_against(header, typed[1:], ORACLE / "expected" / "questions" / "Q-W-S1-P.csv", query)
        self.assertFalse(diverged)
        self.assertTrue(problems)


class ComparatorTests(unittest.TestCase):
    QID = "W-M1"

    def rows(self):
        header, rows = expected_rows("metrics", self.QID)
        typed = [tuple(r[:5]) + (float(r[5]) if r[5] else None,) for r in rows]
        return header, [tuple(None if v == "" else v for v in r[:5]) + (r[5],) for r in typed]

    def compare(self, rows):
        header, _ = expected_rows("metrics", self.QID)
        out = reconcile.Outcome(self.QID, "metrics")
        reconcile.compare_keyed(header, rows, ORACLE / "expected" / "metrics" / f"{self.QID}.csv", out)
        return out

    def test_exact_answer_matches(self):
        _, rows = self.rows()
        self.assertTrue(self.compare(rows).matches)

    def test_row_order_is_irrelevant(self):
        _, rows = self.rows()
        self.assertTrue(self.compare(list(reversed(rows))).matches)

    def test_missing_extra_and_different_rows_are_counted(self):
        _, rows = self.rows()
        broken = rows[1:] + [("year", "W-M1", "1999", None, None, 0.5)]
        changed = list(broken[0])
        changed[5] = (changed[5] or 0) + 0.01
        broken[0] = tuple(changed)
        out = self.compare(broken)
        self.assertEqual((out.missing, out.extra, out.different), (1, 1, 1))
        self.assertFalse(out.matches)

    def test_money_tolerance(self):
        header, rows = expected_rows("metrics", "W-S1")
        key = rows[0]
        out = reconcile.Outcome("W-S1", "metrics")
        actual = [tuple(None if v == "" else v for v in r[:5]) + (Decimal(r[5]),) for r in rows]
        actual[0] = actual[0][:5] + (Decimal(key[5]) + Decimal("0.004"),)
        reconcile.compare_keyed(header, actual, ORACLE / "expected" / "metrics" / "W-S1.csv", out)
        self.assertTrue(out.matches)
        actual[0] = actual[0][:5] + (Decimal(key[5]) + Decimal("0.006"),)
        out = reconcile.Outcome("W-S1", "metrics")
        reconcile.compare_keyed(header, actual, ORACLE / "expected" / "metrics" / "W-S1.csv", out)
        self.assertEqual(out.different, 1)


# ================================================================== 5. negative

class NegativeLintTests(unittest.TestCase):
    def assertRejected(self, doc, pattern):
        problems = lint.lint_view(doc, "t")
        self.assertTrue(any(re.search(pattern, p) for p in problems), problems)

    def test_valid_view_is_accepted(self):
        self.assertEqual(lint.lint_view(valid_view(), "t"), [])

    def test_malformed_yaml_document(self):
        text = (MV / "metric_views" / "nyc_trips.yaml").read_text().replace("measures:\n", "measures:\n  - name: [\n", 1)
        with self.assertRaises(yaml.YAMLError):
            yaml.safe_load(text)
        self.assertRejected(yaml.safe_load("- just\n- a list\n"), r"must be a mapping")

    def test_measure_reference_to_undefined_measure(self):
        doc = valid_view()
        doc["measures"].append({"name": "broken_ratio", "expr": "MEASURE(trip_count) / MEASURE(no_such_measure)",
                                "display_name": "Broken"})
        self.assertRejected(doc, r"MEASURE\(no_such_measure\) references an undefined measure")

    def test_query_measure_reference_to_undefined_measure(self):
        sql = "SELECT pickup_month, MEASURE(no_such_measure) FROM slc.semantic.nyc_trips GROUP BY pickup_month"
        self.assertTrue(any("no_such_measure" in p for p in lint.lint_query(sql, VIEWS)))

    def test_version_rules(self):
        for bad in ("1.1", 0.1, None, True):
            doc = valid_view()
            doc["version"] = bad
            self.assertRejected(doc, r"version must be a number")

    def test_unknown_keys(self):
        doc = valid_view()
        doc["dimensions"] = []
        self.assertRejected(doc, r"unknown top-level keys|use fields")
        doc = valid_view()
        doc["measures"][0]["aggregation"] = "sum"
        self.assertRejected(doc, r"unknown keys \['aggregation'\]")

    def test_duplicate_and_badly_named_members(self):
        doc = valid_view()
        doc["measures"].append(dict(doc["measures"][0]))
        self.assertRejected(doc, r"duplicates a measure name")
        doc = valid_view()
        doc["fields"][0]["name"] = "Pickup Date"
        self.assertRejected(doc, r"lower_snake_case")

    def test_metadata_limits(self):
        doc = valid_view()
        doc["fields"][0]["synonyms"] = [f"s{i}" for i in range(11)]
        self.assertRejected(doc, r"at most 10")
        doc = valid_view()
        doc["fields"][0]["synonyms"] = ["x" * 256]
        self.assertRejected(doc, r"1-255 characters")
        doc = valid_view()
        doc["measures"][0]["display_name"] = "x" * 256
        self.assertRejected(doc, r"display_name")

    def test_format_rules(self):
        doc = valid_view()
        fmt = next(m for m in doc["measures"] if m["format"]["type"] == "currency")["format"]
        del fmt["currency_code"]
        self.assertRejected(doc, r"currency_code")
        doc = valid_view()
        doc["measures"][0]["format"] = {"type": "money"}
        self.assertRejected(doc, r"format.type")
        doc = valid_view()
        doc["measures"][0]["format"]["decimal_places"] = {"type": "exact", "places": "two"}
        self.assertRejected(doc, r"decimal_places")

    def test_join_rules(self):
        doc = valid_view()
        doc["joins"][0]["using"] = ["pickup_date"]
        self.assertRejected(doc, r"exactly one of on or using")
        doc = valid_view()
        doc["joins"][0]["cardinality"] = "many_to_many"
        self.assertRejected(doc, r"cardinality")
        doc = valid_view()
        doc["fields"][0]["expr"] = "zones.zone"
        self.assertRejected(doc, r"qualifier 'zones'")
        doc = valid_view()
        doc["joins"].append(dict(doc["joins"][0]))
        self.assertRejected(doc, r"duplicate join name")

    def test_window_rules(self):
        cases = [
            ({"order": "pickup_date", "range": "rolling 7 day"}, r"range 'rolling 7 day' is not supported"),
            ({"order": "pickup_date", "range": "trailing 7 fortnight"}, r"is not supported"),
            ({"order": "trip_hour", "range": "current"}, r"order 'trip_hour' is not a field"),
            ({"order": "pickup_date", "range": "current", "semiadditive": "average"}, r"semiadditive"),
            ({"order": "pickup_date", "range": "cumulative", "offset": "last year"}, r"offset"),
            ({"order": "pickup_date", "range": "current", "partition": "x"}, r"unknown window keys"),
        ]
        for window, pattern in cases:
            doc = valid_view()
            doc["measures"][0]["window"] = [window]
            self.assertRejected(doc, pattern)
        doc = valid_view()
        doc["measures"][0]["window"] = [{"order": "pickup_date", "range": "cumulative"},
                                        {"order": "pickup_hour", "range": "current"}]
        self.assertRejected(doc, r"pickup_hour is not derived from pickup_date")

    def test_composition_rules(self):
        doc = valid_view()
        doc["measures"].append({"name": "a", "expr": "MEASURE(b) + 1", "display_name": "A"})
        doc["measures"].append({"name": "b", "expr": "MEASURE(a) + 1", "display_name": "B"})
        self.assertRejected(doc, r"measure cycle")
        doc = valid_view()
        doc["measures"].append({"name": "plain", "expr": "fare_amount * 2", "display_name": "Plain"})
        self.assertRejected(doc, r"must aggregate")
        doc = valid_view()
        doc["fields"].append({"name": "bad_field", "expr": "SUM(fare_amount)", "display_name": "Bad"})
        self.assertRejected(doc, r"aggregate functions belong in measures")

    def test_materialization_rules(self):
        base = valid_view()
        base["materialization"] = copy.deepcopy(bmv.MATERIALIZATION["nyc_trips"])
        self.assertEqual(lint.lint_view(base, "t"), [])
        mutations = [
            (lambda m: m.update(mode="strict"), r"mode must be relaxed"),
            (lambda m: m.update(schedule="hourly"), r"schedule"),
            (lambda m: m["materialized_views"][0]["measures"].append("no_such"), r"'no_such' is not a measure"),
            (lambda m: m["materialized_views"][0]["dimensions"].append("no_such"), r"'no_such' is not a field"),
            (lambda m: m["materialized_views"][0].update(partition_by=["pickup_date"]), r"exclusive"),
            (lambda m: m["materialized_views"][0].update(refresh_policy="sometimes"), r"refresh_policy"),
            (lambda m: m["materialized_views"].extend([{"name": "u1", "type": "unaggregated"},
                                                       {"name": "u2", "type": "unaggregated"}]), r"at most one"),
            (lambda m: m["materialized_views"][0].update(cluster_by={"cols": ["pickup_zone"]}), r"not materialized"),
        ]
        for mutate, pattern in mutations:
            doc = copy.deepcopy(base)
            mutate(doc["materialization"])
            self.assertRejected(doc, pattern)
        doc = copy.deepcopy(base)
        doc["filter"] = "is_account_group_member('analysts')"
        self.assertRejected(doc, r"invoker-dependent")

    def test_query_rules(self):
        cases = [
            ("SELECT SUM(total_amount) FROM slc.nyctaxi.fact_trip", r"only slc.semantic"),
            ("SELECT MEASURE(trip_count) FROM slc.semantic.taxi_trips", r"not a defined metric view"),
            ("SELECT MEASURE(revenue) FROM slc.semantic.nyc_trips", r"not a measure of"),
            ("SELECT 1 AS x", r"reads no slc.semantic"),
            ("SELECT MEASURE(trip_count) FROM slc.semantic.nyc_trips JOIN dim_zone z ON 1 = 1", r"physical table"),
        ]
        for sql, pattern in cases:
            problems = lint.lint_query(sql, VIEWS)
            self.assertTrue(any(re.search(pattern, p) for p in problems), (sql, problems))


# ================================================================== 6. emulation on fixtures

class FixtureEmulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = ro.SparkEngine(fixtures=ORACLE / "fixtures", spark=spark())
        cls.emu = local_emulator.Emulator(cls.engine)

    def test_every_query_resolves_with_the_oracle_columns(self):
        wrong = {}
        for q in reconcile.load_queries():
            header, _ = expected_rows(q.kind, q.query_id)
            cols = [c for c, _ in self.emu.analyze(q.sql)]
            if cols != header:
                wrong[q.query_id] = cols
        self.assertEqual(wrong, {})

    def test_non_window_queries_equal_the_oracle_on_fixtures(self):
        tmp = Path(tempfile.mkdtemp(prefix="slc-mv-oracle-"))
        try:
            oracle = {q.query_id: q for q in ro.load_queries()}
            failures, compared = {}, 0
            for q in reconcile.load_queries():
                if self.emu.uses_window(q.sql):
                    continue
                columns, rows = self.engine.execute(oracle[q.query_id].sql)
                expected = tmp / q.kind / f"{q.query_id}.csv"
                ro.write_csv(columns, rows, expected)
                got_cols, got_rows = self.emu.execute(q.sql)
                _, problems = check_against(got_cols, got_rows, expected, q)
                compared += 1
                if problems:
                    failures[q.query_id] = problems
            self.assertEqual(failures, {})
            self.assertEqual(compared, 65)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_window_measures_are_not_emulated(self):
        with self.assertRaises(local_emulator.WindowMeasureError):
            self.emu.execute("SELECT MEASURE(revenue_ytd) FROM slc.semantic.nyc_trips")

    def test_unknown_view_and_measure_are_rejected(self):
        with self.assertRaises(KeyError):
            self.emu.rewrite_query("SELECT MEASURE(trip_count) FROM slc.semantic.no_such_view")
        with self.assertRaises(KeyError):
            self.emu.rewrite_query("SELECT MEASURE(no_such_measure) FROM slc.semantic.nyc_trips")

    def test_unknown_field_fails_resolution(self):
        with self.assertRaises(Exception):
            self.emu.analyze("SELECT no_such_field, MEASURE(trip_count) FROM slc.semantic.nyc_trips GROUP BY no_such_field")


# ================================================================== 7. real data

@unittest.skipUnless(os.environ.get("SLC_LOCAL_B0"), "SLC_LOCAL_B0 not set")
class RealDataEmulationTests(unittest.TestCase):
    def test_non_window_queries_reproduce_committed_answers_on_b0(self):
        engine = ro.SparkEngine(data_root=Path(os.environ["SLC_LOCAL_B0"]) / "warehouse", spark=spark())
        emu = local_emulator.Emulator(engine)
        failures, compared, divergent = {}, 0, set()
        for q in reconcile.load_queries():
            if emu.uses_window(q.sql):
                continue
            columns, rows = emu.execute(q.sql)
            diverged, problems = check_against(columns, rows, ORACLE / "expected" / q.kind / f"{q.query_id}.csv", q)
            compared += 1
            if problems:
                failures[q.query_id] = problems
            if diverged:
                divergent.add(q.query_id)
        self.assertEqual(failures, {})
        self.assertEqual(compared, 65)
        # Every documented divergence is observed on the real data; an unobserved one would be a stale claim.
        self.assertEqual(divergent, {q for q, (_, on_b0) in KNOWN_DIVERGENCES.items() if on_b0})


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    if SPARK is not None:
        SPARK.stop()
    sys.exit(0 if result.wasSuccessful() else 1)
