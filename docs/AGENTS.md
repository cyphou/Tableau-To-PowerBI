# Multi-Agent Architecture — Tableau to Power BI Migration

This project uses an **8-agent specialization model**. Each agent has scoped domain knowledge, file ownership, and clear boundaries.

## Quick Reference

| Agent | Invoke When | Owns |
|-------|-------------|------|
| **@orchestrator** | Pipeline coordination, CLI, batch, wizard | `migrate.py`, `import_to_powerbi.py`, `wizard.py`, `progress.py`, `incremental.py`, `plugins.py` |
| **@extractor** | Parsing Tableau XML, Hyper files, Prep flows, Server API | `tableau_export/*.py` (extract, datasource, hyper, pulse, prep, server) |
| **@converter** | Tableau→DAX formulas, Power Query M generation | `dax_converter.py`, `m_query_builder.py` |
| **@generator** | TMDL semantic model, PBIR report, visuals, Calendar | `tmdl_generator.py`, `pbip_generator.py`, `visual_generator.py`, `thin_report_generator.py`, `goals_generator.py`, `alerts_generator.py` |
| **@assessor** | Migration readiness, scoring, strategy, diff reports | `assessment.py`, `server_assessment.py`, `global_assessment.py`, `strategy_advisor.py`, `visual_diff.py`, `comparison_report.py`, `migration_report.py` |
| **@merger** | Shared semantic model, multi-workbook merge | `shared_model.py`, `merge_config.py` |
| **@deployer** | Fabric/PBI deployment, auth, gateway, telemetry | `deploy/*.py`, `gateway_config.py`, `telemetry.py`, `telemetry_dashboard.py` |
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
    │ (Tableau)  │   │ (DAX/M)   │   │ (PBI)      │
    └────────────┘   └───────────┘   └────────────┘
                                           │
                    ┌──────────────────┬────┴────┐
                    │                  │         │
              ┌─────▼─────┐    ┌──────▼──┐  ┌───▼────┐
              │  Assessor  │    │ Merger  │  │Deployer│
              │ (Analysis) │    │ (Merge) │  │(Fabric)│
              └────────────┘    └─────────┘  └────────┘

              ┌────────────────────────────────────────┐
              │              Tester                     │
              │    (Cross-cutting — reads all, writes   │
              │     only to tests/)                     │
              └────────────────────────────────────────┘
```

## Data Flow

```
1. Orchestrator receives CLI command (migrate.py)
2. Orchestrator delegates to Extractor → 16 JSON files
3. Orchestrator delegates to Converter → DAX/M formulas
4. Orchestrator delegates to Generator → .pbip (TMDL + PBIR)
5. (Optional) Orchestrator delegates to Assessor → readiness report
6. (Optional) Orchestrator delegates to Merger → shared semantic model
7. (Optional) Orchestrator delegates to Deployer → Fabric/PBI workspace
8. Tester validates all steps with 4,823+ tests
```

## Handoff Protocol

When an agent encounters work outside its domain:

1. **Complete your part** — finish everything within your file scope
2. **State the handoff** — clearly describe what needs to happen next
3. **Name the target agent** — e.g., "Hand off to @generator for TMDL updates"
4. **List artifacts** — specify files, functions, and data structures involved
5. **Include context** — provide any intermediate results (dicts, JSON) the next agent needs

## File Ownership Rules

- **One owner per file** — each source file has exactly one owning agent
- **Read access is universal** — any agent can read any file for context
- **Write access is restricted** — only the owning agent modifies a file
- **Tester is special** — reads all source files, writes only to `tests/`
- **Shared files** — `thin_report_generator.py` is co-owned by Generator + Merger

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
- `converter.agent.md` — Formula translation
- `generator.agent.md` — PBI artifact generation
- `assessor.agent.md` — Migration analysis
- `merger.agent.md` — Multi-workbook merge
- `deployer.agent.md` — Fabric/PBI deployment
- `tester.agent.md` — Test creation and validation
