from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import typer

from hg_builder_v0.hg_compile.compile_masks import CompilePolicy, compile_masks, write_compiled_masks
from hg_builder_v0.hg_core_ir.models import (
    FactStatus,
    FactV1,
    ManifestV1,
    Polarity,
    ProvenanceV1,
    SourceType,
)
from hg_builder_v0.hg_core_ir.schema_export import export_schemas
from hg_builder_v0.hg_factlog.store import FactIndex, append_fact, append_facts
from hg_builder_v0.hg_fca_export.export import build_incidence, export_incidence
from hg_builder_v0.hg_fca_export.lattice import build_lattice, write_lattice
from hg_builder_v0.hg_materialize.materialize import MaterializeFilters, MaterializedSnapshot, materialize_snapshot

app = typer.Typer(help="HG Builder v0: fact-log-first, domain-agnostic graph builder")


def _parse_datetime(value: Optional[str]) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _load_fact_payloads(path: Path) -> list[dict]:
    if path.suffix.lower() == ".jsonl":
        rows: list[dict] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            raw = line.strip()
            if not raw:
                continue
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError(f"Expected object JSON in {path}:{line_number}")
            rows.append(payload)
        return rows

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        if any(not isinstance(item, dict) for item in payload):
            raise ValueError(f"Expected list[object] in {path}")
        return payload
    raise ValueError(f"Unsupported input structure in {path}")


def _snapshot_from_payload(payload: dict) -> MaterializedSnapshot:
    assertions = [FactV1.model_validate(row) for row in payload.get("effective_assertions", [])]
    conflicts_report = payload.get("conflicts_report", [])
    duplicates = payload.get("duplicate_fact_ids", [])
    retracted = payload.get("retracted_fact_ids", [])
    return MaterializedSnapshot(
        effective_assertions=assertions,
        conflicts_report=list(conflicts_report) if isinstance(conflicts_report, list) else [],
        duplicate_fact_ids=list(duplicates) if isinstance(duplicates, list) else [],
        retracted_fact_ids=list(retracted) if isinstance(retracted, list) else [],
    )


@app.command("init")
def init_workspace(path: str = typer.Option(".", help="Workspace root to initialize")) -> None:
    root = Path(path)
    dirs = {
        "facts": root / "facts",
        "constraints": root / "constraints",
        "schemas": root / "schemas",
        "snapshots": root / "snapshots",
        "build": root / "build",
    }
    for directory in dirs.values():
        directory.mkdir(parents=True, exist_ok=True)

    schemas = export_schemas(dirs["schemas"])

    manifest = ManifestV1(
        run_id="init",
        created_at=datetime.now(timezone.utc),
        fact_logs=[str(dirs["facts"] / "facts.jsonl")],
        constraint_logs=[str(dirs["constraints"] / "constraints.jsonl")],
        overlays=[],
        description="Scaffolded by hg init",
    )
    (root / "manifest_v1.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    typer.echo(json.dumps({"workspace": str(root), "schemas": schemas}, indent=2, sort_keys=True))


@app.command("append-facts")
def append_facts_command(
    fact_log: str = typer.Option(..., help="Path to facts.jsonl"),
    input_path: str = typer.Option(..., "--input", help="Path to JSON/JSONL facts payload"),
) -> None:
    payloads = _load_fact_payloads(Path(input_path))
    facts = [FactV1.model_validate(payload) for payload in payloads]
    count = append_facts(fact_log, facts)
    typer.echo(json.dumps({"fact_log": fact_log, "appended": count}, indent=2, sort_keys=True))


@app.command("retract-fact")
def retract_fact(
    fact_log: str = typer.Option(..., help="Path to facts.jsonl"),
    fact_id: str = typer.Option(..., help="fact_id to retract"),
    source_type: SourceType = typer.Option(SourceType.HUMAN, help="Provenance source type"),
    source_id: str = typer.Option("cli", help="Provenance source id"),
) -> None:
    index = FactIndex.from_logs(fact_log)
    target = index.find_fact(fact_id)
    if target is None:
        raise typer.BadParameter(f"fact_id not found: {fact_id}")

    event = FactV1(
        fact_id=str(uuid4()),
        object_id=target.object_id,
        attribute_id=target.attribute_id,
        polarity=target.polarity,
        provenance=ProvenanceV1(source_type=source_type, source_id=source_id),
        status=FactStatus.RETRACTED,
        retracts_fact_id=fact_id,
    )
    append_fact(fact_log, event)
    typer.echo(json.dumps({"fact_log": fact_log, "retracted": fact_id, "retraction_fact_id": event.fact_id}, indent=2, sort_keys=True))


@app.command("materialize-snapshot")
def materialize_snapshot_command(
    base_log: list[str] = typer.Option(..., help="One or more base fact logs", show_default=False),
    overlay_log: list[str] = typer.Option([], help="Optional overlay fact logs"),
    graph_version: int | None = typer.Option(None, help="Graph version filter"),
    as_of_time: str | None = typer.Option(None, help="ISO-8601 timestamp filter"),
    environment: str | None = typer.Option(None, help="Environment filter"),
    output: str = typer.Option(..., help="Output materialized snapshot JSON path"),
) -> None:
    filters = MaterializeFilters(
        graph_version=graph_version,
        as_of_time=_parse_datetime(as_of_time),
        environment=environment,
    )
    snapshot = materialize_snapshot(base_logs=base_log, overlays=overlay_log, filters=filters)

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    typer.echo(
        json.dumps(
            {
                "output": str(out),
                "effective_assertions": len(snapshot.effective_assertions),
                "conflicts": len(snapshot.conflicts_report),
            },
            indent=2,
            sort_keys=True,
        )
    )


@app.command("build-lattice")
def build_lattice_command(
    snapshot: str = typer.Option(..., help="Materialized snapshot JSON path"),
    output: str = typer.Option(..., help="Output lattice JSON path"),
    incidence_dir: str | None = typer.Option(None, help="Optional directory to export incidence artifacts"),
) -> None:
    payload = json.loads(Path(snapshot).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise typer.BadParameter("snapshot must be a JSON object")

    materialized = _snapshot_from_payload(payload)

    if incidence_dir:
        export_incidence(materialized, incidence_dir, include_absent=True)

    incidence = build_incidence(materialized)
    lattice = build_lattice(incidence)
    write_lattice(output, lattice)
    typer.echo(json.dumps({"output": output, "nodes": len(lattice["nodes"]), "edges": len(lattice["edges"])}, indent=2, sort_keys=True))


@app.command("validate")
def validate_command(
    fact_log: str = typer.Option(..., help="Path to facts.jsonl"),
    manifest: str | None = typer.Option(None, help="Optional manifest_v1.json path"),
) -> None:
    facts = list(FactIndex.from_logs(fact_log).facts)
    seen: set[str] = set()
    duplicate_ids: set[str] = set()
    asserted_ids: set[str] = set()
    dangling_retractions: list[str] = []

    for fact in facts:
        if fact.fact_id in seen:
            duplicate_ids.add(fact.fact_id)
        seen.add(fact.fact_id)

        if fact.status == FactStatus.ASSERTED:
            asserted_ids.add(fact.fact_id)
        elif fact.retracts_fact_id and fact.retracts_fact_id not in asserted_ids:
            dangling_retractions.append(fact.fact_id)

    manifest_ok = True
    if manifest:
        ManifestV1.model_validate(json.loads(Path(manifest).read_text(encoding="utf-8")))

    report = {
        "facts_total": len(facts),
        "duplicates": sorted(duplicate_ids),
        "dangling_retractions": sorted(dangling_retractions),
        "manifest_ok": manifest_ok,
        "ok": not duplicate_ids and not dangling_retractions,
    }
    typer.echo(json.dumps(report, indent=2, sort_keys=True))
    if not report["ok"]:
        raise typer.Exit(code=1)


@app.command("compile-masks")
def compile_masks_command(
    snapshot: str = typer.Option(..., help="Materialized snapshot JSON path"),
    policy: CompilePolicy = typer.Option(CompilePolicy.OPEN_WORLD, help="Compile policy"),
    output: str = typer.Option(..., help="Output compiled masks JSON path"),
) -> None:
    payload = json.loads(Path(snapshot).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise typer.BadParameter("snapshot must be a JSON object")

    materialized = _snapshot_from_payload(payload)
    compiled = compile_masks(materialized, policy=policy)
    write_compiled_masks(output, compiled)

    typer.echo(json.dumps({"output": output, "policy": policy.value}, indent=2, sort_keys=True))


if __name__ == "__main__":
    app()
