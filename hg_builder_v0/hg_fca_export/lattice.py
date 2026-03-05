from __future__ import annotations

import itertools
import json
from pathlib import Path

from hg_builder_v0.hg_fca_export.export import FCAExportResult


def _powerset(values: list[str]) -> list[frozenset[str]]:
    out: list[frozenset[str]] = []
    for size in range(len(values) + 1):
        for combo in itertools.combinations(values, size):
            out.append(frozenset(combo))
    return out


def build_lattice(incidence: FCAExportResult) -> dict:
    objects = sorted(incidence.objects)
    attributes = sorted(incidence.attributes)

    present_by_object = {object_id: set() for object_id in objects}
    for object_id, attribute_id in incidence.present_edges:
        present_by_object.setdefault(object_id, set()).add(attribute_id)

    concepts: set[tuple[frozenset[str], frozenset[str]]] = set()

    for candidate_intent in _powerset(attributes):
        extent = frozenset(
            object_id for object_id in objects if set(candidate_intent).issubset(present_by_object.get(object_id, set()))
        )

        if extent:
            intent = frozenset(set.intersection(*(present_by_object[obj] for obj in extent)))
        else:
            intent = frozenset(attributes)

        concepts.add((extent, intent))

    concept_rows = sorted(concepts, key=lambda row: (len(row[0]), sorted(row[0]), len(row[1]), sorted(row[1])))

    nodes = []
    for idx, (extent, intent) in enumerate(concept_rows):
        nodes.append(
            {
                "id": f"c_{idx:05d}",
                "extent": sorted(extent),
                "intent": sorted(intent),
            }
        )

    edges = []
    for lower in nodes:
        lower_extent = set(lower["extent"])
        candidates = []
        for upper in nodes:
            upper_extent = set(upper["extent"])
            if lower["id"] == upper["id"]:
                continue
            if lower_extent < upper_extent:
                candidates.append(upper)

        for candidate in candidates:
            candidate_extent = set(candidate["extent"])
            is_cover = True
            for middle in candidates:
                middle_extent = set(middle["extent"])
                if middle["id"] == candidate["id"]:
                    continue
                if lower_extent < middle_extent < candidate_extent:
                    is_cover = False
                    break
            if is_cover:
                edges.append({"from": lower["id"], "to": candidate["id"]})

    return {
        "version": "fca_lattice_v1",
        "objects": objects,
        "attributes": attributes,
        "nodes": nodes,
        "edges": sorted(edges, key=lambda row: (row["from"], row["to"])),
    }


def write_lattice(path: str | Path, lattice: dict) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(lattice, indent=2, sort_keys=True) + "\n", encoding="utf-8")
