from __future__ import annotations

import base64
import json
from pathlib import Path

from hg_builder_v0.hg_compile.compile_masks import CompilePolicy, compile_masks
from hg_builder_v0.hg_core_ir.models import FactStatus, FactV1, Polarity, ProvenanceV1, SourceType, ValidityV1
from hg_builder_v0.hg_factlog.store import append_facts
from hg_builder_v0.hg_materialize.materialize import MaterializeFilters, materialize_snapshot


def _decode_mask(mask_b64: str, count: int) -> list[int]:
    raw = base64.b64decode(mask_b64)
    bits: list[int] = []
    for idx in range(count):
        bits.append((raw[idx // 8] >> (idx % 8)) & 1)
    return bits


def _provenance(source_id: str = "test") -> ProvenanceV1:
    return ProvenanceV1(source_type=SourceType.AUTOMATION, source_id=source_id)


def test_open_world_preserved_end_to_end(tmp_path: Path) -> None:
    fact_log = tmp_path / "facts.jsonl"

    append_facts(
        fact_log,
        [
            FactV1(object_id="dog", attribute_id="barks", polarity=Polarity.PRESENT, provenance=_provenance()),
            FactV1(object_id="cat", attribute_id="barks", polarity=Polarity.ABSENT, provenance=_provenance()),
            FactV1(object_id="cat", attribute_id="furry", polarity=Polarity.PRESENT, provenance=_provenance()),
        ],
    )

    snapshot = materialize_snapshot(base_logs=[fact_log])
    pair_map = snapshot.polarity_by_pair()

    assert pair_map[("dog", "barks")] == Polarity.PRESENT
    assert pair_map[("cat", "barks")] == Polarity.ABSENT
    assert pair_map[("cat", "furry")] == Polarity.PRESENT
    assert ("dog", "furry") not in pair_map  # Unknown remains unknown.

    objects = ["dog", "cat"]
    attributes = ["barks", "furry"]

    open_world = compile_masks(snapshot, policy=CompilePolicy.OPEN_WORLD, objects=objects, attributes=attributes)
    closed_world = compile_masks(snapshot, policy=CompilePolicy.CLOSED_WORLD, objects=objects, attributes=attributes)
    three_valued = compile_masks(snapshot, policy=CompilePolicy.THREE_VALUED, objects=objects, attributes=attributes)

    assert _decode_mask(open_world.mask_absent["furry"], 2) == [0, 0]
    assert _decode_mask(open_world.mask_present["furry"], 2) == [0, 1]

    assert _decode_mask(closed_world.mask_absent["furry"], 2) == [1, 0]

    assert three_valued.mask_unknown is not None
    assert _decode_mask(three_valued.mask_unknown["furry"], 2) == [1, 0]


def test_retraction_removes_asserted_fact_from_effective_view(tmp_path: Path) -> None:
    fact_log = tmp_path / "facts.jsonl"

    asserted = FactV1(
        fact_id="fact_asserted_1",
        object_id="dog",
        attribute_id="barks",
        polarity=Polarity.PRESENT,
        provenance=_provenance(),
    )
    retraction = FactV1(
        fact_id="fact_retraction_1",
        object_id="dog",
        attribute_id="barks",
        polarity=Polarity.PRESENT,
        provenance=_provenance("retractor"),
        status=FactStatus.RETRACTED,
        retracts_fact_id="fact_asserted_1",
    )

    append_facts(fact_log, [asserted, retraction])

    snapshot = materialize_snapshot(base_logs=[fact_log])
    assert snapshot.effective_assertions == []
    assert snapshot.retracted_fact_ids == ["fact_asserted_1"]


def test_overlays_extend_effective_view(tmp_path: Path) -> None:
    base_log = tmp_path / "base.jsonl"
    overlay_log = tmp_path / "overlay.jsonl"

    append_facts(
        base_log,
        [
            FactV1(object_id="fox", attribute_id="howls", polarity=Polarity.PRESENT, provenance=_provenance("base")),
        ],
    )
    append_facts(
        overlay_log,
        [
            FactV1(object_id="wolf", attribute_id="pack_hunter", polarity=Polarity.PRESENT, provenance=_provenance("overlay")),
        ],
    )

    snapshot = materialize_snapshot(base_logs=[base_log], overlays=[overlay_log])
    pair_map = snapshot.polarity_by_pair()

    assert pair_map[("fox", "howls")] == Polarity.PRESENT
    assert pair_map[("wolf", "pack_hunter")] == Polarity.PRESENT


def test_validity_window_filters_by_graph_version(tmp_path: Path) -> None:
    fact_log = tmp_path / "facts.jsonl"

    append_facts(
        fact_log,
        [
            FactV1(
                object_id="db",
                attribute_id="healthy",
                polarity=Polarity.PRESENT,
                validity=ValidityV1(graph_version_min=1, graph_version_max=1),
                provenance=_provenance("v1"),
            ),
            FactV1(
                object_id="db",
                attribute_id="healthy",
                polarity=Polarity.ABSENT,
                validity=ValidityV1(graph_version_min=2),
                provenance=_provenance("v2"),
            ),
        ],
    )

    v1_snapshot = materialize_snapshot(base_logs=[fact_log], filters=MaterializeFilters(graph_version=1))
    v2_snapshot = materialize_snapshot(base_logs=[fact_log], filters=MaterializeFilters(graph_version=2))

    assert v1_snapshot.polarity_by_pair()[("db", "healthy")] == Polarity.PRESENT
    assert v2_snapshot.polarity_by_pair()[("db", "healthy")] == Polarity.ABSENT
    assert v1_snapshot.conflicts_report == []
    assert v2_snapshot.conflicts_report == []
