# Bulk TFL/TFLX — Global Lineage Report & Merge Advisor

## Goal

Analyze an entire portfolio of Tableau Prep flows (`.tfl`/`.tflx`) in bulk, build a **cross-flow lineage graph** (sources → transforms → outputs), generate a **global HTML report**, and **propose merges** to simplify the data preparation landscape before migration.

---

## Current State

| Capability | Status |
|---|---|
| Parse single `.tfl`/`.tflx` → M queries | ✅ Done (`prep_flow_parser.py`) |
| Standalone TFL migration (single + batch) | ✅ Done (`run_standalone_prep()` in `migrate.py`) |
| DAG traversal inside a single flow | ✅ Done (`_topological_sort`, `_process_prep_node`) |
| Input node → connection + table extraction | ✅ Done (`_parse_input_node`) |
| Output node detection | ✅ Done (output flags + leaf-node fallback) |
| Cross-flow lineage | ❌ Not yet |
| Global Prep portfolio report | ❌ Not yet |
| Flow merge recommendations | ❌ Not yet |

---

## Architecture — 3-Phase Pipeline

```
 Phase 1                    Phase 2                    Phase 3
┌──────────┐          ┌──────────────────┐       ┌──────────────────┐
│ Parse    │          │ Build Global     │       │ Merge Advisor    │
│ All TFLs │──JSON──▶ │ Lineage Graph    │──▶    │ + HTML Report    │
│          │          │                  │       │                  │
└──────────┘          └──────────────────┘       └──────────────────┘
  per-flow              cross-flow                 recommendations
  extraction            stitching                  + interactive HTML
```

---

## Phase 1 — Per-Flow Metadata Extraction

**Owner**: `@extractor`
**New file**: `tableau_export/prep_flow_analyzer.py`
**Depends on**: `prep_flow_parser.py` (reuses `read_prep_flow`, `_topological_sort`, `_get_node_type`, `_parse_input_node`)

### Data Model — `FlowProfile`

```python
@dataclass
class FlowProfile:
    """Complete metadata for one Tableau Prep flow."""
    name: str                    # Flow filename (without extension)
    file_path: str               # Absolute path to .tfl/.tflx
    
    # Inputs (sources)
    inputs: List[FlowInput]      # Each source connection
    
    # Outputs (destinations)
    outputs: List[FlowOutput]    # Each output / publish target
    
    # Transformations
    transforms: List[FlowTransform]  # Clean, Aggregate, Join, Union, Pivot, Script
    
    # Internal DAG
    node_count: int
    edge_count: int
    dag_depth: int               # Longest path from input to output
    
    # Complexity signals
    join_count: int
    union_count: int
    script_count: int            # Python/R scripts (manual migration)
    calc_count: int              # Calculated fields
    
    # Raw node graph (for lineage stitching)
    node_graph: Dict[str, List[str]]  # node_id → [downstream_ids]

@dataclass
class FlowInput:
    """A source feeding into a Prep flow."""
    node_id: str
    name: str
    connection_type: str          # postgres, snowflake, csv, etc.
    server: str
    database: str
    schema: str
    table_name: str
    filename: str                 # For file-based sources
    column_count: int
    column_names: List[str]
    fingerprint: str              # SHA-256 of (type+server+db+schema+table)

@dataclass
class FlowOutput:
    """A destination produced by a Prep flow."""
    node_id: str
    name: str
    output_type: str              # PublishExtract, SaveToFile, SaveToDatabase
    target_server: str
    target_database: str
    target_table: str
    target_filename: str
    column_count: int
    column_names: List[str]
    fingerprint: str              # SHA-256 of output target

@dataclass
class FlowTransform:
    """A transformation step inside a Prep flow."""
    node_id: str
    name: str
    transform_type: str           # Clean, Aggregate, Join, Union, Pivot, Script
    details: Dict[str, Any]       # Type-specific metadata
```

### Functions

| Function | Purpose |
|---|---|
| `analyze_flow(filepath) → FlowProfile` | Parse one TFL/TFLX, extract full metadata |
| `analyze_flows_bulk(directory) → List[FlowProfile]` | Scan dir, analyze all `.tfl`/`.tflx` |
| `_extract_inputs(nodes, connections) → List[FlowInput]` | Collect all input nodes |
| `_extract_outputs(nodes, node_results) → List[FlowOutput]` | Collect all output/leaf nodes |
| `_extract_transforms(sorted_ids, nodes) → List[FlowTransform]` | Classify each transform step |
| `_compute_dag_depth(nodes) → int` | Longest path in the flow DAG |
| `_fingerprint_endpoint(type, server, db, schema, table) → str` | SHA-256 fingerprint for matching |

### Estimated effort: ~250 lines

---

## Phase 2 — Cross-Flow Lineage Graph

**Owner**: `@assessor`
**New file**: `powerbi_import/prep_lineage.py`
**Depends on**: `prep_flow_analyzer.py` (FlowProfile, FlowInput, FlowOutput)

### Concept

Tableau Prep flows form a **multi-flow DAG**: one flow's output can be another flow's input. We detect this by **fingerprint matching**: if Flow A's output fingerprint matches Flow B's input fingerprint, there's a lineage edge.

```
Flow A (CSV → Clean → Publish "Sales_Clean")
         ↓ (fingerprint match)
Flow B ("Sales_Clean" → Join with "Products" → Output "Sales_Enriched")
         ↓ (fingerprint match)
Flow C ("Sales_Enriched" → Aggregate → Output "Sales_Summary")
```

### Data Model — `PrepLineageGraph`

```python
@dataclass
class LineageEdge:
    """A cross-flow connection: one flow's output feeds another flow's input."""
    source_flow: str              # Flow name producing the data
    source_output: str            # Output node name
    target_flow: str              # Flow name consuming the data
    target_input: str             # Input node name
    match_type: str               # 'exact' (fingerprint) or 'fuzzy' (name similarity)
    confidence: float             # 0.0–1.0

@dataclass  
class SourceEndpoint:
    """An external source (not produced by any flow in the portfolio)."""
    fingerprint: str
    connection_type: str
    server: str
    database: str
    table_name: str
    consumed_by: List[Tuple[str, str]]  # [(flow_name, input_name)]

@dataclass
class SinkEndpoint:
    """A final output (not consumed by any flow in the portfolio)."""
    fingerprint: str
    output_type: str
    target_table: str
    produced_by: Tuple[str, str]  # (flow_name, output_name)

@dataclass
class PrepLineageGraph:
    """Cross-flow lineage for the entire Prep portfolio."""
    flows: List[FlowProfile]
    edges: List[LineageEdge]           # Cross-flow connections
    external_sources: List[SourceEndpoint]  # True data origins
    final_sinks: List[SinkEndpoint]    # Terminal outputs
    
    # Topology
    layers: List[List[str]]            # Topological layers (parallel execution groups)
    isolated_flows: List[str]          # Flows with no cross-flow edges
    chains: List[List[str]]            # Linear chains (A→B→C)
    
    # Statistics
    total_flows: int
    total_sources: int
    total_outputs: int
    total_transforms: int
    total_cross_flow_edges: int
    max_chain_depth: int
```

### Functions

| Function | Purpose |
|---|---|
| `build_lineage_graph(profiles) → PrepLineageGraph` | Main orchestrator |
| `_match_outputs_to_inputs(profiles) → List[LineageEdge]` | Fingerprint + fuzzy name matching |
| `_identify_external_sources(profiles, edges) → List[SourceEndpoint]` | Sources not produced by any flow |
| `_identify_final_sinks(profiles, edges) → List[SinkEndpoint]` | Outputs not consumed by any flow |
| `_compute_flow_layers(profiles, edges) → List[List[str]]` | Topological layering for visualization |
| `_detect_chains(profiles, edges) → List[List[str]]` | Find linear flow chains |
| `_fuzzy_match_name(output_name, input_name) → float` | Name similarity (normalized Levenshtein-like) |

### Matching Strategy

1. **Exact fingerprint match** (confidence=1.0): SHA-256 of (type+server+db+schema+table) between output and input
2. **Table name match** (confidence=0.8): Same table name, same connection type, different server (dev→prod)
3. **Fuzzy name match** (confidence=0.5–0.7): Published datasource name ≈ input reference name
4. **Published DS match** (confidence=0.9): Output is `PublishExtract`, input is `LoadPublishedDataSource` with matching name

### Estimated effort: ~350 lines

---

## Phase 3 — Global Report & Merge Advisor

**Owner**: `@assessor` (report) + `@merger` (merge logic)
**New file**: `powerbi_import/prep_lineage_report.py`
**Depends on**: `prep_lineage.py`, `html_template.py`

### HTML Report Sections

The report uses the existing `html_template.py` components (stat_grid, data_table, badge, section_open/close, flow_diagram, heatmap_table).

#### Section 1 — Executive Summary (stat cards)

| Card | Value |
|---|---|
| Total Flows | N |
| External Sources | N |
| Final Outputs | N |
| Cross-Flow Edges | N |
| Max Chain Depth | N |
| Merge Candidates | N |

#### Section 2 — Flow Inventory Table

| Flow | Inputs | Outputs | Transforms | Joins | Complexity | Status |
|---|---|---|---|---|---|---|
| Sales_Prep | 3 | 1 | 12 | 2 | Medium | 🟢 |
| Products_Clean | 1 | 1 | 5 | 0 | Low | 🟢 |
| Combined_ETL | 4 | 2 | 22 | 3 | High | 🟡 |

Complexity = weighted score: `joins×3 + unions×2 + scripts×5 + calcs×1 + nodes×0.5`

#### Section 3 — Source Inventory (all external sources across all flows)

| Source | Connection | Server | Database | Table | Used By (flows) |
|---|---|---|---|---|---|
| PostgreSQL | postgres | prod-db | analytics | orders | Sales_Prep, Returns_Prep |
| CSV file | csv | — | — | products.csv | Products_Clean |

Highlight **shared sources** (used by 2+ flows) with a badge.

#### Section 4 — Output Inventory (all final outputs)

| Output | Type | Target | Produced By | Consumed By |
|---|---|---|---|---|
| Sales_Clean | PublishExtract | Tableau Server | Sales_Prep | Combined_ETL |
| Sales_Summary | SaveToFile | /exports/summary.hyper | Combined_ETL | (none — final) |

#### Section 5 — Lineage Diagram (flow diagram / Mermaid-like)

Interactive visual showing the full cross-flow DAG:
- **External sources** (leftmost, blue boxes)
- **Flows** (middle, gray boxes with transform count badge)
- **Final outputs** (rightmost, green boxes)
- **Edges** with labels (fingerprint match or fuzzy)

Use the existing `flow_diagram()` component from `html_template.py`, or generate a Mermaid-compatible diagram with JS rendering.

#### Section 6 — Merge Recommendations

Based on the lineage analysis, propose simplifications:

| Recommendation | Type | Details | Impact |
|---|---|---|---|
| Merge Sales_Prep + Returns_Prep | **Source Consolidation** | Both read from same 3 tables, share 2 transforms | Eliminate 1 flow |
| Chain Sales_Prep → Combined_ETL | **Chain Collapse** | Linear A→B with no fan-out | Merge into 1 flow |
| Deduplicate "orders" source | **Source Dedup** | Read by 3 flows, could use shared query | Reduce 3→1 connections |

### Merge Recommendation Types

| Type | Detection Rule | Recommendation |
|---|---|---|
| **Source Consolidation** | 2+ flows reading identical sources (≥70% fingerprint overlap) | Merge flows into one |
| **Chain Collapse** | Linear chain A→B→C with no fan-out | Combine into single flow |
| **Source Dedup** | Same source fingerprint used by 3+ flows | Extract to shared Dataflow query |
| **Redundant Output** | Two flows producing same output fingerprint | Keep one, remove duplicate |
| **Fan-in Simplification** | Output consumed by 3+ downstream flows | Consider materializing earlier |
| **Isolated Flow** | Flow with no cross-flow edges | Standalone migration (no merge needed) |

### Merge Scoring

Each merge recommendation gets a score (0–100):
- **Source overlap** (0–40): % of shared source fingerprints between candidate flows
- **Transform similarity** (0–30): % of similar transform types in same order
- **Column overlap** (0–20): Jaccard similarity of output column sets
- **Complexity reduction** (0–10): Estimated node reduction from merging

Score ≥ 70 → **Strong merge** (green badge)
Score 40–69 → **Possible merge** (yellow badge)
Score < 40 → **Keep separate** (gray badge)

### Functions

| Function | Purpose |
|---|---|
| `generate_prep_lineage_report(graph, output_path)` | Main HTML report generator |
| `_render_executive_summary(graph) → str` | Stat cards HTML |
| `_render_flow_inventory(graph) → str` | Flow table HTML |
| `_render_source_inventory(graph) → str` | Source table HTML |
| `_render_output_inventory(graph) → str` | Output table HTML |
| `_render_lineage_diagram(graph) → str` | Flow diagram / Mermaid HTML |
| `_render_merge_recommendations(recs) → str` | Merge table HTML |
| `compute_merge_recommendations(graph) → List[MergeRec]` | Core merge advisor logic |
| `save_lineage_json(graph, output_path)` | JSON export for programmatic use |

### Estimated effort: ~500 lines

---

## Phase 4 — CLI Integration

**Owner**: `@orchestrator`
**File**: `migrate.py`

### New CLI Flags

```bash
# Analyze a directory of .tfl/.tflx files and produce lineage report
python migrate.py --prep-lineage path/to/prep_flows/

# Analyze specific TFL files  
python migrate.py --prep-lineage flow1.tfl flow2.tfl flow3.tflx

# Combine with batch workbook migration
python migrate.py --batch examples/ --prep-lineage path/to/prep_flows/

# Output directory for the report
python migrate.py --prep-lineage path/to/flows/ --output-dir /tmp/lineage_output
```

### Flow

```python
def run_prep_lineage_mode(args):
    """Bulk TFL analysis with cross-flow lineage and merge recommendations."""
    # 1. Collect .tfl/.tflx files
    # 2. analyze_flows_bulk() → List[FlowProfile]
    # 3. build_lineage_graph() → PrepLineageGraph
    # 4. compute_merge_recommendations() → List[MergeRec]
    # 5. generate_prep_lineage_report() → HTML
    # 6. save_lineage_json() → JSON
```

### Estimated effort: ~80 lines

---

## Phase 5 — Tests

**Owner**: `@tester`
**New file**: `tests/test_prep_lineage.py`

### Test Categories

| Category | Tests | Description |
|---|---|---|
| FlowProfile extraction | ~10 | Single flow → correct inputs/outputs/transforms |
| Fingerprint matching | ~8 | Exact, fuzzy, published DS, no match |
| Lineage graph | ~8 | Chains, fan-out, fan-in, isolated, cycles |
| Merge recommendations | ~10 | Source consolidation, chain collapse, dedup, scoring |
| HTML report | ~6 | Section rendering, stat cards, Mermaid output |
| CLI integration | ~4 | --prep-lineage flag, directory scan, output files |
| Edge cases | ~6 | Empty dir, single flow, all isolated, circular refs |

### Estimated: ~52 tests, ~600 lines

---

## Sprint Plan

### Sprint A — Foundation (Phase 1 + Phase 2)

| Task | File | Lines | Priority |
|---|---|---|---|
| `FlowProfile` dataclasses | `prep_flow_analyzer.py` | 80 | P0 |
| `analyze_flow()` — single flow extraction | `prep_flow_analyzer.py` | 100 | P0 |
| `analyze_flows_bulk()` — directory scan | `prep_flow_analyzer.py` | 40 | P0 |
| Fingerprint function | `prep_flow_analyzer.py` | 30 | P0 |
| `PrepLineageGraph` dataclasses | `prep_lineage.py` | 60 | P0 |
| `build_lineage_graph()` — cross-flow stitching | `prep_lineage.py` | 120 | P0 |
| Fingerprint matching + fuzzy matching | `prep_lineage.py` | 80 | P0 |
| Layer computation + chain detection | `prep_lineage.py` | 90 | P1 |
| Tests for Phase 1 + 2 | `test_prep_lineage.py` | 350 | P0 |

**Total: ~950 lines**

### Sprint B — Report & Merge Advisor (Phase 3 + Phase 4)

| Task | File | Lines | Priority |
|---|---|---|---|
| Merge recommendation engine | `prep_lineage_report.py` | 150 | P0 |
| Merge scoring (source overlap, transform sim, column overlap) | `prep_lineage_report.py` | 100 | P0 |
| HTML Executive Summary | `prep_lineage_report.py` | 40 | P0 |
| HTML Flow Inventory table | `prep_lineage_report.py` | 40 | P0 |
| HTML Source + Output Inventory | `prep_lineage_report.py` | 60 | P1 |
| HTML Lineage Diagram (Mermaid) | `prep_lineage_report.py` | 80 | P1 |
| HTML Merge Recommendations table | `prep_lineage_report.py` | 50 | P0 |
| JSON export | `prep_lineage_report.py` | 30 | P1 |
| `--prep-lineage` CLI flag | `migrate.py` | 80 | P0 |
| Tests for Phase 3 + 4 | `test_prep_lineage.py` | 250 | P0 |

**Total: ~880 lines**

---

## File Ownership Summary

| File | Owner | New/Edit |
|---|---|---|
| `tableau_export/prep_flow_analyzer.py` | @extractor | **New** (~250 lines) |
| `powerbi_import/prep_lineage.py` | @assessor | **New** (~350 lines) |
| `powerbi_import/prep_lineage_report.py` | @assessor + @merger | **New** (~500 lines) |
| `migrate.py` | @orchestrator | Edit (~80 lines) |
| `tests/test_prep_lineage.py` | @tester | **New** (~600 lines) |
| `docs/PREP_LINEAGE_PLAN.md` | default | **This file** |

**Total new code: ~1,780 lines + ~600 test lines**

---

## Dependencies

- **Zero external dependencies** — all standard library (consistent with project rules)
- Reuses: `prep_flow_parser.py` (read + parse), `html_template.py` (report components), `shared_model.py` (fingerprinting pattern)
- Optional: Mermaid JS CDN for interactive lineage diagram rendering (embedded `<script>` tag, no install)

---

## Output Artifacts

```
output_dir/
├── prep_lineage_report.html    # Interactive HTML report (all 6 sections)
├── prep_lineage.json           # Machine-readable lineage graph
├── flow_profiles/              # Per-flow JSON profiles
│   ├── Sales_Prep.json
│   ├── Products_Clean.json
│   └── Combined_ETL.json
└── merge_recommendations.json  # Actionable merge proposals with scores
```

---

## Example CLI Session

```bash
# Analyze all Prep flows in a directory
$ python migrate.py --prep-lineage examples/prep_flows/

  ═══════════════════════════════════════════════════════
   PREP FLOW LINEAGE ANALYSIS
  ═══════════════════════════════════════════════════════
  
  Scanning: examples/prep_flows/
  Found 12 Tableau Prep flows (.tfl/.tflx)
  
  [1/12] Analyzing: Sales_Prep.tfl
    → 3 inputs, 1 output, 12 transforms
  [2/12] Analyzing: Products_Clean.tflx
    → 1 input, 1 output, 5 transforms
  ...
  
  ── Cross-Flow Lineage ──
  Detected 8 cross-flow connections:
    Sales_Prep → Combined_ETL (exact fingerprint)
    Products_Clean → Combined_ETL (exact fingerprint)
    Combined_ETL → Summary_Agg (table name match)
    ...
  
  ── Merge Recommendations ──
  🟢 Strong merge: Sales_Prep + Returns_Prep (score: 82/100)
     → Both read orders/customers/products, share 5 transforms
  🟡 Possible: Chain collapse Sales_Prep → Combined_ETL (score: 65/100)
  ⚪ Keep separate: Products_Clean (isolated, score: 15/100)
  
  Reports saved to:
    HTML:  artifacts/prep_lineage_report.html
    JSON:  artifacts/prep_lineage.json
```
