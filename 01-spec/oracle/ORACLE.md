# Correctness Oracle — Design and Conventions

Governing scope: `01-spec/SPEC.md` v1.2 § 6 (metric catalog and applicability matrix), § 7 (self-service question bank), § 9 (oracle and reconciliation). Run results, performance statistics and conclusions are in [`ORACLE_REPORT.md`](ORACLE_REPORT.md).

The oracle is the single definition of "correct" for evaluation dimensions E1 (metric correctness), E2 (self-service depth), E7 (AI agent accuracy) and E8 (governance parity). It is plain SQL over the canonical gold tables (SPEC § 5): no metric views, cubes, models or semantic metadata. It is written independently of every stack's model code; stacks are reconciled *to* it, never the reverse.

---

## 1. Inventory

| Path | Contents | Produced by |
|---|---|---|
| `metrics/*.sql` | 22 metric queries: each metric at a fixed set of reconciliation grains | 17 by `build_metric_sql.py`; `W-M2`, `W-C1`, `W-C2`, `N-C1`, `N-C2` hand-written |
| `questions/*.sql` | 70 question queries, one per SPEC § 7 question; the header comment states the interpretation | hand-written |
| `expected/{metrics,questions}/*.csv` | expected answers from the real-data baseline B0 | `run_oracle.py --write-expected` |
| `questions.yaml` | machine-readable question bank: SPEC text, interpretation, SQL path, expected shape | `build_question_bank.py` |
| `fixtures/` | deterministic CSV fixtures with hand-computed answers, plus `schema.json` | `fixtures/build_fixtures.py` |
| `run_oracle.py` | runner: DuckDB, Spark SQL, Databricks; writes, compares, times | — |
| `perf/` | per-query timings per engine (JSON) and the summary table (CSV) | `run_oracle.py --perf`, `summarize_perf.py` |
| `../glossary.yaml` | canonical names, descriptions, synonyms, formats for the 22 metrics and all dimensions | hand-written |
| `../../scripts/test_oracle.py` | test suite (§ 6) | — |

---

## 2. Output contracts

### 2.1 Metric files

Every `metrics/<ID>.sql` returns the same six columns, so one reconciliation harness serves all 22 metrics:

| Column | Type | Meaning |
|---|---|---|
| `grain` | STRING | reconciliation grain, e.g. `year_sales_territory` |
| `measure` | STRING | metric id; multi-output metrics use `<ID>:<component>` (`N-C1:yoy_pct`, `W-C2:units_sold_91d`) |
| `member_1` … `member_3` | STRING | grain members, NULL when unused |
| `value` | BIGINT, DECIMAL or DOUBLE | counts, sums, ratios respectively |

Grains cover the time hierarchy (`total`, `year`, `month`, `day`; WWI also `fiscal_year`) and every **applicable** dimension of the SPEC § 6.5 matrix at its top attribute crossed with calendar year, plus the leaf member where the member set is bounded (stock item, customer). Dimensions marked `N` in the matrix are not emitted. Their expected value is NULL by definition, and the E1 harness asserts that from the matrix.

Member keys use names where names are unique in the source (stock item, customer, employee, state + city) and ids where they are not: TLC zone names repeat across 265 location ids (262 distinct names), so zone grains use `location_id`.

### 2.2 Question files

Each question returns the columns its interpretation names, with a deterministic final `ORDER BY` (ties broken by a stable key, NULLs ordered explicitly) so results compare row by row. Questions that reference "the member with the highest/lowest …" resolve that member inside the SQL, which is how a self-service user or agent must resolve it.

---

## 3. Semantics decisions

| Topic | Rule | Where it matters |
|---|---|---|
| No-data cells | A metric over zero qualifying rows is NULL, never 0 (SPEC § 5.3 rule 7). Filtered measures follow the same rule: `SUM(CASE WHEN … THEN x END)` and `NULLIF(COUNT(x), 0)`. | `N-S2`, `B-W5`, `Q-N-S2-D4`, `Q-A05` |
| Ratios | Always ratio of aggregated sums, cast to DOUBLE, denominator through `NULLIF(…, 0)`. | `W-M1`, `N-M2`, shares, pace |
| Period anchor `t(P)` | Last calendar date of the period that has data, capped at the dataset maximum (WWI 2016-05-31, NYC 2024-12-31); for snapshots `d* = MAX(snapshot_date)` within P. | `W-M2`, `W-C2`, `N-C1`, `N-C2` |
| Trailing window | `[t − 90 days, t]`, both ends inclusive = 91 days, via `t - INTERVAL '90' DAY`. | `W-C2` |
| Same time last year | `[make_date(year(t) − 1, 1, 1), CAST(t - INTERVAL '1' YEAR AS DATE)]`; both engines map 29 Feb to 28 Feb. | `N-C1` |
| Many-to-many | Group grains join the bridge (each line counted once per group); totals are computed without the bridge (deduplicated). | `W-C1`, `W-M2`, `W-C2`, stock group questions |
| SCD Type 2 | As-was = join on the fact surrogate key; as-is = durable key to the `is_current` row. | `Q-W-S1-D4` |
| Non-conformed probes | The oracle returns NULL with a reason, not a fanned-out number. | `Q-W-C2-D4` |

---

## 4. Portable SQL subset

The same files run unmodified on DuckDB 1.4, Apache Spark SQL 4.3 and, by extension, Databricks SQL (Spark SQL dialect). The subset is enforced by the lint in `scripts/test_oracle.py` and proven by the cross-engine test.

| Allowed | Not allowed (and the portable form) |
|---|---|
| `JOIN` / `LEFT JOIN` / `CROSS JOIN`, `NOT EXISTS`, `UNION` / `UNION ALL`, CTEs | `ANTI JOIN` / `SEMI JOIN` (dialect syntax differs) → `NOT EXISTS` |
| `SUM`, `COUNT`, `COUNT(DISTINCT …)`, `MIN`, `MAX`, `ROW_NUMBER() OVER (…)`, `SUM(…) OVER ()` | `QUALIFY` → subquery with `ROW_NUMBER()`; aggregate `FILTER (WHERE …)` → `CASE` inside the aggregate |
| `CAST(… AS DOUBLE / STRING / DATE)`, `NULLIF`, `COALESCE`, `CASE`, `IS NOT DISTINCT FROM`, `\|\|` | `::` casts, `TRY_CAST`, `IIF`, `ISNULL`, `NVL` |
| `make_date`, `year`, `d - INTERVAL 'n' DAY / YEAR` | `DATE_ADD`, `DATEDIFF`, `DATE_TRUNC`, `EXTRACT`, `STRFTIME` (signatures differ) → calendar columns of `dim_date` (`month_start_date`, `day_of_year`, `fiscal_*`) |
| `ORDER BY … NULLS FIRST`, `LIMIT` | engine-default NULL ordering (DuckDB sorts NULLs last, Spark first) |

---

## 5. Running

```bash
# Real-data B0 built by 02-implementations/platform/tools/local_b0.py
python run_oracle.py --engine duckdb --data-root <b0>/warehouse --write-expected expected --repeat 5 --perf perf/duckdb.json
python run_oracle.py --engine spark  --data-root <b0>/warehouse --compare expected --repeat 2 --perf perf/spark.json
# Databricks (job or notebook on serverless; tables resolved in the catalog)
python run_oracle.py --engine databricks --catalog slc --compare expected --perf perf/databricks.json
# Fixtures
python run_oracle.py --engine duckdb-fixtures
```

The runner exits non-zero on any error or mismatch. Tolerances (SPEC § 9.3) are applied by Python type of the actual value: integers exact, DECIMAL within 0.005, DOUBLE within 1e-6. NULL matches only NULL.

---

## 6. Tests

`scripts/test_oracle.py`:

| Layer | Positive | Negative |
|---|---|---|
| Structure | every SPEC metric and question has SQL and an expected answer; generators in sync; headers name their query; multi-row results ordered | lint rejects `QUALIFY`, dialect date functions and unquoted intervals |
| Glossary | metric ids and display names equal SPEC § 6; formats defined | synonym count above the Metric View limit (10) detected |
| Comparator | tolerances accept in-range values | out-of-range money/ratio/count, NULL vs 0, column and row-count mismatches rejected |
| Fixtures | hand-computed answers for every semantic trap | naive average of ratios, summed group revenue, summed daily stock, summed distinct counts rejected |
| Cross-engine | all 92 queries identical on DuckDB and Spark SQL | — |
| Real data (opt-in `SLC_LOCAL_B0`) | committed expected answers reproduce exactly from B0 | — |
