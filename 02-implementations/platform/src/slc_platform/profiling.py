"""Profiling assertions for baseline B0 (SPEC § 13 Phase 2 exit criterion).

Every check is a SQL query that returns zero rows when the assertion holds; any
returned row is a violation. Key checks are generated from slc_platform.schema
so they cannot drift from the informational constraints declared with RELY
(RELY promises the optimizer these hold; a violation would produce wrong
answers in every downstream semantic layer). Domain checks live as .sql files
under src/sql/profiling/.

Queries use two-part names (wwi.fact_sale); the caller sets the catalog first
(USE CATALOG slc on Databricks; spark_catalog locally).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from slc_platform.schema import NYC_TABLES, WWI_TABLES, Table


@dataclass(frozen=True)
class Check:
    check_id: str
    description: str
    sql: str


def _pk_check(schema: str, table: Table) -> Check:
    cols = ", ".join(table.primary_key)
    null_pred = " OR ".join(f"{c} IS NULL" for c in table.primary_key)
    sql = (
        f"SELECT {cols}, n FROM (SELECT {cols}, COUNT(*) AS n FROM {schema}.{table.name} "
        f"GROUP BY {cols}) g WHERE n > 1 OR {null_pred}"
    )
    return Check(
        f"PK-{schema}.{table.name}",
        f"{schema}.{table.name} primary key ({cols}) is unique and not null",
        sql,
    )


def _fk_check(schema: str, table: Table, column: str, parent: str, parent_column: str) -> Check:
    sql = (
        f"SELECT c.{column}, COUNT(*) AS orphan_rows FROM {schema}.{table.name} c "
        f"LEFT ANTI JOIN {schema}.{parent} p ON c.{column} = p.{parent_column} "
        f"WHERE c.{column} IS NOT NULL GROUP BY c.{column}"
    )
    return Check(
        f"FK-{schema}.{table.name}.{column}",
        f"every non-null {schema}.{table.name}.{column} exists in {schema}.{parent}.{parent_column}",
        sql,
    )


def _not_null_check(schema: str, table: Table) -> Check | None:
    required = [name for name, _, nullable in table.columns if not nullable]
    if not required:
        return None
    counts = ", ".join(f"COUNT_IF({c} IS NULL) AS {c}" for c in required)
    any_null = " OR ".join(f"{c} > 0" for c in required)
    return Check(
        f"NN-{schema}.{table.name}",
        f"{schema}.{table.name} NOT NULL columns contain no NULLs",
        f"SELECT * FROM (SELECT {counts} FROM {schema}.{table.name}) n WHERE {any_null}",
    )


def key_checks() -> list[Check]:
    checks: list[Check] = []
    for schema, tables in (("wwi", WWI_TABLES), ("nyctaxi", NYC_TABLES)):
        for table in tables.values():
            not_null = _not_null_check(schema, table)
            if not_null:
                checks.append(not_null)
            if table.primary_key:
                checks.append(_pk_check(schema, table))
            for column, parent, parent_column in table.foreign_keys:
                checks.append(_fk_check(schema, table, column, parent, parent_column))
    return checks


def file_checks(directory: Path) -> list[Check]:
    """Load *.sql checks; the first line must be `-- <CHECK-ID> <description>`."""
    checks = []
    for path in sorted(directory.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        header = text.splitlines()[0]
        if not header.startswith("-- "):
            raise ValueError(f"{path.name}: first line must be '-- <CHECK-ID> <description>'")
        check_id, _, description = header[3:].partition(" ")
        body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
        checks.append(Check(check_id, description.strip(), body.strip().rstrip(";")))
    return checks


def all_checks(directory: Path) -> list[Check]:
    return file_checks(directory) + key_checks()


def run(spark, checks: list[Check], sample: int = 5) -> list[tuple[Check, list]]:
    """Execute checks; return (check, sample_rows) for every violated check."""
    failures = []
    for check in checks:
        rows = spark.sql(check.sql).limit(sample).collect()
        if rows:
            failures.append((check, rows))
    return failures
