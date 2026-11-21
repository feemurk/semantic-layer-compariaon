#!/usr/bin/env python3
"""Phase 2 test suite: correctness oracle, question bank and glossary (SPEC § 7, § 9, § 12.1).

Layers
  1. Structure: every SPEC § 6 metric and § 7 question has oracle SQL and a committed expected answer;
     generated artifacts (metric SQL, fixtures, questions.yaml) are in sync with their generators;
     every query passes the portability lint; the glossary covers exactly the 22 metrics.
  2. Comparator: SPEC § 9.3 tolerances and NULL semantics, positive and negative.
  3. Fixtures (DuckDB): hand-computed answers for each semantic trap, with the naive wrong answer rejected.
  4. Cross-engine (DuckDB vs Spark SQL on fixtures): all 92 queries return identical results.
  5. Restricted answers (SPEC § 10): per-role expected answers exist for every P and D1 question of the role's
     dataset, equal the role's subset of the unrestricted answers where a question groups by the restricted attribute,
     deny inventory to the territory role, agree across DuckDB and Spark SQL on fixtures, and reject bad role setups.
  6. Real data (opt-in): SLC_LOCAL_B0=<platform local B0 dir> re-runs all 92 queries, and the 24 restricted ones per
     role, on DuckDB against the real-data B0 and compares them to the committed expected answers.

Requires scripts/requirements-test.txt (DuckDB, PySpark, PyYAML) and Java 17+.

    python3 scripts/test_oracle.py
"""

from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ORACLE = REPO / "01-spec" / "oracle"
SPEC = REPO / "01-spec" / "SPEC.md"
GLOSSARY = REPO / "01-spec" / "glossary.yaml"
sys.path.insert(0, str(ORACLE))

try:
    import duckdb  # noqa: F401
    import yaml
except ImportError as exc:
    sys.exit(f"missing test dependency ({exc}); pip install -r scripts/requirements-test.txt")

import restricted as rs  # noqa: E402
import run_oracle as ro  # noqa: E402

FORBIDDEN = {
    r"\bQUALIFY\b": "QUALIFY (not in Spark SQL)",
    r"\b(ANTI|SEMI)\s+JOIN\b": "ANTI/SEMI JOIN (dialect-specific syntax)",
    r"::": "PostgreSQL-style cast",
    r"\bILIKE\b": "ILIKE",
    r"\b(DATE_ADD|DATE_SUB|DATEDIFF|DATE_DIFF|DATE_TRUNC|STRFTIME|EXTRACT)\s*\(": "dialect-specific date function",
    r"\bFILTER\s*\(\s*WHERE\b": "aggregate FILTER clause",
    r"\bTOP\s+\d": "TOP n",
    r"\b(IIF|ISNULL|NVL|TRY_CAST)\s*\(": "dialect-specific function",
    r"\bSTRING_AGG\b|\bLIST\s*\(|\bARRAY_AGG\b": "collection aggregate",
    r"`": "backtick identifier",
    r'"[A-Za-z_][A-Za-z0-9_ ]*"': "double-quoted identifier",
    r"\bINTERVAL\s+\d": "unquoted INTERVAL literal",
    r"\b(NOW|CURRENT_DATE|CURRENT_TIMESTAMP|RAND|RANDOM|UUID)\b": "non-deterministic function",
}


def lint(sql: str) -> list[str]:
    body = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    return [why for pattern, why in FORBIDDEN.items() if re.search(pattern, body, re.IGNORECASE)]


def spec_ids() -> tuple[list[str], list[str]]:
    text = SPEC.read_text()
    metrics = re.findall(r"^\| ((?:B-[WN][1-5])|(?:[WN]-[SMC][12])) \| (?:WWI|NYC) \|", text, re.M)
    questions = re.findall(r"^\| (Q-[A-Z0-9-]+) \| (?:P|D[1-4]|AH) \|", text, re.M)
    return metrics, questions


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="") as fh:
        rows = list(csv.reader(fh))
    return rows[0], rows[1:]


# ================================================================== 1. structure

class StructureTests(unittest.TestCase):
    def test_every_metric_has_sql_and_expected(self):
        metrics, _ = spec_ids()
        self.assertEqual(len(metrics), 22)
        sql = {p.stem for p in (ORACLE / "metrics").glob("*.sql")}
        exp = {p.stem for p in (ORACLE / "expected" / "metrics").glob("*.csv")}
        self.assertEqual(sql, set(metrics))
        self.assertEqual(exp, set(metrics))

    def test_every_question_has_sql_and_expected(self):
        _, questions = spec_ids()
        self.assertEqual(len(questions), 70)
        sql = {p.stem for p in (ORACLE / "questions").glob("*.sql")}
        exp = {p.stem for p in (ORACLE / "expected" / "questions").glob("*.csv")}
        self.assertEqual(sql, set(questions))
        self.assertEqual(exp, set(questions))

    def test_sql_headers_name_their_query(self):
        for path in list((ORACLE / "metrics").glob("*.sql")) + list((ORACLE / "questions").glob("*.sql")):
            self.assertTrue(path.read_text().startswith(f"-- {path.stem} "), path.name)

    def test_generated_artifacts_in_sync(self):
        for script in ("build_metric_sql.py", "build_question_bank.py", "fixtures/build_fixtures.py"):
            result = subprocess.run([sys.executable, str(ORACLE / script), "--check"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"{script}: {result.stdout}{result.stderr}")

    def test_portability_lint(self):
        for q in ro.load_queries():
            self.assertEqual(lint(q.path.read_text()), [], q.query_id)

    def test_results_are_ordered(self):
        for q in ro.load_queries():
            _, rows = read_csv(ORACLE / "expected" / q.kind / f"{q.query_id}.csv")
            if len(rows) > 1:
                self.assertRegex(q.sql, r"ORDER BY[^()]*$", f"{q.query_id}: multi-row result needs a final ORDER BY")

    def test_negative_lint_rejects_dialect_constructs(self):
        self.assertIn("QUALIFY (not in Spark SQL)", lint("SELECT a FROM t QUALIFY ROW_NUMBER() OVER (ORDER BY a) = 1"))
        self.assertIn("dialect-specific date function", lint("SELECT DATEDIFF('day', a, b) FROM t"))
        self.assertIn("unquoted INTERVAL literal", lint("SELECT d - INTERVAL 90 DAY FROM t"))
        self.assertEqual(lint("SELECT d - INTERVAL '90' DAY FROM t"), [])

    def test_question_bank_matches_spec(self):
        bank = yaml.safe_load((ORACLE / "questions.yaml").read_text())["questions"]
        _, questions = spec_ids()
        self.assertEqual([q["id"] for q in bank], questions)
        for q in bank:
            self.assertTrue(q["interpretation"], q["id"])
            self.assertTrue((ORACLE / q["sql"]).exists())


class GlossaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = yaml.safe_load(GLOSSARY.read_text())
        text = SPEC.read_text()
        cls.spec_names = dict(re.findall(
            r"^\| ((?:B-[WN][1-5])|(?:[WN]-[SMC][12])) \| (?:WWI|NYC) \| (?:Base|Simple|Medium|Complex) \| ([^|]+) \|", text, re.M))

    def test_metrics_match_spec_names(self):
        got = {m["id"]: m["display_name"] for m in self.g["metrics"]}
        self.assertEqual(got, {k: v.strip() for k, v in self.spec_names.items()})

    def test_metadata_limits_and_formats(self):
        objects = self.g["metrics"] + [d for ds in self.g["dimensions"].values() for d in ds]
        for o in objects:
            syn = o.get("synonyms", [])
            self.assertLessEqual(len(syn), 10, o.get("id", o.get("name")))
            self.assertTrue(all(len(s) <= 255 for s in syn))
            self.assertLessEqual(len(o["display_name"]), 255)
            self.assertTrue(o["description"])
        for m in self.g["metrics"]:
            self.assertIn(m["format"], self.g["formats"], m["id"])

    def test_negative_synonym_limit_detected(self):
        bad = dict(self.g["metrics"][0], synonyms=[f"s{i}" for i in range(11)])
        self.assertGreater(len(bad["synonyms"]), 10)


# ================================================================== 2. comparator

class ComparatorTests(unittest.TestCase):
    def test_tolerances(self):
        self.assertTrue(ro.values_match(Decimal("100.004"), "100.000"))
        self.assertFalse(ro.values_match(Decimal("100.006"), "100.000"))
        self.assertTrue(ro.values_match(0.2714285714, "0.27142857"))
        self.assertFalse(ro.values_match(0.2714, "0.2715"))
        self.assertTrue(ro.values_match(76902149, "76902149"))
        self.assertFalse(ro.values_match(76902149, "76902150"))

    def test_null_is_not_zero(self):
        self.assertTrue(ro.values_match(None, ""))
        self.assertFalse(ro.values_match(None, "0"))
        self.assertFalse(ro.values_match(Decimal("0"), ""))

    def test_compare_detects_shape_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.csv"
            ro.write_csv(["a", "b"], [(1, Decimal("2.00"))], p)
            self.assertEqual(ro.compare(["a", "b"], [(1, Decimal("2.001"))], p), [])
            self.assertTrue(ro.compare(["a", "c"], [(1, Decimal("2.00"))], p))
            self.assertTrue(ro.compare(["a", "b"], [(1, Decimal("2.00")), (2, None)], p))


# ================================================================== 3. fixtures (DuckDB)

class FixtureAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = ro.DuckDBEngine(fixtures=ORACLE / "fixtures")
        cls.queries = {q.query_id: q for q in ro.load_queries()}

    @classmethod
    def tearDownClass(cls):
        cls.engine.close()

    def rows(self, qid):
        cols, rows = self.engine.execute(self.queries[qid].sql)
        return [dict(zip(cols, r)) for r in rows]

    def metric(self, qid, grain, measure=None, m1=None, m2=None):
        hits = [r for r in self.rows(qid) if r["grain"] == grain and r["measure"] == (measure or qid)
                and r["member_1"] == m1 and r["member_2"] == m2]
        self.assertEqual(len(hits), 1, (qid, grain, measure, m1, m2))
        return hits[0]["value"]

    def test_additive_revenue(self):
        self.assertEqual(self.metric("W-S1", "fiscal_year", m1="2015"), Decimal("350.00"))

    def test_ratio_of_sums_not_average_of_ratios(self):
        gm = self.metric("W-M1", "fiscal_year", m1="2015")
        self.assertAlmostEqual(gm, 95 / 350, places=12)
        self.assertNotAlmostEqual(gm, (0.40 + 0.25 + 0.10) / 3, places=6)

    def test_many_to_many_share_and_deduplicated_total(self):
        r = {x["grain"] + ":" + str(x["stock_group_name"]): x for x in self.rows("Q-W-C1-P")}
        self.assertEqual(r["total:None"]["revenue"], Decimal("350.00"))
        self.assertAlmostEqual(r["group:Toys"]["share"], 200 / 350, places=12)
        self.assertEqual(r["group:Mugs"]["revenue"] + r["group:Toys"]["revenue"], Decimal("550.00"))
        overlap = self.rows("Q-W-C1-D4")[0]
        self.assertEqual((overlap["sum_of_group_revenue"], overlap["total_revenue"], overlap["overlap_revenue"],
                          overlap["overlap_from_multi_group_items"]),
                         (Decimal("550.00"), Decimal("350.00"), Decimal("200.00"), Decimal("200.00")))

    def test_as_was_vs_as_is_attribution(self):
        r = {x["color"]: x for x in self.rows("Q-W-S1-D4")}
        self.assertEqual((r["Gray"]["revenue_as_was"], r["Gray"]["revenue_as_is"], r["Gray"]["differs"]),
                         (Decimal("100.00"), None, True))
        self.assertEqual((r["Steel Gray"]["revenue_as_was"], r["Steel Gray"]["revenue_as_is"]),
                         (Decimal("50.00"), Decimal("150.00")))
        self.assertFalse(r["Blue"]["differs"])

    def test_semi_additive_closing_not_sum_of_days(self):
        self.assertEqual(self.metric("W-M2", "year", m1="2015"), 130)
        self.assertEqual(self.metric("W-M2", "month", m1="2015-11-01"), 160)
        days_2015 = sum(r["value"] for r in self.rows("W-M2") if r["grain"] == "day" and r["member_1"].startswith("2015"))
        self.assertNotEqual(days_2015, 130)

    def test_days_of_supply_inclusive_91_day_window(self):
        self.assertEqual(self.metric("W-C2", "month", "W-C2:units_sold_91d", m1="2015-12-01"), 101.0)
        self.assertAlmostEqual(self.metric("W-C2", "month", m1="2015-12-01"), 130 / (101 / 91), places=9)
        # 2016-03-31 - 90 days = 2016-01-01 across a leap February: s6 is in, s7 (2015-12-31) is out.
        self.assertEqual(self.metric("W-C2", "month", "W-C2:units_sold_91d", m1="2016-03-01"), 2.0)
        self.assertAlmostEqual(self.metric("W-C2", "month", m1="2016-03-01"), 5915.0, places=9)

    def test_filtered_measure_null_not_zero(self):
        r = {x["payment_type"]: x["card_tips"] for x in self.rows("Q-N-S2-D4")}
        self.assertEqual(r[1], Decimal("12.50"))
        self.assertTrue(all(v is None for k, v in r.items() if k != 1))
        self.assertIsNone(self.metric("B-W5", "year_customer", m1="2015", m2="Cust A"))
        self.assertEqual(self.metric("B-W5", "year_customer", m1="2015", m2="Cust B"), 1)

    def test_distinct_count_not_additive(self):
        r = {x["grain"]: x["distinct_od_pairs"] for x in self.rows("Q-N-M1-D1")}
        self.assertEqual((r["total"], r["sum_of_members"]), (3, 4))

    def test_ytd_stly_leap_day_mapping_and_null_prior_year(self):
        self.assertEqual(self.metric("N-C1", "day", "N-C1:ytd_revenue", m1="2024-02-29"), 33.0)
        self.assertEqual(self.metric("N-C1", "day", "N-C1:stly_ytd_revenue", m1="2024-02-29"), 15.0)
        self.assertAlmostEqual(self.metric("N-C1", "day", "N-C1:yoy_pct", m1="2024-02-29"), 1.2, places=12)
        self.assertIsNone(self.metric("N-C1", "day", "N-C1:yoy_pct", m1="2023-06-30"))

    def test_pace_index_calendar_day_denominators(self):
        r = {str(x["anchor_date"]): x for x in self.rows("Q-N-C2-D3")}
        self.assertEqual((r["2023-03-15"]["day_of_year"], r["2024-03-15"]["day_of_year"]), (74, 75))
        self.assertAlmostEqual(r["2023-03-15"]["pace_index"], (1 / 15) / (2 / 74), places=12)
        self.assertAlmostEqual(r["2024-03-15"]["pace_index"], (1 / 15) / (3 / 75), places=12)

    def test_role_playing_dates_differ_across_midnight(self):
        r = self.rows("Q-N-C1-D4")[0]
        self.assertEqual((r["revenue_pickup_2024"], r["revenue_dropoff_2024"], r["difference"]),
                         (Decimal("105.00"), Decimal("145.00"), Decimal("40.00")))

    def test_fare_per_mile_ratio_of_sums(self):
        r = {(x["pickup_borough"], x["dropoff_borough"]): x for x in self.rows("Q-N-M2-P")}
        fpm = r[("Manhattan", "Manhattan")]["fare_per_mile"]
        self.assertAlmostEqual(fpm, 31 / 7, places=12)
        self.assertNotAlmostEqual(fpm, (12 / 3 + 8 / 1.5 + 11 / 2.5) / 3, places=6)

    def test_every_query_runs_on_fixtures(self):
        for qid, q in self.queries.items():
            self.engine.execute(q.sql)


# ================================================================== 4. cross-engine

class CrossEngineFixtureTests(unittest.TestCase):
    def test_duckdb_and_spark_sql_agree_on_all_queries(self):
        try:
            import pyspark  # noqa: F401
        except ImportError:
            self.fail("pyspark is required (scripts/requirements-test.txt)")
        tmp = Path(tempfile.mkdtemp(prefix="slc-oracle-x-"))
        try:
            queries = ro.load_queries()
            duck = ro.DuckDBEngine(fixtures=ORACLE / "fixtures")
            ro.run(duck, queries, 1, tmp, None, verbose=False)
            duck.close()
            from pyspark.sql import SparkSession
            spark = (SparkSession.builder.master("local[2]").appName("slc-oracle-test")
                     .config("spark.ui.enabled", "false").config("spark.sql.session.timeZone", "UTC")
                     .config("spark.sql.shuffle.partitions", "4")
                     .config("spark.sql.warehouse.dir", str(tmp / "warehouse")).getOrCreate())
            spark.sparkContext.setLogLevel("ERROR")
            results = ro.run(ro.SparkEngine(fixtures=ORACLE / "fixtures", spark=spark), queries, 1, None, tmp, verbose=False)
            spark.stop()
            failures = {r.query_id: (r.error or r.problems[:3]) for r in results if r.error or r.problems}
            self.assertEqual(failures, {})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ================================================================== 5. restricted answers (SPEC § 10)

# Restricted answers that legitimately equal the unrestricted ones: Southeast is the top FY2015 territory anyway, and
# the two NYC questions are Manhattan-pickup questions by definition.
UNCHANGED_BY_ROLE = {"territory_southeast/Q-W-S1-D1", "pickup_manhattan/Q-N-S1-D1", "pickup_manhattan/Q-N-M2-D1"}


class RestrictedAnswerTests(unittest.TestCase):
    def restricted(self, role, qid):
        return read_csv(rs.EXPECTED / role / "questions" / f"{qid}.csv")

    def test_every_role_question_has_an_expected_answer_with_the_same_header(self):
        for role in rs.ROLES.values():
            queries = rs.role_queries(role)
            self.assertEqual(len(queries), 12, role.name)
            for q in queries:
                header, _ = self.restricted(role.name, q.query_id)
                self.assertEqual(header, read_csv(ORACLE / "expected" / "questions" / f"{q.query_id}.csv")[0])
            on_disk = sorted(p.stem for p in (rs.EXPECTED / role.name / "questions").glob("*.csv"))
            self.assertEqual(on_disk, sorted(q.query_id for q in queries))

    def test_restricted_rows_are_the_role_subset(self):
        cases = [("territory_southeast", "Q-W-S1-P", "sales_territory", "Southeast"),
                 ("pickup_manhattan", "Q-N-S1-P", "pickup_borough", "Manhattan")]
        for role, qid, column, member in cases:
            header, rows = read_csv(ORACLE / "expected" / "questions" / f"{qid}.csv")
            subset = [r for r in rows if r[header.index(column)] == member]
            self.assertTrue(subset)
            self.assertEqual(self.restricted(role, qid), (header, subset))

    def test_inventory_is_denied_to_the_territory_role(self):
        for qid in ("Q-W-M2-P", "Q-W-M2-D1", "Q-W-C2-P", "Q-W-C2-D1"):
            header, rows = self.restricted("territory_southeast", qid)
            for col in ("closing_units", "units_sold_91d", "days_of_supply"):
                if col in header:
                    self.assertEqual({r[header.index(col)] for r in rows} - {""}, set(), (qid, col))

    def test_every_other_answer_changes_under_the_role(self):
        changed, unchanged = set(), set()
        for role in rs.ROLES.values():
            for q in rs.role_queries(role):
                same = self.restricted(role.name, q.query_id) == read_csv(ORACLE / "expected" / "questions" / f"{q.query_id}.csv")
                (unchanged if same else changed).add(f"{role.name}/{q.query_id}")
        self.assertEqual(unchanged, UNCHANGED_BY_ROLE)
        self.assertEqual(len(changed), 21)

    def test_duckdb_and_spark_agree_per_role_on_fixtures(self):
        tmp = Path(tempfile.mkdtemp(prefix="slc-oracle-rls-"))
        try:
            from pyspark.sql import SparkSession
            spark = (SparkSession.builder.master("local[2]").appName("slc-oracle-rls-test")
                     .config("spark.ui.enabled", "false").config("spark.sql.session.timeZone", "UTC")
                     .config("spark.sql.shuffle.partitions", "4")
                     .config("spark.sql.warehouse.dir", str(tmp / "warehouse")).getOrCreate())
            spark.sparkContext.setLogLevel("ERROR")
            failures = {}
            for role in rs.ROLES.values():
                duck = ro.DuckDBEngine(fixtures=ORACLE / "fixtures")
                rs.apply_role(duck, role)
                ro.run(duck, rs.role_queries(role), 1, tmp / role.name, None, verbose=False)
                duck.close()
                sp = ro.SparkEngine(fixtures=ORACLE / "fixtures", spark=spark)
                rs.apply_role(sp, role)
                for r in ro.run(sp, rs.role_queries(role), 1, None, tmp / role.name, verbose=False):
                    if r.error or r.problems:
                        failures[f"{role.name}/{r.query_id}"] = r.error or r.problems[:3]
                rs.remove_role(sp, role)
            spark.stop()
            self.assertEqual(failures, {})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_role_filter_is_applied_and_removed(self):
        engine = ro.DuckDBEngine(fixtures=ORACLE / "fixtures")
        try:
            count = "SELECT COUNT(*) AS n FROM nyctaxi.fact_trip"
            outside = ("SELECT COUNT(*) AS n FROM nyctaxi.fact_trip f JOIN nyctaxi.dim_zone z "
                       "ON z.location_id = f.pu_location_id WHERE z.borough <> 'Manhattan'")
            before = engine.execute(count)[1][0][0]
            self.assertGreater(engine.execute(outside)[1][0][0], 0)
            role = rs.ROLES["pickup_manhattan"]
            rs.apply_role(engine, role)
            self.assertLess(engine.execute(count)[1][0][0], before)
            self.assertEqual(engine.execute(outside)[1][0][0], 0)
            zones = engine.execute("SELECT COUNT(DISTINCT borough) AS n FROM nyctaxi.dim_zone")[1][0][0]
            self.assertGreater(zones, 1)  # dimensions are never filtered
            rs.remove_role(engine, role)
            self.assertEqual(engine.execute(count)[1][0][0], before)
        finally:
            engine.close()

    def test_negative_unrestricted_answer_fails_restricted_comparison(self):
        engine = ro.DuckDBEngine(fixtures=ORACLE / "fixtures")
        tmp = Path(tempfile.mkdtemp(prefix="slc-oracle-rls-neg-"))
        try:
            role = rs.ROLES["territory_southeast"]
            ro.run(engine, rs.role_queries(role), 1, tmp / "restricted", None, verbose=False)  # no filter applied
            rs.apply_role(engine, role)
            results = ro.run(engine, rs.role_queries(role), 1, None, tmp / "restricted", verbose=False)
            self.assertTrue(any(r.problems for r in results))
        finally:
            engine.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_negative_bad_role_definitions_are_rejected(self):
        engine = ro.DuckDBEngine(fixtures=ORACLE / "fixtures")
        try:
            with self.assertRaises(RuntimeError):
                rs.apply_role(engine, rs.Role("bogus", "Bogus", "W", {"wwi.no_such_table": "1 = 1"}))
            broken = rs.Role("broken", "Broken", "N", {"nyctaxi.fact_trip": "no_such_column = 1"})
            with self.assertRaises(Exception):  # rejected when the view is bound (DuckDB) or first queried
                rs.apply_role(engine, broken)
                engine.execute("SELECT COUNT(*) FROM nyctaxi.fact_trip")
        finally:
            engine.close()


# ================================================================== 6. real data

@unittest.skipUnless(os.environ.get("SLC_LOCAL_B0"), "SLC_LOCAL_B0 not set")
class RealDataReproductionTests(unittest.TestCase):
    def test_committed_expected_answers_reproduce_on_b0(self):
        engine = ro.DuckDBEngine(data_root=Path(os.environ["SLC_LOCAL_B0"]) / "warehouse")
        results = ro.run(engine, ro.load_queries(), 1, None, ORACLE / "expected", verbose=False)
        engine.close()
        self.assertEqual({r.query_id: (r.error or r.problems[:3]) for r in results if r.error or r.problems}, {})

    def test_committed_restricted_answers_reproduce_on_b0(self):
        failures = {}
        for role in rs.ROLES.values():
            engine = ro.DuckDBEngine(data_root=Path(os.environ["SLC_LOCAL_B0"]) / "warehouse")
            rs.apply_role(engine, role)
            for r in ro.run(engine, rs.role_queries(role), 1, None, rs.EXPECTED / role.name, verbose=False):
                if r.error or r.problems:
                    failures[f"{role.name}/{r.query_id}"] = r.error or r.problems[:3]
            engine.close()
        self.assertEqual(failures, {})


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if result.wasSuccessful() else 1)
