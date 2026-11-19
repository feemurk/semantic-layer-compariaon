#!/usr/bin/env python3
"""Phase 1 test suite: asserts 01-spec/SPEC.md delivers every locked scope item.

Positive tests run against the committed SPEC.md. Negative tests apply a
targeted mutation to the SPEC text and assert the validator rejects it.

Standard library only. Exits non-zero on failure.

    python3 scripts/test_spec.py
"""

import re
import sys
import unittest
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "01-spec" / "SPEC.md"

REQUIRED_SECTIONS = [
    "## 1. Thesis and Objectives",
    "## 2. Audience and OCM Framing",
    "## 3. Stacks in Scope",
    "## 4. Shared Data Platform",
    "## 5. Canonical Schema",
    "## 6. Metric Catalog (22 Metrics)",
    "## 7. Self-Service Question Bank",
    "## 8. Evaluation Dimensions",
    "## 9. Correctness Oracle and Reconciliation",
    "## 10. Security Scenario",
    "## 11. AI Agent Evaluation Protocol",
    "## 12. Deliverables",
    "## 13. Phase Plan",
    "## 14. Verification Register",
    "## 15. Locked Decisions",
    "## 16. Change Control and Changelog",
]

STACK_IDS = {"S1", "S2", "S3", "S4"}
STACK_FOLDERS = [
    "02-implementations/ssas-md/",
    "02-implementations/powerbi-tabular/",
    "02-implementations/bi-layer/",
    "02-implementations/databricks-metric-views/",
]
WWI_TABLES = [
    "fact_sale", "fact_order", "fact_stock_movement", "stock_holding_current",
    "fact_stock_holding_daily", "dim_stock_item", "dim_stock_group",
    "bridge_stock_item_group", "dim_customer", "dim_city", "dim_employee", "dim_date",
]
NYC_TABLES = ["fact_trip", "fact_trip_quarantine", "dim_zone", "dim_payment_type", "dim_date"]

METRIC_ID_RE = re.compile(r"^(B-[WN][1-5]|[WN]-[SMC][12])$")
KPI_ID_RE = re.compile(r"^[WN]-[SMC][12]$")
QUESTION_ID_RE = re.compile(r"^Q-([WN]-[SMC][12])-(P|D[1-4])$|^Q-A(\d{2})$")
PLACEHOLDER_RE = re.compile(r"\bTODO\b|\bTBD\b|\bFIXME\b|<placeholder>|lorem ipsum", re.I)

EXPECTED_TIERS = {"Simple": 2, "Medium": 2, "Complex": 2}
WWI_MATRIX_COLS = ["Metric", "DATE", "DELIV", "CUST", "BILL", "CITY", "ITEM", "GROUP", "SP", "PICK"]
NYC_MATRIX_COLS = ["Metric", "PDATE", "DDATE", "HOUR", "PZONE", "DZONE", "PAY", "VEND"]


def cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def section(text: str, number: int) -> str:
    start = re.search(rf"^## {number}\. .*$", text, re.M)
    if not start:
        return ""
    nxt = re.search(r"^## \d+\. .*$", text[start.end():], re.M)
    return text[start.end(): start.end() + nxt.start()] if nxt else text[start.end():]


def tables(block: str) -> list[list[list[str]]]:
    """Return markdown tables in a block as lists of rows (header first, separator dropped)."""
    result, current = [], []
    for line in block.splitlines():
        if line.startswith("|"):
            current.append(line)
        elif current:
            result.append(current)
            current = []
    if current:
        result.append(current)
    parsed = []
    for tbl in result:
        rows = [cells(r) for r in tbl if not set(r) <= set("|-: ")]
        parsed.append(rows)
    return parsed


def find_table(block: str, first_header: str) -> list[list[str]]:
    for tbl in tables(block):
        if tbl and tbl[0] and tbl[0][0] == first_header:
            return tbl
    return []


def find_table_by_header(block: str, header: list[str]) -> list[list[str]]:
    for tbl in tables(block):
        if tbl and tbl[0] == header:
            return tbl
    return []


# ---------------------------------------------------------------- validators

def check_structure(text: str) -> list[str]:
    errors = [f"missing section: {s}" for s in REQUIRED_SECTIONS if s not in text]
    if not re.search(r"^\| State \| LOCKED \|$", text, re.M):
        errors.append("header does not declare State LOCKED")
    if not re.search(r"^\| Version \| \d+\.\d+ \|$", text, re.M):
        errors.append("header does not declare a Version")
    for match in PLACEHOLDER_RE.finditer(text):
        errors.append(f"placeholder token: {match.group(0)!r}")
    for i, tbl in enumerate(tables(text)):
        width = len(tbl[0])
        for row in tbl[1:]:
            if len(row) != width:
                errors.append(f"table {i} row width {len(row)} != header {width}: {row[:2]}")
    return errors


def metric_catalog(text: str) -> list[list[str]]:
    tbl = find_table(section(text, 6), "ID")
    return [r for r in tbl[1:] if METRIC_ID_RE.match(r[0])]


def check_metrics(text: str) -> list[str]:
    errors = []
    rows = metric_catalog(text)
    ids = [r[0] for r in rows]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    if dupes:
        errors.append(f"duplicate metric ids: {dupes}")
    if len(set(ids)) != 22:
        errors.append(f"metric catalog has {len(set(ids))} metrics, expected 22")
    base = [r for r in rows if r[2] == "Base"]
    kpis = [r for r in rows if KPI_ID_RE.match(r[0])]
    if len(base) != 10:
        errors.append(f"{len(base)} base measures, expected 10")
    if len(kpis) != 12:
        errors.append(f"{len(kpis)} KPIs, expected 12")
    for dataset in ("WWI", "NYC"):
        tiers = Counter(r[2] for r in kpis if r[1] == dataset)
        if dict(tiers) != EXPECTED_TIERS:
            errors.append(f"{dataset} tier distribution {dict(tiers)} != {EXPECTED_TIERS}")
    for r in kpis:
        if not r[4]:
            errors.append(f"KPI {r[0]} has no mechanism stated")
    mechanisms = [r[4] for r in kpis]
    if len(set(mechanisms)) != len(mechanisms):
        errors.append("KPI mechanisms are not distinct")
    for metric_id in set(ids):
        if not re.search(rf"^### {re.escape(metric_id)} — \S", text, re.M):
            errors.append(f"no definition heading for {metric_id}")
    return errors


def check_applicability(text: str) -> list[str]:
    errors = []
    block = section(text, 6)
    ids = {r[0] for r in metric_catalog(text)}
    for header, prefix in ((WWI_MATRIX_COLS, ("B-W", "W-")), (NYC_MATRIX_COLS, ("B-N", "N-"))):
        tbl = find_table_by_header(block, header)
        if not tbl:
            errors.append(f"missing applicability matrix with header {header}")
            continue
        rows = {r[0]: r[1:] for r in tbl[1:]}
        expected = {i for i in ids if i.startswith(prefix)}
        missing = expected - rows.keys()
        if missing:
            errors.append(f"applicability matrix missing rows: {sorted(missing)}")
        for metric_id, values in rows.items():
            bad = [v for v in values if v not in {"✓", "N"}]
            if bad:
                errors.append(f"invalid applicability values for {metric_id}: {bad}")
    return errors


def check_questions(text: str) -> list[str]:
    errors = []
    tbl = find_table(section(text, 7), "ID")
    rows = tbl[1:]
    ids = [r[0] for r in rows]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    if dupes:
        errors.append(f"duplicate question ids: {dupes}")
    metric_ids = {r[0] for r in metric_catalog(text)}
    kpi_ids = {i for i in metric_ids if KPI_ID_RE.match(i)}
    chains: dict[str, set[str]] = {}
    adhoc = 0
    for r in rows:
        m = QUESTION_ID_RE.match(r[0])
        if not m:
            errors.append(f"invalid question id: {r[0]}")
            continue
        qtype, cited, question = r[1], r[2], r[3]
        if m.group(1):
            chains.setdefault(m.group(1), set()).add(m.group(2))
            if qtype != m.group(2):
                errors.append(f"{r[0]} type {qtype!r} does not match id")
        else:
            adhoc += 1
            if qtype != "AH":
                errors.append(f"{r[0]} must be type AH")
        for metric in (c.strip() for c in cited.split(",")):
            if metric not in metric_ids:
                errors.append(f"{r[0]} cites unknown metric {metric!r}")
        if len(question) < 20:
            errors.append(f"{r[0]} question text too short")
    for kpi in kpi_ids:
        if chains.get(kpi) != {"P", "D1", "D2", "D3", "D4"}:
            errors.append(f"incomplete chain for {kpi}: {sorted(chains.get(kpi, set()))}")
    if adhoc != 10:
        errors.append(f"{adhoc} ad hoc questions, expected 10")
    if len(set(ids)) != 70:
        errors.append(f"question bank has {len(set(ids))} questions, expected 70")
    predefined = sum(1 for r in rows if r[1] == "P")
    if rows and predefined / len(rows) > 0.20:
        errors.append(f"predefined share {predefined}/{len(rows)} exceeds 20%")
    return errors


def check_traceability(text: str) -> list[str]:
    errors = []
    e_ids = {r[0] for r in find_table(section(text, 8), "ID")[1:] if re.match(r"^E\d$", r[0])}
    if e_ids != {f"E{i}" for i in range(1, 10)}:
        errors.append(f"evaluation dimensions {sorted(e_ids)} != E1..E9")
    hyp = find_table(section(text, 1), "ID")[1:]
    if [r[0] for r in hyp] != [f"H{i}" for i in range(1, 9)]:
        errors.append("hypotheses are not exactly H1..H8")
    for r in hyp:
        if r[2] not in e_ids:
            errors.append(f"{r[0]} maps to unknown dimension {r[2]}")
    claims = find_table(section(text, 2), "ID")[1:]
    if [r[0] for r in claims] != [f"MC-0{i}" for i in range(1, 9)]:
        errors.append("claims register is not exactly MC-01..MC-08")
    for r in claims:
        refs = set(re.findall(r"E\d", r[2]))
        if not refs or not refs <= e_ids:
            errors.append(f"{r[0]} evidence {r[2]!r} does not reference valid dimensions")
    return errors


def check_stacks_and_schema(text: str) -> list[str]:
    errors = []
    stacks = find_table(section(text, 3), "ID")
    found = {r[0] for r in stacks[1:]}
    if found != STACK_IDS:
        errors.append(f"stack ids {sorted(found)} != {sorted(STACK_IDS)}")
    for folder in STACK_FOLDERS:
        if folder not in section(text, 3):
            errors.append(f"stack folder not referenced: {folder}")
    if "Yellowfin" not in section(text, 1):
        errors.append("Yellowfin exclusion not recorded in non-goals")
    for name in ("YAML specification 1.1", "MEASURE()", "WITH METRICS LANGUAGE YAML"):
        if name not in text:
            errors.append(f"Databricks currency term missing: {name}")
    schema = section(text, 5)
    for heading, required in (("### 5.1", WWI_TABLES), ("### 5.2", NYC_TABLES)):
        start = schema.find(heading)
        if start < 0:
            errors.append(f"missing schema subsection {heading}")
            continue
        end = schema.find("### ", start + len(heading))
        block = schema[start: end if end > 0 else None]
        listed = {r[0].strip("`") for r in find_table(block, "Table")[1:]}
        missing = [t for t in required if t not in listed]
        if missing:
            errors.append(f"{heading} missing tables: {missing}")
    return errors


def check_verification(text: str) -> list[str]:
    errors = []
    rows = find_table(section(text, 14), "ID")[1:]
    if not rows:
        return ["verification register empty"]
    for r in rows:
        vid, status, source = r[0], r[2], r[3]
        if status not in {"Verified", "Pending"}:
            errors.append(f"{vid} invalid status {status!r}")
        if status == "Verified" and not source.startswith("https://"):
            errors.append(f"{vid} Verified without an https source")
        if status == "Pending" and source != "—":
            errors.append(f"{vid} Pending must not cite a source")
    return errors


ALL_CHECKS = [
    check_structure, check_metrics, check_applicability, check_questions,
    check_traceability, check_stacks_and_schema, check_verification,
]


def validate(text: str) -> list[str]:
    errors = []
    for check in ALL_CHECKS:
        errors.extend(check(text))
    return errors


# --------------------------------------------------------------------- tests

SPEC_TEXT = SPEC_PATH.read_text(encoding="utf-8") if SPEC_PATH.is_file() else ""


class PositiveTests(unittest.TestCase):
    def test_spec_exists(self):
        self.assertTrue(SPEC_PATH.is_file(), "01-spec/SPEC.md missing")

    def test_structure(self):
        self.assertEqual(check_structure(SPEC_TEXT), [])

    def test_metric_catalog_22_with_balanced_tiers(self):
        self.assertEqual(check_metrics(SPEC_TEXT), [])

    def test_applicability_matrix_complete(self):
        self.assertEqual(check_applicability(SPEC_TEXT), [])

    def test_question_bank_self_service_scope(self):
        self.assertEqual(check_questions(SPEC_TEXT), [])

    def test_hypotheses_claims_dimensions_traceable(self):
        self.assertEqual(check_traceability(SPEC_TEXT), [])

    def test_stacks_and_canonical_schema(self):
        self.assertEqual(check_stacks_and_schema(SPEC_TEXT), [])

    def test_verification_register(self):
        self.assertEqual(check_verification(SPEC_TEXT), [])


class NegativeTests(unittest.TestCase):
    def mutate(self, old: str, new: str, count: int = 1) -> str:
        self.assertIn(old, SPEC_TEXT, f"mutation anchor not found: {old!r}")
        return SPEC_TEXT.replace(old, new, count)

    def test_missing_kpi_definition_rejected(self):
        text = self.mutate("### W-C2 — Days of Supply", "### Days of Supply")
        self.assertIn("no definition heading for W-C2", check_metrics(text))

    def test_unbalanced_tiers_rejected(self):
        text = self.mutate("| N-M2 | NYC | Medium |", "| N-M2 | NYC | Complex |")
        self.assertTrue(any("NYC tier distribution" in e for e in check_metrics(text)))

    def test_dropped_metric_rejected(self):
        row = next(l for l in SPEC_TEXT.splitlines() if l.startswith("| B-N5 | NYC | Base |"))
        text = self.mutate(row + "\n", "")
        self.assertIn("metric catalog has 21 metrics, expected 22", check_metrics(text))

    def test_duplicate_question_rejected(self):
        text = self.mutate("| Q-A10 | AH |", "| Q-A09 | AH |")
        errors = check_questions(text)
        self.assertTrue(any("duplicate question ids" in e for e in errors))

    def test_incomplete_chain_rejected(self):
        row = next(l for l in SPEC_TEXT.splitlines() if l.startswith("| Q-N-C2-D3 |"))
        text = self.mutate(row + "\n", "")
        self.assertTrue(any("incomplete chain for N-C2" in e for e in check_questions(text)))

    def test_unknown_metric_citation_rejected(self):
        text = self.mutate("| Q-A07 | AH | B-N1, B-N2 |", "| Q-A07 | AH | B-N1, B-N9 |")
        self.assertIn("Q-A07 cites unknown metric 'B-N9'", check_questions(text))

    def test_predefined_share_over_limit_rejected(self):
        text = SPEC_TEXT
        for n in range(1, 11):
            text = text.replace(f"| Q-A{n:02d} | AH |", f"| Q-A{n:02d} | P |", 1)
        self.assertTrue(any("predefined share" in e for e in check_questions(text)))

    def test_invalid_applicability_value_rejected(self):
        text = self.mutate("| W-C2 | ✓ | N |", "| W-C2 | Y | N |")
        self.assertTrue(any("invalid applicability values for W-C2" in e for e in check_applicability(text)))

    def test_placeholder_rejected(self):
        text = self.mutate("Initial locked specification.", "Initial locked specification. TBD")
        self.assertIn("placeholder token: 'TBD'", check_structure(text))

    def test_unlocked_state_rejected(self):
        text = self.mutate("| State | LOCKED |", "| State | DRAFT |")
        self.assertIn("header does not declare State LOCKED", check_structure(text))

    def test_verified_without_source_rejected(self):
        row = next(l for l in SPEC_TEXT.splitlines() if l.startswith("| V-09 |"))
        broken = re.sub(r"https://\S+ \|$", "— |", row)
        text = self.mutate(row, broken)
        self.assertIn("V-09 Verified without an https source", check_verification(text))

    def test_missing_canonical_table_rejected(self):
        text = self.mutate("| `bridge_stock_item_group` |", "| `bridge_items` |")
        self.assertTrue(any("missing tables: ['bridge_stock_item_group']" in e
                            for e in check_stacks_and_schema(text)))

    def test_hypothesis_to_unknown_dimension_rejected(self):
        text = self.mutate("| Every stack meets the query performance SLOs at NYC Taxi scale. | E3 |",
                           "| Every stack meets the query performance SLOs at NYC Taxi scale. | E10 |")
        self.assertIn("H3 maps to unknown dimension E10", check_traceability(text))

    def test_stray_pipe_breaks_table_rejected(self):
        text = self.mutate("| B-W4 | WWI | Base | Invoice Count |", "| B-W4 | WWI | Base | Invoice | Count |")
        self.assertTrue(any("row width" in e for e in check_structure(text)))


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if result.wasSuccessful() else 1)
