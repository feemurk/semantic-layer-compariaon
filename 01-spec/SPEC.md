# SPEC — Enterprise Semantic Layer Comparative Architecture Study

| Field | Value |
|---|---|
| Version | 1.3 |
| State | LOCKED |
| Locked on | 2026-11-19 (v1.0); amended 2026-11-19 (v1.1, v1.2) and 2026-11-20 (v1.3), § 16 |
| Governs | Phases 1–3 and `04-deliverables/` |
| Change control | § 16. No scope change without a version bump and a changelog entry. |

---

## 1. Thesis and Objectives

### 1.1 Thesis

Marketing for modern semantic layers implies that CI/CD, automated partition management, high-frequency data availability, complex analytical queries at good performance, and AI-agent access require a modern stack. This study tests that implication. A legacy semantic stack (SSAS Multidimensional), engineered with current practices, is evaluated against Power BI / Analysis Services Tabular, Tableau, and Databricks Unity Catalog Metric Views on identical data, identical metric definitions, and an identical self-service question bank.

### 1.2 Hypotheses

Each hypothesis is evaluated for every stack and reported as `Supported`, `Partially Supported`, or `Refuted`, with evidence.

| ID | Hypothesis | Evaluation dimension |
|---|---|---|
| H1 | Every stack returns oracle-identical results for all 22 metrics across the dimensional applicability matrix. | E1 |
| H2 | Every stack answers the full self-service question bank, including diagnostic follow-ups, without model changes between questions. | E2 |
| H3 | Every stack meets the query performance SLOs at NYC Taxi scale. | E3 |
| H4 | Every stack delivers new data to query within the freshness SLO. | E4 |
| H5 | Every stack is built, tested, and deployed through a fully automated CI/CD pipeline with zero manual steps. | E5 |
| H6 | Every stack runs partition and refresh lifecycle management unattended. | E6 |
| H7 | AI agents answer the question bank through each stack's semantic layer, including SSAS Multidimensional, with comparable accuracy. | E7 |
| H8 | The row-level security scenario is enforced identically in every stack, including for agent access. | E8 |

### 1.3 Non-goals

- Skill transfer between personas. Training content exists only to demonstrate capability (§ 2).
- Licensing, pricing, or TCO comparison.
- Production high availability and disaster recovery design.
- Yellowfin, NYC Green Taxi, and For-Hire Vehicle data.
- Tableau Semantics (Tableau Next): forward-looking appendix only, not evaluated.

---

## 2. Audience and OCM Framing

**Audience:** Principal Data Architects, BI Engineering Leads, Analytics Stakeholders.

**OCM purpose:** educate on what each technology can accomplish when engineered well. The organizational change targeted is a decision-quality change: platform choices made on demonstrated capability rather than marketing claims. Training and workshop material is a means to that end, used to make the evidence reproducible by the audience.

### 2.1 Marketing Claims Register

Phase 3 assigns each claim a verdict (`Supported`, `Partially Supported`, `Refuted`) backed by evidence from the evaluation dimensions.

| ID | Claim under test | Evidence source |
|---|---|---|
| MC-01 | OLAP cubes cannot deliver near-real-time data. | E4 |
| MC-02 | Legacy semantic models cannot be managed with modern CI/CD. | E5 |
| MC-03 | Cubes do not scale to high-volume, granular data. | E3, E6 |
| MC-04 | Complex time intelligence and semi-additive logic require a proprietary calculation engine. | E1 |
| MC-05 | AI agents require a modern, SQL-native semantic layer to answer business questions accurately. | E7 |
| MC-06 | Self-service exploration beyond predefined reports requires a lakehouse-native semantic layer. | E2 |
| MC-07 | Only a lakehouse catalog can enforce governance consistently across BI and AI consumers. | E8 |
| MC-08 | Semantic-layer-as-code is unique to YAML-defined metric layers. | E5 |

---

## 3. Stacks in Scope

All stacks use the latest documented release and capabilities as of the lock date. Implementation constraints (licensing, preview access) are out of scope; a documented capability is in scope.

| ID | Stack | Version / platform | Semantic artifacts | Query language | Folder |
|---|---|---|---|---|---|
| S1 | SSAS Multidimensional | SQL Server 2025 Analysis Services, Multidimensional mode, Enterprise Developer edition | UDM: data source view, dimensions, cubes, measure groups, MDX calculation script; MOLAP + ROLAP partitions | MDX | `02-implementations/ssas-md/` |
| S2 | Power BI / Analysis Services Tabular | Microsoft Fabric, F64 capacity; semantic model in TMDL | Tables, relationships, DAX measures, calendars, calculation groups, incremental refresh policies; Import, Direct Lake, DirectQuery variants | DAX | `02-implementations/powerbi-tabular/` |
| S3 | Tableau | Tableau Cloud, current release | Published Data Sources: logical layer relationships (including multi-fact), calculated fields, LOD expressions; live and extract variants | VizQL / VizQL Data Service | `02-implementations/bi-layer/` |
| S4 | Databricks Unity Catalog Metric Views | Serverless SQL warehouse, current channel; Metric View YAML specification 1.1 | Metric views (fields, measures, window measures, composability, joins incl. snowflake and `one_to_many`, LOD, materialization, agent metadata), relationships between metric views (Beta); adjacent Lakeflow and Databricks SQL patterns | SQL with `MEASURE()` | `02-implementations/databricks-metric-views/` |

### 3.1 Required components per stack

| Capability | S1 SSAS MD | S2 Power BI / Tabular | S3 Tableau | S4 Databricks Metric Views |
|---|---|---|---|---|
| Source connectivity to the shared platform (§ 4) | Databricks SQL serverless via ODBC data source | Azure Databricks connector, ADBC driver (Import, DirectQuery); Direct Lake on OneLake over the mirrored Unity Catalog | Databricks connector to serverless SQL (live); Tableau extract (extract variant) | Native |
| Model-as-code format in Git | MD project XML (`.ds`, `.dsv`, `.dim`, `.cube`) and MDX script (`.mdx`) | TMDL (`.tmdl`) and DAX (`.dax`) | Data source XML (`.tds`) | YAML in `CREATE VIEW ... WITH METRICS LANGUAGE YAML` DDL (`.sql`, `.yaml`) |
| CI/CD | GitHub Actions on a self-hosted Windows runner: build, XMLA deploy, process, MDX reconciliation, promote | GitHub Actions: Fabric Git integration and `fabric-cicd`, Best Practice Analyzer rules, DAX reconciliation via `executeQueries`, promote | GitHub Actions: Tableau REST API (`tableauserverclient`) publish, VizQL Data Service reconciliation, promote | GitHub Actions: Databricks Asset Bundles deploy, SQL reconciliation, promote |
| Partition and refresh automation | Scripted (AMO/XMLA) monthly MOLAP partition create, process, merge, retire; daily ROLAP hot partition | Incremental refresh policy (monthly partitions, 24-month window) with real-time DirectQuery partition; Direct Lake framing | Incremental extract refresh on `pickup_ts`; live variant needs none | Liquid clustering on the source; metric view materialization with `refresh_policy` and `schedule` |
| Freshness pattern (§ 9.4) | ROLAP current-day partition over the shared platform plus automated MOLAP roll | Hybrid table real-time partition; Direct Lake | Live connection; extract variant measured separately | Live query on Delta; materialization measured separately |
| Row-level security (§ 10) | Role-based dimension data security on cube dimensions | RLS roles | User functions in data source filters | Unity Catalog row filters / ABAC policies |
| Native AI assistant (§ 11) | None exists; recorded as a finding | Copilot in Power BI | Tableau Agent | Genie Agent over metric views |
| Common agent harness (§ 11) | Repo-built MCP server: discovery rowsets + MDX over XMLA | Repo-built MCP server: DMV discovery + DAX over XMLA | Repo-built MCP server: VizQL Data Service metadata + query | Repo-built MCP server: Unity Catalog metadata + SQL Statement Execution API |
| Agent metadata | Descriptions and translations from `01-spec/glossary.yaml` | Descriptions, synonyms, AI instructions from `01-spec/glossary.yaml` | Field descriptions and synonyms from `01-spec/glossary.yaml` | `comment`, `display_name`, `synonyms`, `format` from `01-spec/glossary.yaml` |

---

## 4. Shared Data Platform

- **Single physical source:** Databricks serverless SQL on Unity Catalog. Every stack reads the same Delta tables and the same columns defined in § 5. No stack keeps its own copy of the source data, other than its own internal storage (MOLAP, VertiPaq, extracts, materializations), which is filled from these tables.
- **Catalog layout:** catalog `slc`, schemas `slc.wwi` and `slc.nyctaxi` (gold, canonical), `slc.raw_wwi` and `slc.raw_nyctaxi` (bronze).
- **Ingestion:**
  - WideWorldImporters: full snapshot of `WideWorldImportersDW` tables listed in § 5.1 (plus `[Dimension].[Date]` for the § 5.4 profiling test), and `Warehouse.StockGroups` and `Warehouse.StockItemStockGroups` from the `WideWorldImporters` OLTP database. Ingested with a Lakeflow Connect SQL Server managed ingestion pipeline (change tracking) from a restored copy of the official sample on SQL Server 2025. Source preparation drops the clustered columnstore index on the four ingested `WideWorldImportersDW` fact tables before enabling change tracking, because SQL Server rejects change tracking and CDC on clustered columnstore tables (V-21); rows and primary keys are unchanged.
  - NYC Taxi: TLC Yellow Taxi monthly Parquet files and the taxi zone lookup. Each downloaded file is read with its own schema and normalized to one landing schema before Auto Loader ingests it into bronze, because column types and name case drift between months and Spark cannot read an INT64 Parquet column as DOUBLE (V-19). Lakeflow pipelines transform bronze into gold.
- **Physical design:** primary and foreign key constraints declared with `RELY`; liquid clustering on `fact_trip (pickup_date)` and `fact_sale (invoice_date)`; all money columns `DECIMAL`. Each dataset's dimensions are published by a pipeline that runs before its facts pipeline, so every foreign key references an existing parent.
- **Deployment:** the platform is a Declarative Automation Bundle (formerly Databricks Asset Bundles) under `02-implementations/platform/`.
- **Baseline snapshot B0:** the complete gold build defined in § 5. All correctness scoring (E1, E2, E7, E8) runs on B0.
- **Network hosts required in Phase 2:** the TLC download CDN and the Microsoft sample download location for WideWorldImporters.

---

## 5. Canonical Schema

Names are snake_case. Each gold table lists its source column mapping. Columns not listed are excluded.

### 5.1 `slc.wwi` — WideWorldImporters

Source date range: 2013-01-01 to 2016-05-31.

| Table | Columns (type) ← source |
|---|---|
| `fact_sale` | `sale_key` BIGINT ← `[Fact].[Sale].[Sale Key]` · `invoice_date` DATE ← `[Invoice Date Key]` · `delivery_date` DATE NULL ← `[Delivery Date Key]` · `city_key` INT ← `[City Key]` · `customer_key` INT ← `[Customer Key]` · `bill_to_customer_key` INT ← `[Bill To Customer Key]` · `stock_item_key` INT ← `[Stock Item Key]` · `salesperson_key` INT ← `[Salesperson Key]` · `wwi_invoice_id` INT ← `[WWI Invoice ID]` · `quantity` INT ← `[Quantity]` · `unit_price` DECIMAL(18,2) ← `[Unit Price]` · `total_excluding_tax` DECIMAL(18,2) ← `[Total Excluding Tax]` · `tax_amount` DECIMAL(18,2) ← `[Tax Amount]` · `profit` DECIMAL(18,2) ← `[Profit]` · `total_including_tax` DECIMAL(18,2) ← `[Total Including Tax]` |
| `fact_order` | `order_key` BIGINT ← `[Fact].[Order].[Order Key]` · `order_date` DATE ← `[Order Date Key]` · `city_key` INT · `customer_key` INT · `stock_item_key` INT · `salesperson_key` INT · `picker_key` INT NULL ← `[Picker Key]` · `wwi_order_id` INT · `wwi_backorder_id` INT NULL · `quantity` INT · `total_excluding_tax` DECIMAL(18,2) |
| `fact_stock_movement` | `movement_key` BIGINT ← `[Fact].[Movement].[Movement Key]` · `movement_date` DATE ← `[Date Key]` · `stock_item_key` INT · `transaction_type_key` INT · `quantity` INT (signed) |
| `stock_holding_current` | `stock_item_key` INT ← `[Fact].[Stock Holding].[Stock Item Key]` · `quantity_on_hand` INT ← `[Quantity On Hand]`. Build input only; not exposed to any semantic layer. |
| `fact_stock_holding_daily` | Derived (§ 5.3). `snapshot_date` DATE · `wwi_stock_item_id` INT · `stock_item_key` INT · `quantity_on_hand` INT · `balance_basis` STRING |
| `dim_stock_item` | `stock_item_key` INT ← `[Dimension].[Stock Item].[Stock Item Key]` · `wwi_stock_item_id` INT · `stock_item` STRING · `brand` STRING · `color` STRING · `size` STRING · `selling_package` STRING · `is_chiller_stock` BOOLEAN · `unit_price` DECIMAL(18,2) · `valid_from` TIMESTAMP · `valid_to` TIMESTAMP · `is_current` BOOLEAN (derived) |
| `dim_stock_group` | `stock_group_id` INT ← `[Warehouse].[StockGroups].[StockGroupID]` · `stock_group_name` STRING ← `[StockGroupName]` |
| `bridge_stock_item_group` | `wwi_stock_item_id` INT ← `[Warehouse].[StockItemStockGroups].[StockItemID]` · `stock_group_id` INT ← `[StockGroupID]` |
| `dim_customer` | `customer_key` INT ← `[Dimension].[Customer].[Customer Key]` · `wwi_customer_id` INT · `customer` STRING · `bill_to_customer` STRING · `category` STRING · `buying_group` STRING · `valid_from` TIMESTAMP · `valid_to` TIMESTAMP · `is_current` BOOLEAN. Role-played as Customer and Bill-To Customer. |
| `dim_city` | `city_key` INT ← `[Dimension].[City].[City Key]` · `wwi_city_id` INT · `city` STRING · `state_province` STRING · `country` STRING · `continent` STRING · `sales_territory` STRING · `region` STRING · `subregion` STRING · `valid_from` TIMESTAMP · `valid_to` TIMESTAMP · `is_current` BOOLEAN |
| `dim_employee` | `employee_key` INT ← `[Dimension].[Employee].[Employee Key]` · `wwi_employee_id` INT · `employee` STRING · `is_salesperson` BOOLEAN · `valid_from` TIMESTAMP · `valid_to` TIMESTAMP · `is_current` BOOLEAN. Role-played as Salesperson and Picker. |
| `dim_date` | Generated (§ 5.4). |

### 5.2 `slc.nyctaxi` — NYC Yellow Taxi

Source window: pickups from 2023-01-01 to 2024-12-31.

| Table | Columns (type) ← source |
|---|---|
| `fact_trip` | `trip_id` BIGINT (deterministic surrogate; ordering defined in the platform build) · `vendor_id` INT ← `VendorID` · `pickup_ts` TIMESTAMP_NTZ ← `tpep_pickup_datetime` · `dropoff_ts` TIMESTAMP_NTZ ← `tpep_dropoff_datetime` · `pickup_date` DATE · `dropoff_date` DATE · `pickup_hour` TINYINT · `pu_location_id` INT ← `PULocationID` · `do_location_id` INT ← `DOLocationID` · `od_pair_id` INT (= `pu_location_id * 1000 + do_location_id`) · `passenger_count` INT NULL · `trip_distance` DECIMAL(9,2) · `payment_type` INT · `fare_amount` DECIMAL(10,2) · `tip_amount` DECIMAL(10,2) · `tolls_amount` DECIMAL(10,2) · `total_amount` DECIMAL(10,2) |
| `fact_trip_quarantine` | All `fact_trip` columns plus `reject_reason` STRING. Not exposed to any semantic layer. |
| `dim_zone` | `location_id` INT ← `LocationID` · `borough` STRING ← `Borough` · `zone` STRING ← `Zone` · `service_zone` STRING ← `service_zone`. Role-played as Pickup Zone and Dropoff Zone. |
| `dim_payment_type` | `payment_type` INT · `payment_type_name` STRING; codes 0–6 per the TLC Yellow Taxi data dictionary |
| `dim_date` | Generated (§ 5.4). Role-played as Pickup Date and Dropoff Date. |

### 5.3 Data rules

1. **NYC valid trip predicate:** a source row enters `fact_trip` only if `pickup_ts < dropoff_ts`, `0 < trip_distance <= 200`, `fare_amount >= 0`, `total_amount >= 0`, and `pickup_date` is within the source window. Every other row goes to `fact_trip_quarantine` with the first failed rule as `reject_reason`.
2. **NYC numeric conversion:** source doubles are converted with `CAST(ROUND(x, 2) AS DECIMAL(p, 2))`.
3. **WWI unknown members:** key `0` rows in WWI dimensions are retained with their source labels. Facts referencing unknown members are never dropped.
4. **WWI SCD Type 2:** facts join on surrogate keys (as-was attribution). As-is attribution uses the durable key (`wwi_*_id`) joined to the row where `is_current = true`. Both attributions must be exposed (§ 7, question `Q-W-S1-D4`). Source profile: only `dim_stock_item.color` differs across versions; sales attributed to `Gray` are `Steel Gray` in the current version (9,472 lines). Customer, city and employee versions carry no attribute changes. `is_current` marks exactly one row per durable key: the open-ended row with the latest `valid_from`, ties broken by the highest surrogate key. 4,612 cities have two open-ended rows with identical `valid_from` and attributes.
5. **Undelivered sales:** rows with `delivery_date IS NULL` group under a NULL Delivery Date member and are included in totals.
6. **Daily stock snapshot derivation:** for every `wwi_stock_item_id` with a current holding and every date `t` from 2013-01-01 to 2016-05-31, let `cum(t)` = Σ movement quantity with `movement_date ≤ t`, and `B(t) = QOH_current − (cum(∞) − cum(t))` (holding back-cast).
   - If `B(t) ≥ 0` for every `t` in the window: `quantity_on_hand = B(t)`, `balance_basis = 'holding_backcast'`.
   - Otherwise the movement history cannot be reconciled with the current holding: `quantity_on_hand = O + cum(t)` with `O = max(0, −min_t cum(t))`, `balance_basis = 'flow_min_opening'`.
   - Source profile (2026-11-19): 218 items back-cast; 9 items flow-based. For those 9 items, `[Fact].[Movement]` and `[Fact].[Purchase]` agree on receipts of 8.6M–25.1M units, while `[Fact].[Stock Holding]` shows 3–50 units on hand.
   - `stock_item_key` is the `dim_stock_item` version whose validity interval contains the start of `t`, or the earliest version if `t` precedes all versions.
7. **No-data semantics:** a NULL value, an empty cell, BLANK, and an absent row are equivalent in reconciliation. No metric returns 0 where the oracle returns NULL.

### 5.4 `dim_date` (both schemas)

Generated, gap-free, covering full calendar years that span every date value in the facts (WWI: 2013–2016; NYC: 2023–2025, because 571 valid trips picked up on 2024-12-31 drop off on 2025-01-01). Columns: `date_key` DATE · `calendar_year` SMALLINT · `calendar_quarter` TINYINT · `calendar_month` TINYINT · `month_name` STRING · `month_start_date` DATE · `day_of_month` TINYINT · `day_of_year` SMALLINT · `day_of_week` TINYINT (ISO, Monday = 1) · `day_name` STRING · `iso_week_number` TINYINT · `fiscal_year` SMALLINT · `fiscal_quarter` TINYINT · `fiscal_month` TINYINT · `fiscal_period_index` INT · `day_of_fiscal_year` SMALLINT.

Fiscal calendar (WWI): fiscal year starts 1 November and is labeled by the calendar year in which it ends; November is `fiscal_month = 1`. `fiscal_period_index = fiscal_year * 12 + fiscal_month` (consecutive across years). A Phase 2 profiling test asserts equality with the source `[Dimension].[Date]` fiscal columns. NYC uses the same columns; fiscal columns are populated by the same rule and are not used by NYC metrics.

---

## 6. Metric Catalog (22 Metrics)

22 metrics: 12 KPIs (2 Simple, 2 Medium, 2 Complex per dataset) and 10 base measures required for self-service exploration.

| ID | Dataset | Tier | Metric | Primary mechanism stressed |
|---|---|---|---|---|
| B-W1 | WWI | Base | Revenue Including Tax | Additive sum |
| B-W2 | WWI | Base | Gross Profit | Additive sum |
| B-W3 | WWI | Base | Units Sold | Additive sum |
| B-W4 | WWI | Base | Invoice Count | Distinct count |
| B-W5 | WWI | Base | Backordered Order Lines | Filtered count on a second fact |
| B-N1 | NYC | Base | Trip Count | Row count |
| B-N2 | NYC | Base | Total Trip Distance | Additive sum |
| B-N3 | NYC | Base | Fare Amount | Additive sum |
| B-N4 | NYC | Base | Tip Amount (All Payment Types) | Additive sum |
| B-N5 | NYC | Base | Tolls Amount | Additive sum |
| W-S1 | WWI | Simple | Revenue (Excl. Tax) | Additive aggregation over SCD2 dimensions with natural and alternate hierarchies (geography vs sales territory; calendar vs fiscal) |
| W-S2 | WWI | Simple | Ordered Quantity | Second fact on a different primary date, combined with W-S1 under one shared Date selection |
| W-M1 | WWI | Medium | Gross Margin % | Non-additive ratio of sums; measure composition |
| W-M2 | WWI | Medium | Closing Stock On Hand | Semi-additive: sum across items, last value across time |
| W-C1 | WWI | Complex | Stock Group Revenue Share | Many-to-many bridge (fan-out trap) with share-of-parent denominator |
| W-C2 | WWI | Complex | Days of Supply | Chasm trap across two facts at different grains, trailing 91-day window, semi-additive numerator |
| N-S1 | NYC | Simple | Gross Trip Revenue | Additive aggregation at ~80M-row scale (storage engine) |
| N-S2 | NYC | Simple | Card Tips | Measure-scoped filter |
| N-M1 | NYC | Medium | Distinct OD Pairs | Non-additive distinct count on a composite key |
| N-M2 | NYC | Medium | Fare per Mile | Role-playing dimension (Pickup vs Dropoff Zone) with a non-additive ratio |
| N-C1 | NYC | Complex | Revenue YTD and YoY % vs STLY | Calendar time intelligence on a timestamp-derived date role |
| N-C2 | NYC | Complex | MTD-to-YTD Daily Pace Index | Period-to-date windows with calendar-day denominators |

### 6.1 Notation

- `ctx` is the evaluation context: all filters and groupings applied to the cell.
- `S`, `O`, `H`, `T` are the rows of `fact_sale`, `fact_order`, `fact_stock_holding_daily`, `fact_trip` in `ctx`.
- For a period-anchored metric, `t(P)` = the last calendar date of the period `P` in `ctx`, capped at the dataset's maximum source date (WWI 2016-05-31; NYC 2024-12-31). With no date in `ctx`, `P` is the full source window.
- `NULLIF(x, 0)` semantics apply to every division: a zero or NULL denominator yields NULL.

### 6.2 Base measures

### B-W1 — Revenue Including Tax
`Σ_{i∈S} total_including_tax_i`

### B-W2 — Gross Profit
`Σ_{i∈S} profit_i`

### B-W3 — Units Sold
`Σ_{i∈S} quantity_i`

### B-W4 — Invoice Count
`COUNT(DISTINCT wwi_invoice_id_i) over i∈S`. Exact distinct count; approximate distinct functions are prohibited.

### B-W5 — Backordered Order Lines
`COUNT(i∈O where wwi_backorder_id_i IS NOT NULL)`

### B-N1 — Trip Count
`COUNT(i∈T)`

### B-N2 — Total Trip Distance
`Σ_{i∈T} trip_distance_i`

### B-N3 — Fare Amount
`Σ_{i∈T} fare_amount_i`

### B-N4 — Tip Amount (All Payment Types)
`Σ_{i∈T} tip_amount_i`

### B-N5 — Tolls Amount
`Σ_{i∈T} tolls_amount_i`

### 6.3 KPIs — WideWorldImporters

### W-S1 — Revenue (Excl. Tax)
`REV = Σ_{i∈S} total_excluding_tax_i`

Required hierarchies: Calendar (Year › Quarter › Month › Date), Fiscal (Fiscal Year › Fiscal Quarter › Fiscal Month › Date), Geography (Continent › Country › State Province › City), Sales Territory (Sales Territory › State Province › City), Stock Group › Stock Item.

### W-S2 — Ordered Quantity
`OQ = Σ_{i∈O} quantity_i`, dated by `order_date`. A single shared Date selection filters W-S1 by `invoice_date` and W-S2 by `order_date` in the same query.

### W-M1 — Gross Margin %
`GM% = B-W2 / REV`. Computed from the aggregated numerator and denominator at every grain; never an aggregate of row-level ratios.

### W-M2 — Closing Stock On Hand
`d* = MAX(snapshot_date of H)` within `P`, then `OH(P) = Σ_{j∈H, snapshot_date_j = d*} quantity_on_hand_j`. Additive across stock items and stock groups (deduplicated, see W-C1); last value across time. Because `fact_stock_holding_daily` is dense, `d* = t(P)`.

### W-C1 — Stock Group Revenue Share
- Group revenue: `REV(g) = Σ_{i∈S, wwi_stock_item_id(i) ∈ members(g)} total_excluding_tax_i`, where `members(g)` comes from `bridge_stock_item_group`.
- Share: `SHARE(g) = REV(g) / REV(ctx without the stock group filter)`.
- At any total across groups, revenue is deduplicated: the total equals W-S1 for the same `ctx`, not `Σ_g REV(g)`.
- Required negative test: `Σ_g REV(g) > W-S1` when any sold item belongs to more than one group; reported totals still equal W-S1. A Phase 2 profiling test asserts at least one stock item belongs to two or more groups.

### W-C2 — Days of Supply
- `t = t(P)`; numerator `OH(P)` from W-M2.
- `U91 = Σ_{i: fact_sale rows with invoice_date in [t − 90, t]} quantity_i`, honoring item and stock group filters and ignoring the date filter's lower bound.
- `DOS = OH(P) / (U91 / 91)`; NULL when `U91 = 0`.
- Conformed dimensions: Date, Stock Item, Stock Group. Grouping or filtering by Customer, Bill-To Customer, City, Salesperson, Picker, or Delivery Date returns NULL. A duplicated (fanned-out) value is a failure.

### 6.4 KPIs — NYC Taxi

### N-S1 — Gross Trip Revenue
`Σ_{i∈T} total_amount_i`

### N-S2 — Card Tips
`Σ_{i∈T, payment_type_i = 1} tip_amount_i`. TLC records tips only for card payments. Grouping by payment type returns NULL for every type except 1.

### N-M1 — Distinct OD Pairs
`COUNT(DISTINCT od_pair_id_i) over i∈T`. Exact.

### N-M2 — Fare per Mile
`B-N3 / B-N2`. Canonical display grain: Pickup Borough × Dropoff Borough, using two roles of `dim_zone`.

### N-C1 — Revenue YTD and YoY % vs STLY
- Anchor: Pickup Date role. `t = t(P)`.
- `YTD(t) = Σ total_amount for pickup_date in [Jan 1 of year(t), t]`.
- `STLY_YTD(t) = Σ total_amount for pickup_date in [Jan 1 of year(t) − 1 year, t − 1 year]`; 29 February maps to 28 February.
- `YOY% = (YTD − STLY_YTD) / STLY_YTD`. NULL for 2023 anchors (no prior-year data).
- Grouping by the Dropoff Date role returns NULL.

### N-C2 — MTD-to-YTD Daily Pace Index
- `t = t(P)`.
- `PACE = (TRIPS_MTD(t) / day_of_month(t)) / (TRIPS_YTD(t) / day_of_year(t))`, with trips counted by Pickup Date.
- Denominators are calendar days elapsed, not days with trips.
- Grouping by the Dropoff Date role returns NULL.

### 6.5 Dimensional applicability matrix

`✓` = must return the oracle value. `N` = must return NULL. Columns: DATE = the shared Date dimension bound to each fact's primary date (`invoice_date`, `order_date`, `snapshot_date`); DELIV = Delivery Date role; CUST = Customer; BILL = Bill-To Customer; CITY = City / Sales Territory; ITEM = Stock Item; GROUP = Stock Group; SP = Salesperson; PICK = Picker.

| Metric | DATE | DELIV | CUST | BILL | CITY | ITEM | GROUP | SP | PICK |
|---|---|---|---|---|---|---|---|---|---|
| B-W1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N |
| B-W2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N |
| B-W3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N |
| B-W4 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N |
| B-W5 | ✓ | N | ✓ | N | ✓ | ✓ | ✓ | ✓ | ✓ |
| W-S1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N |
| W-S2 | ✓ | N | ✓ | N | ✓ | ✓ | ✓ | ✓ | ✓ |
| W-M1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N |
| W-M2 | ✓ | N | N | N | N | ✓ | ✓ | N | N |
| W-C1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N |
| W-C2 | ✓ | N | N | N | N | ✓ | ✓ | N | N |

NYC columns: PDATE = Pickup Date; DDATE = Dropoff Date; HOUR = `pickup_hour`; PZONE = Pickup Zone (Borough › Zone, service zone); DZONE = Dropoff Zone; PAY = Payment Type; VEND = Vendor.

| Metric | PDATE | DDATE | HOUR | PZONE | DZONE | PAY | VEND |
|---|---|---|---|---|---|---|---|
| B-N1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| B-N2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| B-N3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| B-N4 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| B-N5 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| N-S1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| N-S2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| N-M1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| N-M2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| N-C1 | ✓ | N | ✓ | ✓ | ✓ | ✓ | ✓ |
| N-C2 | ✓ | N | ✓ | ✓ | ✓ | ✓ | ✓ |

---

## 7. Self-Service Question Bank

Self-service is the capability target. Predefined executive questions are 12 of 70 questions (17%). Each KPI has a chain: `P` (predefined executive question) followed by `D1` drill-down to a finer grain, `D2` drill-across to a dimension outside `P`, `D3` slice and compare, and `D4` root-cause or boundary probe. Ten ad hoc questions (`AH`) use base measures in combinations no report anticipates. Questions that reference "the member with the highest/lowest …" are resolved dynamically by the oracle; stacks and agents must resolve them, not be told the answer.

All stacks answer every question on B0 without model changes between questions. Expected answers come from the oracle (§ 9).

| ID | Type | Metrics | Question |
|---|---|---|---|
| Q-W-S1-P | P | W-S1 | Revenue (excl. tax) by Sales Territory by fiscal month for fiscal year 2015. |
| Q-W-S1-D1 | D1 | W-S1 | For the Sales Territory with the highest FY2015 revenue, break its revenue in its peak fiscal month down by State Province, then by City. |
| Q-W-S1-D2 | D2 | W-S1 | For that Sales Territory, which 10 stock items contributed the most FY2015 revenue, and what share of the territory's revenue do they represent together? |
| Q-W-S1-D3 | D3 | W-S1 | Compare FY2015 and FY2014 revenue by Buying Group and Customer Category. |
| Q-W-S1-D4 | D4 | W-S1 | Show FY2015 revenue by stock item Color as recorded at time of sale and by each item's current Color; list colors where the two differ. |
| Q-W-S2-P | P | W-S2, W-S1 | Ordered quantity and revenue (excl. tax) by calendar month for 2015 on one shared date axis. |
| Q-W-S2-D1 | D1 | W-S2, B-W3 | For the 2015 month with the largest gap between ordered quantity and units sold, break ordered quantity down by stock item. |
| Q-W-S2-D2 | D2 | W-S2 | For that month, ordered quantity by picker. |
| Q-W-S2-D3 | D3 | W-S2 | Compare ordered quantity by selling package by calendar quarter, 2014 vs 2015. |
| Q-W-S2-D4 | D4 | B-W5 | Backordered order lines in 2015 by salesperson and stock group; identify the salesperson with the most. |
| Q-W-M1-P | P | W-M1 | Gross margin % by Customer Category by fiscal quarter for FY2015. |
| Q-W-M1-D1 | D1 | W-M1, W-S1 | For the category with the lowest FY2015 gross margin %, list the 10 lowest-margin stock items with FY2015 revenue above 10,000. |
| Q-W-M1-D2 | D2 | W-M1 | For those 10 items, gross margin % by Sales Territory. |
| Q-W-M1-D3 | D3 | W-M1 | Gross margin % by selling package, FY2014 vs FY2015. |
| Q-W-M1-D4 | D4 | W-M1 | Which salesperson's gross margin % fell the most from FY2014 to FY2015, and which stock groups drove the change? |
| Q-W-M2-P | P | W-M2 | Closing stock on hand (units) at each fiscal month end of FY2015. |
| Q-W-M2-D1 | D1 | W-M2 | Closing stock on hand at the end of FY2015 by stock group, with a deduplicated total. |
| Q-W-M2-D2 | D2 | W-M2 | For the stock group with the most units at FY2015 end, the 10 stock items with the highest closing stock. |
| Q-W-M2-D3 | D3 | W-M2 | Compare closing stock on hand at 2015-12-31 and 2014-12-31 by selling package and chiller flag. |
| Q-W-M2-D4 | D4 | W-M2 | Which 10 stock items had the lowest closing stock at any calendar month end in 2015, and at which month end? |
| Q-W-C1-P | P | W-C1 | Revenue share by stock group for FY2015, with a grand total equal to total revenue. |
| Q-W-C1-D1 | D1 | W-C1 | For the stock group with the highest FY2015 share, each stock item's share of that group's revenue. |
| Q-W-C1-D2 | D2 | W-C1 | Stock group revenue share within each Sales Territory for FY2015. |
| Q-W-C1-D3 | D3 | W-C1 | Compare stock group shares FY2014 vs FY2015; which group gained the most share points? |
| Q-W-C1-D4 | D4 | W-C1, W-S1 | For FY2015, report the sum of stock group revenues, total revenue, and the overlap amount from items in more than one group. |
| Q-W-C2-P | P | W-C2 | Days of supply at each calendar month end of 2015, company-wide. |
| Q-W-C2-D1 | D1 | W-C2 | Days of supply at 2015-12-31 by stock group. |
| Q-W-C2-D2 | D2 | W-C2 | The 10 stock items with the lowest days of supply at 2015-12-31, excluding items with no sales in the trailing 91 days. |
| Q-W-C2-D3 | D3 | W-C2 | Days of supply for chiller vs non-chiller items at each calendar quarter end of 2015. |
| Q-W-C2-D4 | D4 | W-C2 | Days of supply by Sales Territory at 2015-12-31. Expected: NULL for every territory, with the reason (non-conformed dimension). |
| Q-N-S1-P | P | N-S1 | Gross trip revenue by pickup borough by month for 2024. |
| Q-N-S1-D1 | D1 | N-S1 | For the 2024 month with the highest revenue, the 15 Manhattan pickup zones with the most revenue. |
| Q-N-S1-D2 | D2 | N-S1 | For that month, gross trip revenue by pickup hour and payment type. |
| Q-N-S1-D3 | D3 | N-S1 | Compare monthly gross trip revenue for pickups in the Airports service zone, 2024 vs 2023. |
| Q-N-S1-D4 | D4 | N-S1 | Which 10 dropoff zones received the most 2024 revenue from trips picked up at JFK Airport? |
| Q-N-S2-P | P | N-S2 | Card tips by vendor by month for 2024. |
| Q-N-S2-D1 | D1 | N-S2 | Card tips by pickup hour for December 2024. |
| Q-N-S2-D2 | D2 | N-S2 | Card tips by pickup borough × dropoff borough for 2024. |
| Q-N-S2-D3 | D3 | N-S2, B-N1 | Card tips per card trip (card tips ÷ trip count for payment type 1) by month, 2023 vs 2024. |
| Q-N-S2-D4 | D4 | N-S2 | Card tips by payment type for 2024. Expected: a value only for payment type 1; NULL for all others. |
| Q-N-M1-P | P | N-M1 | Distinct OD pairs by month for 2024. |
| Q-N-M1-D1 | D1 | N-M1 | Distinct OD pairs by payment type for 2024, alongside the overall total (which is less than the sum of payment types). |
| Q-N-M1-D2 | D2 | N-M1 | Distinct OD pairs by pickup hour for Q4 2024. |
| Q-N-M1-D3 | D3 | N-M1 | Distinct OD pairs served by each vendor, 2023 vs 2024. |
| Q-N-M1-D4 | D4 | N-M1 | Among Manhattan pickup zones, the 10 with the most distinct OD pairs in 2024. |
| Q-N-M2-P | P | N-M2 | Fare per mile by pickup borough × dropoff borough for 2024. |
| Q-N-M2-D1 | D1 | N-M2, B-N1 | For Manhattan → Manhattan trips in 2024, the 10 pickup zones with the highest fare per mile among zones with at least 10,000 such trips. |
| Q-N-M2-D2 | D2 | N-M2 | Fare per mile by pickup hour for Manhattan → Manhattan trips in 2024. |
| Q-N-M2-D3 | D3 | N-M2 | Fare per mile by month for pickups in the Airports service zone, 2024 vs 2023. |
| Q-N-M2-D4 | D4 | N-M2 | For trips picked up at JFK Airport in 2024, fare per mile by dropoff borough and payment type; which combination is highest? |
| Q-N-C1-P | P | N-C1 | YTD gross trip revenue and YoY % vs STLY at each month end of 2024. |
| Q-N-C1-D1 | D1 | N-C1 | YoY % of YTD revenue at 2024-06-30 by pickup borough. |
| Q-N-C1-D2 | D2 | N-C1 | For the pickup borough with the lowest YoY % at 2024-06-30, the 10 pickup zones with the largest absolute YTD revenue decline. |
| Q-N-C1-D3 | D3 | N-C1 | YTD revenue and YoY % at 2024-12-31 by payment type. |
| Q-N-C1-D4 | D4 | N-S1 | Gross trip revenue for dropoff dates in 2024 vs pickup dates in 2024; report both and the difference. |
| Q-N-C2-P | P | N-C2 | MTD-to-YTD daily pace index at each month end of 2024. |
| Q-N-C2-D1 | D1 | N-C2 | Pace index at 2024-11-30 by pickup borough. |
| Q-N-C2-D2 | D2 | N-C2 | Pace index at 2024-11-30 by payment type. |
| Q-N-C2-D3 | D3 | N-C2 | Pace index at 2024-03-15 vs 2023-03-15 (leap-year day counts differ). |
| Q-N-C2-D4 | D4 | N-C2, B-N1 | For the pickup zone with the highest pace index at 2024-11-30 among zones with at least 50,000 YTD trips, daily trip counts for November 2024. |
| Q-A01 | AH | B-W1 | The 5 bill-to customers with the highest revenue including tax in calendar 2015. |
| Q-A02 | AH | B-W4 | Invoice count by salesperson by fiscal year. |
| Q-A03 | AH | B-W3 | Units sold by stock group by delivery month for January–May 2016, delivered lines only. |
| Q-A04 | AH | B-W2 | The 20 State Province × Customer Category combinations with the highest gross profit in calendar 2015. |
| Q-A05 | AH | B-W5 | Backordered order lines by stock group by calendar quarter for 2015. |
| Q-A06 | AH | B-N1 | Trip count by pickup hour and day of week for 2024. |
| Q-A07 | AH | B-N1, B-N2 | Average trip distance (total distance ÷ trip count) by pickup borough for 2024. |
| Q-A08 | AH | B-N5 | Total tolls by dropoff borough for trips picked up at LaGuardia Airport in 2024. |
| Q-A09 | AH | B-N4, N-S2 | Tip amount (all payment types) vs card tips by payment type for 2024. |
| Q-A10 | AH | B-N3, B-N1 | Fare amount per trip by vendor by month for 2024. |

---

## 8. Evaluation Dimensions

| ID | Dimension | Measurement | Pass criterion |
|---|---|---|---|
| E1 | Metric correctness | Every metric × every applicability-matrix cell type, at year, month, and leaf grains, reconciled to the oracle | 100% of cells within tolerance (§ 9.3) |
| E2 | Self-service depth | All 70 questions answered through the stack's self-service interface on B0 | 100% correct; zero model changes during the run |
| E3 | Query performance | Each question's stack-native query (MDX, DAX, VizQL, SQL), run at concurrency 1 and 10, warm and cold cache | Warm p95 ≤ 2 s for `P`; warm p95 ≤ 5 s for `D1`–`D4` and `AH` at concurrency 10; cold latency reported |
| E4 | Data freshness | End-to-end latency from file landing to first visibility in a stack query, using sentinel trips (§ 9.4) | p95 ≤ 15 minutes |
| E5 | CI/CD | A model change flows lint → deploy to test → process/refresh → oracle reconciliation subset → promote, triggered by a Git push | Zero manual steps; rollback by redeploying the previous commit |
| E6 | Partition and refresh automation | Unattended monthly rollover on NYC: create, process, merge or retire beyond 24 months | Two consecutive simulated rollovers succeed with E1 still passing |
| E7 | AI agent accessibility | Question bank through native assistants and the common harness (§ 11) | Reported per lane: accuracy, pass@3, 3-of-3 consistency, median latency |
| E8 | Governance parity | RLS scenario (§ 10) through BI clients and agents | Restricted identities see exactly the oracle's restricted results in every lane |
| E9 | Boundaries | Each place a stack needs an adjacent component or workaround to meet E1–E8 | Every boundary documented with mechanism, workaround, and cost in complexity |

### 8.1 Initial boundary register

Confirmed or rejected in Phase 3.

| ID | Boundary | Basis |
|---|---|---|
| B-01 | Metric view materialization cannot be used when the source has RLS, column masking, or ABAC policies, and filters cannot use invoker-dependent functions. This conflicts with E8 for materialized NYC metrics. | Documented (V-06) |
| B-02 | Metric view many-to-one joins select the first matching row when the join is actually many-to-many; the stock group bridge (W-C1) needs a `one_to_many` join, an LOD pattern, or an upstream table. | Documented (V-03) |
| B-03 | Multi-fact analysis (W-C2) in metric views needs `one_to_many` joins or relationships between metric views (Beta). | Documented (V-03, V-07) |
| B-04 | SSAS Multidimensional has no native natural-language assistant; it is reachable by agents only through the common harness. | Hypothesis |
| B-05 | Tableau has no built-in semi-additive aggregation; W-M2 needs LOD or table calculation logic. | Hypothesis |
| B-06 | SSAS Multidimensional distinct counts (B-W4, N-M1) require a dedicated measure group per distinct count measure. | Hypothesis |
| B-07 | Metric view window measures anchor a coarser group on the last order value with data in that group, not the calendar end of the period; period-to-date and same-period-last-year values differ from calendar-anchored definitions for members without activity on the period's last day (N-C1, N-C2). | Hypothesis (V-30) |
| B-08 | Metric views reach dimension members only through fact rows (the source is the fact, joins are left outer lookups); members without facts in scope are absent from results. | Documented (V-03) |

---

## 9. Correctness Oracle and Reconciliation

### 9.1 Oracle definition

The oracle is an independent reference implementation of every metric and every question, written as plain SQL directly against the canonical gold tables. It uses no semantic layer: no metric views, no cubes, no models. It is the single definition of "correct" for E1, E2, E7, and E8.

- **Location:** `01-spec/oracle/` — one `.sql` file per metric and per question.
- **Authoritative run:** executed on Databricks serverless SQL against B0; results are stored as versioned expected-answer files under `01-spec/oracle/expected/`.
- **CI run:** the same SQL, restricted to an ANSI subset that DuckDB and Databricks SQL both execute, runs in the repository test suite against small deterministic Parquet fixtures under `01-spec/oracle/fixtures/`. Fixture totals are hand-verifiable. This tests the oracle itself (positive cases, plus negative cases such as fan-out duplication, NULL-vs-zero, leap-year day counts, and censored windows) without requiring a Databricks connection.
- **Independence:** oracle SQL is never generated from, or copied out of, any stack's model code.

### 9.2 Reconciliation

Each stack's Phase 2 test suite executes the stack-native query for each metric cell and question, and compares results to `01-spec/oracle/expected/` row by row on the grouping keys.

### 9.3 Tolerances

| Value type | Tolerance |
|---|---|
| Counts and distinct counts | Exact |
| Money and distance sums | Absolute difference ≤ 0.005 |
| Ratios, shares, indexes, percentages | Absolute difference ≤ 1e-6 |
| Dates and member labels | Exact; NULL, BLANK, `Unknown`, and absent rows equivalent per § 5.3 rule 7 |

### 9.4 Freshness test protocol

- The December 2024 NYC partition is removed and replayed into the bronze landing volume in micro-batches every 60 seconds, each batch carrying the next 15 minutes of trips in `pickup_ts` order.
- Each batch includes one sentinel trip with a unique `trip_id` and a landing timestamp.
- Each stack is polled with a query for the sentinel; latency = first successful return − landing timestamp.
- After replay completes, the gold build equals B0 and E1 is re-run.

---

## 10. Security Scenario

| Dataset | Role | Rule | Expected effect |
|---|---|---|---|
| WWI | Territory Analyst – Southeast | Sales and order rows restricted to `dim_city.sales_territory = 'Southeast'` (as-was city) | All sale- and order-based metrics restricted; W-M2 and W-C2 return NULL (no inventory access) |
| NYC | Manhattan Pickup Analyst | Trip rows restricted to Pickup Zone `borough = 'Manhattan'` | The Dropoff Zone role is unrestricted for browsing; all NYC metrics reflect only Manhattan pickups |

Implementation per stack is listed in § 3.1. Every lane in § 11 runs the restricted question subset (all `P` and `D1` questions) as each role, and results must match the oracle's restricted expected answers.

---

## 11. AI Agent Evaluation Protocol

### 11.1 Lanes

| Lane | Client | Stack access |
|---|---|---|
| A — Native | Genie Agent (S4), Copilot in Power BI (S2), Tableau Agent (S3) | Native assistant over the semantic layer. S1 has no native lane (B-04). |
| B — Common harness | GitHub Copilot agent mode (primary) and Claude Code (secondary) | One repo-built MCP server per stack under `02-implementations/agent-harness/` |

### 11.2 Common harness contract

Every MCP server exposes the same two tools:

1. `describe_model` — returns metrics, dimensions, hierarchies, descriptions, and synonyms from the stack's own metadata.
2. `run_query` — executes a query in the stack's native language and returns a tabular result.

Rules:
- No server exposes the canonical tables, the oracle, or expected answers.
- Every agent receives the same system prompt template and the same metadata investment: descriptions and synonyms for all 22 metrics and all dimensions, sourced from `01-spec/glossary.yaml` and loaded into each stack's native metadata.
- The S1 server uses ADOMD.NET or XMLA over HTTPS against SSAS 2025 and issues MDX; it is the agent path that tests MC-05.

### 11.3 Scoring

- Each of the 70 questions runs 3 times per lane per stack, in a fresh session each time.
- A run is correct when every requested value matches the oracle within § 9.3 tolerances at the requested grain, and NULL-expected cells are reported as not applicable.
- Reported per lane and stack: accuracy, pass@3, 3-of-3 consistency, median latency, and tool calls per question.

---

## 12. Deliverables

Priority order is fixed: code pack → architecture reference → executive deck → workshop.

| Priority | Deliverable | Location | Build |
|---|---|---|---|
| 1 | Code pack: platform, four stack implementations, oracle, agent harness, test suites | `01-spec/oracle/`, `02-implementations/*` | Source in Git |
| 2 | Architecture reference document | `04-deliverables/architecture_reference.docx` | `scripts/build_architecture_reference.py` |
| 3 | Executive deck | `04-deliverables/executive_deck.pptx` | `scripts/build_executive_deck.py` |
| 4 | Hands-on workshop: lab guide and exercises reproducing the evidence for MC-01 through MC-08 | `04-deliverables/workshop_lab_guide.docx` | `scripts/build_workshop_lab_guide.py` |

### 12.1 Repository additions defined by this spec

| Path | Contents | Phase |
|---|---|---|
| `01-spec/glossary.yaml` | Canonical names, descriptions, synonyms, formats for all metrics and dimensions | 2 |
| `01-spec/oracle/` | Oracle SQL, fixtures, expected answers | 2 |
| `02-implementations/platform/` | Asset Bundle, Lakeflow pipelines, replay simulator, data rules § 5.3 | 2 |
| `02-implementations/agent-harness/` | Four MCP servers, evaluation runner | 2 |
| `03-boundaries-ocm/` | Evaluation scorecard (E1–E9), Marketing Claims Register verdicts, boundary analysis, enablement modules | 3 |

Every directory under `02-implementations/` follows CLAUDE.md § 6 (architectural guide plus standalone code files).

---

## 13. Phase Plan

| Phase | Deliverable | Exit criterion |
|---|---|---|
| 1 | `01-spec/SPEC.md` (this document) | `scripts/test_spec.py` passes; STATUS updated |
| 2 | Platform and data build (B0) | Profiling tests pass (fiscal calendar, bridge overlap, snapshot derivation, quarantine rules) |
| 2 | Oracle and question bank expected answers | Oracle fixture suite passes on DuckDB; expected answers generated on B0 |
| 2 | S1–S4 implementations | E1 and E2 reconciliation suites pass per stack; E5 and E6 pipelines run green |
| 2 | Agent harness | Harness contract tests pass for all four MCP servers |
| 3 | Evaluation scorecard E1–E9 | All dimensions measured for all stacks |
| 3 | Claims register verdicts and boundary analysis | Every MC and B entry has a verdict with linked evidence |
| 3 | OCM enablement modules | Each module maps to at least one MC entry and reproduces its evidence |

---

## 14. Verification Register

Vendor capability claims this spec relies on. `Pending` entries are verified against official documentation at the start of the Phase 2 work that depends on them (CLAUDE.md § 3, § 5); a failed verification triggers a spec amendment (§ 16).

| ID | Claim | Status | Source (checked 2026-11-19 unless Pending) |
|---|---|---|---|
| V-01 | Metric View YAML 1.1 adds agent metadata (`display_name`, `format`, `synonyms`, `comment`), `cardinality`/`one_to_many`, window `offset`, `inclusive`/`exclusive` modifiers, and numeric index windows (DBR 19); SQL warehouses track the latest Databricks SQL version | Verified | https://docs.databricks.com/aws/en/uc-semantics/metric-views/feature-availability |
| V-02 | Window measures: required `order` and `range` (`current`, `cumulative`, `trailing`, `leading`, `all`); optional `semiadditive` (`first`, `last`; default `last`) and `offset`; trailing ranges exclude the anchor by default; YTD via `cumulative` plus `range: current` on the year field; composition via `MEASURE()` | Verified | https://docs.databricks.com/aws/en/uc-semantics/metric-views/advanced-techniques |
| V-03 | Joins: star and nested snowflake joins; default `many_to_one`; for true many-to-many the first matching row is selected; `one_to_many` aggregates a joined fact independently at its own grain | Verified | https://docs.databricks.com/aws/en/uc-semantics/metric-views/yaml-reference |
| V-04 | DDL form `CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$`; top-level `fields` (`dimensions` accepted as a synonym) | Verified | https://docs.databricks.com/aws/en/uc-semantics/metric-views/yaml-reference |
| V-05 | LOD in metric views: fixed LOD via window functions in field `expr`; coarser LOD via window measures with `range: all` | Verified | https://docs.databricks.com/aws/en/uc-semantics/metric-views/level-of-detail |
| V-06 | Materialization: `schedule`, `mode: relaxed`, `materialized_views` (`aggregated`/`unaggregated`), `refresh_policy` (`auto`, `incremental`, `incremental strict`, `full`); source cannot have RLS, column masking, or ABAC; no invoker-dependent expressions; `one_to_many` limits to exact match | Verified | https://docs.databricks.com/aws/en/uc-semantics/metric-views/yaml-reference |
| V-07 | Relationships between metric views (Beta): metadata-only `MANY TO ONE` etc. relationships declared with `ALTER VIEW ... ADD CONSTRAINT`; supports constellation schemas | Verified | https://docs.databricks.com/aws/en/uc-semantics/metric-views/relationships |
| V-08 | Genie Agents and AI/BI dashboards consume metric views; dashboards apply `MEASURE()` automatically and surface agent metadata | Verified | https://docs.databricks.com/aws/en/uc-semantics/metric-views/query |
| V-09 | SQL Server 2025 Analysis Services ships Multidimensional mode; Data Mining discontinued (2022); msmdpump HTTP disabled by default in 2025 (HTTPS required) | Verified | https://learn.microsoft.com/en-us/analysis-services/what-s-new-in-sql-server-analysis-services?view=sql-analysis-services-2025 |
| V-10 | Power BI Azure Databricks connector uses the ADBC driver by default for new connections since February 2026 | Verified | https://learn.microsoft.com/en-us/power-query/connectors/databricks-azure |
| V-11 | SSAS Multidimensional data source over the Databricks ODBC driver for processing and ROLAP | Pending | — |
| V-12 | Direct Lake on OneLake over a mirrored Azure Databricks Unity Catalog | Pending | — |
| V-13 | Power BI calendar-based time intelligence, hybrid tables with real-time DirectQuery partition, Copilot AI instructions and verified answers | Pending | — |
| V-14 | Tableau multi-fact relationships, VizQL Data Service, Tableau Agent over Published Data Sources | Pending | — |
| V-15 | GitHub Copilot agent mode MCP server support | Pending | — |
| V-16 | Unity Catalog ABAC policies as applied to the § 10 scenario: schema-level `CREATE POLICY ... ROW FILTER ... TO principals FOR TABLES WHEN has_tag_value(...) MATCH COLUMNS ... USING COLUMNS (...)`; governed tags applied to target objects are a prerequisite; `DROP POLICY name ON SCHEMA` has no `IF EXISTS`; row filters cannot reference tables with their own active row filters | Verified | https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/policies |
| V-17 | Fabric Git integration with TMDL and `fabric-cicd` deployment | Pending | — |
| V-18 | Lakeflow pipelines Python API is `pyspark.pipelines` (`dp`); `@dp.materialized_view` and `@dp.table` accept `schema` DDL with primary and foreign keys, `cluster_by`, and `private` | Verified | https://docs.databricks.com/aws/en/ldp/developer/python-ref |
| V-19 | Auto Loader on Parquet picks the widest type across files; schema hints make the reader read as the hinted type and rescue mismatches into `_rescued_data`; case-mismatched names are rescued unless `readerCaseSensitive` is false. Spark 4.3 fails reading INT64 as DOUBLE (reproduced on TLC 2023-01/2023-02) | Verified | https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader/schema |
| V-20 | Lakeflow Connect SQL Server: continuous gateway on classic compute, serverless ingestion pipeline, table-level `objects` with `destination_table`, change tracking for tables with primary keys | Verified | https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/sql-server-pipeline |
| V-21 | SQL Server change tracking cannot be used with columnstore indexes; CDC is supported only with a nonclustered columnstore index (reproduced as Msg 35353 on SQL Server 2025) | Verified | https://learn.microsoft.com/en-us/sql/t-sql/statements/create-columnstore-index-transact-sql |
| V-22 | Bundles manage `catalogs` (direct engine), `schemas` and `volumes`; serverless job environments use `environment_version`; pipeline `root_path` is added to `sys.path` | Verified | https://docs.databricks.com/aws/en/dev-tools/bundles/resources |
| V-23 | Materialized view incremental refresh includes a `WINDOW_FUNCTION` technique | Verified | https://docs.databricks.com/aws/en/ldp/incremental-refresh |
| V-24 | Lakeflow Connect bronze tables keep SQL Server column names, including spaces (gold transforms reference e.g. `` `Sale Key` ``) | Pending | — |
| V-25 | TLC Yellow Taxi data dictionary labels payment type 0 as "Flex Fare trip" | Pending | — |
| V-26 | `DELETE` on a streaming table that an Auto Loader flow writes to (freshness replay `prepare`) | Pending | — |
| V-27 | A principal with `SELECT` on a metric view can query it; the view reads its sources with its owner's privileges; materialized metric views cannot be owned by a group | Verified | https://docs.databricks.com/aws/en/uc-semantics/metric-views/manage |
| V-28 | ABAC row filter policies on a metric view's source tables evaluate the querying principal (not the view owner) when queried through the metric view | Pending | — |
| V-29 | Window `offset` accepts dated values (`-1 year`, DBR 18.1+) and yields NULL when the shifted frame falls outside the data; `trailing`/`leading` default to `exclusive`; `refresh_policy` values `auto`, `incremental`, `incremental strict`, `full` | Verified | https://docs.databricks.com/aws/en/uc-semantics/metric-views/yaml-reference |
| V-30 | A window measure queried at a coarser grain than its `order` field is evaluated at the last order value with data in each group (`semiadditive: last`) | Pending | — |
| V-31 | Query `WHERE` filters on a metric view apply before window measures are evaluated, so a filter on the order field truncates the window | Pending | — |
| V-32 | Bundle `sync.paths` may include paths outside the bundle root; the sync root moves to the common ancestor and keeps the folder structure | Verified | https://docs.databricks.com/aws/en/dev-tools/bundles/sharing |
| V-33 | GitHub Actions deploy bundles with `databricks/setup-cli` and workload identity federation (`DATABRICKS_AUTH_TYPE: github-oidc`, `id-token: write`) | Verified | https://docs.databricks.com/aws/en/dev-tools/ci-cd/github |

---

## 15. Locked Decisions

| ID | Decision | Source |
|---|---|---|
| D-01 | Tableau (Cloud, Published Data Sources, logical layer, LOD) is the third stack; Yellowfin is out of scope. | Scope Q1 |
| D-02 | Tableau Semantics is a forward-looking appendix, not evaluated. | Scope Q1 |
| D-03 | OCM purpose is capability education: showing that legacy stacks, engineered with modern practices, deliver CI/CD, partition automation, high-frequency availability, complex query performance, and AI access. Persona skill transfer is a non-goal. | Scope Q2 |
| D-04 | Deliverable priority: code pack → architecture reference → executive deck → workshop. | Scope Q3 |
| D-05 | Correctness is defined by an independent SQL oracle (§ 9). | Scope Q3 |
| D-06 | Latest documented runtimes and capabilities across all stacks; implementation realities (licensing, preview enrollment) are out of scope. Databricks on serverless SQL. | Scope Q4 |
| D-07 | Power BI on Fabric F64 with Import, Direct Lake, and DirectQuery variants, including Power BI against Databricks. | Scope Q4 |
| D-08 | Databricks serverless SQL is the single physical source for all stacks; connectivity method per stack is an implementation choice (§ 3.1). | Scope Q4 |
| D-09 | All governance and AI angles in scope: RLS parity, native assistant accuracy, lineage and certification, plus a common agent harness that includes SSAS Multidimensional via GitHub Copilot. | Scope Q5 |
| D-10 | Scope targets self-service analytics: predefined questions are a minority of the question bank; diagnostic follow-ups at finer grains and across wider dimensions are in scope. | Scope Q5 |
| D-11 | WideWorldImporters (DW sample plus two OLTP reference tables) replaces Contoso. | Scope Q6 |
| D-12 | NYC Yellow Taxi only, pickups 2023-01-01 to 2024-12-31. | Scope Q6 |
| D-13 | Metric count is 22: 12 KPIs plus 10 base measures. | Scope Q5 |
| D-14 | Required download hosts are added to the environment when Phase 2 data builds start. | Scope Q6 |

---

## 16. Change Control and Changelog

Amendments require: a version bump in the header, a changelog row, an updated `scripts/test_spec.py` where structure changes, and a `STATUS.md` update.

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-11-19 | Initial locked specification. |
| 1.1 | 2026-11-19 | Phase 2 platform build corrections from profiling the real sources (restored WideWorldImporters on SQL Server 2025; 24 TLC months). § 4: clustered columnstore index removal before change tracking, landing normalization for TLC type drift, dimensions-before-facts pipelines, bundle rename. § 5.1 and § 5.3 rule 6: back-cast snapshot with flow fallback and `balance_basis`, because 9 items' movement history cannot be reconciled with current holdings. § 5.3 rule 4 and `Q-W-S1-D4`: SCD2 probe moved from customer category (no history in source) to stock item color; single current row per durable key despite 4,612 duplicated open-ended city rows. § 5.4: NYC calendar extended to 2025 for dropoff dates. § 5.2: `passenger_count` marked NULL (5,400,588 source rows, all payment type 0). § 14: V-18 to V-26. |
| 1.2 | 2026-11-19 | Question bank corrections found by running the correctness oracle on the real-data B0. Q-N-M1-D1: distinct OD pairs are exactly additive across pickup borough, because the pair determines its pickup zone and borough, so the non-additivity probe moves to payment type. Q-W-M1-D3 and Q-W-S2-D3: chiller items sell only from 2016-01-02, so the FY2014/FY2015 and 2014/2015 comparisons move from the chiller flag to selling package. Q-W-M2-D4: no stock item is at zero on any 2015 month end (minimum 7,196 units), so the question asks for the 10 lowest month-end balances. |
| 1.3 | 2026-11-20 | Phase 2 S4 (metric views) findings. § 8.1: B-07 (window anchor on the last date with data, not the calendar period end) and B-08 (members reachable only through facts). § 14: V-16 verified; V-27 to V-33 added (metric view permissions, ABAC through metric views, window offset and refresh policy, anchor and filter-before-window semantics, bundle sync outside the root, GitHub Actions federation). |
