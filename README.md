# Belief-Intervention-Graph (BIG)

This repository implements a Belief-Intervention-Graph workflow for uncertainty-aware hypothesis discovery:

- Belief: FCA-compatible hypothesis coverage over an append-only fact log
- Intervention: controlled fault injections and live trajectory collection
- Graph: emergent causal structure distilled from repeated evidence

The design goal is to preserve correctness under uncertainty while progressively learning useful causal structure.

## BIG Architecture

The system is organized as three cooperating tiers:

1. Tier 1 - Belief Layer (FCA)
- hypothesis templates
- observation predicates
- monotone elimination with open-world semantics

2. Tier 2 - Intervention Layer (Chaos/Live Runs)
- controlled injections
- trajectory capture from metrics/logs/traces/events
- empirical dependency and propagation discovery

3. Tier 3 - Graph Distillation Layer (Agentic/Heuristic)
- alias normalization
- mechanism extraction
- edge reconstruction and candidate causal pathways

The tiers operate in loops:

- back to Tier 1 when coverage gaps are found
- back to Tier 2 when empirical validation is required
- back to Tier 3 when structural compression is needed

See `docs/architecture-overview.md` for the full design.

## What This Repo Provides

### Core package (`hg_builder_v0`)

- `hg_core_ir`: Pydantic IR + JSON schema export
- `hg_factlog`: append/read/index fact logs
- `hg_materialize`: validity + overlay + retraction materialization
- `hg_fca_export`: incidence export + lattice build
- `hg_compile`: policy-driven mask compilation
- `migration`: legacy snapshot migration hook
- `hg_cli.py`: Typer CLI (`hg`)

### BIG support scripts

- `itbench_ingest.py`: ITBench ground-truth -> fact log ingestion
- `itbench_fca_all.py`: FCA-oriented multi-scenario analysis
- `itbench_live_graph_eval.py`: live artifact graph evaluation
- `alias_normalizer.py`: cross-object/component canonicalization
- `mechanism_extractor.py`: mechanism tags from artifact evidence
- `edge_builder.py`: candidate edge reconstruction

## Core Data/Reasoning Invariants

- append-only fact log is canonical truth
- explicit polarity: `present | absent | unknown`
- open-world by default (`unknown` is not silently cast to `absent`)
- retractions are tombstones (`status=retracted`, `retracts_fact_id`), never overwrites
- IDs are domain-neutral (`object_id`, `attribute_id`)

These invariants make Tier 1 (belief control) deterministic and order-invariant.

## Canonical IR Files

Use `hg init` to scaffold/export:

- `fact_v1.json`
- `constraint_v1.json`
- `manifest_v1.json`

## CLI Quickstart

```bash
hg init --path ./workspace
hg append-facts --fact-log ./workspace/facts/facts.jsonl --input ./facts_batch.jsonl
hg retract-fact --fact-log ./workspace/facts/facts.jsonl --fact-id <fact_id>
hg materialize-snapshot --base-log ./workspace/facts/facts.jsonl --output ./workspace/snapshots/snapshot.json
hg compile-masks --snapshot ./workspace/snapshots/snapshot.json --policy open_world --output ./workspace/build/masks.json
hg build-lattice --snapshot ./workspace/snapshots/snapshot.json --output ./workspace/build/lattice.json
hg validate --fact-log ./workspace/facts/facts.jsonl --manifest ./workspace/manifest_v1.json
```

## Typical BIG Loop

1. Initialize hypothesis templates and predicates (Tier 1).
2. Ingest benchmark/live artifacts into fact log.
3. Materialize snapshot and run FCA/lattice analysis.
4. Run interventions and collect trajectories (Tier 2).
5. Normalize entities, tag mechanisms, reconstruct edges (Tier 3).
6. Feed discovered dependencies and observability gaps back into Tier 1.
7. Repeat until belief space contracts and graph structure stabilizes.

## Tests

```bash
pytest
```

Acceptance coverage includes:

- open-world preservation
- retraction behavior
- overlay composition
- validity-window filtering

## Docs Site (GitHub Pages)

- URL: `https://meadowlark-bradsher.github.io/hypothesis-graph/`
- Source: `docs/`
- Workflow: `.github/workflows/deploy-pages.yml`

Setup once in repository settings:

1. Open `Settings -> Pages`.
2. Set `Build and deployment` source to `GitHub Actions`.
3. Push to `feature/fca-hg` (or run workflow manually).
