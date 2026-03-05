from __future__ import annotations

import json
import uuid
from pathlib import Path

from hg_builder_v0.hg_core_ir.models import (
    ConstraintKind,
    ConstraintV1,
    FactStatus,
    FactV1,
    Polarity,
    ProvenanceV1,
    SourceType,
)
from hg_builder_v0.hg_factlog.store import append_facts


def _deterministic_id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, '|'.join(parts))}"


def migrate_hcg_snapshot(
    snapshot_path: str | Path,
    factlog_output_path: str | Path,
    constraint_output_path: str | Path | None = None,
    source_id: str = "hcg_snapshot",
) -> dict[str, int]:
    payload = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Legacy snapshot must be a JSON object")

    facts: list[FactV1] = []
    for row in payload.get("evaluations", []):
        if not isinstance(row, dict):
            continue
        predicate_id = row.get("predicate_id")
        hypothesis_id = row.get("hypothesis_id")
        value = row.get("value")
        if not isinstance(predicate_id, str) or not isinstance(hypothesis_id, str):
            continue
        if not isinstance(value, bool):
            continue

        polarity = Polarity.PRESENT if value else Polarity.ABSENT
        facts.append(
            FactV1(
                fact_id=_deterministic_id("fact", hypothesis_id, predicate_id, str(value)),
                object_id=hypothesis_id,
                attribute_id=predicate_id,
                polarity=polarity,
                confidence=float(row.get("confidence", 1.0)) if row.get("confidence") is not None else 1.0,
                provenance=ProvenanceV1(source_type=SourceType.MIGRATION, source_id=source_id),
                status=FactStatus.ASSERTED,
            )
        )

    facts_written = append_facts(factlog_output_path, facts)

    constraints_written = 0
    if constraint_output_path is not None:
        out = Path(constraint_output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as handle:
            for row in payload.get("constraints", []):
                if not isinstance(row, dict):
                    continue
                kind = row.get("type")
                if kind == "implies":
                    constraint_kind = ConstraintKind.IMPLIES
                elif kind == "conflicts_with":
                    constraint_kind = ConstraintKind.CONFLICTS_WITH
                else:
                    continue

                src = row.get("from")
                dst = row.get("to")
                if not isinstance(src, str) or not isinstance(dst, str):
                    continue

                constraint = ConstraintV1(
                    constraint_id=_deterministic_id("constraint", src, dst, constraint_kind.value),
                    kind=constraint_kind,
                    lhs_attribute_ids=[src],
                    rhs_attribute_ids=[dst],
                    provenance=ProvenanceV1(source_type=SourceType.MIGRATION, source_id=source_id),
                )
                handle.write(json.dumps(constraint.model_dump(mode="json"), sort_keys=True) + "\n")
                constraints_written += 1

    return {
        "facts_written": facts_written,
        "constraints_written": constraints_written,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate legacy HCG snapshot to fact_v1 fact log")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--facts", required=True)
    parser.add_argument("--constraints", default="")
    parser.add_argument("--source-id", default="hcg_snapshot")
    args = parser.parse_args()

    summary = migrate_hcg_snapshot(
        snapshot_path=args.snapshot,
        factlog_output_path=args.facts,
        constraint_output_path=args.constraints or None,
        source_id=args.source_id,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
