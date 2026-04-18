# Multi-Agent Architecture — Tableau to Power BI Migration

This project uses a **12-agent specialization model**. Each agent has scoped domain knowledge, file ownership, and clear boundaries. Four new specialist agents (@dax, @wiring, @semantic, @visual) provide deep expertise in their domains, while @converter and @generator remain as coordination layers.

## Quick Reference

| Agent | Invoke When | Owns |
|-------|-------------|------|
| **@orchestrator** | Pipeline coordination, CLI, batch, wizard | `migrate.py`, `import_to_powerbi.py`, `wizard.py`, `progress.py`, `incremental.py`, `plugins.py`, `notebook_api.py`, `api_server.py` |
| **@extractor** | Parsing Tableau XML, Hyper files, Prep flows, Server API | `tableau_export/*.py` (extract, datasource, hyper, pulse, prep, server) |
| **@dax** | DAX formula correctness, conversion, optimization, aggregation context, cross-table refs | `dax_converter.py`, `dax_optimizer.py` + DAX post-processing in `tmdl_generator.py` |
| **@wiring** | DAX↔M bridge, calc column vs measure classification, M generation, M step injection | `m_query_builder.py`, `calc_column_utils.py` + M functions in `tmdl_generator.py` |
| **@semantic** | TMDL semantic model, relationships, Calendar, RLS, hierarchies, parameters | `tmdl_generator.py` (structural), `fabric_semantic_model_generator.py` |
| **@visual** | PBIR report, visual containers, slicers, filters, bookmarks, themes, pages | `pbip_generator.py`, `visual_generator.py` |
| **@converter** | _(Coordination layer)_ Cross-cutting DAX+M tasks | Delegates to @dax and @wiring |
| **@generator** | _(Coordination layer)_ Fabric-native generation, cross-cutting model+report tasks | `fabric_project_generator.py`, `lakehouse_generator.py`, `dataflow_generator.py`, `notebook_generator.py`, `pipeline_generator.py`, `fabric_constants.py`, `fabric_naming.py` |
| **@assessor** | Migration readiness, scoring, strategy, diff reports, validation | `assessment.py`, `server_assessment.py`, `global_assessment.py`, `strategy_advisor.py`, `visual_diff.py`, `comparison_report.py`, `migration_report.py`, `equivalence_tester.py`, `regression_suite.py`, `schema_drift.py`, `validator.py` |
| **@merger** | Shared semantic model, multi-workbook merge, Fabric merge | `shared_model.py`, `merge_config.py` (+ co-owns `merge_assessment.py`, `merge_report_html.py`, `thin_report_generator.py`) |
| **@deployer** | Fabric/PBI deployment, auth, gateway, telemetry, multi-tenant | `deploy/*.py`, `gateway_config.py`, `telemetry.py`, `telemetry_dashboard.py`, `refresh_generator.py` |
| **@tester** | Tests, coverage, fixtures, regression | `tests/*.py` |

## Architecture Diagram

```
                        ┌──────────────┐
                        │ Orchestrator │  ← CLI entry, pipeline coordination
                        └──────┬───────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
        ┌─────▼─────┐   ┌─────▼─────┐   ┌─────▼─────┐
        │ Extractor  │   │ Converter │   │ Generator  │
        │ (Tableau)  │   │ (coord.)  │   │ (coord.)   │
        └────────────┘   └─────┬─────┘   └─────┬──────┘
                          ┌────┴────┐     ┌─────┴──────┐
                          │         │     │            │
                     ┌────▼──┐ ┌───▼───┐ ┌▼────────┐ ┌▼──────┐
                     │  DAX  │ │Wiring │ │Semantic │ │Visual │
                     │(formulas)│(DAX↔M)│ │(TMDL)   │ │(PBIR) │
                     └───────┘ └───────┘ └─────────┘ └───────┘
                                              │
                        ┌─────────────────┬────┴────┐
                        │                 │         │
                  ┌─────▼─────┐    ┌──────▼──┐  ┌───▼────┐
                  │  Assessor  │    │ Merger  │  │Deployer│
                  │ (Analysis) │    │ (Merge) │  │(Fabric)│
                  └────────────┘    └─────────┘  └────────┘

              ┌────────────────────────────────────────────┐
              │                  Tester                     │
              │    (Cross-cutting — reads all, writes       │
              │     only to tests/)                         │
              └────────────────────────────────────────────┘
```

## Specialist Agent Decomposition

The original 8-agent model had two overloaded agents:
- **@converter** owned all DAX conversion + all M generation → now split into **@dax** + **@wiring**
- **@generator** owned all TMDL model + all PBIR report + Fabric → now split into **@semantic** + **@visual** (Fabric stays with @generator)

### @dax — DAX Formula Specialist
- Owns: `dax_converter.py`, `dax_optimizer.py`
- Co-owns: DAX post-processing blocks in `tmdl_generator.py` (SUM wrapping, measure unwrapping, RELATED/LOOKUPVALUE)
- Expertise: Aggregation context (bare column refs vs iterator row context), cross-table semantics, DAX optimization

### @wiring — DAX↔M Bridge Specialist
- Owns: `m_query_builder.py`, `calc_column_utils.py`
- Co-owns: M functions in `tmdl_generator.py` (`_dax_to_m_expression()`, `_inject_m_steps_into_partition()`, `_build_m_transform_steps()`, `_fix_m_if_else_balance()`, `_quote_m_identifiers()`)
- Expertise: Calc column vs measure classification, M pushdown decisions, M step chaining

### @semantic — Semantic Model Specialist
- Owns: `tmdl_generator.py` (structural parts: tables, relationships, Calendar, RLS, hierarchies, parameters, self-healing, TMDL writers)
- Owns: `fabric_semantic_model_generator.py`
- Expertise: TMDL structure, relationship cardinality, join graph analysis, data model correctness

### @visual — Report Visual Specialist
- Owns: `pbip_generator.py` (report parts: pages, visuals, slicers, filters, bookmarks, layout, formatting)
- Owns: `visual_generator.py`
- Expertise: PBIR v4.0 schema, visual type mapping (118+), slicer configuration, filter levels

## Data Flow

```
1. Orchestrator receives CLI command (migrate.py)
2. Orchestrator delegates to Extractor → 17 JSON files
3. Orchestrator delegates to conversion:
   a. @dax converts Tableau formulas → DAX expressions
   b. @wiring classifies measure vs calc column, builds M queries
4. Orchestrator delegates to generation:
   a. @semantic builds TMDL model (tables, relationships, Calendar, RLS)
   b. @visual builds PBIR report (pages, visuals, slicers, filters)
   c. @generator coordinates Fabric output (Lakehouse, Dataflow, Notebook, Pipeline)
5. @semantic runs self-healing (TMDL self-repair)
6. (Optional) @assessor → readiness report
7. (Optional) @merger → shared semantic model
8. (Optional) @deployer → Fabric/PBI workspace
9. @tester validates all steps with 7,072+ tests
```

## Handoff Protocol

When an agent encounters work outside its domain:

1. **Complete your part** — finish everything within your file scope
2. **State the handoff** — clearly describe what needs to happen next
3. **Name the target agent** — e.g., "Hand off to @semantic for TMDL updates"
4. **List artifacts** — specify files, functions, and data structures involved
5. **Include context** — provide any intermediate results (dicts, JSON) the next agent needs

## File Ownership Rules

- **One owner per file** — each source file has exactly one owning agent
- **Read access is universal** — any agent can read any file for context
- **Write access is restricted** — only the owning agent modifies a file
- **Tester is special** — reads all source files, writes only to `tests/`
- **Co-owned functions** — `tmdl_generator.py` has shared ownership: @semantic owns structural parts, @dax owns DAX post-processing, @wiring owns M functions
- **Cross-cutting** — `security_validator.py` is used by Extractor, Orchestrator, and Deployer (no single owner — all contributors coordinate)

## When NOT to Use Specialized Agents

Use the **default agent** (or @orchestrator) for:
- Quick questions about the project
- Multi-domain tasks that touch 3+ agents
- Documentation updates (CHANGELOG, README, etc.)
- Sprint planning and gap analysis
- Git operations (commit, push, branch)

## Agent Files

All agent definitions are in `.github/agents/`:
- `shared.instructions.md` — Base rules inherited by all agents
- `orchestrator.agent.md` — Pipeline coordination
- `extractor.agent.md` — Tableau parsing
- `dax.agent.md` — DAX formula specialist (NEW)
- `wiring.agent.md` — DAX↔M bridge specialist (NEW)
- `semantic.agent.md` — Semantic model specialist (NEW)
- `visual.agent.md` — Report visual specialist (NEW)
- `converter.agent.md` — Formula coordination layer (delegates to @dax + @wiring)
- `generator.agent.md` — Generation coordination layer (delegates to @semantic + @visual, owns Fabric)
- `assessor.agent.md` — Migration analysis + validation
- `merger.agent.md` — Multi-workbook merge (PBIP + Fabric)
- `deployer.agent.md` — Fabric/PBI deployment + multi-tenant
- `tester.agent.md` — Test creation and validation
