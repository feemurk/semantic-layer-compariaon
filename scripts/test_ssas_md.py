#!/usr/bin/env python3
"""Phase 2 test suite: S1 SSAS Multidimensional (02-implementations/ssas-md).

Layers
  1. Structure: required files; guide links resolve and record documentation URLs; generated ASSL, XMLA, adapter DDL
     and reconciliation queries in sync with their builders; CI workflow shape; no secrets.
  2. Model (ASSL): every model file and the deploy command are well-formed XML; lint_mdx resolves every binding,
     relationship, natural hierarchy, cube dimension and measure group; distinct counts in dedicated measure groups
     (B-06); Stock Group many-to-many on every WWI fact; LastNonEmpty closing stock; partition coverage; glossary
     descriptions and synonyms.
  3. Relational layer on the oracle fixtures (DuckDB): every DSV named query executes and returns its declared columns;
     dimension keys are unique and every attribute relationship is a functional dependency; fact keys resolve to
     dimension members; monthly partitions are disjoint and cover every trip; captions use the oracle's text formats.
  4. Queries: 22 metric and 70 question files cover the oracle; every query passes lint_mdx (cube, hierarchy, level,
     measure and member-property resolution; @column and @branch declarations match the oracle headers and grains).
  5. Security, rollover and comparator: SPEC § 10 roles; E6 rollover plans (create, process, re-slice, retire beyond
     24 months, idempotent rerun, two consecutive rollovers); oracle comparison with SPEC § 5.3 rule 7.
  6. Negative: malformed definitions and MDX referring to undefined measures, hierarchies, levels or properties are
     rejected; wrong headers and grains are rejected; malformed rollover input is rejected.

No SSAS instance is used: MDX execution and processing are verified only on a deployment (scripts/reconcile.ps1).
Requires scripts/requirements-test.txt. Exits non-zero on failure.

    python3 scripts/test_ssas_md.py
"""

from __future__ import annotations

import copy
import csv
import re
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MD = REPO / "02-implementations" / "ssas-md"
ORACLE = REPO / "01-spec" / "oracle"
GUIDE = MD / "SSAS_MD_GUIDE.md"
WORKFLOW = REPO / ".github" / "workflows" / "s1-ssas-md.yml"
for p in (MD, MD / "jobs", MD / "tools", ORACLE):
    sys.path.insert(0, str(p))

try:
    import duckdb  # noqa: F401
    import yaml
except ImportError as exc:  # pinned deps are mandatory, never a silent skip
    sys.exit(f"missing test dependency ({exc}); pip install -r scripts/requirements-test.txt")

import build_model as bm  # noqa: E402
import build_reconciliation_queries as brq  # noqa: E402
import compare  # noqa: E402
import lint_mdx  # noqa: E402
import partition_rollover as pr  # noqa: E402
import run_oracle as ro  # noqa: E402

NS = {"a": bm.NS}
CATALOGS, CATALOG_PROBLEMS = lint_mdx.load_catalog(MD / "model", MD / "mdx")
_DUCK: ro.DuckDBEngine | None = None


def duck() -> ro.DuckDBEngine:
    global _DUCK
    if _DUCK is None:
        _DUCK = ro.DuckDBEngine(fixtures=ORACLE / "fixtures")
    return _DUCK


def run_sql(sql: str) -> tuple[list[str], list[tuple]]:
    return duck().execute(sql)


def oracle_header(kind: str, qid: str) -> list[str]:
    with (ORACLE / "expected" / kind / f"{qid}.csv").open(newline="", encoding="utf-8") as fh:
        return next(csv.reader(fh))


def oracle_grains(qid: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    with (ORACLE / "expected" / "metrics" / f"{qid}.csv").open(newline="", encoding="utf-8") as fh:
        for row in list(csv.reader(fh))[1:]:
            out.setdefault(row[0], set()).add(row[1])
    return out


def cube_root(name: str) -> ET.Element:
    return ET.parse(MD / "model" / f"{name}.cube").getroot()


def t(el: ET.Element, tag: str) -> str:
    found = el.find(f"a:{tag}", NS)
    return found.text if found is not None and found.text else ""


# ================================================================== 1. structure

class StructureTests(unittest.TestCase):
    def test_required_files(self):
        required = [
            "SSAS_MD_GUIDE.md", "build_model.py", "build_reconciliation_queries.py", "lint_mdx.py",
            "mdx/WWI.mdx", "mdx/NYC.mdx", "adapter/01_polybase.sql", "adapter/02_external_tables.sql",
            "adapter/03_statistics.sql", "deploy/slc.xmla", "deploy/process_full.xmla", "jobs/partition_rollover.py",
            "tools/compare.py", "scripts/deploy.ps1", "scripts/reconcile.ps1", "scripts/rollover.ps1",
            "model/slc.database", "model/slc.ds", "model/slc.dsv", "model/WWI.cube", "model/NYC.cube",
        ]
        self.assertEqual([r for r in required if not (MD / r).is_file()], [])
        self.assertEqual(sorted(p.stem for p in (MD / "dsv").glob("*.sql")), sorted(bm.DSV_TABLES))
        self.assertEqual(sorted(p.stem for p in (MD / "model").glob("*.dim")), sorted(d.id for d in bm.DIMENSIONS))
        self.assertTrue(WORKFLOW.is_file())

    def test_generated_files_in_sync(self):
        stale = [str(p.relative_to(MD)) for p, text in bm.outputs().items() if not p.exists() or p.read_text() != text]
        self.assertEqual(stale, [])
        stale = [m for m in brq.METRICS if (brq.OUT / f"{m}.mdx").read_text() != brq.render(m)]
        self.assertEqual(stale, [])

    def test_guide_links_sections_and_sources(self):
        text = GUIDE.read_text()
        local = [l for l in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text) if not l.startswith("http")]
        self.assertGreater(len(local), 15)
        self.assertEqual([l for l in local if not (GUIDE.parent / l).resolve().exists()], [])
        for section in ("Model structure", "Calculation semantics", "Security model", "Performance behavior",
                        "Limitations"):
            self.assertRegex(text, rf"(?m)^## \d+\. {section}")
        for url in ("supported-data-sources-ssas-multidimensional", "polybase-configure-odbc-generic",
                    "what-s-new-in-sql-server-analysis-services", "analysis-services-features-by-edition",
                    "define-semiadditive-behavior", "parallelperiod-mdx"):
            self.assertIn(url, text)
        self.assertRegex(text, r"checked 2026-\d\d-\d\d")
        for block in re.findall(r"```[a-z]*\n(.*?)```", text, re.S):
            self.assertNotRegex(block, r"\.\.\.|TODO|<placeholder>")

    def test_workflow(self):
        wf = yaml.safe_load(WORKFLOW.read_text())
        self.assertEqual(list(wf["jobs"]), ["lint", "test", "promote"])
        self.assertEqual(wf["jobs"]["test"]["needs"], "lint")
        self.assertEqual(wf["jobs"]["promote"]["needs"], "test")
        for job in ("test", "promote"):
            self.assertIn("self-hosted", wf["jobs"][job]["runs-on"])
            self.assertIn("windows", wf["jobs"][job]["runs-on"])
            runs = " ".join(s.get("run", "") for s in wf["jobs"][job]["steps"])
            self.assertIn("deploy.ps1", runs)
            self.assertIn("reconcile.ps1", runs)
            self.assertIn("-FailOnMismatch", runs)
        lint_runs = " ".join(s.get("run", "") for s in wf["jobs"]["lint"]["steps"])
        for step in ("build_model.py --check", "build_reconciliation_queries.py --check", "lint_mdx.py",
                     "scripts/test_ssas_md.py"):
            self.assertIn(step, lint_runs)

    def test_no_secrets_committed(self):
        texts = [WORKFLOW.read_text()] + [p.read_text() for p in MD.rglob("*") if p.suffix in {".sql", ".ps1", ".xmla", ".ds"}]
        for text in texts:
            self.assertNotRegex(text, r"(?i)dapi[0-9a-f]{16}|password\s*=\s*'[^$']|SECRET\s*=\s*N'[^$]")
        self.assertIn("$(DATABRICKS_TOKEN)", (MD / "adapter" / "01_polybase.sql").read_text())


# ================================================================== 2. model

class ModelTests(unittest.TestCase):
    def test_all_xml_well_formed_in_assl_namespace(self):
        for path in list((MD / "model").glob("*")) + list((MD / "deploy").glob("*.xmla")):
            root = ET.parse(path).getroot()
            self.assertTrue(root.tag.startswith(f"{{{bm.NS}}}"), path.name)

    def test_catalog_resolves(self):
        self.assertEqual(CATALOG_PROBLEMS, [])
        self.assertEqual(set(CATALOGS), {"WWI", "NYC"})

    def test_deploy_command_holds_the_whole_database(self):
        root = ET.parse(MD / "deploy" / "slc.xmla").getroot()
        self.assertEqual(root.tag, f"{{{bm.NS}}}Create")
        self.assertEqual(root.get("AllowOverwrite"), "true")
        db = root.find("a:ObjectDefinition/a:Database", NS)
        self.assertEqual(len(db.findall("a:Dimensions/a:Dimension", NS)), len(bm.DIMENSIONS))
        self.assertEqual({t(c, "ID") for c in db.findall("a:Cubes/a:Cube", NS)}, {"WWI", "NYC"})
        self.assertEqual(len(db.findall("a:Roles/a:Role", NS)), len(bm.ROLES))

    def test_data_source_is_sql_server_adapter(self):
        ds = ET.parse(MD / "model" / "slc.ds").getroot()
        cs = t(ds, "ConnectionString")
        self.assertIn("Provider=MSOLEDBSQL", cs)
        self.assertNotIn("MSDASQL", cs)
        self.assertNotIn("ODBC", cs.upper().replace("PROVIDER=MSOLEDBSQL", ""))

    def test_distinct_counts_have_dedicated_measure_groups(self):
        for cube in ("WWI", "NYC"):
            for mg in cube_root(cube).findall("a:MeasureGroups/a:MeasureGroup", NS):
                funcs = [t(m, "AggregateFunction") for m in mg.findall("a:Measures/a:Measure", NS)]
                if "DistinctCount" in funcs:
                    self.assertEqual(funcs, ["DistinctCount"], t(mg, "ID"))

    def test_stock_group_many_to_many_on_every_wwi_fact(self):
        for mg in cube_root("WWI").findall("a:MeasureGroups/a:MeasureGroup", NS):
            if t(mg, "ID") == "Stock Item Group Bridge":
                continue
            m2m = [d for d in mg.findall("a:Dimensions/a:Dimension", NS)
                   if d.get(lint_mdx.XSI_TYPE) == "ManyToManyMeasureGroupDimension"]
            self.assertEqual([(t(d, "CubeDimensionID"), t(d, "MeasureGroupID")) for d in m2m],
                             [("Stock Group", "Stock Item Group Bridge")], t(mg, "ID"))

    def test_bridge_relates_at_durable_item_granularity(self):
        mg = next(m for m in cube_root("WWI").findall("a:MeasureGroups/a:MeasureGroup", NS)
                  if t(m, "ID") == "Stock Item Group Bridge")
        attrs = {t(d, "CubeDimensionID"): t(d.find("a:Attributes/a:Attribute", NS), "AttributeID")
                 for d in mg.findall("a:Dimensions/a:Dimension", NS)}
        self.assertEqual(attrs, {"Stock Item": "WWI Stock Item ID", "Stock Group": "Stock Group"})

    def test_semi_additive_and_unrelated_dimensions(self):
        measures = {t(m, "Name"): (t(m, "AggregateFunction"), t(mg, "IgnoreUnrelatedDimensions"))
                    for mg in cube_root("WWI").findall("a:MeasureGroups/a:MeasureGroup", NS)
                    for m in mg.findall("a:Measures/a:Measure", NS)}
        self.assertEqual(measures["Closing Units"], ("LastNonEmpty", "false"))
        for cube in ("WWI", "NYC"):
            for mg in cube_root(cube).findall("a:MeasureGroups/a:MeasureGroup", NS):
                self.assertEqual(t(mg, "IgnoreUnrelatedDimensions"), "false", t(mg, "ID"))

    def test_unknown_members_for_nullable_keys(self):
        for mg in cube_root("WWI").findall("a:MeasureGroups/a:MeasureGroup", NS):
            for d in mg.findall("a:Dimensions/a:Dimension", NS):
                if t(d, "CubeDimensionID") in {"Delivery Date", "Picker"}:
                    kc = d.find("a:Attributes/a:Attribute/a:KeyColumns/a:KeyColumn", NS)
                    self.assertEqual(t(kc, "NullProcessing"), "UnknownMember")

    def test_nyc_partitions_monthly_molap_plus_rolap_hot(self):
        for mg in cube_root("NYC").findall("a:MeasureGroups/a:MeasureGroup", NS):
            parts = mg.findall("a:Partitions/a:Partition", NS)
            molap = [p for p in parts if t(p, "StorageMode") == "Molap"]
            rolap = [p for p in parts if t(p, "StorageMode") == "Rolap"]
            self.assertEqual(len(molap), 24, t(mg, "ID"))
            self.assertEqual([t(p, "ID") for p in rolap], [f"{t(mg, 'ID')} Hot"])
            self.assertIn("t.pickup_date >= '2025-01-01'", t(rolap[0].find("a:Source", NS), "QueryDefinition"))

    def test_glossary_metadata_loaded(self):
        glossary = {m["id"]: m for m in yaml.safe_load((REPO / "01-spec" / "glossary.yaml").read_text())["metrics"]}
        descriptions = {}
        for cube in ("WWI", "NYC"):
            root = cube_root(cube)
            for m in root.iter(f"{{{bm.NS}}}Measure"):
                descriptions[t(m, "Name")] = t(m, "Description")
            for c in root.iter(f"{{{bm.NS}}}CalculationProperty"):
                descriptions[t(c, "CalculationReference")[len("[Measures].["):-1]] = t(c, "Description")
        mapped = {}
        for cube in bm.CUBES.values():
            for mg in cube["measure_groups"]:
                for m in mg.measures:
                    if m.metric:
                        mapped[m.metric] = m.name
        for cube_calcs in bm.CALCULATED.values():
            for name, metric in cube_calcs.items():
                if metric:
                    mapped[metric] = name
        self.assertEqual(set(mapped), set(glossary))
        for metric, name in mapped.items():
            self.assertEqual(descriptions[name], glossary[metric]["description"], metric)
        self.assertGreaterEqual((MD / "model" / "WWI.cube").read_text().count("slc:synonyms"), 10)

    def test_calculated_members_match_builder(self):
        for cube in ("WWI", "NYC"):
            self.assertEqual(CATALOGS[cube].calculated_measures, set(bm.CALCULATED[cube]), cube)

    def test_stly_avoids_parallelperiod(self):
        script = (MD / "mdx" / "NYC.mdx").read_text()
        code = re.sub(r"//[^\n]*|/\*.*?\*/", "", script, flags=re.S)
        self.assertNotIn("ParallelPeriod", code)
        self.assertIn('Properties("STLY Date ID")', code)

    def test_adapter_covers_every_table_the_dsv_reads(self):
        ddl = (MD / "adapter" / "02_external_tables.sql").read_text()
        created = set(re.findall(r"CREATE EXTERNAL TABLE (\w+\.\w+)", ddl))
        read = set()
        for p in (MD / "dsv").glob("*.sql"):
            read |= set(re.findall(r"\b((?:wwi|nyctaxi)\.\w+)\b", p.read_text()))
        self.assertEqual(read - created, set())
        self.assertEqual(len(re.findall(r"LOCATION = 'slc\.", ddl)), len(created))


# ================================================================== 3. relational layer on fixtures

class FixtureRelationalTests(unittest.TestCase):
    def test_every_named_query_executes_with_declared_columns(self):
        for table, declared in bm.DSV_TABLES.items():
            cols, _ = run_sql(bm.dsv_sql(table))
            self.assertEqual(cols, list(declared), table)

    def test_dimension_keys_and_attribute_relationships(self):
        for d in bm.DIMENSIONS:
            cols, rows = run_sql(bm.dsv_sql(d.table))
            idx = {c: i for i, c in enumerate(cols)}
            records = [dict(zip(cols, r)) for r in rows]
            key_attr = next(a for a in d.attrs if a.usage == "Key")
            keys = [tuple(r[c] for c in key_attr.key) for r in records]
            self.assertEqual(len(keys), len(set(keys)), f"{d.id}: key attribute {key_attr.name} not unique")
            attrs = {a.name: a for a in d.attrs}
            for a in d.attrs:
                if a.name_col:
                    self.assertIn(a.name_col, idx, f"{d.id}.{a.name}")
                    self._functional(records, a.key, [a.name_col], f"{d.id}: {a.name} key -> name")
                for rel in a.related:
                    self._functional(records, a.key, attrs[rel].key, f"{d.id}: {a.name} -> {rel}")

    def _functional(self, records, lhs, rhs, label):
        seen = {}
        for r in records:
            k = tuple(r[c] for c in lhs)
            v = tuple(r[c] for c in rhs)
            self.assertEqual(seen.setdefault(k, v), v, f"{label} violated for {k}")

    def test_fact_keys_resolve_to_dimension_members(self):
        dim_tables = {d.id: d.table for d in bm.DIMENSIONS}
        for cube_id, cube in bm.CUBES.items():
            cube_dims = dict(cube["dimensions"])
            for mg in cube["measure_groups"]:
                _, fact_rows = run_sql(bm.dsv_sql(mg.table))
                fact_cols = list(bm.DSV_TABLES[mg.table])
                for d in mg.dims:
                    if d.many_to_many:
                        continue
                    dim = bm.DIM_BY_ID[cube_dims[d.cube_dim]]
                    attr = next(a for a in dim.attrs if a.name == d.attribute)
                    dcols, drows = run_sql(bm.dsv_sql(dim_tables[dim.id]))
                    members = {tuple(r[dcols.index(c)] for c in attr.key) for r in drows}
                    for r in fact_rows:
                        key = tuple(r[fact_cols.index(c)] for c in d.columns)
                        if None in key:
                            self.assertTrue(d.unknown, f"{cube_id}/{mg.id}: NULL {d.columns} without unknown member")
                            continue
                        self.assertIn(key, members, f"{cube_id}/{mg.id}: {d.cube_dim} key {key} has no member")

    def test_partitions_disjoint_and_complete(self):
        _, total = run_sql("SELECT COUNT(*) FROM nyctaxi.fact_trip")
        for mg in bm.CUBES["NYC"]["measure_groups"]:
            counted = 0
            for _name, _storage, query in bm.partitions(mg):
                _, rows = run_sql(f"SELECT COUNT(*) FROM ({query}) p")
                counted += rows[0][0]
            self.assertEqual(counted, total[0][0], mg.id)

    def test_captions_use_oracle_text_formats(self):
        cols, rows = run_sql(bm.dsv_sql("wwi_date"))
        rec = dict(zip(cols, rows[0]))
        self.assertRegex(rec["date_name"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(rec["month_name"], r"^\d{4}-\d{2}-01$")
        self.assertRegex(rec["calendar_year_name"], r"^\d{4}$")
        cols, rows = run_sql(bm.dsv_sql("nyc_date"))
        by_date = {dict(zip(cols, r))["date_name"]: dict(zip(cols, r)) for r in rows}
        self.assertEqual(by_date["2024-02-29"]["stly_date_id"], 20230228)
        self.assertEqual(by_date["2024-03-01"]["stly_date_id"], 20230301)
        self.assertIsNone(by_date["2023-06-30"]["stly_date_id"])
        self.assertEqual(by_date["2024-12-31"]["in_source_window"], 1)
        self.assertEqual(by_date["2025-01-01"]["in_source_window"], 0)
        _, rows = run_sql(bm.dsv_sql("wwi_stock_item"))
        self.assertTrue({r[9] for r in rows} <= {"true", "false"})


# ================================================================== 4. queries

class QueryTests(unittest.TestCase):
    def test_coverage(self):
        stems = lambda d, ext: sorted(p.stem for p in d.glob(f"*{ext}"))  # noqa: E731
        self.assertEqual(stems(MD / "queries" / "metrics", ".mdx"), stems(ORACLE / "metrics", ".sql"))
        self.assertEqual(stems(MD / "queries" / "questions", ".mdx"), stems(ORACLE / "questions", ".sql"))
        self.assertEqual(len(stems(MD / "queries" / "questions", ".mdx")), 70)

    def test_questions_pass_lint(self):
        problems = []
        for p in sorted((MD / "queries" / "questions").glob("*.mdx")):
            problems += lint_mdx.lint_question(p.read_text(), CATALOGS, oracle_header("questions", p.stem), p.stem)
        self.assertEqual(problems, [])

    def test_metrics_pass_lint_and_cover_oracle_grains(self):
        problems = []
        for p in sorted((MD / "queries" / "metrics").glob("*.mdx")):
            problems += lint_mdx.lint_metric(p.read_text(), CATALOGS, oracle_grains(p.stem), p.stem)
        self.assertEqual(problems, [])

    def test_calculation_scripts_pass_lint(self):
        for cube in ("WWI", "NYC"):
            self.assertEqual(lint_mdx.lint_mdx_text((MD / "mdx" / f"{cube}.mdx").read_text(), CATALOGS[cube],
                                                    query=False), [])

    def test_dropoff_role_returns_null_for_period_metrics(self):
        script = (MD / "mdx" / "NYC.mdx").read_text()
        self.assertRegex(script, r"SCOPE\(\[Dropoff Date\]\.\[Calendar Year\]\.\[Calendar Year\]\.Members\);\s+THIS = NULL;")


# ================================================================== 5. security, rollover, comparator

class SecurityTests(unittest.TestCase):
    def permissions(self, cube):
        out = {}
        for cp in cube_root(cube).findall("a:CubePermissions/a:CubePermission", NS):
            dims = {}
            for dp in cp.findall("a:DimensionPermissions/a:CubeDimensionPermission", NS):
                for ap in dp.findall("a:AttributePermissions/a:AttributePermission", NS):
                    dims[(t(dp, "CubeDimensionID"), t(ap, "AttributeID"))] = (t(ap, "AllowedSet"), t(ap, "VisualTotals"))
            out[t(cp, "RoleID")] = dims
        return out

    def test_territory_role(self):
        wwi = self.permissions("WWI")["Territory Analyst - Southeast"]
        self.assertEqual(wwi[("City", "Sales Territory")], ("{[City].[Sales Territory].&[Southeast]}", "1"))
        self.assertEqual(wwi[("Inventory Access", "Access")], ("{}", "1"))
        self.assertNotIn("Territory Analyst - Southeast", self.permissions("NYC"))

    def test_manhattan_role_restricts_pickup_only(self):
        nyc = self.permissions("NYC")["Manhattan Pickup Analyst"]
        self.assertEqual(set(nyc), {("Pickup Zone", "Borough")})
        self.assertEqual(nyc[("Pickup Zone", "Borough")], ("{[Pickup Zone].[Borough].&[Manhattan]}", "1"))
        self.assertNotIn("Manhattan Pickup Analyst", self.permissions("WWI"))

    def test_inventory_access_relates_only_to_stock(self):
        for mg in cube_root("WWI").findall("a:MeasureGroups/a:MeasureGroup", NS):
            dims = {t(d, "CubeDimensionID") for d in mg.findall("a:Dimensions/a:Dimension", NS)}
            self.assertEqual("Inventory Access" in dims, t(mg, "ID") == "Stock Holdings", t(mg, "ID"))

    def test_allowed_sets_name_existing_attributes(self):
        for cube in ("WWI", "NYC"):
            for role, dims in self.permissions(cube).items():
                for (cube_dim, attr), (allowed, _) in dims.items():
                    self.assertIn(f"[{cube_dim}].[{attr}]", CATALOGS[cube].attributes)
                    if allowed != "{}":
                        self.assertTrue(allowed.startswith(f"{{[{cube_dim}].[{attr}].&["), allowed)


class RolloverTests(unittest.TestCase):
    def current(self):
        return [name for mg in bm.CUBES["NYC"]["measure_groups"] for name, _, _ in bm.partitions(mg)]

    def test_close_month_creates_processes_reslices_and_retires(self):
        actions = pr.plan("2025-01", self.current())
        for mg in pr.MEASURE_GROUPS:
            self.assertIn(("create", mg, f"{mg} 2025-01"), actions)
            self.assertIn(("process", mg, f"{mg} 2025-01"), actions)
            self.assertIn(("reslice_hot", mg, f"2025-02-01"), actions)
            self.assertEqual([a for a in actions if a[0] == "delete" and a[1] == mg], [("delete", mg, f"{mg} 2023-01")])

    def test_rerun_is_idempotent(self):
        after = self.current() + [f"{mg} 2025-01" for mg in pr.MEASURE_GROUPS]
        verbs = [a[0] for a in pr.plan("2025-01", after)]
        self.assertNotIn("create", verbs)
        self.assertIn("process", verbs)

    def test_two_consecutive_rollovers_keep_24_months(self):
        current = self.current()
        for month in ("2025-01", "2025-02"):
            actions = pr.plan(month, current)
            current = [p for p in current if ("delete", p.rsplit(" ", 1)[0], p) not in actions]
            current += [a[2] for a in actions if a[0] == "create"]
        for mg in pr.MEASURE_GROUPS:
            months = sorted(p for p in current if pr.MONTH.match(p) and p.startswith(f"{mg} "))
            self.assertEqual(len(months), 24)
            self.assertEqual(months[0], f"{mg} 2023-03")
            self.assertEqual(months[-1], f"{mg} 2025-02")

    def test_xmla_is_transactional_and_well_formed(self):
        actions = pr.plan("2025-01", self.current())
        root = ET.fromstring(pr.to_xmla(actions).split("\n", 1)[1])
        self.assertEqual(root.get("Transaction"), "true")
        self.assertEqual(len(root.findall("a:Create", NS)), 2)
        self.assertEqual(len(root.findall("a:Alter", NS)), 2)
        self.assertEqual(len(root.findall("a:Delete", NS)), 2)
        self.assertEqual(len(root.findall("a:Parallel/a:Process", NS)), 2)
        hot = root.find("a:Alter/a:ObjectDefinition/a:Partition", NS)
        self.assertEqual(t(hot, "StorageMode"), "Rolap")
        self.assertIn("'2025-02-01'", t(hot.find("a:Source", NS), "QueryDefinition"))
        clear = ET.fromstring(pr.clear_cache_xmla(actions).split("\n", 1)[1])
        self.assertEqual(len(clear.findall("a:ClearCache", NS)), 2)

    def test_partition_queries_cover_the_closed_month_on_fixtures(self):
        actions = pr.plan("2024-12", [p for p in self.current() if not p.endswith("2024-12")])
        root = ET.fromstring(pr.to_xmla(actions).split("\n", 1)[1])
        for part in root.findall("a:Create/a:ObjectDefinition/a:Partition", NS):
            run_sql(t(part.find("a:Source", NS), "QueryDefinition"))


class ComparatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="slc-md-cmp-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, kind, qid, header, rows):
        path = self.tmp / kind / f"{qid}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(header)
            w.writerows(rows)
        return path

    def expected(self, kind, qid):
        with (ORACLE / "expected" / kind / f"{qid}.csv").open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        return rows[0], rows[1:]

    def test_oracle_answer_matches_itself(self):
        for kind, qid in (("metrics", "W-S1"), ("questions", "Q-W-S1-P")):
            header, rows = self.expected(kind, qid)
            fn = compare.compare_metric if kind == "metrics" else compare.compare_question
            out = fn(self.write(kind, qid, header, rows), ORACLE / "expected" / kind / f"{qid}.csv", qid)
            self.assertTrue(out.matches, out.problems[:3])

    def test_metric_differences_and_rule_7(self):
        header, rows = self.expected("metrics", "N-C1")
        null_rows = [r for r in rows if r[5] == ""]
        self.assertTrue(null_rows)
        kept = [r for r in rows if r[5] != ""]
        out = compare.compare_metric(self.write("metrics", "N-C1", header, kept),
                                     ORACLE / "expected" / "metrics" / "N-C1.csv", "N-C1")
        self.assertTrue(out.matches, "absent rows must equal NULL values")
        changed = copy.deepcopy(kept)
        changed[0][5] = str(float(changed[0][5]) + 1)
        changed.append(["year", "N-C1:ytd_revenue", "1999", "", "", "5"])
        out = compare.compare_metric(self.write("metrics", "N-C1", header, changed[1:] + [changed[0]][:0] + [changed[0]]),
                                     ORACLE / "expected" / "metrics" / "N-C1.csv", "N-C1")
        self.assertEqual((out.different, out.extra), (1, 1))

    def test_unknown_label_equals_null(self):
        header, rows = self.expected("metrics", "B-W1")
        swapped = [r[:2] + [("Unknown" if (r[0] == "delivery_year" and r[2] == "") else r[2])] + r[3:] for r in rows]
        out = compare.compare_metric(self.write("metrics", "B-W1", header, swapped),
                                     ORACLE / "expected" / "metrics" / "B-W1.csv", "B-W1")
        self.assertTrue(out.matches, out.problems[:3])

    def test_question_multiset_order_and_tolerance(self):
        header, rows = self.expected("questions", "Q-W-M1-P")
        nudged = [r[:-1] + [str(float(r[-1]) + 5e-7)] for r in reversed(rows)]
        out = compare.compare_question(self.write("questions", "Q-W-M1-P", header, nudged),
                                       ORACLE / "expected" / "questions" / "Q-W-M1-P.csv", "Q-W-M1-P")
        self.assertTrue(out.matches, out.problems[:3])
        broken = [r[:-1] + [str(float(r[-1]) + 1e-3)] for r in rows]
        out = compare.compare_question(self.write("questions", "Q-W-M1-P", header, broken[1:]),
                                       ORACLE / "expected" / "questions" / "Q-W-M1-P.csv", "Q-W-M1-P")
        self.assertFalse(out.matches)
        self.assertEqual(out.missing, len(rows))


# ================================================================== 6. negative

def swap(text: str, old: str, new: str) -> str:
    """Apply a mutation and fail loudly if it does not apply, so no negative test passes on unchanged input."""
    if old not in text:
        raise AssertionError(f"mutation target not found: {old!r}")
    return text.replace(old, new)


class NegativeTests(unittest.TestCase):
    QUESTION = (MD / "queries" / "questions" / "Q-W-M1-P.mdx").read_text()
    HEADER = oracle_header("questions", "Q-W-M1-P")

    def rejected(self, text, pattern, header=None):
        problems = lint_mdx.lint_question(text, CATALOGS, header if header is not None else self.HEADER, "t")
        self.assertTrue(any(re.search(pattern, p) for p in problems), problems)

    def test_valid_question_accepted(self):
        self.assertEqual(lint_mdx.lint_question(self.QUESTION, CATALOGS, self.HEADER, "t"), [])

    def test_malformed_definition(self):
        tmp = Path(tempfile.mkdtemp(prefix="slc-md-neg-"))
        try:
            shutil.copytree(MD / "model", tmp / "model")
            shutil.copytree(MD / "mdx", tmp / "mdx")
            dim = tmp / "model" / "Customer.dim"
            dim.write_text(swap(dim.read_text(), "</Attributes>", "</Attribute>"))
            _, problems = lint_mdx.load_catalog(tmp / "model", tmp / "mdx")
            self.assertTrue(any("malformed XML" in p for p in problems), problems)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_broken_model_references(self):
        tmp = Path(tempfile.mkdtemp(prefix="slc-md-neg-"))
        try:
            shutil.copytree(MD / "model", tmp / "model")
            shutil.copytree(MD / "mdx", tmp / "mdx")
            dim = tmp / "model" / "City.dim"
            dim.write_text(swap(dim.read_text(), "<AttributeID>Continent</AttributeID>", "<AttributeID>Planet</AttributeID>"))
            cube = tmp / "model" / "WWI.cube"
            text = swap(cube.read_text(), "<ColumnID>profit</ColumnID>", "<ColumnID>margin</ColumnID>")
            cube.write_text(swap(text, "<MeasureGroupID>Stock Item Group Bridge</MeasureGroupID>",
                                 "<MeasureGroupID>No Such Bridge</MeasureGroupID>"))
            _, problems = lint_mdx.load_catalog(tmp / "model", tmp / "mdx")
            for pattern in (r"unknown attribute 'Planet'", r"unknown column wwi_sales\.margin",
                            r"many-to-many via unknown measure group 'No Such Bridge'"):
                self.assertTrue(any(re.search(pattern, p) for p in problems), (pattern, problems))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_undefined_measure(self):
        self.rejected(swap(self.QUESTION, "[Measures].[Gross Profit], [Measures].[Gross Margin %]}", "[Measures].[Net Profit], [Measures].[Gross Margin %]}"),
                      r"undefined measure \[Measures\]\.\[Net Profit\]")

    def test_undefined_measure_in_calculation_script(self):
        script = swap((MD / "mdx" / "WWI.mdx").read_text(), "[Measures].[Gross Profit] / ", "[Measures].[Margin] / ")
        self.assertTrue(any("undefined measure [Measures].[Margin]" in p
                            for p in lint_mdx.lint_mdx_text(script, CATALOGS["WWI"], query=False)))

    def test_unknown_hierarchy_level_and_member(self):
        self.rejected(swap(self.QUESTION, "[Customer].[Category].[Category].Members", "[Customer].[Segment].[Segment].Members"),
                      r"unknown hierarchy \[Customer\]\.\[Segment\]")
        self.rejected(swap(self.QUESTION, "[Customer].[Category].[Category].Members", "[Customer].[Category].[Tier].Members"),
                      r"unknown level or member \[Customer\]\.\[Category\]\.\[Tier\]")

    def test_unknown_member_property(self):
        q = swap((MD / "queries" / "questions" / "Q-W-C2-P.mdx").read_text(), '"Month End Date"', '"Month Label"')
        problems = lint_mdx.lint_question(q, CATALOGS, oracle_header("questions", "Q-W-C2-P"), "t")
        self.assertTrue(any("Month Label" in p for p in problems), problems)

    def test_unbalanced_and_wrong_cube(self):
        self.rejected(swap(self.QUESTION, "{[Measures].[Revenue]}) ON ROWS", "{[Measures].[Revenue]} ON ROWS"), r"unclosed|unbalanced")
        problems = lint_mdx.lint_question(swap(self.QUESTION, "FROM [WWI]", "FROM [Sales]"), CATALOGS, self.HEADER, "t")
        self.assertTrue(any("FROM must name a cube" in p for p in problems), problems)

    def test_header_and_column_sources(self):
        self.rejected(self.QUESTION, r"oracle header", header=["customer_category", "fiscal_quarter", "revenue"])
        self.rejected(swap(self.QUESTION, "// @column profit = [Measures].[Gross Profit]",
                           "// @column profit = [Measures].[Units Sold]"),
                      r"not on the COLUMNS axis")
        self.rejected(swap(self.QUESTION, "// @column customer_category = [Customer].[Category]",
                           "// @column customer_category = [Customer].[Buying Group]"),
                      r"not on the ROWS axis")

    def test_metric_grain_and_label_mismatch(self):
        text = (MD / "queries" / "metrics" / "W-S1.mdx").read_text()
        problems = lint_mdx.lint_metric(swap(text, "grain=year_color", "grain=year_colour"), CATALOGS,
                                        oracle_grains("W-S1"), "W-S1")
        self.assertTrue(any("oracle grains" in p for p in problems), problems)
        problems = lint_mdx.lint_metric(swap(text, "values=W-S1:", "values=W-S9:"), CATALOGS,
                                        oracle_grains("W-S1"), "W-S1")
        self.assertTrue(any("measure labels" in p for p in problems), problems)

    def test_rollover_rejects_malformed_month(self):
        import subprocess
        result = subprocess.run([sys.executable, str(MD / "jobs" / "partition_rollover.py"), "--close", "2025-13",
                                 "--current", "Trips Hot", "--out", "/dev/null", "--clear-cache-out", "/dev/null"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("YYYY-MM", result.stderr)


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if result.wasSuccessful() else 1)
