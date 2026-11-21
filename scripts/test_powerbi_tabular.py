#!/usr/bin/env python3
"""Phase 2 test suite: S2 Power BI / Analysis Services Tabular (02-implementations/powerbi-tabular).

Layers
  1. Structure: required files; guide links resolve; documentation URLs and dates recorded; generated TMDL and
     reconciliation DAX in sync with their builders; Fabric Git item files (.platform, definition.pbism).
  2. Models: all six TMDL models parse and pass lint_model.check_model (structure, relationship integrity and
     filter-path ambiguity, measure references, RLS, linguistic metadata, BPA rules); the three storage variants
     share one logical model; storage modes, hybrid incremental refresh policy, Direct Lake entity partitions;
     glossary coverage of the 22 metrics; SPEC § 10 roles.
  3. Queries: 22 metric and 70 question DAX queries cover the oracle, return the oracle's column names in order, and
     reference only model objects and known DAX functions.
  4. Deployment: parameter.yml binds every environment token and connection; BPA rule file matches the linter;
     reconciliation comparator semantics (SPEC § 5.3 rule 7, § 9.3); CI workflow shape.
  5. Negative: malformed TMDL, DAX referencing an undefined measure, and the other model and query rules.

No Power BI engine runs here: DAX execution and reconciliation run on Fabric (deploy/reconcile.py). Standard library
plus PyYAML (scripts/requirements-test.txt). Exits non-zero on failure.

    python3 scripts/test_powerbi_tabular.py
"""

from __future__ import annotations

import copy
import csv
import json
import re
import shutil
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
S2 = REPO / "02-implementations" / "powerbi-tabular"
ORACLE = REPO / "01-spec" / "oracle"
GUIDE = S2 / "POWERBI_TABULAR_GUIDE.md"
WORKFLOW = REPO / ".github" / "workflows" / "s2-powerbi-tabular.yml"
for p in (S2, S2 / "deploy"):
    sys.path.insert(0, str(p))

try:
    import yaml
except ImportError as exc:  # pinned deps are mandatory, never a silent skip
    sys.exit(f"missing test dependency ({exc}); pip install -r scripts/requirements-test.txt")

import build_model as bm  # noqa: E402
import build_reconciliation_queries as brq  # noqa: E402
import deploy as dep  # noqa: E402
import lint_model as lm  # noqa: E402
import reconcile as rc  # noqa: E402

MODEL_DIRS = lm.model_dirs()
MODELS = {d.name.removesuffix(".SemanticModel"): lm.load_model(d / "definition") for d in MODEL_DIRS}


def oracle_ids(kind: str) -> list[str]:
    return sorted(p.stem for p in (ORACLE / kind).glob("*.sql"))


def stack_ids(kind: str) -> list[str]:
    return sorted(p.stem for p in (S2 / "queries" / kind).glob("*.dax"))


def expected(kind: str, qid: str) -> tuple[list[str], list[list[str]]]:
    with (ORACLE / "expected" / kind / f"{qid}.csv").open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    return rows[0], rows[1:]


def copy_model(name: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="slc-s2-")) / "definition"
    shutil.copytree(S2 / "models" / f"{name}.SemanticModel" / "definition", tmp)
    return tmp


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text, f"{old!r} not in {path.name}"
    path.write_text(text.replace(old, new, 1))


# ================================================================== 1. structure

class StructureTests(unittest.TestCase):
    def test_required_files(self):
        required = ["POWERBI_TABULAR_GUIDE.md", "build_model.py", "build_reconciliation_queries.py", "lint_model.py",
                    "deploy/deploy.py", "deploy/reconcile.py", "deploy/parameter.yml", "deploy/requirements.txt",
                    "deploy/bpa_rules.json", "deploy/XmlaQuery/XmlaQuery.csproj", "deploy/XmlaQuery/Program.cs",
                    "copilot/ai_instructions_wwi.md", "copilot/ai_instructions_nyc.md", "copilot/verified_answers.md"]
        self.assertEqual([r for r in required if not (S2 / r).is_file()], [])
        self.assertTrue(WORKFLOW.is_file())

    def test_six_fabric_items(self):
        names = sorted(MODELS)
        self.assertEqual(names, sorted(f"SLC_{d}_{v}" for d in ("WWI", "NYC") for v in ("Import", "DirectLake", "DirectQuery")))
        ids = set()
        for d in MODEL_DIRS:
            platform = json.loads((d / ".platform").read_text())
            self.assertEqual(platform["metadata"]["type"], "SemanticModel")
            self.assertEqual(platform["metadata"]["displayName"], d.name.removesuffix(".SemanticModel"))
            ids.add(platform["config"]["logicalId"])
            self.assertGreaterEqual(float(json.loads((d / "definition.pbism").read_text())["version"]), 4.0)
            for f in ("database.tmdl", "model.tmdl", "relationships.tmdl", "expressions.tmdl", "cultures/en-US.tmdl"):
                self.assertTrue((d / "definition" / f).is_file(), f"{d.name}/{f}")
        self.assertEqual(len(ids), 6)

    def test_generated_files_in_sync(self):
        stale = [str(p.relative_to(S2)) for p, t in bm.outputs().items() if not p.exists() or p.read_text() != t]
        self.assertEqual(stale, [])
        self.assertEqual([m for m in brq.ORDER if (brq.OUT / f"{m}.dax").read_text() != brq.render(m)], [])

    def test_no_placeholders_in_code(self):
        for path in list((S2 / "models").rglob("*.tmdl")) + list((S2 / "queries").rglob("*.dax")):
            self.assertNotRegex(path.read_text(), r"\.\.\.|TODO|<placeholder>|…", path.name)

    def test_guide_sections_links_and_sources(self):
        text = GUIDE.read_text()
        for section in ("Model structure", "Calculation semantics", "Security model", "Performance behavior", "Limitations"):
            self.assertRegex(text, rf"(?m)^## \d+\. {section}")
        links = [l for l in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text) if not l.startswith("http")]
        self.assertGreater(len(links), 12)
        self.assertEqual([l for l in links if not (GUIDE.parent / l).resolve().exists()], [])
        for url in ("tmdl/tmdl-overview", "desktop-time-intelligence", "direct-lake-overview",
                    "incremental-refresh-overview", "execute-queries-in-group", "copilot-prepare-data-ai-instructions",
                    "copilot-prepare-data-ai-verified-answers", "service-premium-service-principal", "databricks-azure"):
            self.assertIn(url, text)
        self.assertRegex(text, r"checked 2026-\d\d-\d\d")
        for block in re.findall(r"```[a-z]*\n(.*?)```", text, re.S):
            self.assertNotRegex(block, r"\.\.\.|TODO|<placeholder>")


# ================================================================== 2. models

class ModelTests(unittest.TestCase):
    def test_every_model_passes_lint(self):
        problems = [p for m in MODELS.values() for p in lm.check_model(m)]
        self.assertEqual(problems, [])

    def logical(self, model: lm.Model) -> dict:
        tables = {}
        for name, t in model.tables.items():
            tables[name] = {
                "columns": {c.name: (c.props.get("dataType"), c.props.get("sourceColumn"), "isHidden" in c.flags)
                            for c in t.children if c.kind == "column"},
                "measures": {m.name: m.expression for m in t.children if m.kind == "measure"},
            }
        rels = sorted(tuple(sorted(r.props.items())) for r in model.relationships)
        roles = {r.name: {c.name: c.expression for c in r.children} for r in model.roles.values()}
        return {"tables": tables, "relationships": rels, "roles": roles}

    def test_variants_share_one_logical_model(self):
        for ds in ("WWI", "NYC"):
            base = self.logical(MODELS[f"SLC_{ds}_Import"])
            for v in ("DirectLake", "DirectQuery"):
                self.assertEqual(self.logical(MODELS[f"SLC_{ds}_{v}"]), base, f"{ds} {v}")

    def partition_modes(self, name: str) -> dict[str, str]:
        return {t: next(c for c in o.children if c.kind == "partition").props["mode"] for t, o in MODELS[name].tables.items()}

    def test_storage_modes(self):
        self.assertEqual(set(self.partition_modes("SLC_WWI_Import").values()), {"import"})
        nyc_import = self.partition_modes("SLC_NYC_Import")
        self.assertEqual(nyc_import.pop("Trips"), "import")
        self.assertEqual(set(nyc_import.values()), {"dual"})
        for ds in ("WWI", "NYC"):
            dq = self.partition_modes(f"SLC_{ds}_DirectQuery")
            facts = {"Sales", "Orders", "Stock Holding", "Trips"}
            self.assertEqual({t for t, m in dq.items() if m == "directQuery"}, facts & set(dq))
            self.assertEqual({m for t, m in dq.items() if t not in facts}, {"dual"})
        dl = self.partition_modes("SLC_WWI_DirectLake")
        self.assertEqual({t for t, m in dl.items() if m != "directLake"}, {"Stock Item (Current)"})
        self.assertEqual(set(self.partition_modes("SLC_NYC_DirectLake").values()), {"directLake"})

    def test_direct_lake_entities_point_at_the_mirrored_catalog(self):
        for name in ("SLC_WWI_DirectLake", "SLC_NYC_DirectLake"):
            model = MODELS[name]
            self.assertIn("AzureStorage.DataLake(OneLakeSourceUrl", model.expressions["DirectLake - slc"].expression)
            for t in model.tables.values():
                part = next(c for c in t.children if c.kind == "partition")
                if part.props["mode"] == "directLake":
                    src = next(c for c in part.children if c.kind == "source")
                    self.assertIn(src.props["schemaName"], {"wwi", "nyctaxi"})

    def test_hybrid_incremental_refresh_policy(self):
        trips = MODELS["SLC_NYC_Import"].tables["Trips"]
        policy = next(c for c in trips.children if c.kind == "refreshPolicy")
        self.assertEqual(policy.props["mode"], "hybrid")
        self.assertEqual((policy.props["rollingWindowGranularity"], policy.props["rollingWindowPeriods"]), ("month", "24"))
        self.assertIn("RangeStart", policy.props["sourceExpression"])
        self.assertIn("RangeEnd", policy.props["sourceExpression"])
        self.assertIn("RangeStart", MODELS["SLC_NYC_Import"].expressions)
        others = [n for n, m in MODELS.items() for t in m.tables.values() for c in t.children
                  if c.kind == "refreshPolicy" and n != "SLC_NYC_Import"]
        self.assertEqual(others, [])

    def test_connector_uses_adbc_and_navigation(self):
        text = (S2 / "models" / "SLC_WWI_DirectQuery.SemanticModel" / "definition" / "tables" / "Sales.tmdl").read_text()
        self.assertIn('Implementation = "2.0"', text)
        self.assertIn("Databricks.Catalogs(", text)
        self.assertNotIn("Databricks.Query", text)  # not supported with DirectQuery (connector documentation)

    def test_glossary_metrics_covered(self):
        ids = {m.annotations.get("SLC_MetricId") for model in (MODELS["SLC_WWI_Import"], MODELS["SLC_NYC_Import"])
               for _, m in model.measures().values()}
        glossary = yaml.safe_load((REPO / "01-spec" / "glossary.yaml").read_text())
        self.assertEqual({m["id"] for m in glossary["metrics"]} - ids, set())

    def test_visible_measures_carry_agent_metadata(self):
        for model in (MODELS["SLC_WWI_Import"], MODELS["SLC_NYC_Import"]):
            for _, m in model.measures().values():
                if "isHidden" not in m.flags:
                    self.assertTrue(m.description, m.name)
                    self.assertIn("formatString", m.props, m.name)
            entities = json.loads(next(x for x in model.cultures["en-US"].children
                                       if x.kind == "linguisticMetadata").expression)["Entities"]
            self.assertGreater(len(entities), 8)

    def test_spec_section_10_roles(self):
        wwi = MODELS["SLC_WWI_Import"].roles["Territory Analyst - Southeast"]
        perms = {c.name: c.expression for c in wwi.children if c.kind == "tablePermission"}
        self.assertEqual(perms, {"City": "'City'[Sales Territory] = \"Southeast\"", "Stock Holding": "FALSE ()"})
        nyc = MODELS["SLC_NYC_Import"].roles["Manhattan Pickup Analyst"]
        perms = {c.name: c.expression for c in nyc.children if c.kind == "tablePermission"}
        self.assertEqual(perms, {"Pickup Zone": "'Pickup Zone'[Pickup Borough] = \"Manhattan\""})

    def test_role_playing_and_bridge_relationships(self):
        wwi = MODELS["SLC_WWI_Import"]
        rels = [lm.relationship_parts(wwi, r) for r in wwi.relationships]
        self.assertIn(("Sales", "delivery_date", "Delivery Date", "Delivery Date"), rels)
        self.assertIn(("Sales", "bill_to_customer_key", "Bill-To Customer", "Bill-To Customer Key"), rels)
        m2m = [r for r in wwi.relationships if r.props.get("toCardinality") == "many"]
        self.assertEqual(len(m2m), 1)
        self.assertEqual(m2m[0].props.get("crossFilteringBehavior"), "oneDirection")
        self.assertFalse(any(r.props.get("isActive") == "false" for m in MODELS.values() for r in m.relationships))

    def test_non_conformed_dimensions_are_guarded(self):
        measures = MODELS["SLC_WWI_Import"].measures()
        self.assertIn("ISCROSSFILTERED ( 'Picker' )", measures["Revenue (Excl. Tax)"][1].expression)
        self.assertIn("ISCROSSFILTERED ( 'City' )", measures["Closing Stock On Hand"][1].expression)
        nyc = MODELS["SLC_NYC_Import"].measures()
        self.assertIn("ISCROSSFILTERED ( 'Dropoff Date' )", nyc["Revenue YTD"][1].expression)
        self.assertIn("DATE ( 2024, 12, 31 )", nyc["Pickup Anchor Date"][1].expression)
        self.assertIn("EDATE ( t, -12 )", nyc["Revenue STLY YTD"][1].expression)


# ================================================================== 3. queries

class QueryTests(unittest.TestCase):
    def test_coverage(self):
        self.assertEqual(stack_ids("metrics"), oracle_ids("metrics"))
        self.assertEqual(stack_ids("questions"), oracle_ids("questions"))

    def test_output_columns_match_oracle(self):
        wrong = {}
        for kind in ("metrics", "questions"):
            for path in sorted((S2 / "queries" / kind).glob("*.dax")):
                header, _ = expected(kind, path.stem)
                cols = lm.output_columns(path.read_text())
                if cols != header:
                    wrong[path.stem] = cols
        self.assertEqual(wrong, {})

    def test_queries_reference_only_model_objects(self):
        problems = []
        for path in sorted((S2 / "queries").glob("*/*.dax")):
            model = MODELS[f"SLC_{lm.model_for_query(path)}_Import"]
            problems += lm.check_query(model, path.read_text(), path.name)
        self.assertEqual(problems, [])

    def test_metric_queries_render_members_as_text(self):
        for path in (S2 / "queries" / "metrics").glob("*.dax"):
            text = path.read_text()
            self.assertNotRegex(text, r'"member_\d", (?!FORMAT|CONVERT|\')', path.name)

    def test_rows_with_null_measures_are_kept_where_the_oracle_lists_them(self):
        # Card tips are blank for most vendor-months and payment codes; the oracle still lists those rows.
        for qid in ("Q-N-S2-P", "Q-N-S2-D1", "Q-N-S2-D2"):
            self.assertIn('"__trips", [Trip Count]', (S2 / "queries" / "questions" / f"{qid}.dax").read_text())
        self.assertIn("SUMMARIZE ( 'Payment Type'", (S2 / "queries" / "questions" / "Q-N-S2-D4.dax").read_text())


# ================================================================== 4. deployment and reconciliation

class DeploymentTests(unittest.TestCase):
    def test_parameter_file_binds_every_token_and_model(self):
        params = yaml.safe_load((S2 / "deploy" / "parameter.yml").read_text())
        finds = {e["find_value"] for e in params["find_replace"]}
        self.assertEqual(finds, set(bm.TOKENS.values()))
        for e in params["find_replace"]:
            self.assertEqual(set(e["replace_value"]), {"test", "prod"})
            self.assertEqual(e["item_type"], "SemanticModel")
        committed = "\n".join(p.read_text() for p in (S2 / "models").rglob("expressions.tmdl"))
        for token in bm.TOKENS.values():
            self.assertIn(token, committed)
        binding = params["semantic_model_binding"]
        self.assertEqual(set(binding["default"]["connection_id"]), {"test", "prod"})
        for entry in binding["models"]:
            for name in entry["semantic_model_name"]:
                self.assertIn(name, MODELS)

    def test_deploy_selects_variants(self):
        self.assertEqual(dep.model_names(["directlake"]), ["SLC_WWI_DirectLake", "SLC_NYC_DirectLake"])
        with self.assertRaises(KeyError):
            dep.model_names(["composite"])

    def test_bpa_rule_file_matches_linter(self):
        rules = json.loads((S2 / "deploy" / "bpa_rules.json").read_text())
        self.assertEqual({r["ID"] for r in rules}, set(lm.BPA_RULES))
        for r in rules:
            self.assertEqual(set(r), {"ID", "Name", "Category", "Description", "Severity", "Scope", "Expression",
                                      "CompatibilityLevel"})

    def test_workflow_shape(self):
        wf = yaml.safe_load(WORKFLOW.read_text())
        self.assertEqual(list(wf["jobs"]), ["lint", "test", "promote"])
        self.assertEqual(wf["jobs"]["test"]["needs"], "lint")
        self.assertEqual(wf["jobs"]["promote"]["needs"], "test")
        runs = " ".join(s.get("run", "") for s in wf["jobs"]["lint"]["steps"])
        self.assertIn("scripts/test_powerbi_tabular.py", runs)
        test_runs = " ".join(s.get("run", "") for s in wf["jobs"]["test"]["steps"])
        self.assertIn("deploy.py --environment test", test_runs)
        self.assertIn("--transport xmla", test_runs)
        self.assertIn("--fail-on-mismatch", test_runs)
        self.assertNotRegex(WORKFLOW.read_text(), r"Password=[A-Za-z0-9]")


class ComparatorTests(unittest.TestCase):
    def metric_rows(self, qid: str):
        header, rows = expected("metrics", qid)
        return header, [r[:5] + [None if r[5] == "" else (Decimal(r[5]) if "." in r[5] else int(r[5]))] for r in rows]

    def test_exact_metric_result_matches(self):
        header, rows = self.metric_rows("W-S1")
        out = rc.Outcome("W-S1", "metrics")
        rc.compare_metric(header, rows, ORACLE / "expected" / "metrics" / "W-S1.csv", out)
        self.assertTrue(out.matches, out.problems[:3])

    def test_absent_row_equals_null_value(self):
        header, rows = self.metric_rows("B-W5")
        nulls = [r for r in rows if r[5] is None]
        self.assertTrue(nulls, "B-W5 has NULL cells in the oracle")
        out = rc.Outcome("B-W5", "metrics")
        rc.compare_metric(header, [r for r in rows if r[5] is not None], ORACLE / "expected" / "metrics" / "B-W5.csv", out)
        self.assertTrue(out.matches, out.problems[:3])

    def test_missing_extra_and_different_are_counted(self):
        header, rows = self.metric_rows("W-S1")
        broken = copy.deepcopy(rows[1:]) + [["year", "W-S1", "1999", None, None, Decimal("1.00")]]
        broken[0][5] = broken[0][5] + Decimal("0.01")
        out = rc.Outcome("W-S1", "metrics")
        rc.compare_metric(header, broken, ORACLE / "expected" / "metrics" / "W-S1.csv", out)
        self.assertEqual((out.missing, out.extra, out.different), (1, 1, 1))

    def test_question_multiset_and_dates(self):
        header, rows = expected("questions", "Q-W-S2-P")
        actual = [[f"{r[0]}T00:00:00", int(r[1]), Decimal(r[2])] for r in reversed(rows)]
        out = rc.Outcome("Q-W-S2-P", "questions")
        rc.compare_question(header, actual, ORACLE / "expected" / "questions" / "Q-W-S2-P.csv", out)
        self.assertTrue(out.matches, out.problems[:3])
        out = rc.Outcome("Q-W-S2-P", "questions")
        rc.compare_question(header, actual[1:], ORACLE / "expected" / "questions" / "Q-W-S2-P.csv", out)
        self.assertEqual(out.missing, 1)

    def test_tolerances(self):
        self.assertTrue(rc.values_match(Decimal("100.004"), "100"))
        self.assertTrue(rc.values_match(Decimal("12.344"), "12.34"))
        self.assertFalse(rc.values_match(Decimal("12.35"), "12.34"))
        self.assertTrue(rc.values_match(0.2690905797346775, "0.269090579734677"))
        self.assertFalse(rc.values_match(0.2691, "0.269090579734677"))
        self.assertFalse(rc.values_match(None, "0"))
        self.assertFalse(rc.values_match(0, ""))
        self.assertTrue(rc.values_match(True, "true"))
        self.assertTrue(rc.values_match("2015-12-31T00:00:00", "2015-12-31"))

    def test_wrong_columns_are_rejected(self):
        out = rc.Outcome("W-S1", "metrics")
        rc.compare_metric(["grain", "measure"], [], ORACLE / "expected" / "metrics" / "W-S1.csv", out)
        self.assertFalse(out.matches)


# ================================================================== 5. negative

class NegativeTmdlTests(unittest.TestCase):
    def test_malformed_tmdl_is_rejected(self):
        cases = [
            "table Sales\n    measure X = 1\n",  # spaces instead of tabs
            "\tdataType: int64\n",  # indented without a parent
            "dataType: int64\n",  # property outside an object
            "table T\n\tmeasure M =\n",  # expression expected
            "/// orphan description\n",  # description not followed by an object
            "table T\n\tlineageTag: a\n\tlineageTag: b\n",  # duplicate property
            "table T\n\t!!! not tmdl\n",
        ]
        for text in cases:
            with self.assertRaises(lm.TmdlError, msg=repr(text)):
                lm.parse_tmdl(text, "t.tmdl")

    def test_valid_snippet_parses(self):
        objs = lm.parse_tmdl("/// d\ntable 'A B'\n\tmeasure 'M 1' =\n\t\t\tSUM ( 'A B'[c] )\n\t\tformatString: 0\n"
                             "\tcolumn c\n\t\tdataType: int64\n\t\tsummarizeBy: none\n\t\tsourceColumn: c\n", "t.tmdl")
        self.assertEqual(objs[0].name, "A B")
        self.assertEqual(objs[0].description, "d")
        self.assertEqual(objs[0].children[0].expression, "SUM ( 'A B'[c] )")

    def check(self, model_name: str, mutate) -> list[str]:
        d = copy_model(model_name)
        try:
            mutate(d)
            return lm.check_model(lm.load_model(d))
        finally:
            shutil.rmtree(d.parent, ignore_errors=True)

    def assertFlags(self, problems: list[str], pattern: str):
        self.assertTrue(any(re.search(pattern, p) for p in problems), problems[:5])

    def test_measure_referencing_undefined_measure(self):
        p = self.check("SLC_WWI_Import", lambda d: edit(d / "tables" / "Sales.tmdl",
                       "DIVIDE ( [Gross Profit], [Revenue (Excl. Tax)] )", "DIVIDE ( [Gross Profit], [Net Revenue] )"))
        self.assertFlags(p, r"\[Net Revenue\] is neither a measure")

    def test_relationship_to_unknown_column(self):
        p = self.check("SLC_WWI_Import", lambda d: edit(d / "relationships.tmdl", "toColumn: Date.Date", "toColumn: Date.DateKey"))
        self.assertFlags(p, r"unknown column Date\[DateKey\]")

    def test_bidirectional_and_duplicate_relationships(self):
        def mutate(d):
            text = (d / "relationships.tmdl").read_text()
            first = text.split("\n\n")[0]
            (d / "relationships.tmdl").write_text(text + "\n" + first.replace("relationship ", "relationship 0")
                                                  + "\n\tcrossFilteringBehavior: bothDirections\n")
        p = self.check("SLC_WWI_Import", mutate)
        self.assertFlags(p, r"SLC_NO_BIDIRECTIONAL")
        self.assertFlags(p, r"two active relationships")

    def test_role_on_unknown_table_and_bad_filter(self):
        p = self.check("SLC_NYC_Import", lambda d: edit(d / "roles" / "Manhattan Pickup Analyst.tmdl",
                       "tablePermission 'Pickup Zone' = 'Pickup Zone'[Pickup Borough]",
                       "tablePermission 'Pickup Area' = 'Pickup Area'[Pickup Borough]"))
        self.assertFlags(p, r"filters unknown table Pickup Area")

    def test_bpa_violations(self):
        p = self.check("SLC_NYC_Import", lambda d: edit(d / "tables" / "Trips.tmdl",
                       "DIVIDE ( [Fare Amount], [Total Trip Distance] )", "[Fare Amount] / [Total Trip Distance]"))
        self.assertFlags(p, r"SLC_DIVIDE Fare per Mile")
        p = self.check("SLC_NYC_Import", lambda d: edit(d / "model.tmdl", "\tdiscourageImplicitMeasures\n", ""))
        self.assertFlags(p, r"SLC_DISCOURAGE_IMPLICIT")
        p = self.check("SLC_NYC_Import", lambda d: edit(d / "tables" / "Trips.tmdl",
                       "\tcolumn trip_id\n\t\tdataType: int64\n\t\tisHidden\n", "\tcolumn trip_id\n\t\tdataType: int64\n"))
        self.assertFlags(p, r"SLC_FACT_COLUMNS_HIDDEN Trips\[trip_id\]")

    def test_invalid_partition_mode_and_missing_entity(self):
        p = self.check("SLC_NYC_DirectLake", lambda d: edit(d / "tables" / "Trips.tmdl", "mode: directLake", "mode: lakehouse"))
        self.assertFlags(p, r"invalid mode 'lakehouse'")
        p = self.check("SLC_NYC_DirectLake", lambda d: edit(d / "tables" / "Trips.tmdl",
                       "expressionSource: 'DirectLake - slc'", "expressionSource: 'DirectLake - other'"))
        self.assertFlags(p, r"unknown expression")

    def test_linguistic_binding_to_unknown_measure(self):
        p = self.check("SLC_NYC_Import", lambda d: edit(d / "cultures" / "en-US.tmdl",
                       '"ConceptualProperty": "Card Tips"', '"ConceptualProperty": "Card Tipz"'))
        self.assertFlags(p, r"binds unknown property Card Tipz")


class NegativeQueryTests(unittest.TestCase):
    model = MODELS["SLC_NYC_Import"]

    def problems(self, dax: str) -> list[str]:
        return lm.check_query(self.model, dax, "q")

    def test_query_referencing_undefined_measure(self):
        p = self.problems('EVALUATE SELECTCOLUMNS ( { 1 }, "x", [Net Fare] )')
        self.assertTrue(any("[Net Fare] is neither a measure" in x for x in p), p)

    def test_unknown_table_column_and_function(self):
        p = self.problems("EVALUATE SELECTCOLUMNS ( Trips, \"a\", 'Pickup Area'[Borough], \"b\", Trips[fare], \"c\", FAREX ( 1 ) )")
        self.assertTrue(any("unknown table 'Pickup Area'" in x for x in p), p)
        self.assertTrue(any("unknown column Trips[fare]" in x for x in p), p)
        self.assertTrue(any("unknown DAX function FAREX" in x for x in p), p)

    def test_unbalanced_parentheses(self):
        self.assertTrue(any("unbalanced" in x for x in self.problems('EVALUATE ROW ( "a", [Trip Count]')))

    def test_output_shape_rules(self):
        for dax in ('ROW ( "a", 1 )', 'EVALUATE Trips', 'EVALUATE ROW ( "a", 1 ) EVALUATE ROW ( "b", 2 )',
                    'EVALUATE SELECTCOLUMNS ( Trips, [Trip Count], 1 )', 'EVALUATE ROW ( "a" )'):
            with self.assertRaises(ValueError, msg=dax):
                lm.output_columns(dax)
        self.assertEqual(lm.output_columns('EVALUATE UNION ( ROW ( "a", 1, "b", 2 ), ROW ( "c", 3, "d", 4 ) )'), ["a", "b"])


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if result.wasSuccessful() else 1)
