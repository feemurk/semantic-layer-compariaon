# CLAUDE.md

Binding project rules for the Enterprise Semantic Layer Comparative Architecture Study. These rules override default behavior for every change in this repository.

## 1. Purpose

A multi-phase comparative architecture study of semantic layer technologies, spanning legacy stacks (SSAS, Power BI Tabular, traditional BI-layer models) and modern stacks (Databricks Unity Catalog Metric Views). Each stack is evaluated against one common specification, documented at architectural depth, and assessed for the boundaries of its approach.

## 2. Audience

- Principal Data Architects
- BI Engineering Leads
- Analytics Stakeholders

Write for these readers. Assume fluency in dimensional modeling, calculation engines (DAX, MDX, SQL), and Unity Catalog governance. Do not explain foundational concepts.

## 3. Style

- Direct and technically rigorous. State the claim, then the evidence.
- Zero filler: no preambles, no recap paragraphs that restate the body, no marketing language.
- Zero placeholder pseudocode. No `...`, `TODO`, `<placeholder>`, or illustrative stubs inside code blocks. Every code block is complete and valid for its target stack.
- Tables for comparisons. Evaluation dimensions are named identically across all stacks.
- Vendor capability claims cite the official documentation URL and the product or spec version checked.

## 4. Phase Map

| Phase | Scope | Location |
|---|---|---|
| 1 | Specification: comparison dimensions, evaluation criteria, test scenarios | `01-spec/` |
| 2 | Stack implementations, one directory per stack | `02-implementations/<stack>/` |
| 3 | Boundaries and OCM analysis | `03-boundaries-ocm/` |

Phase 2 stacks: `ssas-md/`, `powerbi-tabular/`, `bi-layer/`, `databricks-metric-views/`.

Deliverable outputs live in `04-deliverables/` and follow § 8.

## 5. Databricks Currency

All Unity Catalog Metric Views code MUST:

- Follow YAML spec v1.1 or later.
- Use the DDL form `CREATE VIEW ... WITH METRICS LANGUAGE YAML`.
- Reference measures through `MEASURE()`.
- Cover, where the scenario calls for them: window measures (`order`, `range`, `semiadditive`, `offset`), composability (measures built on other measures), materialization, and agent metadata.
- Be verified against the official Databricks documentation for the spec version in use before any YAML is committed. The owning guide records the documentation URL and the spec version checked.

## 6. Code Separation

Every stack directory under `02-implementations/` contains BOTH:

1. A deep architectural guide in Markdown (`.md`) covering model structure, calculation semantics, security model, performance behavior, and limitations.
2. Standalone code files in their native formats (`.mdx`, `.dax`, `.yaml`, `.sql`, and similar). The guide references these files by path.

Guides link to standalone code files; they do not duplicate full listings that exist as files. A stack directory missing either category is incomplete and cannot carry `Complete` status.

## 7. Progress Hygiene

- `STATUS.md` is updated at the START and at the COMPLETION of every deliverable.
- Status values are exactly: `Not Started`, `In Progress`, `Complete`, `Blocked`.
- `Last Updated` is an ISO date (`YYYY-MM-DD`).
- `Notes` records the scope change, blocker, or verification result. `Blocked` and `Complete` rows always carry a note.
- A deliverable is `Complete` only when its test suite passes (§ 9).

## 8. Deliverable Builds

- Never hand-edit binary files (`.pptx`, `.docx`, `.xlsx`, `.pdf`).
- Each binary deliverable in `04-deliverables/` is produced by a Python builder committed under `scripts/`. Naming: `scripts/build_<name>.py` produces `04-deliverables/<name>.<ext>`.
- Builders are reproducible: the same inputs yield the same document content. Library versions are pinned.
- The builder script and its compiled output are committed together in the same change.

## 9. Testing Protocol

- Every scope item in the Phase Map has a test suite under `scripts/` that asserts the artifact exists and conforms to its specification.
- Each suite includes positive tests (the artifact exists, matches the spec, and passes validation) and negative tests (malformed or out-of-scope input is rejected). Examples of required negative cases:
  - Databricks YAML: a malformed document, and a `MEASURE()` reference to a measure that is not defined.
  - Structural files: a missing required directory or `.gitkeep`, an invalid status value, a wrong table header, and a missing phase row.
- Test suites run with the standard library or pinned dependencies and exit non-zero on failure.
- Failing tests are fixed or the deliverable is marked `Blocked` with the failure recorded in `Notes`. Tests are never skipped or weakened to pass.
- The command and result of each suite run are recorded in the `Notes` column of `STATUS.md` when a deliverable reaches `Complete`.
