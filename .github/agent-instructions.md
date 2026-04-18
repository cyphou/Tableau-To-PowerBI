# Agent Behavior Instructions — Tableau to Power BI Migration

Rules for AI coding agents working in this codebase. Read `.github/copilot-instructions.md` for full project context (architecture, file map, DAX/M/PBIR specs, visual mappings).

**Multi-agent architecture**: This project uses a 12-agent specialization model. See `docs/AGENTS.md` for the full architecture diagram, and `.github/agents/` for per-agent definitions.

---

## Project Context (Quick Reference)

- **Pipeline**: `.twbx` → Extraction (17 JSON files) → Generation (`.pbip` in PBIR v4.0 + TMDL)
- **Source**: `tableau_export/` (extraction + DAX converter + M query builder)
- **Target**: `powerbi_import/` (TMDL generator + PBIR report + visual generator)
- **Tests**: `pytest tests/ --tb=short -q` — currently **7,072 tests** across 141+ files
- **Python**: 3.12+ stdlib only — **no external dependencies** for core migration
- **Dev plan**: `docs/DEVELOPMENT_PLAN.md` — check current sprint before starting work
- **Agents**: 12 specialized agents in `.github/agents/` — see `docs/AGENTS.md`

---

## Learned Lessons (Hard-Won — DO NOT Repeat These Mistakes)

These are real bugs that occurred during development. Review before every implementation task.

### Function Name Traps
- Use `convert_tableau_formula_to_dax()` — **NOT** `convert_tableau_to_dax()` (doesn't exist)
- Use `resolve_custom_visual_type()` for tuple returns `(visual_type, custom_info)`
- Use `resolve_visual_type()` for string returns (visual type name only)
- `GatewayConfigGenerator()` takes **no constructor args** — pass datasources to methods
- Always `grep_search` for an existing function/class name before creating a new one

### Regex Pitfalls in DAX Converter
- **Infinite loop risk**: regex replacement text must NOT match the search pattern (e.g., `WINDOW_AVG` replacement contained text that re-matched the `WINDOW_` pattern — caused infinite loop)
- **Comment text re-matching**: when adding `/* comment */` after a conversion, ensure the comment text doesn't contain the original Tableau function name that would re-trigger the regex
- Always test regex patterns with `re.sub()` on edge-case inputs before committing

### Deduplication & Shadowing
- `resolve_visual_type` was accidentally shadowed by a second definition with different return type — check for duplicate function names in the same file
- Tables are deduplicated by the extractor (`type="table"` filtering) — don't re-deduplicate downstream
- Parameters appear in both old and new XML formats — both feed `param_map`, so dedup logic must handle both sources

### API & Signature Mismatches
- Test function signatures MUST match implementation — if you change a constructor, update ALL callers AND tests
- `GatewayConfigGenerator` API mismatch caused 5 test failures that cascaded — always verify the call site
- Python 3.14 changed `Element.__bool__()` behavior — use `elem is not None` instead of `if elem` or `elem or other_elem`

### File Edit Tool Gotchas
- When a table/section appears TWICE in a file, `replace_string_in_file` fails with "Multiple matches" — use unique surrounding context (headings, nearby unique text) to disambiguate
- Always include 3-5 lines of unchanged context before and after the target text
- Read the file FIRST, then edit — never assume content from memory or conversation summaries

---

## Workflow Rules

### 1. Plan Before Build
- Use your native task tracker (manage_todo_list) for multi-step work
- For sprints: read `docs/DEVELOPMENT_PLAN.md` first to understand scope and sequencing
- If something goes sideways, STOP and re-plan — don't keep pushing broken code

### 2. Read Before Write
- **Always read target code before editing** — never assume file contents
- Read `copilot-instructions.md` at session start for project rules
- Check `docs/DEVELOPMENT_PLAN.md` for current sprint context

### 3. Testing Contract
- Run `pytest tests/ --tb=short -q` after EVERY implementation change
- If tests fail → fix them before reporting completion
- New features **require** new tests — no exceptions
- Never weaken test assertions to make tests pass
- Include test command + pass/fail count in completion summary
- For coverage work: `pytest tests/ --cov=powerbi_import --cov=tableau_export --cov-report=term-missing --tb=no -q`

### 4. Scope Discipline
- Only modify files directly related to the task
- No drive-by refactors, no "while I'm here" improvements
- If you spot an unrelated issue, note it in your summary — don't fix it
- **No external dependencies** — stdlib only for core migration
- Prefer the smallest change that solves the problem

### 5. Git Hygiene
- Commit with conventional-style messages: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`
- Never commit generated artifacts, `__pycache__/`, or temp files
- Stage only files related to the current task
- Push only when tests pass

### 6. Autonomous Execution
- When given a bug → fix it. Don't ask for hand-holding
- When given a feature → implement it + write tests + run suite
- Don't ask "should I continue?" — always continue until done
- Don't explain what you're "about to do" — do it, then summarize

---

## Project-Specific Rules

1. **Calculated columns vs measures** — 3-factor classification:
   - Has aggregation (SUM, COUNT...) → measure
   - No aggregation + has column references → calculated column
   - No aggregation + no column refs → measure
2. **RELATED()** — manyToOne cross-table refs only
3. **LOOKUPVALUE()** — manyToMany cross-table refs only
4. **SUM(IF(...))** → `SUMX('table', IF(...))` (also AVG→AVERAGEX, etc.)
5. **SemanticModel** — PBI naming convention (not "Dataset")
6. **Apostrophes** — escaped in TMDL: `'name'` → `''name''`
7. **Single-line DAX** — multi-line formulas must be condensed
8. **Test framework** — `unittest.TestCase` classes, run via `pytest`
9. **Two XML parameter formats** — old `<column[@param-domain-type]>` + new `<parameters><parameter>`

---

## Anti-Patterns (Never Do These)

- Don't create summary/documentation files unless asked
- Don't use placeholder values like "TODO" or "FIXME" in shipped code
- Don't add a function with a name that already exists in the same module
- Don't write regex replacements where the output matches the input pattern
- Don't assume `Element` truthiness in Python 3.14+ — use `is not None`
- Don't call `convert_tableau_to_dax()` — it doesn't exist
- Don't touch `tasks/` directory — this project doesn't use it
- Don't add external dependencies without explicit user approval
- Don't batch-replace text that appears in multiple locations — disambiguate first
