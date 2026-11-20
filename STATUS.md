# STATUS

Phase tracking for the Enterprise Semantic Layer Comparative Architecture Study. Governed by `CLAUDE.md` § 7 (Progress Hygiene). Scope is defined by `01-spec/SPEC.md` v1.3 (LOCKED).

Status values: `Not Started` · `In Progress` · `Complete` · `Blocked`

| Phase | Deliverable | Status | Last Updated | Notes |
|---|---|---|---|---|
| 1 | Specification `01-spec/SPEC.md` v1.3: 22-metric catalog, canonical schema, 70-question self-service bank, evaluation E1–E9, oracle, security, agent protocol | Complete | 2026-11-20 | Locked v1.0; amended under § 16 to v1.1 (Phase 2 source-profiling corrections), v1.2 (four question-bank corrections found by the oracle on real data) and v1.3 (S4 findings: boundaries B-07, B-08; V-16 verified; V-27 to V-33). `python3 scripts/test_spec.py`: 22 passed. |
| 2 | Shared data platform and baseline B0 (`02-implementations/platform/`) | Blocked | 2026-11-19 | Code complete and verified on the real sources: local B0 from restored WWI (SQL Server 2025) and 24 TLC months passes 71/71 profiling checks; `scripts/test_platform.py` 62/62 with all real-data layers on. Blocked on a Databricks workspace and a reachable SQL Server 2025 host to deploy the bundle and build B0 there (runbook: `PLATFORM_GUIDE.md` § 7). Confirm V-24 to V-26 on first deployment. |
| 2 | Correctness oracle, fixtures, expected answers, question bank, glossary (`01-spec/oracle/`, `01-spec/glossary.yaml`) | Complete | 2026-11-19 | 22 metric + 70 question queries; answers from the local real-data B0 committed; 92/92 identical on DuckDB 1.4.1 and Spark SQL 4.3.0. Raw-SQL floor: all 70 questions ≤ 1.08 s on DuckDB (4 vCPU). Report: `01-spec/oracle/ORACLE_REPORT.md`. `SLC_LOCAL_B0=<b0> python3 scripts/test_oracle.py`: 29 passed. Authoritative Databricks run pending a workspace. |
| 2 | Implementation: SSAS Multidimensional (`02-implementations/ssas-md/`) | Not Started | 2026-11-19 | SPEC § 3.1 S1. Verify V-11 before build. |
| 2 | Implementation: Power BI / Tabular (`02-implementations/powerbi-tabular/`) | Not Started | 2026-11-19 | SPEC § 3.1 S2. Import, Direct Lake, DirectQuery variants on F64. Verify V-12, V-13, V-17. |
| 2 | Implementation: Tableau (`02-implementations/bi-layer/`) | Not Started | 2026-11-19 | SPEC § 3.1 S3. Verify V-14. |
| 2 | Implementation: Databricks Metric Views (`02-implementations/databricks-metric-views/`) | In Progress | 2026-11-20 | SPEC § 3.1 S4. Started: metric view YAML 1.1 (re-verified against docs.databricks.com), DDL, relationships, security and materialization variants, stack-native queries for all 70 questions, reconciliation job, guide, tests. |
| 2 | Agent harness: four MCP servers and evaluation runner (`02-implementations/agent-harness/`) | Not Started | 2026-11-19 | SPEC § 11. Verify V-15. |
| 3 | Evaluation scorecard E1–E9 (`03-boundaries-ocm/`) | Not Started | 2026-11-19 | SPEC § 8. |
| 3 | Marketing claims verdicts MC-01 to MC-08 and boundary analysis (`03-boundaries-ocm/`) | Not Started | 2026-11-19 | SPEC § 2.1, § 8.1. |
| 3 | OCM enablement modules (`03-boundaries-ocm/`) | Not Started | 2026-11-19 | SPEC § 12, § 13. Feeds the workshop deliverable. |
