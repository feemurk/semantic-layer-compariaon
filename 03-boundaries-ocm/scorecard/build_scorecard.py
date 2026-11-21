#!/usr/bin/env python3
"""Build PROJECTED_SCORECARD.md from scorecard.yaml after validating it against SPEC § 8.2.

validate() returns every rule violation; the builder refuses to write an invalid scorecard, and
scripts/test_scorecard.py calls validate() for its positive and negative cases.

    python3 build_scorecard.py            # validate and write PROJECTED_SCORECARD.md
    python3 build_scorecard.py --check    # exit 1 if invalid or if the committed Markdown is stale
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SPEC = REPO / "01-spec" / "SPEC.md"
SOURCE = HERE / "scorecard.yaml"
OUTPUT = HERE / "PROJECTED_SCORECARD.md"

STACKS = {"S1": "SSAS MD", "S2": "Power BI / Tabular", "S3": "Tableau", "S4": "Databricks Metric Views"}
DIMENSIONS = [f"E{i}" for i in range(1, 10)]
RATINGS = ["Meets", "Meets with workaround", "Partial", "Does not meet", "Not assessable"]
LEVELS = {"Measured": "High", "Locally verified": "High", "Documented": "Medium", "Design inference": "Low", "Unknown": None}
CONFIDENCE = ["Low", "Medium", "High"]
MEASUREMENTS = {"E3", "E4", "E7"}
VERDICTS = {"Supported", "Refuted", "Refuted with cost", "Inconclusive"}
CELL_REF = re.compile(r"^(S[1-4])/(E[1-9])$")


def _rows(text: str, first: str) -> list[list[str]]:
    return [[c.strip() for c in l.strip().strip("|").split("|")] for l in text.splitlines()
            if l.startswith(f"| {first}")]


def spec_registers(text: str | None = None) -> dict:
    """V- entries with status, B- entries, E dimensions, MC claims and their dimensions, from the SPEC."""
    text = text if text is not None else SPEC.read_text()
    v = {r[0]: r[2] for r in _rows(text, "V-") if re.fullmatch(r"V-\d+", r[0])}
    b = {r[0]: r[1] for r in _rows(text, "B-") if re.fullmatch(r"B-\d+", r[0])}
    e = {r[0]: {"name": r[1], "criterion": r[3]} for r in _rows(text, "E") if re.fullmatch(r"E\d", r[0])}
    mc = {r[0]: {"claim": r[1], "dims": re.findall(r"E\d", r[2])} for r in _rows(text, "MC-") if re.fullmatch(r"MC-\d\d", r[0])}
    return {"V": v, "B": b, "E": e, "MC": mc}


def _cap_ok(level: str, confidence: str) -> bool:
    cap = LEVELS.get(level)
    return cap is not None and CONFIDENCE.index(confidence) <= CONFIDENCE.index(cap)


def _citation_problems(where: str, citations, regs: dict) -> list[str]:
    problems = []
    if not citations:
        return [f"{where}: no citations"]
    for c in citations:
        if re.fullmatch(r"V-\d+", str(c)):
            if c not in regs["V"]:
                problems.append(f"{where}: cites unknown {c}")
        elif re.fullmatch(r"B-\d+", str(c)):
            if c not in regs["B"]:
                problems.append(f"{where}: cites unknown {c}")
        elif not (REPO / str(c)).exists():
            problems.append(f"{where}: cited path {c} does not exist")
    return problems


def validate(doc, regs: dict | None = None) -> list[str]:
    """Every SPEC § 8.2 rule violation in a parsed scorecard; empty when it conforms."""
    regs = regs or spec_registers()
    if not isinstance(doc, dict):
        return ["scorecard must be a mapping"]
    problems: list[str] = []
    cells = doc.get("cells") or []
    seen: dict[str, dict] = {}
    for cell in cells:
        if not isinstance(cell, dict):
            problems.append(f"cell {cell!r} must be a mapping")
            continue
        key = f"{cell.get('stack')}/{cell.get('dimension')}"
        if not CELL_REF.match(key):
            problems.append(f"{key}: stack must be S1-S4 and dimension E1-E9")
            continue
        if key in seen:
            problems.append(f"{key}: duplicate cell")
        seen[key] = cell
        rating, level, conf = cell.get("rating"), cell.get("evidence"), cell.get("confidence")
        if rating not in RATINGS:
            problems.append(f"{key}: rating {rating!r} is not one of {RATINGS}")
        if level not in LEVELS:
            problems.append(f"{key}: evidence {level!r} is not one of {list(LEVELS)}")
            continue
        if level == "Unknown":
            if rating != "Not assessable":
                problems.append(f"{key}: Unknown evidence implies Not assessable")
        elif conf not in CONFIDENCE:
            problems.append(f"{key}: confidence {conf!r} is not one of {CONFIDENCE}")
        elif not _cap_ok(level, conf):
            problems.append(f"{key}: confidence {conf} exceeds the {level} cap ({LEVELS[level]})")
        pending = cell.get("pending") or []
        for v in pending:
            if regs["V"].get(v) != "Pending":
                problems.append(f"{key}: {v} is listed as pending but is not Pending in SPEC § 14")
        cited_pending = {c for c in cell.get("citations") or [] if regs["V"].get(c) == "Pending"}
        if cited_pending - set(pending):
            problems.append(f"{key}: cites Pending {sorted(cited_pending - set(pending))} without listing it as pending")
        if pending and conf not in (None, "Low"):
            problems.append(f"{key}: depends on Pending {pending}, so confidence is capped at Low")
        if cell.get("dimension") in MEASUREMENTS:
            if not str(cell.get("expected_range") or "").strip():
                problems.append(f"{key}: E3, E4 and E7 cells need an expected_range")
            if conf == "High":
                problems.append(f"{key}: E3, E4 and E7 cells are capped at Medium confidence")
            if rating == "Meets" and level != "Measured":
                problems.append(f"{key}: E3, E4 and E7 cells rate at most Meets with workaround unless Measured")
        elif cell.get("expected_range"):
            problems.append(f"{key}: expected_range belongs to E3, E4 and E7 only")
        boundaries = cell.get("boundaries") or []
        for b in boundaries:
            if b not in regs["B"]:
                problems.append(f"{key}: boundary {b} is not in SPEC § 8.1")
        if rating == "Meets with workaround" and not boundaries:
            problems.append(f"{key}: Meets with workaround must name its B- entries")
        if rating == "Partial" and not str(cell.get("subset") or "").strip():
            problems.append(f"{key}: Partial must state the subset that holds and fails")
        for field in ("rationale", "confirm"):
            if not str(cell.get(field) or "").strip():
                problems.append(f"{key}: {field} is required")
        problems += _citation_problems(key, cell.get("citations"), regs)
    missing = sorted({f"{s}/{e}" for s in STACKS for e in DIMENSIONS} - set(seen))
    if missing:
        problems.append(f"missing cells: {missing}")

    verdicts = doc.get("verdicts") or []
    claims = set()
    for v in verdicts:
        claim = v.get("claim")
        claims.add(claim)
        if claim not in regs["MC"]:
            problems.append(f"{claim}: not a claim of SPEC § 2.1")
            continue
        if v.get("verdict") not in VERDICTS:
            problems.append(f"{claim}: verdict {v.get('verdict')!r} is not one of {sorted(VERDICTS)}")
        level, conf = v.get("evidence"), v.get("confidence")
        if level not in LEVELS or level == "Unknown" or conf not in CONFIDENCE or not _cap_ok(level, conf):
            problems.append(f"{claim}: evidence {level!r} with confidence {conf!r} violates the § 8.2 caps")
        refs = v.get("cells") or []
        if not refs:
            problems.append(f"{claim}: a verdict must cite its E-cells")
        for ref in refs:
            if ref not in seen:
                problems.append(f"{claim}: cites unknown cell {ref}")
        if refs and not {r.split("/")[1] for r in refs} & set(regs["MC"][claim]["dims"]):
            problems.append(f"{claim}: cites no cell of its dimensions {regs['MC'][claim]['dims']}")
        for field in ("rationale", "confirm"):
            if not str(v.get(field) or "").strip():
                problems.append(f"{claim}: {field} is required")
    if claims != set(regs["MC"]):
        problems.append(f"verdicts must cover exactly {sorted(regs['MC'])}, got {sorted(c for c in claims if c)}")

    for i, f in enumerate(doc.get("findings") or []):
        for ref in f.get("cells") or []:
            if ref not in seen:
                problems.append(f"finding {i + 1}: cites unknown cell {ref}")
        if not f.get("cells"):
            problems.append(f"finding {i + 1}: must cite cells")
    return problems


# --------------------------------------------------------------------------- rendering

ABBR = {"Measured": "M", "Locally verified": "LV", "Documented": "Doc", "Design inference": "DI", "Unknown": "U"}


def _flat(text) -> str:
    return " ".join(str(text).split())


def _link(c: str) -> str:
    if re.fullmatch(r"[VB]-\d+", c):
        return c
    rel = Path("../..") / c
    return f"[{Path(c).name}]({rel.as_posix()})"


def render(doc: dict, regs: dict) -> str:
    cells = {f"{c['stack']}/{c['dimension']}": c for c in doc["cells"]}
    out = [
        "# Projected Evaluation Scorecard",
        "",
        f"**PROJECTED — not measured.** SPEC v{doc['spec_version']} § 8.2, as of {doc['as_of']}. Generated by "
        "[build_scorecard.py](build_scorecard.py) from [scorecard.yaml](scorecard.yaml) and validated by "
        "[scripts/test_scorecard.py](../../scripts/test_scorecard.py). Each cell rates a stack against an E-dimension "
        "pass criterion (SPEC § 8) from the documentation, the local evidence in this repository and the design. A "
        "measured run supersedes any cell.",
        "",
        "## 1. Headline findings",
        "",
    ]
    for f in doc.get("findings") or []:
        out.append(f"- {_flat(f['text'])} ({', '.join(f['cells'])})")
    out += ["", "## 2. Matrix (projected)", "",
            "Cell format: rating · evidence level · confidence. Evidence: LV locally verified, Doc documented, "
            "DI design inference, M measured, U unknown.", "",
            "| Dimension | " + " | ".join(f"{s} {n}" for s, n in STACKS.items()) + " |",
            "|---|" + "---|" * len(STACKS)]
    for e in DIMENSIONS:
        row = [f"{e} {regs['E'][e]['name']}"]
        for s in STACKS:
            c = cells[f"{s}/{e}"]
            row.append(f"{c['rating']} · {ABBR[c['evidence']]} · {c.get('confidence') or '—'}")
        out.append("| " + " | ".join(row) + " |")
    ratings = Counter(c["rating"] for c in doc["cells"])
    levels = Counter(c["evidence"] for c in doc["cells"])
    conf = Counter(c.get("confidence") for c in doc["cells"])
    def dist(counter, order):
        return ", ".join(f"{k} {counter[k]}" for k in order if counter[k])
    out += ["", f"- Ratings: {dist(ratings, RATINGS)}.",
            f"- Evidence: {dist(levels, list(LEVELS))}.",
            f"- Confidence: {dist(conf, list(reversed(CONFIDENCE)))}."]
    out += ["", "## 3. Marketing claims (projected verdicts)", "",
            "| Claim | Statement | Verdict | Evidence · confidence | Cells |", "|---|---|---|---|---|"]
    for v in doc["verdicts"]:
        out.append(f"| {v['claim']} | {regs['MC'][v['claim']]['claim']} | **{v['verdict']}** | "
                   f"{ABBR[v['evidence']]} · {v['confidence']} | {', '.join(v['cells'])} |")
    out.append("")
    for v in doc["verdicts"]:
        out += [f"**{v['claim']} — {v['verdict']}.** {_flat(v['rationale'])} *Confirmed or overturned by:* "
                f"{_flat(v['confirm'])}", ""]
    out += ["## 4. Cells", ""]
    for n, e in enumerate(DIMENSIONS, start=1):
        out += [f"### 4.{n} {e} {regs['E'][e]['name']}", "", f"Pass criterion: {regs['E'][e]['criterion']}", ""]
        for s, name in STACKS.items():
            c = cells[f"{s}/{e}"]
            out.append(f"**{s} {name} — {c['rating']}** ({c['evidence']}, {c.get('confidence') or 'no'} confidence)")
            out.append("")
            out.append(f"- Rationale: {_flat(c['rationale'])}")
            if c.get("subset"):
                out.append(f"- Holds and fails: {_flat(c['subset'])}")
            if c.get("expected_range"):
                out.append(f"- Expected range: {_flat(c['expected_range'])}")
            if c.get("boundaries"):
                out.append(f"- Boundaries: {', '.join(c['boundaries'])}")
            if c.get("pending"):
                out.append(f"- Depends on pending verification: {', '.join(c['pending'])}")
            out.append(f"- Sources: {', '.join(_link(x) for x in c['citations'])}")
            out.append(f"- Confirmed or overturned by: {_flat(c['confirm'])}")
            out.append("")
    pend = {}
    for key, c in cells.items():
        for v in c.get("pending") or []:
            pend.setdefault(v, []).append(key)
    out += ["## 5. What a measured run settles first", "",
            "Pending vendor behaviors the projection depends on, with the cells each one moves:", "",
            "| Verification item | Cells |", "|---|---|"]
    for v in sorted(pend, key=lambda x: int(x.split("-")[1])):
        out.append(f"| {v} | {', '.join(sorted(pend[v]))} |")
    weak = sorted(k for k, c in cells.items() if c["evidence"] == "Design inference" and not c.get("pending")
                  and c["dimension"] in MEASUREMENTS)
    out += ["", f"Measurement cells resting on design inference alone: {', '.join(weak) or 'none'}.", ""]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    regs = spec_registers()
    doc = yaml.safe_load(SOURCE.read_text())
    problems = validate(doc, regs)
    for p in problems:
        print(p)
    if problems:
        raise SystemExit(1)
    text = render(doc, regs)
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != text:
            print(f"stale {OUTPUT.name}")
            raise SystemExit(1)
        return
    OUTPUT.write_text(text)


if __name__ == "__main__":
    main()
