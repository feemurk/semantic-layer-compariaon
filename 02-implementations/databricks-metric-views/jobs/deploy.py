"""Deploy the metric views in one of two profiles (SPEC § 10, boundary B-01).

governed     Views without materialization, then row filter functions, tags, ABAC policies and grants. The views are
             replaced first so no materialization exists when the policies attach to the source tables.
accelerated  ABAC policies dropped, then views with materialization, then one synchronous refresh per materialized view.

The two profiles are mutually exclusive on one workspace: the policies govern the shared gold tables of every stack.
"""

from __future__ import annotations

import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
SECURITY = HERE / "security"
VIEW_ORDER = [
    "wwi_sales", "wwi_sales_by_stock_group", "wwi_orders", "wwi_orders_by_stock_group",
    "wwi_stock", "wwi_stock_by_stock_group", "nyc_trips",
]
GOVERNED_SECURITY = ["01_row_filter_functions.sql", "02_tags.sql", "03_policies.sql", "04_grants.sql"]
ACCELERATED_SECURITY = ["90_drop_policies.sql"]


def split_statements(text: str) -> list[str]:
    """Split a SQL script on ';' outside quotes, backticks, '--' comments and $$ blocks; drop comment-only pieces."""
    statements, buf, i, n = [], [], 0, len(text)
    quote = None  # one of ', ", `, $$
    while i < n:
        ch = text[i]
        if quote is None:
            if text.startswith("--", i):
                end = text.find("\n", i)
                end = n if end == -1 else end
                buf.append(text[i:end])
                i = end
                continue
            if text.startswith("$$", i):
                quote = "$$"
                buf.append("$$")
                i += 2
                continue
            if ch in "'\"`":
                quote = ch
            elif ch == ";":
                statements.append("".join(buf))
                buf = []
                i += 1
                continue
            buf.append(ch)
            i += 1
            continue
        if quote == "$$" and text.startswith("$$", i):
            quote = None
            buf.append("$$")
            i += 2
            continue
        if quote != "$$" and ch == "\\" and i + 1 < n:
            buf.append(text[i:i + 2])
            i += 2
            continue
        if ch == quote:
            quote = None
        buf.append(ch)
        i += 1
    if quote is not None:
        raise ValueError(f"unterminated {quote} block")
    statements.append("".join(buf))
    return [s.strip() for s in statements if code_of(s)]


def code_of(stmt: str) -> str:
    return "\n".join(l for l in stmt.splitlines() if not l.strip().startswith("--")).strip()


def materialized_views(sql_dir: Path) -> list[str]:
    return [v for v in VIEW_ORDER if "\nmaterialization:" in (sql_dir / f"{v}.sql").read_text()]


def plan(profile: str) -> list[tuple[str, str]]:
    """(source label, statement) pairs in execution order."""
    steps: list[tuple[str, str]] = []

    def add(path: Path) -> None:
        for stmt in split_statements(path.read_text()):
            steps.append((str(path.relative_to(HERE)), stmt))

    sql_dir = HERE / "sql" / profile
    steps.append(("schema", "CREATE SCHEMA IF NOT EXISTS slc.semantic "
                            "COMMENT 'Unity Catalog metric views of the study (SPEC § 3.1 S4).'"))
    if profile == "governed":
        for view in VIEW_ORDER:
            add(sql_dir / f"{view}.sql")
        for name in GOVERNED_SECURITY:
            add(SECURITY / name)
    else:
        for name in ACCELERATED_SECURITY:
            add(SECURITY / name)
        for view in VIEW_ORDER:
            add(sql_dir / f"{view}.sql")
        for view in materialized_views(sql_dir):
            steps.append(("refresh", f"REFRESH MATERIALIZED VIEW slc.semantic.{view}"))
    return steps


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, choices=["governed", "accelerated"])
    parser.add_argument("--dry-run", action="store_true", help="print the plan without a Spark session")
    args = parser.parse_args()
    steps = plan(args.profile)
    if args.dry_run:
        for label, stmt in steps:
            code = code_of(stmt)
            print(f"[{label}] {code.splitlines()[0] if code.startswith('CREATE OR REPLACE VIEW') else code}")
        return

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    applied = 0
    for label, stmt in steps:
        code = code_of(stmt)
        head = " ".join(code.split())[:110]
        try:
            spark.sql(code)
            applied += 1
            print(f"ok    [{label}] {head}", flush=True)
        except Exception as exc:  # POLICY_NOT_FOUND on DROP POLICY means the policy is already absent
            message = str(exc)
            if code.upper().startswith("DROP POLICY") and "POLICY_NOT_FOUND" in message:
                applied += 1
                print(f"skip  [{label}] {head} (not present)", flush=True)
                continue
            print(f"FAIL  [{label}] {head}\n      {message.splitlines()[0][:400]}", flush=True)
            break
    print(f"{args.profile}: {applied} of {len(steps)} statements applied")
    if applied != len(steps):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
