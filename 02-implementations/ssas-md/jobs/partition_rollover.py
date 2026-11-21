#!/usr/bin/env python3
"""E6 monthly rollover for the NYC measure groups of S1 (SPEC § 3.1 S1, § 8 E6).

Partition scheme (build_model.py): one MOLAP partition per pickup month ("<Measure Group> YYYY-MM") and one ROLAP
hot partition ("<Measure Group> Hot") covering every pickup date from the first unclosed month on. Closing month M:

1. create the MOLAP partition for M and ProcessFull it;
2. re-slice the hot ROLAP partition to start at M + 1 (Alter; a ROLAP partition holds no data, so no reprocess);
3. delete MOLAP partitions older than the retention window (24 months);
4. clear the cache of the hot partition so ROLAP queries read the new boundary.

The same plan applies to Trips and OD Pairs. Partitions are never merged: retention is monthly, and a merged
partition could not be retired one month at a time. The plan is computed from the current partition list, so a
rerun after a failure resumes without duplicating work.

    python3 jobs/partition_rollover.py --close 2025-01 --current "<partition names, comma-separated>"
        --out rollover.xmla --clear-cache-out clear_cache.xmla   (one command line)
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import build_model  # noqa: E402

NS = build_model.NS
MEASURE_GROUPS = [mg.id for mg in build_model.CUBES["NYC"]["measure_groups"] if mg.partitioned_by_month]
RETENTION_MONTHS = 24
MONTH = re.compile(r"^(?P<mg>.+) (?P<y>\d{4})-(?P<m>\d{2})$")


def add_months(y: int, m: int, n: int) -> tuple[int, int]:
    i = y * 12 + (m - 1) + n
    return i // 12, i % 12 + 1


def plan(close: str, current: list[str], retention: int = RETENTION_MONTHS) -> list[tuple[str, str, str]]:
    """Ordered actions (verb, measure group, partition or boundary) to close month `close` (YYYY-MM)."""
    y, m = (int(x) for x in close.split("-"))
    keep_from = add_months(y, m, -(retention - 1))
    ny, nm = add_months(y, m, 1)
    actions: list[tuple[str, str, str]] = []
    existing = set(current)
    for mg in MEASURE_GROUPS:
        name = f"{mg} {close}"
        if name not in existing:
            actions.append(("create", mg, name))
        actions.append(("process", mg, name))
        actions.append(("reslice_hot", mg, f"{ny:04d}-{nm:02d}-01"))
        for p in sorted(existing):
            match = MONTH.match(p)
            if match and match.group("mg") == mg and (int(match.group("y")), int(match.group("m"))) < keep_from:
                actions.append(("delete", mg, p))
        actions.append(("clear_cache", mg, f"{mg} Hot"))
    return actions


def _sub(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    el = ET.SubElement(parent, f"{{{NS}}}{tag}")
    if text is not None:
        el.text = text
    return el


def _object(parent: ET.Element, mg: str, partition: str | None = None) -> None:
    _sub(parent, "DatabaseID", build_model.DATABASE)
    _sub(parent, "CubeID", "NYC")
    _sub(parent, "MeasureGroupID", mg)
    if partition:
        _sub(parent, "PartitionID", partition)


def _month_bounds(name: str) -> tuple[str, str]:
    match = MONTH.match(name)
    y, m = int(match.group("y")), int(match.group("m"))
    ny, nm = add_months(y, m, 1)
    return f"{y:04d}-{m:02d}-01", f"{ny:04d}-{nm:02d}-01"


def to_xmla(actions: list[tuple[str, str, str]]) -> str:
    """One transactional Batch; processing runs after every structural change in the batch."""
    batch = ET.Element(f"{{{NS}}}Batch", {"Transaction": "true"})
    tables = {mg.id: mg.table for mg in build_model.CUBES["NYC"]["measure_groups"]}
    processes = []
    for verb, mg, target in actions:
        if verb == "create":
            create = _sub(batch, "Create")
            _object(_sub(create, "ParentObject"), mg)
            start, end = _month_bounds(target)
            obj = _sub(create, "ObjectDefinition")
            build_model.partition_element(obj, target, "Molap", build_model.partition_query(tables[mg], start, end))
        elif verb == "reslice_hot":
            alter = ET.SubElement(batch, f"{{{NS}}}Alter", {"ObjectExpansion": "ObjectProperties"})
            _object(_sub(alter, "Object"), mg, f"{mg} Hot")
            obj = _sub(alter, "ObjectDefinition")
            build_model.partition_element(obj, f"{mg} Hot", "Rolap", build_model.partition_query(tables[mg], target, None))
        elif verb == "delete":
            delete = _sub(batch, "Delete")
            _object(_sub(delete, "Object"), mg, target)
        elif verb == "process":
            processes.append((mg, target))
    if processes:
        par = _sub(batch, "Parallel")
        for mg, target in processes:
            proc = _sub(par, "Process")
            _object(_sub(proc, "Object"), mg, target)
            _sub(proc, "Type", "ProcessFull")
    return build_model.xml_text(batch)


def clear_cache_xmla(actions: list[tuple[str, str, str]]) -> str:
    """ClearCache commands for the hot partitions' measure groups, run after the transactional batch commits."""
    batch = ET.Element(f"{{{NS}}}Batch", {"Transaction": "false"})
    for verb, mg, _target in actions:
        if verb == "clear_cache":
            clear = _sub(batch, "ClearCache")
            _object(_sub(clear, "Object"), mg)
    return build_model.xml_text(batch)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--close", required=True, help="month to close, YYYY-MM")
    parser.add_argument("--current", required=True, help="comma-separated partition names of the NYC cube")
    parser.add_argument("--retention", type=int, default=RETENTION_MONTHS)
    parser.add_argument("--out", type=Path, required=True, help="transactional rollover batch (XMLA)")
    parser.add_argument("--clear-cache-out", type=Path, required=True, help="ClearCache batch (XMLA)")
    args = parser.parse_args()
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", args.close):
        raise SystemExit(f"--close must be YYYY-MM, got {args.close!r}")
    actions = plan(args.close, [p for p in args.current.split(",") if p], args.retention)
    args.out.write_text(to_xmla(actions))
    args.clear_cache_out.write_text(clear_cache_xmla(actions))


if __name__ == "__main__":
    main()
