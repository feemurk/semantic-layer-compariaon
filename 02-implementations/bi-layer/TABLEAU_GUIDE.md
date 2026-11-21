# S3: Tableau Published Data Sources

Stack S3 of SPEC § 3.1. Three Tableau published data sources run over Databricks serverless SQL (live). Each has an extract variant. The 22 metrics and 70 questions are answered through the VizQL Data Service (VDS), with no model change between questions.

**Documentation baseline**, checked 2026-11-21. `help.tableau.com` is not reachable from the build environment (egress proxy refusal), so the sources split in two:

- **Machine-readable specifications**, read and vendored under [schemas/vendor/](schemas/vendor/) with checksums in [schemas/vendor/NOTICE.md](schemas/vendor/NOTICE.md):
  - the Tableau 2026.3 document schema, `twb_2026.3.0.xsd`, from https://raw.githubusercontent.com/tableau/tableau-document-schemas/main/schemas/2026_3/twb_2026.3.0.xsd;
  - the VizQL Data Service OpenAPI 20263.0, from https://raw.githubusercontent.com/tableau/VizQL-Data-Service/main/VizQLDataServiceOpenAPISchema.json.
- **Behavior claims** taken from the official help pages through search-index excerpts. Each is listed with its URL and as a verification item in § 8:

| Topic | URL |
|---|---|
| Multi-fact relationship models: shared tables; related, unrelated and stitched dimensions | https://help.tableau.com/current/online/en-us/datasource_mfr_multiple_base_tables.htm |
| Relationships aggregate measures before joining (no fan-out) | https://help.tableau.com/current/online/en-us/datasource_datamodel.htm |
| Data source filter scope: pervasive vs logical-table filters; filters limit join culling | https://help.tableau.com/current/pro/desktop/en-us/filtering_datasource.htm |
| RLS with user functions in data source filters; `ISMEMBEROF` takes a literal group name | https://help.tableau.com/current/server/en-us/rls_bestpractices.htm |
| Incremental extract refresh on a date, datetime or increasing integer column | https://help.tableau.com/current/pro/desktop/en-us/extracting_refresh.htm |
| Tableau Agent indexes captions, descriptions (first 150 characters), roles and types | https://help.tableau.com/current/online/en-us/web_author_einstein.htm |
| VDS permissions: API Access capability, plus View and Connect on the published data source | https://help.tableau.com/current/api/vizql-data-service/en-us/docs/vds_configuration.html |
| VDS custom calculations, including LOD expressions | https://help.tableau.com/current/api/vizql-data-service/en-us/docs/vds_create_queries.html |
| REST: create extract, run extract refresh (incremental flag), publish | https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api_ref_extract_and_encryption.htm |

The tableauserverclient 0.42 calls used by the jobs were read from the installed package source: `publish`, `create_extract`, `refresh(incremental=)`, `download`, `update_permissions` and `Permission.Capability.VizqlDataApiAccess`.

## 1. Deliverable map

| Concern | File |
|---|---|
| Single definition of the three data sources: logical tables, relationships, fields, calculations, RLS | [model.py](model.py) |
| VDS query constructors and output typing | [vds.py](vds.py) |
| Builder (renders everything below; `--check` fails on drift) | [build_tableau.py](build_tableau.py) |
| Published data sources (Tableau 2026.3 document format) | [datasources/slc_wwi_sales_orders.tds](datasources/slc_wwi_sales_orders.tds), [datasources/slc_wwi_stock.tds](datasources/slc_wwi_stock.tds), [datasources/slc_nyc_trips.tds](datasources/slc_nyc_trips.tds) |
| Field catalog (caption, local name, type, formula, description) | [datasources/field_catalog.json](datasources/field_catalog.json) |
| E1 reconciliation: VDS queries per oracle grain (22) | [queries/metrics/](queries/metrics/) |
| Question answers: VDS queries plus assembly (70); their definitions | [queries/questions/](queries/questions/), [question_specs.py](question_specs.py) |
| Linter (XSD, OpenAPI, cross-references) | [lint_tableau.py](lint_tableau.py) |
| Validation entry point for `.tds` and the `user:` namespace stand-in | [schemas/tds.xsd](schemas/tds.xsd), [schemas/tableau_user_namespace.xsd](schemas/tableau_user_namespace.xsd) |
| Publish (live and extract variants, connection binding, extract settings, permissions) | [jobs/publish.py](jobs/publish.py) |
| Extract refresh automation (E6) | [jobs/refresh.py](jobs/refresh.py) |
| VDS reconciliation runner (E1, sequential E3 timings) | [jobs/reconcile.py](jobs/reconcile.py) |
| Local VDS stand-in over the oracle fixtures | [tools/vds_emulator.py](tools/vds_emulator.py) |
| CI/CD workflow (E5) | [../../.github/workflows/s3-tableau.yml](../../.github/workflows/s3-tableau.yml) |
| Test suite | [../../scripts/test_tableau.py](../../scripts/test_tableau.py) |
| Pinned dependencies | [requirements.txt](requirements.txt) |

## 2. Model structure

| Published data source | Base tables (facts) | Shared and role tables | Metrics |
|---|---|---|---|
| SLC WWI Sales and Orders | Sales (`fact_sale`), Orders (`fact_order`) | Date, Customer, City, Stock Item and Salesperson are shared by both facts. Delivery Date and Bill-To Customer are sales-only roles; Picker is an orders-only role. Current Stock Item and Stock Group Membership hang off Stock Item. | B-W1–B-W5, W-S1, W-S2, W-M1, W-C1 |
| SLC WWI Stock | Stock Daily (dense item-day snapshot plus trailing 91-day item sales) | Date, Stock Item, Current Stock Item, Stock Group Membership | W-M2, W-C2 |
| SLC NYC Trips | Trips (`fact_trip` plus pickup borough for RLS) | Pickup Calendar, Pickup Zone, Dropoff Zone, Payment Type | B-N1–B-N5, N-S1, N-S2, N-M1, N-M2, N-C1, N-C2 |

- **Logical tables are custom SQL with prefixed aliases** (`sale_`, `ord_`, `d_`, `si_` and so on). The two facts share column names (`total_excluding_tax`, `quantity`), and role-played tables repeat whole schemas. Prefixing gives every field a deterministic, unique local name, so calculations and VDS captions never depend on Tableau's automatic disambiguation.
- **Multi-fact (W-S2).** Sales and Orders are separate base tables related to the same Date table. A single VDS query on `Month Start Date` therefore returns ordered quantity by order date and revenue by invoice date side by side (Q-W-S2-P, Q-W-S2-D1).
- **Role-playing.** A role is its own logical table over the same physical table: Delivery Date, Bill-To Customer, Picker, Pickup/Dropoff Zone. NYC dropoff dates are calculated fields over the trip's own `dropoff_date`.
- **SCD2.** Facts relate to Stock Item on the surrogate key (as-was `Color`). Current Stock Item is the `is_current` version, related to Stock Item on the durable id (as-is `Current Color`, `Current Stock Item`).
- **Many-to-many stock groups (W-C1).** Stock Group Membership (the bridge, with group names) relates to Stock Item on the durable id. Relationships aggregate a measure before joining, so revenue by Stock Group credits each line to every group of its item. The same measure without Stock Group never touches the bridge and is deduplicated. Unlike S4 (B-02), no bridge-expanded copy of the fact is needed.
- **Stock is a separate data source.** In a multi-fact model a dimension unrelated to a measure's table is cross-joined, and the measure repeats across its members. Stock in the sales model would therefore return a replicated days-of-supply per Sales Territory, which SPEC § 6.3 counts as a failure (W-C2 CITY = N). As its own data source it has no City table; Q-W-C2-D4 lists territories from the sales data source with a NULL value and the reason.
- **Agent metadata.** Captions are the glossary display names; descriptions are the glossary descriptions with the synonyms appended ("Also called: …"). Tableau has no field-level synonym property in a data source, and Ask Data synonyms are a separate, legacy feature. 15 of the 69 visible descriptions exceed the 150 characters Tableau Agent indexes. In 5 of them the synonyms start after character 150 and are invisible to the agent (§ 8).

## 3. Calculation semantics

### 3.1 Additive, distinct and ratio measures

| Measure | Formula (local names) |
|---|---|
| Revenue (Excl. Tax), Revenue Including Tax, Gross Profit, Units Sold, Ordered Quantity, trip sums | `SUM([...])` |
| Invoice Count, Distinct OD Pairs | `COUNTD([sale_wwi_invoice_id])`, `COUNTD([trip_od_pair_id])` |
| Gross Margin %, Fare per Mile | `SUM(numerator) / SUM(denominator)` (Tableau returns NULL on division by zero) |
| Backordered Order Lines | `IF COUNT([ord_wwi_backorder_id]) > 0 THEN COUNT(...) END` (blank, not 0, when no line qualifies) |
| Card Tips | `SUM(IF [trip_payment_type] = 1 THEN [trip_tip_amount] END)` (blank for other payment types) |
| Presence: Sales Line Count, Order Line Count, Snapshot Row Count, Trip Count | `COUNT` of the fact key |

### 3.2 Share of parent (W-C1)

`Stock Group Revenue Share = SUM([sale_total_excluding_tax]) / MIN({EXCLUDE [sg_stock_group_name] : SUM([sale_total_excluding_tax])})`. The EXCLUDE denominator is the same context without Stock Group, computed without the bridge, so it is deduplicated. Q-W-C1-D2 uses the measure unchanged as the share of each territory. `MIN` reads the replicated coarser value once per mark.

### 3.3 Semi-additive closing stock and days of supply (W-M2, W-C2, B-05)

Tableau has no semi-additive aggregation. The workaround is a level-of-detail pattern:

- `Period End Snapshot Date = {EXCLUDE <every non-date dimension of the data source> : MAX([stk_snapshot_date])}`: the last snapshot date of the view's period, d* in SPEC § 6.3.
- `Closing Stock On Hand = SUM(IF [stk_snapshot_date] = [Period End Snapshot Date] THEN [stk_quantity_on_hand] END)`.
- `Units Sold Trailing 91 Days` takes the same value at d* of the item-level trailing sum. The Stock Daily custom SQL computes that sum with `SUM(...) OVER (PARTITION BY item ORDER BY snapshot_date ROWS BETWEEN 90 PRECEDING AND CURRENT ROW)`; the snapshot is dense, so 91 rows are 91 days. The window therefore ignores the query's date filter, as the spec requires.
- `Days of Supply = [Closing Stock On Hand] / ([Units Sold Trailing 91 Days] / 91)`, blank when no unit sold.

The EXCLUDE list must name every non-date dimension. An earlier version took the last date within each partition instead. Local emulation showed it was wrong under SCD2: Gray reported its pre-change balance at the 2015 year end, although the oracle has no Gray row on d*. `test_closing_stock_period_end_excludes_every_non_date_dimension` fails if a dimension is added without extending the list. That maintenance coupling is the cost of B-05.

### 3.4 Period-to-date measures (N-C1, N-C2)

The NYC data source has an **As-of Date** parameter (default 2024-12-31):

- **Revenue YTD**: pickup date from `DATETRUNC('year', As-of)` through As-of.
- **Same Time Last Year**: the same window shifted back one year; `DATEADD` maps 29 February to 28 February.
- **YoY %**, **Trips MTD/YTD**, **As-of Day of Month/Year**: derived from the same windows.
- **Pace Index** = `(ZN(Trips MTD) / day of month) / (Trips YTD / day of year)`, with calendar days elapsed.

The anchor is the calendar date, so members without trips on the period's last day get the oracle's value. This is the difference from S4, where the window anchor is the last date with data (B-07). The cost: one VDS query per anchor. Q-N-C1-P and Q-N-C2-P issue 12 queries each; N-C1 and N-C2 reconciliation issue 731 day-anchored queries each. Grouping by the Dropoff Date role does not return NULL (applicability `N`), because the measures filter on the pickup date regardless of the view (§ 8).

### 3.5 Question plans

A question is a set of independent VDS queries plus an assembly in DuckDB over their results ([question_specs.py](question_specs.py) docstring):

- **VDS has no query composition.** A drill path such as "the top territory, then its peak month, then its cities" is answered by querying each grain once and selecting in assembly. The cost is over-fetching: all territories' cities come back, and one is kept.
- **Assembly never reads fact rows.** It selects, joins, pivots one value per cell, ranks, and applies arithmetic to returned values, such as change % or the combined share of ten listed items.
- **Fact-driven rows.** Every fact-driven query carries the fact's presence measure, and assembly keeps rows where it is positive. This reproduces the oracle's inner joins whichever join type the relationship model picks for unmatched members (verification item V-NEW-4).
- **Dimension-driven rows.** Q-W-S2-P (the 2015 month axis), Q-N-S2-D4 (all seven payment codes) and Q-N-C2-D4 (all 30 November days) take their member list from a dimension-only query. Tableau returns a table's full domain, so these match the oracle row for row; S4 cannot express them (B-08).

## 4. Security model

| Data source | Data source filter (boolean calculation = true) | Scope | Effect |
|---|---|---|---|
| SLC WWI Sales and Orders | `NOT ISMEMBEROF('slc_territory_southeast') OR [ci_sales_territory] = 'Southeast'` | Pervasive. The calculation references City, and a filter on another table's field cannot be scoped to one logical table. | City and the tables related to it (Sales, Orders) are restricted to Southeast for the group |
| SLC WWI Stock | `NOT ISMEMBEROF('slc_territory_southeast') AND NOT ISNULL([stk_snapshot_date])` | Logical table (Stock Daily) | No stock rows for the territory group: W-M2 and W-C2 are blank |
| SLC NYC Trips | `NOT ISMEMBEROF('slc_pickup_manhattan') OR [trip_rls_pickup_borough] = 'Manhattan'` | Logical table (Trips) | All trip measures reflect Manhattan pickups; Pickup and Dropoff Zone members stay browsable |

- User functions in data source filters of a *published* data source are the documented pattern, because workbook authors cannot remove them. VDS evaluates them for the querying identity, whether a JWT user or a PAT owner.
- The NYC Trips custom SQL carries the pickup borough, so the RLS filter references only the Trips table and can be scoped. A filter on Pickup Zone would be pervasive and would also narrow the Dropoff Zone member list, which SPEC § 10 keeps unrestricted.
- [jobs/publish.py](jobs/publish.py) grants the two groups View, Connect and API Access (`VizqlDataApiAccess`) on both variants.
- Prerequisites: the Tableau groups `slc_territory_southeast` and `slc_pickup_manhattan` exist (synchronized from the identity provider), and the site permits VDS.
- E8 cannot be scored until the oracle carries restricted expected answers per role, a gap shared with S4.

## 5. Performance behavior

- **Live variant.** Each VDS query compiles to SQL on Databricks serverless SQL. Relationships let Tableau join only the logical tables a query needs. Data source filters limit that join culling, and the pervasive WWI RLS filter always joins City; this is the documented trade-off. Custom SQL relations are emitted as subqueries that the Databricks optimizer inlines. Date filters prune through the platform's liquid clustering (`invoice_date`, `order_date`, `snapshot_date`, `pickup_date`).
- **Extract variant.** "<name> (Extract)" is created server-side and stored in Hyper. Incremental refresh is configured on NYC trips on `trip_pickup_ts`: [jobs/refresh.py](jobs/refresh.py) `incremental` appends rows above the highest key, while the WWI extracts refresh in full. Monthly `rollover` performs a full refresh. The rolling 24-month relative-date extract filter, anchored at `--retention-anchor`, then retires the month that left the window, which an incremental refresh cannot do (E6).
- **Cost drivers specific to Tableau.**
  - The anchor-per-query pattern: a full reconciliation is 1,972 VDS calls for metrics and 122 for questions.
  - Over-fetching in drill plans.
  - The EXCLUDE period-end calculation, which Tableau evaluates as an extra subquery per stock query.
- **Measurement.** [jobs/reconcile.py](jobs/reconcile.py) records per question the cold first run and the median of three warm runs at concurrency 1. Concurrency-10 timings for E3 belong to the common load runner; compare them with the raw-SQL floor in `01-spec/oracle/ORACLE_REPORT.md`.

## 6. Deployment and CI/CD (E5)

The workflow [s3-tableau.yml](../../.github/workflows/s3-tableau.yml) runs on every push touching this stack, the oracle answers or the glossary:

1. `lint`: `build_tableau.py --check`, `lint_tableau.py`, the test suite.
2. `test` (GitHub environment `test`): `publish.py`, then the gate `reconcile.py --select 'Q-*-P' --repeat 1 --fail-on-mismatch`, which checks the 12 `P` questions.
3. `promote` (environment `prod`, `main` only): the same sequence.

Publishing binds the committed `.tds` to the target environment. The Databricks host and SQL warehouse HTTP path are written into the named connection; the Databricks token is embedded as the connection credential. Nothing environment-specific is committed. Rollback is a redeploy of the previous commit.

## 7. Verification

| Layer | Evidence |
|---|---|
| Document format | All three `.tds` validate against the official Tableau 2026.3 XSD, applied to the `<datasource>` content model. Connection internals are `processContents="skip"` in that schema and are not validated. |
| Query format | All 280 metric query shapes (anchored ones also with the parameter applied) and all 122 question queries validate against the official VDS OpenAPI 20263.0 schema. Anchors vary only the parameter value. The Field `oneOf` and Filter discriminator are resolved, and undefined filter properties are rejected. |
| Cross-references | Every calculation, filter, relationship and column-map reference resolves. Every VDS caption, parameter and ad hoc calculation resolves against its data source. `AGG` is applied only to aggregate calculations. |
| Contract | Metric grains equal the oracle's grains. All 70 assemblies produce the oracle's exact header. |
| Plans on fixtures | Through [tools/vds_emulator.py](tools/vds_emulator.py), all 22 metric and 70 question plans reproduce the oracle's answers on the oracle fixtures, so the decomposition and every assembly are right. The emulator restates each calculation in SQL, so this is not evidence of Tableau's evaluation. |
| Tableau execution | Pending a Tableau site connected to the platform workspace (the reconciliation runner and gate are ready). |

## 8. Limitations and boundaries

| ID | Boundary | Mechanism | Workaround and cost |
|---|---|---|---|
| B-05 (confirmed) | No semi-additive aggregation | A measure has no "last value over time" setting | EXCLUDE period-end LOD naming every non-date dimension; a coupling enforced by a test |
| V-NEW boundary A | VDS has no query composition or dependent queries | Each query is independent | Drill paths query each grain and select client-side; over-fetching |
| V-NEW boundary B | Period-to-date measures need an explicit anchor | Calendar-anchored YTD/MTD over arbitrary views needs a parameter or table calculations | As-of Date parameter: exact calendar semantics, one VDS query per anchor (731 per day-grain reconciliation) |
| V-NEW boundary C | Agent metadata | No synonym property in a data source; Tableau Agent indexes 150 characters of a description | Synonyms appended to descriptions; 5 of 69 visible fields have synonyms beyond the indexed prefix |
| V-NEW boundary D | Multi-fact replicates measures over unrelated dimensions | Unrelated dimensions are cross-joined | Stock is a separate published data source; cross-fact stock questions span two data sources |
| — | Dropoff Date applicability (`N`) for N-C1/N-C2 is not enforced | The As-of measures ignore the view's date role | Documented; queries never group period-to-date measures by the dropoff role |

Verification items not settled by documentation available here:

1. Parameters defined inside a published `.tds`, overridable through VDS `query.parameters`. The OpenAPI defines the override; the in-file parameter form follows the workbook format.
2. Databricks connection attributes in the named connection: `class='databricks'`, `server`, `v-http-path`, `authentication='auth-pass'` with user `token`. These are not validated by the XSD.
3. Extract refresh settings `<refresh increment-key= incremental-updates=>` and a relative-date extract filter with `period-anchor`. Both are XSD-valid; their behavior is unverified.
4. The join type a relationship model uses for unmatched dimension members in VDS results. Presence measures make the answers independent of it.
5. Aggregate calculations queried with `function: "AGG"`, and an INCLUDE/EXCLUDE result read through `MIN`.
