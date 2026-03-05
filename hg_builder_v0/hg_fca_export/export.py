from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from hg_builder_v0.hg_core_ir.models import Polarity
from hg_builder_v0.hg_materialize.materialize import MaterializedSnapshot


@dataclass
class FCAExportResult:
    objects: list[str]
    attributes: list[str]
    present_edges: list[tuple[str, str]]
    absent_edges: list[tuple[str, str]]
    unknown_edges: list[tuple[str, str]]


def build_incidence(snapshot: MaterializedSnapshot) -> FCAExportResult:
    assertions = snapshot.effective_assertions
    objects = sorted({fact.object_id for fact in assertions})
    attributes = sorted({fact.attribute_id for fact in assertions})

    pair_to_polarity = snapshot.polarity_by_pair()

    present_edges: list[tuple[str, str]] = []
    absent_edges: list[tuple[str, str]] = []
    unknown_edges: list[tuple[str, str]] = []

    for object_id in objects:
        for attribute_id in attributes:
            polarity = pair_to_polarity.get((object_id, attribute_id))
            if polarity == Polarity.PRESENT:
                present_edges.append((object_id, attribute_id))
            elif polarity == Polarity.ABSENT:
                absent_edges.append((object_id, attribute_id))
            else:
                unknown_edges.append((object_id, attribute_id))

    return FCAExportResult(
        objects=objects,
        attributes=attributes,
        present_edges=present_edges,
        absent_edges=absent_edges,
        unknown_edges=unknown_edges,
    )


def export_incidence(snapshot: MaterializedSnapshot, output_dir: str | Path, include_absent: bool = True) -> dict[str, str]:
    result = build_incidence(snapshot)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    objects_path = out / "objects.json"
    attributes_path = out / "attributes.json"
    present_path = out / "incidence_present.csv"

    objects_path.write_text(json.dumps(result.objects, indent=2) + "\n", encoding="utf-8")
    attributes_path.write_text(json.dumps(result.attributes, indent=2) + "\n", encoding="utf-8")

    with present_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["object_id", "attribute_id"])
        writer.writerows(result.present_edges)

    written = {
        "objects": str(objects_path),
        "attributes": str(attributes_path),
        "incidence_present": str(present_path),
    }

    if include_absent:
        absent_path = out / "incidence_absent.csv"
        with absent_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["object_id", "attribute_id"])
            writer.writerows(result.absent_edges)
        written["incidence_absent"] = str(absent_path)

    return written
