#!/usr/bin/env python3
"""Structural test suite for repository initialization.

Asserts that the scaffold, STATUS.md, and CLAUDE.md conform to the
initialization specification. Positive tests run against the repository;
negative tests run against generated fixtures in a temporary directory.

Standard library only. Exits non-zero on failure.

    python3 scripts/test_init_structure.py
"""

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_DIRS = [
    "01-spec",
    "02-implementations/ssas-md",
    "02-implementations/powerbi-tabular",
    "02-implementations/bi-layer",
    "02-implementations/databricks-metric-views",
    "03-boundaries-ocm",
    "04-deliverables",
    "scripts",
]

STATUS_HEADER = ["Phase", "Deliverable", "Status", "Last Updated", "Notes"]
VALID_STATUSES = {"Not Started", "In Progress", "Complete", "Blocked"}
REQUIRED_PHASES = {"1", "2", "3"}
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

CLAUDE_REQUIRED_HEADINGS = [
    "## 1. Purpose",
    "## 2. Audience",
    "## 3. Style",
    "## 4. Phase Map",
    "## 5. Databricks Currency",
    "## 6. Code Separation",
    "## 7. Progress Hygiene",
    "## 8. Deliverable Builds",
    "## 9. Testing Protocol",
]
CLAUDE_REQUIRED_PHRASES = [
    "Principal Data Architects",
    "BI Engineering Leads",
    "Analytics Stakeholders",
    "CREATE VIEW ... WITH METRICS LANGUAGE YAML",
    "MEASURE()",
    "YAML spec v1.1",
    "STATUS.md",
]


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def check_structure(root: Path) -> list[str]:
    errors = []
    for rel in REQUIRED_DIRS:
        directory = root / rel
        if not directory.is_dir():
            errors.append(f"missing directory: {rel}")
        elif not (directory / ".gitkeep").is_file():
            errors.append(f"missing .gitkeep: {rel}")
    return errors


def check_status(path: Path) -> list[str]:
    if not path.is_file():
        return [f"missing file: {path.name}"]
    rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("|")]
    if len(rows) < 3:
        return ["STATUS table has no data rows"]

    errors = []
    header = _cells(rows[0])
    if header != STATUS_HEADER:
        errors.append(f"invalid header: {header}")
    if not set(rows[1]) <= set("|-: "):
        errors.append("invalid table separator row")

    phases_seen = set()
    for row in rows[2:]:
        cells = _cells(row)
        if len(cells) != len(STATUS_HEADER):
            errors.append(f"row has {len(cells)} cells, expected {len(STATUS_HEADER)}: {row}")
            continue
        phase, deliverable, status, updated, notes = cells
        if phase not in REQUIRED_PHASES:
            errors.append(f"invalid phase: {phase!r}")
        phases_seen.add(phase)
        if not deliverable:
            errors.append("empty deliverable")
        if status not in VALID_STATUSES:
            errors.append(f"invalid status: {status!r}")
        if not DATE_RE.fullmatch(updated):
            errors.append(f"invalid date: {updated!r}")
        if status in {"Blocked", "Complete"} and not notes:
            errors.append(f"{status} row without notes: {deliverable!r}")

    missing = REQUIRED_PHASES - phases_seen
    if missing:
        errors.append(f"missing phase rows: {sorted(missing)}")
    return errors


def check_claude(path: Path) -> list[str]:
    if not path.is_file():
        return ["missing file: CLAUDE.md"]
    text = path.read_text(encoding="utf-8")
    errors = [f"missing heading: {h}" for h in CLAUDE_REQUIRED_HEADINGS if h not in text]
    errors += [f"missing rule text: {p}" for p in CLAUDE_REQUIRED_PHRASES if p not in text]
    return errors


def render_status(rows: list[list[str]], header: list[str] = STATUS_HEADER) -> str:
    lines = [
        "# STATUS",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


VALID_ROWS = [
    ["1", "Specification", "Not Started", "2026-11-19", "Scaffolded."],
    ["2", "Implementation", "Not Started", "2026-11-19", "Scaffolded."],
    ["3", "Boundaries and OCM", "Not Started", "2026-11-19", "Scaffolded."],
]


class PositiveTests(unittest.TestCase):
    def test_required_directories_exist_with_gitkeep(self):
        self.assertEqual(check_structure(REPO_ROOT), [])

    def test_status_table_conforms_to_spec(self):
        self.assertEqual(check_status(REPO_ROOT / "STATUS.md"), [])

    def test_status_covers_phases_1_to_3(self):
        text = (REPO_ROOT / "STATUS.md").read_text(encoding="utf-8")
        for phase in REQUIRED_PHASES:
            self.assertRegex(text, rf"\n\| {phase} \|", f"no row for phase {phase}")

    def test_claude_rules_present(self):
        self.assertEqual(check_claude(REPO_ROOT / "CLAUDE.md"), [])

    def test_valid_status_fixture_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "STATUS.md"
            path.write_text(render_status(VALID_ROWS), encoding="utf-8")
            self.assertEqual(check_status(path), [])


class NegativeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for rel in REQUIRED_DIRS:
            (self.root / rel).mkdir(parents=True)
            (self.root / rel / ".gitkeep").touch()

    def tearDown(self):
        self._tmp.cleanup()

    def _status_file(self, content: str) -> Path:
        path = self.root / "STATUS.md"
        path.write_text(content, encoding="utf-8")
        return path

    def test_missing_directory_detected(self):
        shutil.rmtree(self.root / "03-boundaries-ocm")
        self.assertIn("missing directory: 03-boundaries-ocm", check_structure(self.root))

    def test_missing_gitkeep_detected(self):
        (self.root / "04-deliverables" / ".gitkeep").unlink()
        self.assertIn("missing .gitkeep: 04-deliverables", check_structure(self.root))

    def test_invalid_status_rejected(self):
        rows = [["1", "Specification", "Done", "2026-11-19", "x"]] + VALID_ROWS[1:]
        errors = check_status(self._status_file(render_status(rows)))
        self.assertIn("invalid status: 'Done'", errors)

    def test_wrong_header_rejected(self):
        header = STATUS_HEADER[:-1] + ["Owner"]
        errors = check_status(self._status_file(render_status(VALID_ROWS, header=header)))
        self.assertTrue(any(e.startswith("invalid header") for e in errors))

    def test_malformed_date_rejected(self):
        rows = [["1", "Specification", "Not Started", "2026/11/19", "x"]] + VALID_ROWS[1:]
        errors = check_status(self._status_file(render_status(rows)))
        self.assertIn("invalid date: '2026/11/19'", errors)

    def test_missing_phase_row_rejected(self):
        errors = check_status(self._status_file(render_status(VALID_ROWS[:2])))
        self.assertIn("missing phase rows: ['3']", errors)

    def test_complete_without_notes_rejected(self):
        rows = [["1", "Specification", "Complete", "2026-11-19", ""]] + VALID_ROWS[1:]
        errors = check_status(self._status_file(render_status(rows)))
        self.assertTrue(any("without notes" in e for e in errors))

    def test_missing_claude_section_detected(self):
        text = "\n".join(
            [h for h in CLAUDE_REQUIRED_HEADINGS if not h.startswith("## 9.")]
            + CLAUDE_REQUIRED_PHRASES
        )
        path = self.root / "CLAUDE.md"
        path.write_text(text, encoding="utf-8")
        self.assertIn("missing heading: ## 9. Testing Protocol", check_claude(path))


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if result.wasSuccessful() else 1)
