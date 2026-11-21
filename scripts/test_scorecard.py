#!/usr/bin/env python3
"""Phase 3 test suite: projected evaluation scorecard and claims verdicts (SPEC § 8.2, § 13).

Positive: the committed scorecard covers all 36 cells (E1-E9 x S1-S4) and the eight MC claims, obeys every § 8.2 rule
(rating scale, evidence levels, confidence caps, pending items, measurement caps, boundaries, subsets, citations,
confirming observations, claim-dimension mapping), and PROJECTED_SCORECARD.md is in sync with it.
Negative: each § 8.2 rule rejects a scorecard that breaks it.

Requires PyYAML (scripts/requirements-test.txt). Exits non-zero on failure.

    python3 scripts/test_scorecard.py
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCORECARD = REPO / "03-boundaries-ocm" / "scorecard"
sys.path.insert(0, str(SCORECARD))

try:
    import yaml
except ImportError as exc:
    sys.exit(f"missing test dependency ({exc}); pip install -r scripts/requirements-test.txt")

import build_scorecard as bs  # noqa: E402

REGS = bs.spec_registers()
DOC = yaml.safe_load(bs.SOURCE.read_text())


def cell(doc, key):
    stack, dim = key.split("/")
    return next(c for c in doc["cells"] if c["stack"] == stack and c["dimension"] == dim)


class PositiveTests(unittest.TestCase):
    def test_committed_scorecard_is_valid(self):
        self.assertEqual(bs.validate(DOC, REGS), [])

    def test_covers_every_cell_and_claim(self):
        keys = {f"{c['stack']}/{c['dimension']}" for c in DOC["cells"]}
        self.assertEqual(len(DOC["cells"]), 36)
        self.assertEqual(keys, {f"{s}/E{i}" for s in bs.STACKS for i in range(1, 10)})
        self.assertEqual(sorted(v["claim"] for v in DOC["verdicts"]), [f"MC-0{i}" for i in range(1, 9)])

    def test_spec_registers_parse(self):
        self.assertEqual(sorted(REGS["E"]), [f"E{i}" for i in range(1, 10)])
        self.assertEqual(len(REGS["MC"]), 8)
        self.assertIn("B-19", REGS["B"])
        self.assertEqual(REGS["V"]["V-28"], "Pending")
        self.assertEqual(REGS["V"]["V-11"], "Verified")

    def test_markdown_in_sync_and_labeled_projected(self):
        text = bs.render(DOC, REGS)
        self.assertEqual(bs.OUTPUT.read_text(), text)
        self.assertIn("**PROJECTED — not measured.**", text)
        self.assertIn("## 2. Matrix (projected)", text)
        self.assertIn("SPEC v1.5 § 8.2", text)

    def test_counts_quoted_in_findings_match_the_data(self):
        low = sum(1 for c in DOC["cells"] if c["confidence"] == "Low")
        finding = next(f["text"] for f in DOC["findings"] if "low-confidence" in f["text"])
        self.assertIn(f"{low} of the 36 cells", finding)

    def test_no_measured_cells_yet(self):
        # Every cell is a projection until a deployed run exists; a Measured cell would need § 9 evidence.
        self.assertNotIn("Measured", {c["evidence"] for c in DOC["cells"]})


class NegativeTests(unittest.TestCase):
    def assertRejected(self, mutate, pattern):
        doc = copy.deepcopy(DOC)
        mutate(doc)
        problems = bs.validate(doc, REGS)
        self.assertTrue(any(pattern in p for p in problems), problems)

    def test_invalid_rating_and_evidence(self):
        self.assertRejected(lambda d: cell(d, "S1/E1").update(rating="Excellent"), "rating 'Excellent'")
        self.assertRejected(lambda d: cell(d, "S1/E1").update(evidence="Hearsay"), "evidence 'Hearsay'")

    def test_confidence_above_evidence_cap(self):
        self.assertRejected(lambda d: cell(d, "S1/E1").update(confidence="High"), "exceeds the Design inference cap")
        self.assertRejected(lambda d: cell(d, "S2/E6").update(confidence="High"), "exceeds the Documented cap")

    def test_pending_dependency_caps_confidence(self):
        def mutate(d):
            c = cell(d, "S2/E6")
            c["pending"] = ["V-46"]
            c["citations"].append("V-46")
        self.assertRejected(mutate, "capped at Low")

    def test_cited_pending_item_must_be_declared(self):
        self.assertRejected(lambda d: cell(d, "S2/E6")["citations"].append("V-46"), "without listing it as pending")

    def test_verified_item_cannot_be_pending(self):
        self.assertRejected(lambda d: cell(d, "S1/E1").update(pending=["V-11"]), "is not Pending")

    def test_measurement_cells_rules(self):
        self.assertRejected(lambda d: cell(d, "S2/E3").update(rating="Meets"), "unless Measured")
        self.assertRejected(lambda d: cell(d, "S2/E3").pop("expected_range"), "need an expected_range")
        self.assertRejected(lambda d: cell(d, "S1/E1").update(expected_range="fast"), "belongs to E3, E4 and E7 only")

    def test_workaround_needs_a_boundary(self):
        self.assertRejected(lambda d: cell(d, "S1/E3").update(boundaries=[]), "must name its B- entries")
        self.assertRejected(lambda d: cell(d, "S1/E3").update(boundaries=["B-99"]), "is not in SPEC § 8.1")

    def test_partial_needs_a_subset(self):
        self.assertRejected(lambda d: cell(d, "S4/E1").pop("subset"), "must state the subset")

    def test_unknown_evidence_implies_not_assessable(self):
        self.assertRejected(lambda d: cell(d, "S1/E1").update(evidence="Unknown"), "implies Not assessable")

    def test_citations_must_resolve(self):
        self.assertRejected(lambda d: cell(d, "S1/E1")["citations"].append("V-999"), "cites unknown V-999")
        self.assertRejected(lambda d: cell(d, "S1/E1")["citations"].append("docs/missing.md"), "does not exist")
        self.assertRejected(lambda d: cell(d, "S1/E1").update(citations=[]), "no citations")

    def test_rationale_and_confirmation_required(self):
        self.assertRejected(lambda d: cell(d, "S3/E5").update(confirm=""), "confirm is required")
        self.assertRejected(lambda d: cell(d, "S3/E5").update(rationale=" "), "rationale is required")

    def test_missing_and_duplicate_cells(self):
        self.assertRejected(lambda d: d["cells"].remove(cell(d, "S3/E9")), "missing cells: ['S3/E9']")
        self.assertRejected(lambda d: d["cells"].append(copy.deepcopy(cell(d, "S3/E9"))), "duplicate cell")

    def test_verdict_rules(self):
        def verdict(d, claim):
            return next(v for v in d["verdicts"] if v["claim"] == claim)
        self.assertRejected(lambda d: verdict(d, "MC-01").update(verdict="Busted"), "verdict 'Busted'")
        self.assertRejected(lambda d: verdict(d, "MC-01").update(cells=["S1/E7"]), "cites no cell of its dimensions")
        self.assertRejected(lambda d: verdict(d, "MC-01").update(cells=["S9/E4"]), "cites unknown cell")
        self.assertRejected(lambda d: verdict(d, "MC-02").update(confidence="High"), "violates the § 8.2 caps")
        self.assertRejected(lambda d: d["verdicts"].pop(), "verdicts must cover exactly")

    def test_finding_must_cite_existing_cells(self):
        self.assertRejected(lambda d: d["findings"][0].update(cells=["S5/E1"]), "cites unknown cell")


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if result.wasSuccessful() else 1)
