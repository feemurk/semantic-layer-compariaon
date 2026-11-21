# S2 — Power BI / Analysis Services Tabular on Fabric F64

Stack S2 of SPEC § 3.1. There are two semantic models, SLC WWI and SLC NYC, each defined once in TMDL and rendered in three storage-mode variants: Import (NYC as a hybrid table), Direct Lake on OneLake and DirectQuery. They serve the 22 metrics and the 70 questions through DAX, with no model change between questions.

**Documentation baseline.** Every vendor claim below was checked 2026-11-20 against the following sources. The date is the page's "last updated" date.

| Topic | URL | Page date |
|---|---|---|
| TMDL syntax, folder layout, descriptions | https://learn.microsoft.com/en-us/analysis-services/tmdl/tmdl-overview | 2024-08-05 |
| PBIP semantic model folder (`definition.pbism` 4.0+, `definition/`, `.platform`) | https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset | 2026-09-29 |
| Fabric Git integration | https://learn.microsoft.com/en-us/fabric/cicd/git-integration/intro-to-git-integration | 2026-10-25 |
| Calendar-based time intelligence (preview) | https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-time-intelligence | 2025-09-16 |
| Direct Lake (sources, composite models, guardrails, limitations) | https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-overview | 2026-09-18 |
| Direct Lake TMDL (`AzureStorage.DataLake`, parameters) | https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-develop | 2026 |
| Mirrored Azure Databricks Unity Catalog | https://learn.microsoft.com/en-us/fabric/mirroring/azure-databricks | 2026-10-28 |
| Incremental refresh and real-time (hybrid) data | https://learn.microsoft.com/en-us/power-bi/connect-data/incremental-refresh-overview | 2025-09-24 |
| Refresh policy over XMLA/TOM (hybrid mode, compatibility 1565) | https://learn.microsoft.com/en-us/power-bi/connect-data/incremental-refresh-xmla | 2025-10-29 |
| Azure Databricks connector (`Databricks.Catalogs`, ADBC `Implementation = "2.0"`) | https://learn.microsoft.com/en-us/power-query/connectors/databricks-azure | 2026-10-09 |
| executeQueries REST API (limits, service principals and RLS) | https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/execute-queries-in-group | 2026 |
| XMLA with service principals (connection string) | https://learn.microsoft.com/en-us/power-bi/enterprise/service-premium-service-principal | 2026 |
| XMLA endpoint, RLS and service principals | https://learn.microsoft.com/en-us/power-bi/enterprise/service-premium-connect-tools | 2026 |
| Row-level security | https://learn.microsoft.com/en-us/fabric/security/service-admin-row-level-security | 2026-05-13 |
| Copilot AI instructions | https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-prepare-data-ai-instructions | 2026-09-29 |
| Prep data for AI (LSDL storage, Git sync) | https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-prepare-data-ai | 2026-05-30 |
| Verified answers (CI/CD not supported) | https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-prepare-data-ai-verified-answers | 2026-09-10 |
| fabric-cicd 1.4.0 (`FabricWorkspace`, `publish_all_items`, `parameter.yml`) | https://pypi.org/project/fabric-cicd/ (package source read for the API) | 2026-10-07 |

## 1. Deliverable map

| Concern | File |
|---|---|
| Single source of both models (tables, relationships, DAX measures, roles, agent metadata, storage variants) | [build_model.py](build_model.py) |
| Fabric Git items: six semantic models in TMDL | [models/](models/) |
| E1 reconciliation queries (22), generated from the oracle's own grain lists | [queries/metrics/](queries/metrics/), [build_reconciliation_queries.py](build_reconciliation_queries.py) |
| Question queries (70) | [queries/questions/](queries/questions/) |
| TMDL reader, model and query linter, Best Practice Analyzer rules | [lint_model.py](lint_model.py), [deploy/bpa_rules.json](deploy/bpa_rules.json) |
| fabric-cicd deployment and refresh | [deploy/deploy.py](deploy/deploy.py), [deploy/parameter.yml](deploy/parameter.yml), [deploy/requirements.txt](deploy/requirements.txt) |
| Reconciliation runner (REST executeQueries or XMLA) | [deploy/reconcile.py](deploy/reconcile.py), [deploy/XmlaQuery/Program.cs](deploy/XmlaQuery/Program.cs) |
| Copilot AI instructions and verified answers | [copilot/ai_instructions_wwi.md](copilot/ai_instructions_wwi.md), [copilot/ai_instructions_nyc.md](copilot/ai_instructions_nyc.md), [copilot/verified_answers.md](copilot/verified_answers.md) |
| CI/CD workflow (E5) | [../../.github/workflows/s2-powerbi-tabular.yml](../../.github/workflows/s2-powerbi-tabular.yml) |
| Test suite | [../../scripts/test_powerbi_tabular.py](../../scripts/test_powerbi_tabular.py) |

Edit `build_model.py`, not the generated TMDL. `build_model.py --check` and the test suite fail on drift, and the test suite also asserts that the three variants of each dataset share one logical model.

## 2. Model structure

### 2.1 SLC WWI

| Table | Source (`slc.wwi`) | Role |
|---|---|---|
| Sales, Orders, Stock Holding | `fact_sale`, `fact_order`, `fact_stock_holding_daily` | Facts; numeric and key columns hidden, measures exposed |
| Date | `dim_date` | Shared date: invoice date (Sales), order date (Orders), snapshot date (Stock Holding); marked date table; Calendar and Fiscal hierarchies |
| Delivery Date | `dim_date` | Delivery role of Sales; undelivered lines fall into the blank member |
| Customer, Bill-To Customer | `dim_customer` | Two roles of one dimension |
| Salesperson, Picker | `dim_employee` | Two roles; Picker relates to Orders only |
| City | `dim_city` | Geography and Sales Territory hierarchies |
| Stock Item | `dim_stock_item` | SCD2 versions (as-was) |
| Stock Item (Current) | `dim_stock_item` where `is_current` | As-is attributes, one row per durable id |
| Stock Group, Stock Item Group (hidden bridge) | `dim_stock_group`, `bridge_stock_item_group` | Many-to-many stock groups |

### 2.2 SLC NYC

There is one fact, Trips (`fact_trip`). It has role-played Pickup Date, Dropoff Date, Pickup Zone and Dropoff Zone tables, and a Payment Type table. Vendor ID and Pickup Hour stay as visible fact columns.

### 2.3 Design decisions

- **Role-playing dimensions are separate tables, not inactive relationships.** N-M2 needs pickup borough × dropoff borough in the same visual, and `USERELATIONSHIP` activates one role per measure evaluation, so two roles of one table cannot be on two axes. Separate tables also give Copilot unambiguous field names ('Pickup Zone'[Pickup Borough] vs 'Dropoff Zone'[Dropoff Borough]) and avoid duplicating every measure per role. The model has no inactive relationship; the test suite checks this.
- **SCD2.** Facts join `Stock Item` on the surrogate key (as-was). `Stock Item (Current)` filters `Stock Item` on the durable id (one side unique), so as-is attributes such as Current Color slice the same facts (Q-W-S1-D4).
- **Many-to-many stock groups (W-C1).** `Stock Group` filters the bridge, and the bridge filters `Stock Item` through one many-to-many relationship on the durable id, in one direction only. A group selection therefore becomes a set of items: a sale line counts once inside any group selection, totals across groups are deduplicated by construction, and the sum of group values exceeds the total (Q-W-C1-D4 reports the fan-out explicitly). No relationship is bidirectional; the BPA rule `SLC_NO_BIDIRECTIONAL` enforces this.
- **Chasm trap (W-C2).** Stock Holding and Sales share Date and Stock Item. Days of Supply combines the closing balance with `CALCULATE` over Sales on a 91-day window, so no fact is joined to the other.
- **Agent metadata.** Descriptions (TMDL `///`), formats and display folders come from `01-spec/glossary.yaml`, and synonyms go into the linguistic metadata of `cultures/en-US.tmdl`. AI instructions per model are in `copilot/`.

### 2.4 Storage variants

| Variant | Facts | Dimensions | Source expression |
|---|---|---|---|
| Import (WWI) | Import | Import | `Databricks.Catalogs(..., [Implementation = "2.0"])` navigation to `slc.<schema>.<table>` |
| Import (NYC) | Import with a hybrid refresh policy on Trips | Dual | Same; Trips filtered by `RangeStart`/`RangeEnd` on `pickup_ts` |
| Direct Lake | Direct Lake entity partitions | Direct Lake; `Stock Item (Current)` Import | `AzureStorage.DataLake(OneLakeSourceUrl)` on the mirrored Azure Databricks catalog |
| DirectQuery | DirectQuery | Dual | Same connector as Import |

DirectQuery uses catalog navigation, not `Databricks.Query`, which the connector documentation does not support with DirectQuery. Environment-specific values are committed as tokens (`SLC_DATABRICKS_HOST`, `SLC_DATABRICKS_HTTP_PATH`, `SLC_ONELAKE_SOURCE_URL`) and replaced per stage by fabric-cicd from [deploy/parameter.yml](deploy/parameter.yml). Connections are bound per model through `semantic_model_binding`.

## 3. Calculation semantics

| Metric | Measure | Mechanism |
|---|---|---|
| B-W1–B-W4, W-S1 | Revenue Including Tax, Gross Profit, Units Sold, Invoice Count, Revenue (Excl. Tax) | `SUM` / exact `DISTINCTCOUNT`; blank under a Picker filter (matrix N) |
| B-W5, W-S2 | Backordered Order Lines, Ordered Quantity | `COUNT` of non-blank backorder ids (blank when 0); blank under Delivery Date or Bill-To filters |
| W-M1 | Gross Margin % | `DIVIDE([Gross Profit], [Revenue (Excl. Tax)])`: ratio of sums at every grain |
| W-M2 | Closing Stock On Hand | Anchor d* = last snapshot date in the period over all items (`Snapshot Anchor Date`); sum of quantity on that date |
| W-C1 | Stock Group Revenue Share | Revenue / revenue with the stock group filter removed |
| W-C2 | Days of Supply, Units Sold 91D | Closing units × 91 / units sold on invoice dates d*−90 … d*, honoring item and group filters |
| B-N1–B-N5, N-S1 | Trip Count, distance, fare, tips, tolls, Gross Trip Revenue | `COUNTROWS` / `SUM` |
| N-S2 | Card Tips | `CALCULATE(SUM(tip_amount), KEEPFILTERS(payment_type = 1))`; blank for other payment types |
| N-M1 | Distinct OD Pairs | Exact `DISTINCTCOUNT(od_pair_id)` |
| N-M2 | Fare per Mile | `DIVIDE([Fare Amount], [Total Trip Distance])` |
| N-C1 | Revenue YTD, Revenue STLY YTD, Revenue YoY % vs STLY | Anchor t = last calendar day of the pickup period, capped at 2024-12-31; `DATESBETWEEN` from 1 January to t, and from 1 January of the prior year to `EDATE(t, -12)` (29 February → 28 February) |
| N-C2 | Trips MTD, Trips YTD, Days Elapsed in Month/Year, MTD-to-YTD Daily Pace Index | Same anchor; calendar days elapsed as denominators |

Properties that matter for reconciliation:

- **Calendar anchors.** `Pickup Anchor Date` is computed from the date dimension (`MAX` of the dates in context, capped at 2024-12-31), not from fact rows. A month in which a member has no trips still evaluates at the month end, which is the oracle's definition. The S4 metric views anchor on the last row with data instead (S4 boundary B-07).
- **Members from dimensions.** Questions that list every member, such as Q-N-S2-D4 with all seven payment codes, iterate the dimension. This reproduces the oracle where the metric views cannot (S4 boundary B-08).
- **Applicability matrix N cells.** Measures return blank when a non-conformed dimension is cross-filtered (`ISCROSSFILTERED`). Without the guard, an unrelated dimension repeats the grand total on every member. That would be a silent wrong answer, and SPEC § 6.5 counts it as a failure.
- **Time intelligence is explicit DAX.** Calendar-based time intelligence is in preview, cannot be used with composite models (the WWI Direct Lake variant and the NYC hybrid model with Dual dimensions are composite), and is documented to give unexpected results with RLS. The explicit measures implement the SPEC anchor, cap and 29 February rule exactly in every variant.

## 4. Security model

| Role | Model | Table permissions | SPEC § 10 effect |
|---|---|---|---|
| Territory Analyst - Southeast | SLC WWI | `City`: `'City'[Sales Territory] = "Southeast"`; `Stock Holding`: `FALSE ()` | Sales and orders restricted by as-was city; W-M2 and W-C2 blank |
| Manhattan Pickup Analyst | SLC NYC | `Pickup Zone`: `'Pickup Zone'[Pickup Borough] = "Manhattan"` | Trips restricted to Manhattan pickups; Dropoff Zone browsing unrestricted |

- The roles are in Git ([models/](models/) `roles/*.tmdl`); membership (the Entra groups `slc_territory_southeast` and `slc_pickup_manhattan`) is assigned in the service and is recorded as an annotation on each role.
- RLS filters reach the facts through single-direction relationships only, so no bidirectional filter can leak around a role.
- Service principals cannot be RLS role members, and executeQueries refuses service principals on models with RLS. E8 (governance parity) therefore runs `reconcile.py --transport rest --impersonate <user>` with a user token. The CI gate uses XMLA with a service principal that is a workspace member: RLS does not apply to it, which is correct for unrestricted E1.
- Direct Lake on OneLake does not apply SQL analytics endpoint RLS, so semantic model roles are the enforcement point. Whether the Unity Catalog ABAC policies of S4 apply to Direct Lake reads of mirrored tables is not stated in the pages above (pending verification).

## 5. Performance behavior

- **Import (WWI).** Every table is in VertiPaq; a full refresh reloads all tables (WWI is small enough that no refresh policy is needed).
- **Hybrid (NYC Import).** The refresh policy keeps 24 monthly partitions (`rollingWindowGranularity: month`, `rollingWindowPeriods: 24`), refreshes the last 3 days incrementally, and adds a real-time DirectQuery partition after the last refresh (`mode: hybrid`). Dimensions are Dual, as the documentation recommends for tables related to a hybrid table. The service creates, merges and retires partitions on each refresh with `applyRefreshPolicy` (E6). Queries touching only historical months stay in VertiPaq, while queries that include the current day issue SQL to Databricks serverless for that partition (E4).
- **Direct Lake.** Columns are transcoded from the mirrored Delta tables on demand. F64 guardrails: 5,000 files and row groups per table, 1.5 billion rows per table, 25 GB memory. NYC (~80 M trips) is far inside them. Mirroring propagates Unity Catalog changes in seconds to minutes, and automatic updates reframe the model.
- **DirectQuery.** Every query becomes SQL against serverless SQL through ADBC. Dual dimensions resolve slicers from memory. Date windows reach the source as predicates on `pickup_date`, the clustering column of `fact_trip`; the generated SQL is captured in the E3 run, not asserted here.
- **Measurement.** `reconcile.py` records cold (first run) and warm (median of the rest) times per query at concurrency 1. Concurrency 10 belongs to the common E3 load runner. executeQueries limits (100,000 rows or 1,000,000 values, 15 MB, 120 calls per minute per user) bound REST-based runs. The largest reconciliation result, N-C1 at about 5,200 rows × 6 columns, is far inside them.

## 6. Deployment and CI/CD (E5)

The workflow [s2-powerbi-tabular.yml](../../.github/workflows/s2-powerbi-tabular.yml) runs on every push to this stack, the oracle answers or the glossary:

1. **`lint`.** Both generators run in `--check` mode, then `lint_model.py` (TMDL structure, DAX references, BPA rules) and the test suite.
2. **`test`.** `deploy.py --environment test` publishes the six models with fabric-cicd 1.4.0 (environment-variable replacement in `parameter.yml`, connection binding). It then requests an enhanced refresh with `applyRefreshPolicy` per model and waits for it. `reconcile.py --transport xmla --select 'Q-*-P' --fail-on-mismatch` gates on the 12 predefined questions for the Import and Direct Lake models.
3. **`promote`.** On `main` only, the same deployment runs against `prod`.

Authentication uses workload identity federation (`azure/login`) for fabric-cicd and the Power BI REST API. The XMLA gate uses the documented service-principal connection string (`User ID=app:<appId>@<tenantId>;Password=<secret>`), so it needs one stored secret (`XMLA_CLIENT_SECRET`). Rollback is a redeploy of the previous commit.

Manual steps that remain, each counted against E5's "zero manual steps":

- Fabric connections (Azure Databricks, OneLake) are created once per environment and referenced by id.
- RLS role membership is assigned once per environment.
- AI instructions are applied once through Prep data for AI. They then live in the LSDL and travel with the model, but each deployment needs a model refresh to sync them.
- Verified answers are configured in the service, because they are not supported by Git, REST APIs or deployment pipelines ([copilot/verified_answers.md](copilot/verified_answers.md)).

## 7. Verification

| Layer | Evidence | Where |
|---|---|---|
| Documentation | Sources and dates above | Documentation baseline table |
| Static | TMDL of all six models parses and passes structure, relationship-integrity, filter-path-ambiguity, RLS and BPA checks; 92 DAX queries reference only model objects and known functions; output columns equal the oracle headers in order | `scripts/test_powerbi_tabular.py` |
| Deployment logic | parameter.yml covers every token and model; comparator implements SPEC § 5.3 rule 7 and § 9.3 tolerances (positive and negative cases) | same |
| Fabric execution | E1 for 92 queries in all three variants, E3 timings, E8 per role | Pending a Fabric F64 workspace (`STATUS.md`) |

No DAX engine runs locally (Analysis Services is not available on Linux), so no query result is claimed here. The linter checks that queries reference only model objects; it is not an evaluator.

## 8. Limitations and boundaries

| ID | Boundary | Consequence in S2 | Workaround and cost |
|---|---|---|---|
| B-NEW-1 | Direct Lake one-side columns must be unique, and Direct Lake on OneLake cannot use non-materialized views | The gold schema has no current-row table, so `Stock Item (Current)` cannot be a Direct Lake table | Composite model: that table is Import from the Databricks connector, at the cost of one refresh per deployment. Alternatively a materialized current-item table on the platform. |
| B-NEW-2 | Verified answers are not supported by Git integration, REST APIs or deployment pipelines | 12 verified answers are configured by hand per workspace | Manual registry ([copilot/verified_answers.md](copilot/verified_answers.md)); a manual step under E5 |
| B-NEW-3 | executeQueries refuses service principals on models with RLS | CI cannot use the REST API to reconcile RLS models unattended | XMLA runner over ADOMD.NET with a service-principal secret; a .NET 8 build step and one stored secret |
| B-NEW-4 | Calendar-based time intelligence is preview and cannot be used with composite models | The built-in calendar functions are not usable in the Direct Lake and hybrid variants | Explicit DAX windows over the marked date table (§ 3); more DAX to maintain, exact SPEC semantics |
| B-NEW-5 | An unrelated dimension filter does not blank a measure; it repeats the total | SPEC § 6.5 N cells would show wrong values | `ISCROSSFILTERED` guards in every affected measure; each new dimension needs a guard review |

Further limits:

- **Linguistic metadata format.** The JSON layout written to `cultures/en-US.tmdl` (`Entities` → `Definition.Binding` → `Terms`) follows what Power BI Desktop serializes. Microsoft documents that the LSDL holds synonyms and AI instructions, but not its schema (pending verification). AI instructions are applied through the documented dialog for that reason.
- **Role membership and connections** are environment configuration outside Git (§ 6).
- **Restricted expected answers.** Restricted expected answers per role now exist (`01-spec/oracle/expected/restricted`, 24 questions, SPEC § 10); E8 is scored against them once the stack is deployed.
