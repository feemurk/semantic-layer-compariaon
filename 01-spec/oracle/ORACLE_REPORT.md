# Correctness Oracle — Run Report, Analysis and Conclusions

Run date: 2026-11-19. Scope: SPEC v1.2 § 6, § 7, § 9. Design and conventions: [`ORACLE.md`](ORACLE.md). Raw timings: [`perf/duckdb.json`](perf/duckdb.json), [`perf/spark_questions.json`](perf/spark_questions.json), [`perf/spark_metrics.json`](perf/spark_metrics.json); merged table: [`perf/summary.csv`](perf/summary.csv).

---

## 1. Results at a glance

| Item | Result |
|---|---|
| Oracle queries | 92: 22 metric files, 70 question files |
| Expected answers | 70,381 metric rows and 2,063 question rows, committed under `expected/` (3.9 MB CSV) |
| Execution | 92/92 run without error on DuckDB 1.4.1 and Apache Spark SQL 4.3.0 against the real-data baseline B0 |
| Cross-engine reconciliation | 92/92 Spark SQL results identical to DuckDB within SPEC § 9.3 tolerances (0 mismatches) |
| Determinism | two independent DuckDB runs produced byte-identical expected-answer files |
| Fixture answers | every hand-computed fixture answer reproduced; every naive wrong answer rejected (§ 3.2) |
| Test suite | `scripts/test_oracle.py`: 38/38 pass, including the opt-in real-data reproduction of all 92 answers and the 24 restricted answers |
| Specification | 4 question-bank defects found on real data and corrected under change control (SPEC v1.2, § 4.2) |
| Restricted answers (added 2026-11-21) | 24 per-role answers (SPEC § 10) written on DuckDB in 61 s and reproduced identically on Spark SQL in 179 s; see § 9 |
| Not run | the authoritative Databricks serverless run (SPEC § 9.1): no workspace is attached to this environment |

---

## 2. Environment and method

| Component | Value |
|---|---|
| Host | 4 vCPU Intel Xeon @ 2.10 GHz, 15 GB RAM, local SSD; single node, no other workload during measured runs |
| Data | local B0 built by `02-implementations/platform/tools/local_b0.py` from the restored WideWorldImporters (SQL Server 2025) and 24 TLC months; `fact_trip` 76,902,149 rows (2.0 GB Parquet), WWI gold 12 MB |
| DuckDB | 1.4.1, 4 threads, Parquet read through views (no import, no indexes) |
| Spark SQL | Apache Spark 4.3.0 `local[4]`, 8 GB driver, 32 shuffle partitions, JDK 21; Parquet tables over the same files |
| Runs | DuckDB: 5 runs per query (1 first + 4 warm); Spark: questions 2 runs, metric files 1 run |
| Timing | wall clock around `execute` + full result fetch; "warm" = median of runs after the first |

The operating-system file cache was warm for all reported runs. DuckDB keeps no result cache, so its first and warm runs differ little. The very first touch of the 2 GB trip table after the build took 52 s, and that figure is excluded from the tables.

---

## 3. Correctness

### 3.1 Cross-engine reconciliation

The question pass (70 queries × 2 runs, 584 s) and the metric pass (22 queries, 1,749 s) on Spark SQL were compared value by value against the DuckDB answers: integers exactly, DECIMAL within 0.005, DOUBLE within 1e-6, NULL only to NULL. **All 92 matched.** The SQL files are therefore portable across two independent engines with different NULL ordering, decimal arithmetic, date arithmetic and CTE planning. Spark SQL is the dialect base of Databricks SQL, which is the third target (SPEC § 9.1).

### 3.2 Semantic traps proven on fixtures

| Trap | Oracle answer (fixture) | Naive answer rejected |
|---|---|---|
| Ratio of sums (W-M1) | 95 / 350 = 0.271429 | average of line margins 0.25 |
| Many-to-many total (W-C1, Q-W-C1-D4) | deduplicated 350.00; overlap 200.00 | summed groups 550.00 |
| SCD2 as-was vs as-is (Q-W-S1-D4) | Gray 100.00 as-was / NULL as-is; Steel Gray 50.00 / 150.00 | single attribution |
| Semi-additive closing (W-M2) | 2015 = 130 units (last day) | sum of 2015 daily balances |
| Trailing window (W-C2) | 91 days inclusive across a leap February: 2016-03-31 window starts 2016-01-01 | 90- or 92-day windows |
| Filtered measure (N-S2, B-W5) | NULL for non-card types and non-qualifying groups | 0 |
| Distinct count (Q-N-M1-D1) | total 3 | sum of members 4 |
| STLY leap mapping (N-C1) | 2024-02-29 → 2023-02-28; YoY 1.2; 2023 anchors NULL | 2023-03-01 or 0 |
| Calendar-day pace (N-C2) | day_of_year 75 (2024) vs 74 (2023) | days with trips |
| Role-playing dates (Q-N-C1-D4) | pickup-2024 105.00 vs dropoff-2024 145.00 | one date role |

---

## 4. Analysis — what the answers show

### 4.1 Findings on the real data

1. **The many-to-many trap is large, not marginal.** FY2015 revenue summed over stock groups is 86,259,190.95 against a deduplicated total of 53,827,320.95: an overstatement of **60.3%** (32,431,870.00, entirely from items in two or more groups). FY2015 group shares sum to 160.3%. Any stack or agent that totals stock group members instead of re-evaluating the measure without the group filter misstates revenue by 60%.
2. **Distinct-count additivity depends on the dimension.** Distinct OD pairs in 2024 are exactly additive over pickup borough, pickup zone, dropoff borough and dropoff zone. The pair determines both zones, so the members partition it: 50,124 = 50,124. Over payment type the same metric is not additive: the members sum to 127,214, 2.54 times the total. A semantic layer that flags a distinct count "non-additive" everywhere is safe but not informative; the test must probe attributes the key does not determine.
3. **Role-playing dates change totals.** 2024 revenue by Dropoff Date is 2,469.25 lower than by Pickup Date, the net of midnight crossings on 31 December 2023 (in) and 31 December 2024 (out).
4. **SCD2 history in WideWorldImporters is a single attribute.** Only stock item color changes, and only for Gray → Steel Gray. FY2015 as-was Gray revenue is 1,885,586.00, all reported as Steel Gray under current attribution.
5. **Time intelligence on NYC.** 2024 YTD revenue is 1,137,552,670.65 against an STLY of 1,076,266,768.12 (+5.69%). YoY moves from −4.33% at January end to positive from April. The pace index sits below 1 only in July (0.902) and August (0.885), the summer trough, and equals 1 at January end by construction.
6. **Days of Supply is dominated by a source anomaly.** At 2015-12-31, the 9 flow-basis items (SPEC § 5.3 rule 6) hold 103,123,389 of 134,661,497 closing units (76.6%). Company-wide DOS is about 11,000 days; for the 218 reconciled items alone it is 4,436 days. W-C2 remains a valid mechanism test (chasm trap, inclusive window, semi-additive numerator), but its business level is not meaningful on this sample. `balance_basis` must be exposed by every stack so consumers can separate reconciled history.
7. **Unknown members carry real volume.** The largest "bill-to customer" in 2015 is the unknown member (`Unknown`, 23,971,428.29 revenue including tax). The source has three bill-to customers, so `Q-A01` ("top 5") returns three rows.

### 4.2 Question-bank defects found by the oracle (SPEC v1.2)

| Question | As written in v1.1 | Evidence | Correction |
|---|---|---|---|
| Q-N-M1-D1 | distinct OD pairs by pickup borough "less than the sum of boroughs" | sum = total = 50,124 (finding 2) | by payment type: 127,214 vs 50,124 |
| Q-W-M1-D3 | chiller vs non-chiller margin, FY2014 vs FY2015 | chiller items sell only from 2016-01-02 | by selling package |
| Q-W-S2-D3 | chiller vs non-chiller ordered quantity, 2014 vs 2015 | same | by selling package |
| Q-W-M2-D4 | items at zero closing stock on a 2015 month end | minimum month-end balance is 7,196 units: empty answer | 10 lowest month-end balances |

Each correction preserves the question's mechanism (non-additivity probe, slice and compare, boundary probe) and produces a non-degenerate answer. `Q-W-C2-D3` (chiller days of supply) was kept deliberately: chiller items hold stock but have no 2015 sales, so it tests the NULL-denominator rule.

---

## 5. Performance statistics

### 5.1 By workload group (seconds; warm median per query, then median / max / total across queries)

| Group | Queries | DuckDB median / max / total | Spark SQL median / max / total |
|---|---|---|---|
| WWI metric files | 11 | 0.131 / 1.382 / 2.7 | 4.288 / 7.981 / 48.8 |
| NYC metric files | 11 | 10.739 / 15.532 / 108.1 | 178.406 / 206.922 / 1,699.6 |
| WWI questions | 35 | 0.016 / 0.040 / 0.6 | 0.509 / 1.327 / 19.3 |
| NYC questions | 35 | 0.464 / 1.081 / 18.5 | 6.909 / 16.878 / 259.4 |
| Predefined (P) | 12 | 0.066 / 1.002 / 2.9 | 0.839 / 8.766 / 35.3 |
| Diagnostic (D1–D4) | 48 | 0.097 / 1.081 / 13.8 | 1.273 / 16.878 / 205.7 |
| Ad hoc (AH) | 10 | 0.143 / 0.713 / 2.4 | 3.340 / 8.427 / 37.7 |
| All 92 | 92 | 0.183 / 15.532 / 130.0 | 4.208 / 206.922 / 2,027.1 |

### 5.2 Question latency against the SPEC E3 targets

E3 targets apply to semantic layers at concurrency 10. These single-session figures are the raw-SQL reference floor, not an E3 result.

| Engine | p50 | p95 | max | ≤ 2 s | ≤ 5 s | First-run p50 |
|---|---|---|---|---|---|---|
| DuckDB | 0.071 s | 0.983 s | 1.081 s | 70/70 | 70/70 | 0.073 s |
| Spark SQL (local) | 1.219 s | 12.951 s | 16.878 s | 39/70 | 42/70 | 1.439 s |

### 5.3 Most expensive queries

| Query | Shape | DuckDB warm | Spark warm |
|---|---|---|---|
| N-M1 | distinct count at 14 grains over 76.9M trips | 15.53 s | 162.6 s |
| N-M2, N-S2, N-S1, B-N2…B-N5 | additive / ratio at 14 grains | 10.5–11.8 s | 166.8–206.9 s |
| N-C1, N-C2 | YTD/STLY and pace at 4 periods × 5 member dimensions (5,226 rows) | 2.71 s, 2.63 s | 29.3 s, 24.5 s |
| Q-N-S2-D2 | card tips, pickup × dropoff borough | 1.08 s | 8.66 s |
| Q-N-S1-D2 | dynamic top month, then hour × payment type | 0.47 s | 16.88 s |

---

## 6. Analysis — performance

1. **Raw SQL on the canonical star schema already meets the E3 latency targets on one 4-core node.** DuckDB answers all 70 questions, including the 58 diagnostic and ad hoc questions, in at most 1.081 s against 76.9M trips, with no aggregates, indexes or caching. This is the floor every semantic layer is measured against in E3. A stack slower than raw SQL on the same physical data must justify itself on E2, E5–E8 rather than speed.
2. **Engine choice dominates SQL choice.** The same SQL runs a median 22.9× slower on Spark local mode (90th percentile 40.7×): 39/70 questions under 2 s, max 16.9 s. Local mode runs the JVM engine without Photon, caching or serverless scale-out, so these figures say nothing about Databricks serverless SQL. They show that at this data size, execution-engine efficiency, not query formulation, decides interactive latency. That bears directly on MC-03 ("cubes do not scale"): what matters is the engine and the physical design, not the label.
3. **Aggregate-first beats scan-per-grain.** The 14-grain additive metric files re-scan the trip fact once per grain; neither engine reuses the CTE scan across `UNION ALL` branches. That costs 10.5–15.5 s on DuckDB and 160–207 s on Spark. `N-C1` and `N-C2` aggregate to daily rows once and evaluate every anchor from that small table. They produce more output (5,226 rows) and harder logic in about 2.7 s: 3.9–4.5× faster than the additive files on DuckDB and 5.7–8.4× faster on Spark. Pre-aggregation (MOLAP aggregations, VertiPaq, Metric View materialization) is therefore the mechanism to examine in E3 and E6, and a fair comparison must include it.
4. **Distinct counts are the most expensive mechanism** (N-M1, 15.5 s, the slowest file). SSAS distinct-count measure groups, VertiPaq dictionary encoding and Metric View materialization of `COUNT(DISTINCT …)` are the specific capabilities to test (B-06).
5. **The cost sits in the NYC diagnostic tail.** WWI questions finish in ≤ 40 ms. NYC questions account for 18.5 s of 19.1 s total question time on DuckDB, concentrated in the multi-dimension diagnostics (D2, D4) that SPEC § 7 makes the majority of the bank. Optimizing only the 12 predefined questions would miss most of the work.
6. **Dynamic-member questions cost a second scan.** "The month with the highest revenue, then …" (`Q-N-S1-D1`, `D2`) scans the fact twice. On DuckDB that is negligible (0.4 s); on Spark it is 16 s. Agents and self-service tools resolve such questions in two steps, so E7 latency will show the same doubling.

---

## 7. Conclusions

1. **The oracle is complete and trustworthy for Phase 2 reconciliation.** All 22 metrics and 70 questions have deterministic SQL and committed answers, proven on two engines and against hand-computed fixtures. Stacks will be reconciled to `expected/`.
2. **The question bank is stronger after running against real data.** Four questions that would have produced degenerate or factually wrong expectations were corrected (SPEC v1.2) before any stack was built against them.
3. **E3 has a quantified floor.** Raw star-schema SQL on a single 4-core node answers every question in at most 1.1 s. Semantic-layer latency claims in this study are judged against that number.
4. **Three data caveats travel with the answers:** Days of Supply is dominated by 9 irreconcilable items (expose `balance_basis`); the unknown bill-to member carries the largest bill-to volume; chiller items exist only from January 2016.
5. **Remaining step:** the authoritative run on Databricks serverless SQL (`run_oracle.py --engine databricks --catalog slc --compare expected`) once a workspace is available. Any difference from the committed answers is a platform or dialect defect to resolve before stack reconciliation starts.

---

## 8. Reproduction

```bash
pip install -r scripts/requirements-test.txt
B0=<dir built by 02-implementations/platform/tools/local_b0.py>
python 01-spec/oracle/run_oracle.py --engine duckdb --data-root $B0/warehouse --compare 01-spec/oracle/expected --repeat 5 --perf 01-spec/oracle/perf/duckdb.json
python 01-spec/oracle/run_oracle.py --engine spark --data-root $B0/warehouse --select 'Q-*' --compare 01-spec/oracle/expected --repeat 2 --perf 01-spec/oracle/perf/spark_questions.json
python 01-spec/oracle/run_oracle.py --engine spark --data-root $B0/warehouse --select '[BWN]-*' --compare 01-spec/oracle/expected --perf 01-spec/oracle/perf/spark_metrics.json
python 01-spec/oracle/summarize_perf.py 01-spec/oracle/perf/duckdb.json 01-spec/oracle/perf/spark_questions.json 01-spec/oracle/perf/spark_metrics.json
SLC_LOCAL_B0=$B0 python scripts/test_oracle.py
```

---

## 9. Restricted answers (SPEC § 10), 2026-11-21

| Item | Result |
|---|---|
| Scope | 24 questions: the 12 `P` and `D1` questions of WWI as Territory Analyst – Southeast, and the 12 of NYC as Manhattan Pickup Analyst |
| Method | Row filters on the fact tables beneath the unchanged question SQL ([`restricted.py`](restricted.py), ORACLE.md § 5.1) |
| Execution | 24/24 written on DuckDB 1.4.1 (61 s); 24/24 identical on Spark SQL 4.3.0 (179 s); raw timings in [`perf/restricted_duckdb.json`](perf/restricted_duckdb.json), [`perf/restricted_spark.json`](perf/restricted_spark.json) |
| Subset property | Restricted Q-W-S1-P equals the Southeast rows of the unrestricted answer, and restricted Q-N-S1-P equals the Manhattan rows, value for value |
| Unchanged answers | 3 of 24, all legitimate: Southeast is the top FY2015 territory regardless (Q-W-S1-D1), and Q-N-S1-D1 and Q-N-M2-D1 already ask about Manhattan pickups |
| Inventory denial | W-M2 and W-C2 answers carry no values for the territory role: no rows for grouped questions, a NULL total for Q-W-M2-D1 |

These answers make E8 scoreable. The S4 emulator already reproduces them for the 15 role questions that use no window measure, by applying the same filters to the metric views' source tables (`scripts/test_databricks_metric_views.py`).

```bash
python 01-spec/oracle/restricted.py --engine duckdb --data-root $B0/warehouse --write-expected 01-spec/oracle/expected/restricted --perf 01-spec/oracle/perf/restricted_duckdb.json
python 01-spec/oracle/restricted.py --engine spark --data-root $B0/warehouse --compare 01-spec/oracle/expected/restricted --perf 01-spec/oracle/perf/restricted_spark.json
```
