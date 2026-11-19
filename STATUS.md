# STATUS

Phase tracking for the Enterprise Semantic Layer Comparative Architecture Study. Governed by `CLAUDE.md` § 7 (Progress Hygiene). Scope is defined by `01-spec/SPEC.md` v1.0 (LOCKED).

Status values: `Not Started` · `In Progress` · `Complete` · `Blocked`

| Phase | Deliverable | Status | Last Updated | Notes |
|---|---|---|---|---|
| 1 | Specification `01-spec/SPEC.md` v1.0: 22-metric catalog, canonical schema, 70-question self-service bank, evaluation E1–E9, oracle, security, agent protocol | Complete | 2026-11-19 | Locked. `python3 scripts/test_spec.py`: 22 tests passed (8 positive, 14 negative). `python3 scripts/test_init_structure.py`: 13 passed. |
| 2 | Shared data platform and baseline B0 (`02-implementations/platform/`) | Not Started | 2026-11-19 | SPEC § 4–5. Requires TLC and WideWorldImporters download hosts added to the environment. |
| 2 | Correctness oracle, fixtures, expected answers, glossary (`01-spec/oracle/`, `01-spec/glossary.yaml`) | Not Started | 2026-11-19 | SPEC § 9. DuckDB fixture suite in CI; authoritative run on Databricks serverless SQL. |
| 2 | Implementation: SSAS Multidimensional (`02-implementations/ssas-md/`) | Not Started | 2026-11-19 | SPEC § 3.1 S1. Verify V-11 before build. |
| 2 | Implementation: Power BI / Tabular (`02-implementations/powerbi-tabular/`) | Not Started | 2026-11-19 | SPEC § 3.1 S2. Import, Direct Lake, DirectQuery variants on F64. Verify V-12, V-13, V-17. |
| 2 | Implementation: Tableau (`02-implementations/bi-layer/`) | Not Started | 2026-11-19 | SPEC § 3.1 S3. Verify V-14. |
| 2 | Implementation: Databricks Metric Views (`02-implementations/databricks-metric-views/`) | Not Started | 2026-11-19 | SPEC § 3.1 S4. YAML 1.1 capabilities verified (V-01 to V-08); re-verify syntax before committing YAML. |
| 2 | Agent harness: four MCP servers and evaluation runner (`02-implementations/agent-harness/`) | Not Started | 2026-11-19 | SPEC § 11. Verify V-15. |
| 3 | Evaluation scorecard E1–E9 (`03-boundaries-ocm/`) | Not Started | 2026-11-19 | SPEC § 8. |
| 3 | Marketing claims verdicts MC-01 to MC-08 and boundary analysis (`03-boundaries-ocm/`) | Not Started | 2026-11-19 | SPEC § 2.1, § 8.1. |
| 3 | OCM enablement modules (`03-boundaries-ocm/`) | Not Started | 2026-11-19 | SPEC § 12, § 13. Feeds the workshop deliverable. |
