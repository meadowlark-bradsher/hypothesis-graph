# HG Builder v0

`hg_builder_v0` is a fact-log-first, domain-agnostic Layer-C graph construction package for FCA workflows.

## Principles

- append-only fact log is canonical truth
- explicit polarity: `present | absent | unknown`
- open-world by default (unknown is never silently converted to absent)
- retractions are tombstones (`status=retracted`, `retracts_fact_id`), never overwrites
- domain-neutral IDs: `object_id`, `attribute_id`

## Package Layout

- `hg_builder_v0/hg_core_ir`: Pydantic IR + JSON schema export
- `hg_builder_v0/hg_factlog`: append/read/index fact logs
- `hg_builder_v0/hg_materialize`: validity + overlay + retraction materialization
- `hg_builder_v0/hg_fca_export`: incidence export + local lattice build
- `hg_builder_v0/hg_compile`: policy-driven mask compilation
- `hg_builder_v0/migration`: legacy snapshot migration hook
- `hg_builder_v0/hg_cli.py`: Typer CLI (`hg`)

## Canonical IR Files

Use `hg init` to scaffold and export:

- `fact_v1.json`
- `constraint_v1.json`
- `manifest_v1.json`

## CLI

```bash
hg init --path ./workspace
hg append-facts --fact-log ./workspace/facts/facts.jsonl --input ./facts_batch.jsonl
hg retract-fact --fact-log ./workspace/facts/facts.jsonl --fact-id <fact_id>
hg materialize-snapshot --base-log ./workspace/facts/facts.jsonl --output ./workspace/snapshots/snapshot.json
hg compile-masks --snapshot ./workspace/snapshots/snapshot.json --policy open_world --output ./workspace/build/masks.json
hg build-lattice --snapshot ./workspace/snapshots/snapshot.json --output ./workspace/build/lattice.json
hg validate --fact-log ./workspace/facts/facts.jsonl --manifest ./workspace/manifest_v1.json
```

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
