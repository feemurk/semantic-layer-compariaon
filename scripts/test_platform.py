#!/usr/bin/env python3
"""Phase 2 test suite: shared data platform (02-implementations/platform, SPEC § 4-5, § 9.4).

Layers
  1. Static (PyYAML): bundle structure and cross-references, schema.py vs SPEC § 5,
     SQL Server preparation script coverage.
  2. Transform unit tests (local PySpark on fixtures): calendar, WWI conform and the
     daily snapshot derivation, NYC normalization / conform / trip_id, replay planning.
  3. Profiling checks: every check executes; targeted violations are detected.
  4. Real data (opt-in):
       SLC_LOCAL_B0=<dir>   warehouse built by 02-implementations/platform/tools/local_b0.py;
                            asserts zero profiling failures and the source-profiled row counts.
       SLC_TLC_DIR=<dir>    raw TLC files; asserts lossless normalization across schema drift.
       SLC_SQLSERVER_CONTAINER=<name>  restored WWI in a SQL Server container; runs the
                            preparation script twice (idempotency) and checks change tracking.

Requires scripts/requirements-test.txt and Java 17+. Exits non-zero on failure.

    python3 scripts/test_platform.py
"""

from __future__ import annotations

import copy
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLATFORM = REPO / "02-implementations" / "platform"
SRC = PLATFORM / "src"
SPEC = REPO / "01-spec" / "SPEC.md"
sys.path.insert(0, str(SRC))

try:
    import yaml
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
except ImportError as exc:  # pinned deps are mandatory, never a silent skip
    sys.exit(f"missing test dependency ({exc}); pip install -r scripts/requirements-test.txt")

from slc_platform import calendar, nyctaxi, profiling, replay, wwi  # noqa: E402
from slc_platform.schema import (  # noqa: E402
    DATE_COLUMNS,
    NYC_TABLES,
    WWI_TABLES,
)

SPARK: SparkSession | None = None
WAREHOUSE: str | None = None


def setUpModule():
    global SPARK, WAREHOUSE
    WAREHOUSE = tempfile.mkdtemp(prefix="slc-test-warehouse-")
    SPARK = (
        SparkSession.builder.master("local[2]")
        .appName("slc-test-platform")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.warehouse.dir", WAREHOUSE)
        .getOrCreate()
    )
    SPARK.sparkContext.setLogLevel("ERROR")


def tearDownModule():
    if SPARK is not None:
        SPARK.stop()
    if WAREHOUSE:
        shutil.rmtree(WAREHOUSE, ignore_errors=True)


def spark_type(sql_type: str) -> str:
    return sql_type.lower()


def schema_of(df) -> list[tuple[str, str]]:
    return [(f.name, f.dataType.simpleString()) for f in df.schema.fields]


# =============================================================== 1. static: bundle

def load_bundle(root: Path) -> dict:
    """Return {'root': databricks.yml dict, 'files': {path: dict}, 'resources': merged}."""
    main = yaml.safe_load((root / "databricks.yml").read_text())
    files = {root / "databricks.yml": main}
    for pattern in main.get("include", []):
        for path in sorted(root.glob(pattern)):
            files[path] = yaml.safe_load(path.read_text())
    merged: dict = {}
    origin: dict = {}
    for path, doc in files.items():
        for rtype, items in (doc or {}).get("resources", {}).items():
            for key, value in items.items():
                merged.setdefault(rtype, {})[key] = value
                origin[(rtype, key)] = path
    return {"root": main, "files": files, "resources": merged, "origin": origin}


REF_RE = re.compile(r"\$\{(resources|var)\.([A-Za-z0-9_]+)(?:\.([A-Za-z0-9_]+))?")
CONF_RE = re.compile(r'spark\.conf\.get\("([a-z_.]+)"\)')


def _walk(node, path=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, path + (i,))
    else:
        yield path, node


def validate_bundle(bundle: dict) -> list[str]:
    errors: list[str] = []
    res = bundle["resources"]
    variables = bundle["root"].get("variables", {})

    for path, doc in bundle["files"].items():
        for where, value in _walk(doc):
            if not isinstance(value, str):
                continue
            for kind, a, b in REF_RE.findall(value):
                if kind == "var" and a not in variables:
                    errors.append(f"{path.name}: undefined variable ${{var.{a}}} at {where}")
                if kind == "resources" and (a not in res or b not in res[a]):
                    errors.append(f"{path.name}: dangling reference resources.{a}.{b} at {where}")

    for (rtype, key), path in bundle["origin"].items():
        if key not in res.get(rtype, {}):
            continue  # removed resource; references to it are reported above
        spec = res[rtype][key]
        base = path.parent
        if rtype == "pipelines":
            for lib in spec.get("libraries", []):
                include = lib.get("glob", {}).get("include", "")
                folder = (base / include.removesuffix("/**")).resolve()
                if not folder.exists():
                    errors.append(f"pipeline {key}: library path missing {include}")
                    continue
                used = set()
                for py in folder.rglob("*.py"):
                    used |= set(CONF_RE.findall(py.read_text()))
                missing = used - set(spec.get("configuration", {}))
                if missing:
                    errors.append(f"pipeline {key}: configuration missing {sorted(missing)}")
            if "root_path" in spec and not (base / spec["root_path"]).resolve().exists():
                errors.append(f"pipeline {key}: root_path missing {spec['root_path']}")
            if "libraries" in spec and not spec.get("serverless"):
                errors.append(f"pipeline {key}: transformation pipelines must be serverless")
        if rtype == "jobs":
            env_keys = {e["environment_key"]: e for e in spec.get("environments", [])}
            for env in env_keys.values():
                if str(env.get("spec", {}).get("environment_version")) != "6":
                    errors.append(f"job {key}: environment_version must be '6' (latest)")
            task_keys = {t["task_key"] for t in spec.get("tasks", [])}
            for task in spec.get("tasks", []):
                for dep in task.get("depends_on", []):
                    if dep["task_key"] not in task_keys:
                        errors.append(f"job {key}: task {task['task_key']} depends on unknown {dep['task_key']}")
                if "spark_python_task" in task:
                    pyfile = (base / task["spark_python_task"]["python_file"]).resolve()
                    if not pyfile.exists():
                        errors.append(f"job {key}: python_file missing {task['spark_python_task']['python_file']}")
                    if task.get("environment_key") not in env_keys:
                        errors.append(f"job {key}: task {task['task_key']} has no serverless environment")

    pipelines = res.get("pipelines", {})
    gateway = pipelines.get("wwi_gateway", {})
    if not gateway.get("continuous"):
        errors.append("wwi_gateway must be continuous (Lakeflow Connect requirement)")
    ingestion = pipelines.get("wwi_ingestion", {})
    if not ingestion.get("serverless") or ingestion.get("continuous"):
        errors.append("wwi_ingestion must be serverless and triggered")
    objects = ingestion.get("ingestion_definition", {}).get("objects", [])
    destinations = {o["table"]["destination_table"] for o in objects if "table" in o}
    if destinations != set(wwi.BRONZE.values()):
        errors.append(f"ingestion destinations {sorted(destinations ^ set(wwi.BRONZE.values()))} differ from wwi.BRONZE")

    build = res.get("jobs", {}).get("slc_platform_build", {})
    deps = {t["task_key"]: {d["task_key"] for d in t.get("depends_on", [])} for t in build.get("tasks", [])}
    for child, parent in [
        ("wwi_gold_dimensions", "wwi_ingest"),
        ("wwi_gold_facts", "wwi_gold_dimensions"),
        ("nyctaxi_dimensions", "load_tlc"),
        ("nyctaxi_trips", "nyctaxi_dimensions"),
    ]:
        if parent not in deps.get(child, set()):
            errors.append(f"build job: {child} must depend on {parent}")
    if not {"wwi_gold_facts", "nyctaxi_trips"} <= deps.get("profiling", set()):
        errors.append("build job: profiling must run after both fact pipelines")

    freshness = bundle["root"].get("targets", {}).get("freshness", {})
    if not freshness.get("resources", {}).get("pipelines", {}).get("nyctaxi_trips", {}).get("continuous"):
        errors.append("target freshness must run nyctaxi_trips continuously (SPEC § 9.4)")
    return errors


class BundleStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_bundle(PLATFORM)

    def test_bundle_valid(self):
        self.assertEqual(validate_bundle(self.bundle), [])

    def test_expected_resources_present(self):
        res = self.bundle["resources"]
        self.assertEqual(set(res["schemas"]), {"raw_wwi", "wwi", "raw_nyctaxi", "nyctaxi", "ops"})
        self.assertEqual(
            set(res["pipelines"]),
            {"wwi_gateway", "wwi_ingestion", "wwi_gold_dimensions", "wwi_gold_facts",
             "nyctaxi_dimensions", "nyctaxi_trips"},
        )
        self.assertEqual(self.bundle["root"]["bundle"]["engine"], "direct")

    def test_negative_dangling_pipeline_reference(self):
        bundle = copy.deepcopy(self.bundle)
        del bundle["resources"]["pipelines"]["wwi_gold_dimensions"]
        errors = validate_bundle(bundle)
        self.assertTrue(any("dangling reference resources.pipelines.wwi_gold_dimensions" in e for e in errors))

    def test_negative_missing_pipeline_configuration(self):
        bundle = copy.deepcopy(self.bundle)
        del bundle["resources"]["pipelines"]["nyctaxi_trips"]["configuration"]["slc.landing_path"]
        self.assertTrue(any("configuration missing ['slc.landing_path']" in e for e in validate_bundle(bundle)))

    def test_negative_stale_environment_version(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["resources"]["jobs"]["slc_platform_build"]["environments"][0]["spec"]["environment_version"] = "2"
        self.assertTrue(any("environment_version must be '6'" in e for e in validate_bundle(bundle)))

    def test_negative_facts_not_after_dimensions(self):
        bundle = copy.deepcopy(self.bundle)
        for task in bundle["resources"]["jobs"]["slc_platform_build"]["tasks"]:
            if task["task_key"] == "wwi_gold_facts":
                task["depends_on"] = [{"task_key": "wwi_ingest"}]
        self.assertIn("build job: wwi_gold_facts must depend on wwi_gold_dimensions", validate_bundle(bundle))

    def test_negative_ingestion_destination_drift(self):
        bundle = copy.deepcopy(self.bundle)
        objs = bundle["resources"]["pipelines"]["wwi_ingestion"]["ingestion_definition"]["objects"]
        objs[0]["table"]["destination_table"] = "fact_sale_raw"
        self.assertTrue(any("differ from wwi.BRONZE" in e for e in validate_bundle(bundle)))


# =============================================================== 1. static: schema vs SPEC

COL_RE = re.compile(
    r"`([a-z_0-9]+)` ((?:BIGINT|INT|DATE|STRING|BOOLEAN|TIMESTAMP_NTZ|TIMESTAMP|TINYINT|SMALLINT|DECIMAL\(\d+,\d+\)))( NULL)?"
)


def spec_section(text: str, start: str, end: str) -> str:
    i = text.index(start)
    j = text.index(end, i + len(start))
    return text[i:j]


def spec_tables(block: str) -> dict[str, list[tuple[str, str, bool]]]:
    out = {}
    for line in block.splitlines():
        m = re.match(r"^\| `([a-z_]+)` \| (.*) \|$", line)
        if m:
            out[m.group(1)] = [(n, t, bool(nl)) for n, t, nl in COL_RE.findall(m.group(2))]
    return out


class SchemaMatchesSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = SPEC.read_text()
        cls.wwi = spec_tables(spec_section(text, "### 5.1", "### 5.2"))
        cls.nyc = spec_tables(spec_section(text, "### 5.2", "### 5.3"))
        date_block = spec_section(text, "### 5.4", "---")
        cls.dates = [(n, t, bool(nl)) for n, t, nl in COL_RE.findall(date_block.split("Columns:")[1].split("\n")[0])]

    def _compare(self, spec_cols, table):
        self.assertEqual([c[0] for c in spec_cols], table.column_names, table.name)
        for (name, stype, s_null), (_, ttype, t_null) in zip(spec_cols, table.columns):
            self.assertEqual(stype, ttype, f"{table.name}.{name} type")
            self.assertEqual(s_null, t_null, f"{table.name}.{name} nullability (SPEC marks NULL)")

    def test_wwi_tables_match_spec(self):
        self.assertEqual(set(self.wwi), set(WWI_TABLES))
        for name, cols in self.wwi.items():
            if name != "dim_date":
                self._compare(cols, WWI_TABLES[name])

    def test_nyc_tables_match_spec(self):
        self.assertEqual(set(self.nyc), set(NYC_TABLES))
        for name, cols in self.nyc.items():
            if name not in ("dim_date", "fact_trip_quarantine"):
                self._compare(cols, NYC_TABLES[name])
        quarantine = NYC_TABLES["fact_trip_quarantine"]
        self.assertEqual(quarantine.column_names, NYC_TABLES["fact_trip"].column_names + ["reject_reason"])

    def test_dim_date_matches_spec(self):
        self.assertEqual([(n, t) for n, t, _ in self.dates], [(n, t) for n, t, _ in DATE_COLUMNS])

    def test_negative_type_drift_detected(self):
        drifted = [("sale_key", "INT", False)] + self.wwi["fact_sale"][1:]
        with self.assertRaises(AssertionError):
            self._compare(drifted, WWI_TABLES["fact_sale"])


# =============================================================== 1. static: SQL Server prep

class SourcePrepScriptTests(unittest.TestCase):
    PREP = SRC / "sql" / "source" / "02_wwi_source_prep.sql"

    def test_every_ingested_table_gets_change_tracking(self):
        text = self.PREP.read_text()
        bundle = load_bundle(PLATFORM)
        objects = bundle["resources"]["pipelines"]["wwi_ingestion"]["ingestion_definition"]["objects"]
        for obj in objects:
            t = obj["table"]
            pair = f"(N'{t['source_schema']}', N'{t['source_table']}')"
            oltp = f"[{t['source_schema']}].[{t['source_table']}] ENABLE CHANGE_TRACKING"
            self.assertTrue(pair in text or oltp in text, f"no change tracking for {t['source_schema']}.{t['source_table']}")

    def test_clustered_columnstore_dropped_for_ingested_facts(self):
        text = self.PREP.read_text()
        for idx in ("CCX_Fact_Sale", "CCX_Fact_Order", "CCX_Fact_Movement", "CCX_Fact_Stock_Holding"):
            self.assertIn(idx, text)

    def test_no_credentials_committed(self):
        for path in (SRC / "sql").rglob("*.sql"):
            self.assertNotRegex(path.read_text(), r"PASSWORD\s*=\s*N'[^$]", path.name)

    @unittest.skipUnless(os.environ.get("SLC_SQLSERVER_CONTAINER"), "SLC_SQLSERVER_CONTAINER not set")
    def test_prep_script_idempotent_against_restored_copy(self):
        container = os.environ["SLC_SQLSERVER_CONTAINER"]
        sa_password = os.environ["SLC_SQLSERVER_PASSWORD"]
        sqlcmd = ["docker", "exec", container, "/opt/mssql-tools18/bin/sqlcmd", "-S", "localhost",
                  "-U", "sa", "-P", sa_password, "-C", "-b"]
        subprocess.run(["docker", "cp", str(self.PREP), f"{container}:/tmp/slc_prep.sql"], check=True)
        ingest_password = "Aa1!" + secrets.token_urlsafe(18)  # satisfies SQL Server complexity policy
        for _ in range(2):
            subprocess.run(sqlcmd + ["-i", "/tmp/slc_prep.sql", "-v", "INGEST_LOGIN=slc_ingest_test",
                                     f"INGEST_PASSWORD={ingest_password}"], check=True, capture_output=True)
        out = subprocess.run(
            sqlcmd + ["-h", "-1", "-W", "-Q",
                      "SET NOCOUNT ON; SELECT COUNT(*) FROM WideWorldImportersDW.sys.change_tracking_tables; "
                      "SELECT COUNT(*) FROM WideWorldImporters.sys.change_tracking_tables;"],
            check=True, capture_output=True, text=True,
        ).stdout.split()
        self.assertEqual(out[:2], ["9", "2"])


# =============================================================== 2. transforms: calendar

class CalendarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = calendar.dim_date(SPARK, "2012-11-01", "2025-12-31").collect()
        cls.by_date = {r["date_key"]: r for r in rows}

    def test_schema_matches_canonical(self):
        df = calendar.dim_date(SPARK, "2024-01-01", "2024-01-02")
        self.assertEqual(schema_of(df), [(n, spark_type(t)) for n, t, _ in DATE_COLUMNS])

    def test_fiscal_year_starts_1_november_labeled_by_end_year(self):
        # Values asserted against WideWorldImportersDW [Dimension].[Date].
        cases = {
            date(2013, 10, 31): (2013, 12, 4),
            date(2013, 11, 1): (2014, 1, 1),
            date(2013, 12, 1): (2014, 2, 1),
            date(2014, 1, 1): (2014, 3, 1),
        }
        for d, (fy, fm, fq) in cases.items():
            r = self.by_date[d]
            self.assertEqual((r["fiscal_year"], r["fiscal_month"], r["fiscal_quarter"]), (fy, fm, fq), d)

    def test_fiscal_period_index_consecutive_across_year_boundary(self):
        oct31 = self.by_date[date(2013, 10, 31)]["fiscal_period_index"]
        nov1 = self.by_date[date(2013, 11, 1)]["fiscal_period_index"]
        self.assertEqual(nov1 - oct31, 1)

    def test_day_of_fiscal_year(self):
        self.assertEqual(self.by_date[date(2013, 11, 1)]["day_of_fiscal_year"], 1)
        self.assertEqual(self.by_date[date(2014, 10, 31)]["day_of_fiscal_year"], 365)
        self.assertEqual(self.by_date[date(2016, 10, 31)]["day_of_fiscal_year"], 366)  # FY2016 holds 29 Feb

    def test_iso_day_of_week_and_week(self):
        self.assertEqual(self.by_date[date(2024, 1, 1)]["day_of_week"], 1)   # Monday
        self.assertEqual(self.by_date[date(2024, 1, 7)]["day_of_week"], 7)   # Sunday
        self.assertEqual(self.by_date[date(2024, 12, 30)]["iso_week_number"], 1)

    def test_leap_year_day_counts(self):
        self.assertEqual(self.by_date[date(2024, 3, 15)]["day_of_year"], 75)
        self.assertEqual(self.by_date[date(2023, 3, 15)]["day_of_year"], 74)

    def test_gap_free(self):
        days = sorted(self.by_date)
        self.assertEqual(len(days), (days[-1] - days[0]).days + 1)


# =============================================================== 2. transforms: WWI

OPEN = datetime(9999, 12, 31, 23, 59, 59, 999999)


def stock_item_bronze(rows):
    schema = (
        "`Stock Item Key` INT, `WWI Stock Item ID` INT, `Stock Item` STRING, `Color` STRING, "
        "`Selling Package` STRING, `Brand` STRING, `Size` STRING, `Is Chiller Stock` BOOLEAN, "
        "`Unit Price` DECIMAL(18,2), `Valid From` TIMESTAMP, `Valid To` TIMESTAMP"
    )
    return SPARK.createDataFrame(rows, schema)


class WwiConformTests(unittest.TestCase):
    def test_dim_stock_item_schema_and_current_flag(self):
        bronze = stock_item_bronze([
            (10, 1, "Mug", "Gray", "Each", None, None, False, Decimal("13.00"),
             datetime(2013, 1, 1), datetime(2015, 6, 1)),
            (11, 1, "Mug", "Steel Gray", "Each", None, None, False, Decimal("13.00"),
             datetime(2015, 6, 1), OPEN),
        ])
        out = wwi.conform("dim_stock_item", bronze)
        expected = [(n, spark_type(t)) for n, t, _ in WWI_TABLES["dim_stock_item"].columns]
        self.assertEqual(schema_of(out), expected)
        current = {r["stock_item_key"]: r["is_current"] for r in out.collect()}
        self.assertEqual(current, {10: False, 11: True})

    def test_duplicate_open_ended_rows_yield_one_current_row(self):
        # [Dimension].[City] shape: two open-ended rows, same valid_from, same attributes.
        bronze = stock_item_bronze([
            (1420, 7, "Mug", "Gray", "Each", None, None, False, Decimal("1.00"), datetime(2013, 1, 1), datetime(2015, 7, 1, 16)),
            (110372, 7, "Mug", "Gray", "Each", None, None, False, Decimal("1.00"), datetime(2015, 7, 1, 16), OPEN),
            (113749, 7, "Mug", "Gray", "Each", None, None, False, Decimal("1.00"), datetime(2015, 7, 1, 16), OPEN),
        ])
        current = {r["stock_item_key"]: r["is_current"] for r in wwi.conform("dim_stock_item", bronze).collect()}
        self.assertEqual(current, {1420: False, 110372: False, 113749: True})

    def test_every_mapped_table_conforms_to_schema(self):
        for table, mapping in wwi.MAPPINGS.items():
            types = {n: t for n, t, _ in WWI_TABLES[table].columns}
            ddl = ", ".join(f"`{src}` {types[gold]}" for gold, src in mapping)
            out = wwi.conform(table, SPARK.createDataFrame([], ddl))
            self.assertEqual(out.columns, WWI_TABLES[table].column_names, table)

    def test_negative_missing_source_column_fails(self):
        bronze = stock_item_bronze([]).drop("Color")
        with self.assertRaises(Exception):
            wwi.conform("dim_stock_item", bronze).schema  # analysis fails on the missing column


class SnapshotDerivationTests(unittest.TestCase):
    """SPEC § 5.3 rule 6 on a 5-day window, 2020-01-01..2020-01-05."""

    @classmethod
    def setUpClass(cls):
        items = SPARK.createDataFrame(
            [
                (10, 1, datetime(2019, 1, 1), datetime(2020, 1, 3)),
                (11, 1, datetime(2020, 1, 3), OPEN),
                (20, 2, datetime(2019, 1, 1), OPEN),
                (30, 3, datetime(2020, 1, 3), OPEN),
                (40, 4, datetime(2019, 1, 1), OPEN),
                (50, 5, datetime(2019, 1, 1), OPEN),
            ],
            "stock_item_key INT, wwi_stock_item_id INT, valid_from TIMESTAMP, valid_to TIMESTAMP",
        )
        movement = SPARK.createDataFrame(
            [
                (1, date(2020, 1, 2), 10, 1, 5),
                (2, date(2020, 1, 4), 11, 1, -3),
                (3, date(2020, 1, 2), 20, 1, 100),
                (4, date(2020, 1, 2), 30, 1, -5),
                (5, date(2020, 1, 4), 30, 1, 3),
                (6, date(2019, 12, 15), 40, 1, 4),
                (7, date(2020, 1, 2), 50, 1, 9),
            ],
            "movement_key BIGINT, movement_date DATE, stock_item_key INT, transaction_type_key INT, quantity INT",
        )
        holding = SPARK.createDataFrame([(11, 10), (20, 1), (30, 0), (40, 4)], "stock_item_key INT, quantity_on_hand INT")
        dates = calendar.dim_date(SPARK, "2019-12-01", "2020-01-31")
        out = wwi.fact_stock_holding_daily(movement, holding, items, dates, "2020-01-01", "2020-01-05")
        cls.schema = schema_of(out)
        cls.rows = {(r["wwi_stock_item_id"], r["snapshot_date"].day): r for r in out.collect()}

    def series(self, item):
        return [self.rows[(item, d)]["quantity_on_hand"] for d in range(1, 6)]

    def test_schema_matches_canonical(self):
        self.assertEqual(self.schema, [(n, spark_type(t)) for n, t, _ in WWI_TABLES["fact_stock_holding_daily"].columns])

    def test_dense_grid_only_items_with_holding(self):
        self.assertEqual(len(self.rows), 4 * 5)
        self.assertNotIn((5, 1), self.rows)

    def test_reconcilable_item_back_casts_to_current_holding(self):
        self.assertEqual(self.series(1), [8, 13, 13, 10, 10])
        self.assertEqual({self.rows[(1, d)]["balance_basis"] for d in range(1, 6)}, {wwi.BASIS_BACKCAST})

    def test_irreconcilable_receipts_fall_back_to_flow(self):
        self.assertEqual(self.series(2), [0, 100, 100, 100, 100])
        self.assertEqual(self.rows[(2, 1)]["balance_basis"], wwi.BASIS_FLOW)

    def test_flow_opening_is_minimum_keeping_balance_non_negative(self):
        self.assertEqual(self.series(3), [5, 0, 0, 3, 3])
        self.assertEqual(min(self.series(3)), 0)

    def test_movements_before_window_counted(self):
        self.assertEqual(self.series(4), [4, 4, 4, 4, 4])
        self.assertEqual(self.rows[(4, 1)]["balance_basis"], wwi.BASIS_BACKCAST)

    def test_version_key_by_validity_and_earliest_fallback(self):
        self.assertEqual([self.rows[(1, d)]["stock_item_key"] for d in range(1, 6)], [10, 10, 11, 11, 11])
        self.assertEqual([self.rows[(3, d)]["stock_item_key"] for d in range(1, 6)], [30] * 5)

    def test_never_negative(self):
        self.assertTrue(all(r["quantity_on_hand"] >= 0 for r in self.rows.values()))


# =============================================================== 2. transforms: NYC

LANDING_FIELDS = [n for n, _ in nyctaxi.LANDING_COLUMNS]
BASE_TRIP = {
    "VendorID": 2, "tpep_pickup_datetime": datetime(2024, 3, 15, 8, 10, 0),
    "tpep_dropoff_datetime": datetime(2024, 3, 15, 8, 30, 0), "passenger_count": 1.0,
    "trip_distance": 3.4567, "RatecodeID": 1.0, "store_and_fwd_flag": "N", "PULocationID": 132,
    "DOLocationID": 236, "payment_type": 1, "fare_amount": 20.0, "extra": 0.0, "mta_tax": 0.5,
    "tip_amount": 4.0, "tolls_amount": 0.0, "improvement_surcharge": 1.0, "total_amount": 25.5,
    "congestion_surcharge": 2.5, "airport_fee": 0.0, "source_file": "f1.parquet",
}


def trip(**overrides):
    row = dict(BASE_TRIP, **overrides)
    return tuple(row[f] for f in LANDING_FIELDS)


def landing(rows):
    return SPARK.createDataFrame(rows, nyctaxi.LANDING_DDL)


def epoch(ts: datetime) -> int:
    return int(ts.replace(tzinfo=timezone.utc).timestamp())


class NycNormalizeTests(unittest.TestCase):
    def test_drifted_schemas_normalize_identically_and_losslessly(self):
        jan = SPARK.createDataFrame(
            [(1, datetime(2023, 1, 1, 0, 5), datetime(2023, 1, 1, 0, 15), 2.0, 1.2, 1.0, 132, 236, 1, 9.3, 1.25)],
            "VendorID BIGINT, tpep_pickup_datetime TIMESTAMP_NTZ, tpep_dropoff_datetime TIMESTAMP_NTZ, "
            "passenger_count DOUBLE, trip_distance DOUBLE, RatecodeID DOUBLE, PULocationID BIGINT, "
            "DOLocationID BIGINT, payment_type BIGINT, fare_amount DOUBLE, airport_fee DOUBLE",
        )
        feb = SPARK.createDataFrame(
            [(2, datetime(2023, 2, 1, 0, 5), datetime(2023, 2, 1, 0, 25), 3, 2.5, 1, 140, 236, 2, 14.2, 0.0)],
            "VendorID INT, tpep_pickup_datetime TIMESTAMP_NTZ, tpep_dropoff_datetime TIMESTAMP_NTZ, "
            "passenger_count BIGINT, trip_distance DOUBLE, RatecodeID BIGINT, PULocationID INT, "
            "DOLocationID INT, payment_type BIGINT, fare_amount DOUBLE, Airport_fee DOUBLE",
        )
        a = nyctaxi.normalize_source(jan, "yellow_tripdata_2023-01.parquet")
        b = nyctaxi.normalize_source(feb, "yellow_tripdata_2023-02.parquet")
        expected = [(n, spark_type(t)) for n, t in nyctaxi.LANDING_COLUMNS]
        self.assertEqual(schema_of(a), expected)
        self.assertEqual(schema_of(b), expected)
        rows = {r["source_file"]: r for r in a.unionByName(b).collect()}
        self.assertEqual(rows["yellow_tripdata_2023-02.parquet"]["passenger_count"], 3.0)
        self.assertEqual(rows["yellow_tripdata_2023-01.parquet"]["airport_fee"], 1.25)
        self.assertEqual(rows["yellow_tripdata_2023-02.parquet"]["airport_fee"], 0.0)
        self.assertIsNone(rows["yellow_tripdata_2023-01.parquet"]["congestion_surcharge"])

    @unittest.skipUnless(os.environ.get("SLC_TLC_DIR"), "SLC_TLC_DIR not set")
    def test_real_drifted_months_normalize_losslessly(self):
        d = Path(os.environ["SLC_TLC_DIR"])
        totals = {}
        frames = []
        for m in ("2023-01", "2023-02"):
            raw = SPARK.read.parquet(str(d / f"yellow_tripdata_{m}.parquet"))
            totals[m] = raw.agg(F.count("*"), F.count("passenger_count"), F.sum("passenger_count")).first()
            frames.append(nyctaxi.normalize_source(raw, m))
        union = frames[0].unionByName(frames[1])
        got = union.groupBy("source_file").agg(F.count("*"), F.count("passenger_count"), F.sum("passenger_count"))
        for r in got.collect():
            self.assertEqual(tuple(r)[1:], tuple(totals[r["source_file"]]), r["source_file"])


class NycConformTests(unittest.TestCase):
    def conform_one(self, **overrides):
        return nyctaxi.conform(landing([trip(**overrides)])).first()

    def test_valid_trip_columns(self):
        r = self.conform_one()
        self.assertIsNone(r["reject_reason"])
        self.assertEqual(r["trip_id"], epoch(BASE_TRIP["tpep_pickup_datetime"]) * 100)
        self.assertEqual(r["trip_distance"], Decimal("3.46"))
        self.assertEqual(r["od_pair_id"], 132236)
        self.assertEqual((r["pickup_date"], r["pickup_hour"]), (date(2024, 3, 15), 8))

    def test_schema_matches_canonical(self):
        out = nyctaxi.fact_trip(nyctaxi.conform(landing([trip()])))
        self.assertEqual(schema_of(out), [(n, spark_type(t)) for n, t, _ in NYC_TABLES["fact_trip"].columns])

    def test_each_rule_rejects_with_its_reason(self):
        cases = [
            ({"tpep_dropoff_datetime": BASE_TRIP["tpep_pickup_datetime"]}, "pickup_not_before_dropoff"),
            ({"trip_distance": 0.0}, "trip_distance_out_of_range"),
            ({"trip_distance": 200.01}, "trip_distance_out_of_range"),
            ({"fare_amount": -1.0}, "negative_fare_amount"),
            ({"total_amount": -1.0}, "negative_total_amount"),
            ({"tpep_pickup_datetime": datetime(2025, 1, 1, 0, 0, 0),
              "tpep_dropoff_datetime": datetime(2025, 1, 1, 0, 9, 0)}, "pickup_outside_window"),
            ({"tpep_pickup_datetime": datetime(2022, 12, 31, 23, 59, 59),
              "tpep_dropoff_datetime": datetime(2023, 1, 1, 0, 9, 0)}, "pickup_outside_window"),
        ]
        for overrides, reason in cases:
            self.assertEqual(self.conform_one(**overrides)["reject_reason"], reason, overrides)

    def test_boundaries_accepted(self):
        self.assertIsNone(self.conform_one(trip_distance=200.0)["reject_reason"])
        late = self.conform_one(tpep_pickup_datetime=datetime(2024, 12, 31, 23, 59, 59),
                                tpep_dropoff_datetime=datetime(2025, 1, 1, 0, 10, 0))
        self.assertIsNone(late["reject_reason"])
        self.assertEqual(late["dropoff_date"], date(2025, 1, 1))

    def test_first_failed_rule_wins(self):
        r = self.conform_one(tpep_dropoff_datetime=BASE_TRIP["tpep_pickup_datetime"], trip_distance=0.0, fare_amount=-5.0)
        self.assertEqual(r["reject_reason"], "pickup_not_before_dropoff")

    def test_null_predicate_is_a_failure(self):
        self.assertEqual(self.conform_one(fare_amount=None)["reject_reason"], "negative_fare_amount")
        r = self.conform_one(tpep_pickup_datetime=None)
        self.assertEqual(r["reject_reason"], "pickup_not_before_dropoff")
        self.assertIsNone(r["trip_id"])

    def test_trip_id_deterministic_across_file_splits_and_order(self):
        same_second = [trip(fare_amount=20.0), trip(fare_amount=20.0), trip(fare_amount=10.0, total_amount=15.5)]
        whole = nyctaxi.conform(landing(same_second))
        split = nyctaxi.conform(
            landing([trip(fare_amount=10.0, total_amount=15.5, source_file="b.parquet")]).unionByName(
                landing([trip(fare_amount=20.0, source_file="a.parquet"), trip(fare_amount=20.0, source_file="c.parquet")])
            )
        )
        key = lambda df: sorted((r["trip_id"], str(r["fare_amount"])) for r in df.collect())  # noqa: E731
        self.assertEqual(key(whole), key(split))
        base = epoch(BASE_TRIP["tpep_pickup_datetime"]) * 100
        self.assertEqual(key(whole), [(base, "10.00"), (base + 1, "20.00"), (base + 2, "20.00")])

    def test_split_into_fact_and_quarantine(self):
        conformed = nyctaxi.conform(landing([
            trip(),
            trip(fare_amount=-1.0, tpep_pickup_datetime=datetime(2024, 3, 15, 9, 0),
                 tpep_dropoff_datetime=datetime(2024, 3, 15, 9, 10)),
        ]))
        self.assertEqual(nyctaxi.fact_trip(conformed).count(), 1)
        q = nyctaxi.fact_trip_quarantine(conformed)
        self.assertEqual(q.columns, NYC_TABLES["fact_trip_quarantine"].column_names)
        self.assertEqual(q.first()["reject_reason"], "negative_fare_amount")

    def test_payment_types_cover_profiled_codes(self):
        codes = {r["payment_type"] for r in nyctaxi.dim_payment_type(SPARK).collect()}
        self.assertTrue({0, 1, 2, 3, 4, 5} <= codes)  # codes present in 2023-2024 data
        self.assertEqual(codes, set(range(7)))


# =============================================================== 2. transforms: replay

class ReplayTests(unittest.TestCase):
    def test_batch_boundaries_and_clamping(self):
        ts = [
            datetime(2024, 11, 30, 23, 0), datetime(2024, 12, 1, 0, 0), datetime(2024, 12, 1, 0, 14, 59),
            datetime(2024, 12, 1, 0, 15), datetime(2024, 12, 31, 23, 59, 59), datetime(2025, 1, 2, 3, 0),
        ]
        df = replay.assign_batches(landing([trip(tpep_pickup_datetime=t, tpep_dropoff_datetime=t) for t in ts]))
        got = [r["batch_no"] for r in df.orderBy("tpep_pickup_datetime").collect()]
        self.assertEqual(got, [0, 0, 0, 1, replay.LAST_BATCH, replay.LAST_BATCH])
        self.assertEqual(replay.LAST_BATCH, 2975)

    def test_replay_log_counts_valid_trips_and_picks_sentinel(self):
        def at(h, m, **kw):
            t = datetime(2024, 12, 1, h, m)
            return trip(tpep_pickup_datetime=t, tpep_dropoff_datetime=datetime(2024, 12, 1, h, m + 2), **kw)
        rows = [at(0, 5), at(0, 10), at(0, 20), at(0, 25, fare_amount=-1.0)]
        conformed = replay.assign_batches(nyctaxi.conform(landing(rows)), ts_col="pickup_ts")
        log = {r["batch_no"]: r for r in replay.replay_log(conformed).collect()}
        self.assertEqual(log[0]["expected_trip_count_for_date"], 2)
        self.assertEqual(log[1]["expected_trip_count_for_date"], 3)
        self.assertEqual(log[1]["rows_landed"], 2)
        self.assertEqual(log[0]["sentinel_trip_id"], epoch(datetime(2024, 12, 1, 0, 10)) * 100)


# =============================================================== 3. profiling checks

BRONZE_STUBS = {
    "raw_wwi.dw_dimension_date": "`Date` DATE, `Fiscal Year` INT, `Fiscal Month Number` INT, "
                                 "`Calendar Year` INT, `Calendar Month Number` INT",
    **{f"raw_wwi.{t}": "id INT" for t in wwi.BRONZE.values() if t != "dw_dimension_date"},
    "raw_nyctaxi.trips_bronze": nyctaxi.LANDING_DDL,
}


def create_empty_catalog():
    for db in ("raw_wwi", "wwi", "raw_nyctaxi", "nyctaxi"):
        SPARK.sql(f"CREATE DATABASE IF NOT EXISTS {db}")
    for schema, tables in (("wwi", WWI_TABLES), ("nyctaxi", NYC_TABLES)):
        for t in tables.values():
            cols = ", ".join(f"{n} {ty}" for n, ty, _ in t.columns)
            SPARK.sql(f"DROP TABLE IF EXISTS {schema}.{t.name}")
            SPARK.sql(f"CREATE TABLE {schema}.{t.name} ({cols}) USING parquet")
    for name, ddl in BRONZE_STUBS.items():
        SPARK.sql(f"DROP TABLE IF EXISTS {name}")
        SPARK.sql(f"CREATE TABLE {name} ({ddl}) USING parquet")


def put(table: str, rows, schema_ddl: str | None = None):
    db, name = table.split(".")
    if schema_ddl is None:
        spec = (WWI_TABLES if db == "wwi" else NYC_TABLES)[name]
        schema_ddl = ", ".join(f"{n} {t}" for n, t, _ in spec.columns)
    SPARK.createDataFrame(rows, schema_ddl).write.mode("overwrite").insertInto(table)


class ProfilingChecksTests(unittest.TestCase):
    CHECK_DIR = SRC / "sql" / "profiling"

    def setUp(self):
        create_empty_catalog()
        self.checks = {c.check_id: c for c in profiling.all_checks(self.CHECK_DIR)}

    def violated(self, check_id: str) -> bool:
        return bool(SPARK.sql(self.checks[check_id].sql).collect())

    def test_every_check_executes(self):
        for check in self.checks.values():
            SPARK.sql(check.sql).collect()  # raises on any syntax or resolution error

    def test_generated_checks_cover_every_constraint(self):
        expected = 0
        for tables in (WWI_TABLES, NYC_TABLES):
            for t in tables.values():
                expected += bool(t.primary_key) + len(t.foreign_keys) + any(not nl for _, _, nl in t.columns)
        self.assertEqual(len(profiling.key_checks()), expected)

    def test_check_files_have_ids(self):
        ids = [c.check_id for c in profiling.file_checks(self.CHECK_DIR)]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(re.match(r"^P-(WWI|NYC)-\d{2}$", i) for i in ids), ids)

    def test_pk_duplicate_detected(self):
        put("wwi.dim_stock_group", [(1, "Mugs"), (1, "Toys")])
        self.assertTrue(self.violated("PK-wwi.dim_stock_group"))

    def test_fk_orphan_detected_and_clean_passes(self):
        put("wwi.dim_stock_group", [(1, "Mugs")])
        put("wwi.bridge_stock_item_group", [(100, 1)])
        self.assertFalse(self.violated("FK-wwi.bridge_stock_item_group.stock_group_id"))
        put("wwi.bridge_stock_item_group", [(100, 1), (101, 2)])
        self.assertTrue(self.violated("FK-wwi.bridge_stock_item_group.stock_group_id"))

    def test_not_null_violation_detected(self):
        put("wwi.dim_stock_group", [(1, None)], "stock_group_id INT, stock_group_name STRING")
        self.assertTrue(self.violated("NN-wwi.dim_stock_group"))

    def test_bridge_overlap_check(self):
        put("wwi.bridge_stock_item_group", [(100, 1), (101, 2)])
        self.assertTrue(self.violated("P-WWI-02"))
        put("wwi.bridge_stock_item_group", [(100, 1), (100, 2)])
        self.assertFalse(self.violated("P-WWI-02"))

    def test_negative_snapshot_balance_detected(self):
        put("wwi.fact_stock_holding_daily", [(date(2014, 1, 1), 1, 10, -1, "holding_backcast")])
        self.assertTrue(self.violated("P-WWI-04"))

    def test_fact_trip_predicate_violation_detected(self):
        bad = (1, 2, datetime(2024, 1, 1, 8), datetime(2024, 1, 1, 8), date(2024, 1, 1), date(2024, 1, 1), 8,
               1, 2, 1002, 1, Decimal("1.00"), 1, Decimal("5.00"), Decimal("0"), Decimal("0"), Decimal("5.00"))
        put("nyctaxi.fact_trip", [bad])
        self.assertTrue(self.violated("P-NYC-02"))

    def test_wrong_quarantine_reason_detected(self):
        row = (1, 2, datetime(2024, 1, 1, 8), datetime(2024, 1, 1, 8, 5), date(2024, 1, 1), date(2024, 1, 1), 8,
               1, 2, 1002, 1, Decimal("0.00"), 1, Decimal("5.00"), Decimal("0"), Decimal("0"), Decimal("5.00"))
        put("nyctaxi.fact_trip_quarantine", [row + ("trip_distance_out_of_range",)])
        self.assertFalse(self.violated("P-NYC-03"))
        put("nyctaxi.fact_trip_quarantine", [row + ("negative_fare_amount",)])
        self.assertTrue(self.violated("P-NYC-03"))

    def test_trip_id_slot_overflow_detected(self):
        t = datetime(2024, 1, 1, 8, 0, 0)
        rows = [trip(tpep_pickup_datetime=t, fare_amount=float(i)) for i in range(101)]
        landing(rows).write.mode("overwrite").insertInto("raw_nyctaxi.trips_bronze")
        self.assertTrue(self.violated("P-NYC-04"))


# =============================================================== 4. real data

EXPECTED_B0 = {
    "wwi.fact_sale": 228_265,
    "wwi.fact_order": 231_412,
    "wwi.fact_stock_movement": 236_667,
    "wwi.stock_holding_current": 227,
    "wwi.fact_stock_holding_daily": 227 * 1247,
    "wwi.bridge_stock_item_group": 442,
    "wwi.dim_stock_item": 672,
    "wwi.dim_date": 1461,
    "nyctaxi.fact_trip": 76_902_149,
    "nyctaxi.fact_trip_quarantine": 2_577_797,
    "nyctaxi.dim_zone": 265,
    "nyctaxi.dim_date": 1096,
}


@unittest.skipUnless(os.environ.get("SLC_LOCAL_B0"), "SLC_LOCAL_B0 not set")
class RealDataB0Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads((Path(os.environ["SLC_LOCAL_B0"]) / "local_b0_result.json").read_text())

    def test_all_profiling_checks_pass(self):
        self.assertEqual(self.result["failed"], [])
        self.assertEqual(self.result["checks"], len(profiling.all_checks(SRC / "sql" / "profiling")))

    def test_row_counts_match_source_profile(self):
        for table, n in EXPECTED_B0.items():
            self.assertEqual(self.result["summary"][table], n, table)

    def test_snapshot_bases(self):
        self.assertEqual(self.result["summary"]["wwi.balance_basis_items"],
                         {wwi.BASIS_BACKCAST: 218, wwi.BASIS_FLOW: 9})

    def test_quarantine_reasons_match_source_profile(self):
        self.assertEqual(self.result["summary"]["nyctaxi.reject_reasons"], {
            "trip_distance_out_of_range": 1_528_475,
            "negative_fare_amount": 1_016_835,
            "pickup_not_before_dropoff": 29_079,
            "negative_total_amount": 3_276,
            "pickup_outside_window": 132,
        })


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if result.wasSuccessful() else 1)
