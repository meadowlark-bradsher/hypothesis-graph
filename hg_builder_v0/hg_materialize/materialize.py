from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, Protocol, Sequence

from hg_builder_v0.hg_core_ir.models import FactStatus, FactV1, Polarity
from hg_builder_v0.hg_factlog.store import dedupe_by_fact_id, read_facts


PathLike = str | Path


@dataclass
class MaterializeFilters:
    graph_version: int | None = None
    as_of_time: datetime | None = None
    environment: str | None = None
    object_ids: set[str] | None = None
    attribute_ids: set[str] | None = None


class ConflictResolver(Protocol):
    def resolve(self, object_id: str, attribute_id: str, facts: Sequence[FactV1]) -> FactV1 | None: ...


@dataclass
class MaterializedSnapshot:
    effective_assertions: list[FactV1]
    conflicts_report: list[dict]
    duplicate_fact_ids: list[str] = field(default_factory=list)
    retracted_fact_ids: list[str] = field(default_factory=list)

    def polarity_by_pair(self) -> dict[tuple[str, str], Polarity]:
        return {(fact.object_id, fact.attribute_id): fact.polarity for fact in self.effective_assertions}

    def to_dict(self) -> dict:
        return {
            "effective_assertions": [fact.model_dump(mode="json") for fact in self.effective_assertions],
            "conflicts_report": self.conflicts_report,
            "duplicate_fact_ids": self.duplicate_fact_ids,
            "retracted_fact_ids": self.retracted_fact_ids,
        }


def _iter_logs(base_logs: Sequence[PathLike], overlays: Sequence[PathLike] | None) -> Iterator[FactV1]:
    overlay_logs = list(overlays or [])
    for fact in read_facts(list(base_logs) + overlay_logs):
        yield fact


def _is_valid_for_filters(fact: FactV1, filters: MaterializeFilters) -> bool:
    validity = fact.validity

    if filters.object_ids is not None and fact.object_id not in filters.object_ids:
        return False
    if filters.attribute_ids is not None and fact.attribute_id not in filters.attribute_ids:
        return False

    if validity is None:
        return True

    if filters.graph_version is not None:
        if validity.graph_version_min is not None and filters.graph_version < validity.graph_version_min:
            return False
        if validity.graph_version_max is not None and filters.graph_version > validity.graph_version_max:
            return False

    if filters.as_of_time is not None:
        if validity.time_start is not None and filters.as_of_time < validity.time_start:
            return False
        if validity.time_end is not None and filters.as_of_time > validity.time_end:
            return False

    if filters.environment is not None and validity.environment is not None:
        if isinstance(validity.environment, str):
            return filters.environment == validity.environment
        return filters.environment in validity.environment

    return True


def materialize_snapshot(
    base_logs: Sequence[PathLike],
    overlays: Sequence[PathLike] | None = None,
    filters: MaterializeFilters | None = None,
    conflict_resolver: ConflictResolver | None = None,
) -> MaterializedSnapshot:
    active_filters = filters or MaterializeFilters()

    deduped = dedupe_by_fact_id(_iter_logs(base_logs=base_logs, overlays=overlays))
    filtered_facts = [fact for fact in deduped.facts if _is_valid_for_filters(fact, active_filters)]

    tombstones: set[str] = set()
    active_by_id: dict[str, FactV1] = {}
    active_sequence: list[str] = []

    for fact in filtered_facts:
        if fact.status == FactStatus.RETRACTED:
            if fact.retracts_fact_id:
                tombstones.add(fact.retracts_fact_id)
                active_by_id.pop(fact.retracts_fact_id, None)
            continue

        if fact.fact_id in tombstones:
            continue

        active_by_id[fact.fact_id] = fact
        active_sequence.append(fact.fact_id)

    active_assertions: list[FactV1] = []
    seen_active_ids: set[str] = set()
    for fact_id in active_sequence:
        if fact_id in seen_active_ids:
            continue
        seen_active_ids.add(fact_id)
        fact = active_by_id.get(fact_id)
        if fact is not None:
            active_assertions.append(fact)

    by_pair: dict[tuple[str, str], list[FactV1]] = {}
    for fact in active_assertions:
        by_pair.setdefault((fact.object_id, fact.attribute_id), []).append(fact)

    conflicts_report: list[dict] = []
    effective_assertions: list[FactV1] = []

    for (object_id, attribute_id), facts in sorted(by_pair.items(), key=lambda item: item[0]):
        polarities = {fact.polarity for fact in facts}
        if len(polarities) <= 1:
            # Deterministic pick when duplicate assertions of the same polarity exist.
            effective_assertions.append(facts[-1])
            continue

        chosen: FactV1 | None = None
        if conflict_resolver is not None:
            chosen = conflict_resolver.resolve(object_id=object_id, attribute_id=attribute_id, facts=facts)

        if chosen is not None:
            effective_assertions.append(chosen)
            continue

        conflicts_report.append(
            {
                "object_id": object_id,
                "attribute_id": attribute_id,
                "fact_ids": [fact.fact_id for fact in facts],
                "polarities": sorted({fact.polarity.value for fact in facts}),
            }
        )

    return MaterializedSnapshot(
        effective_assertions=sorted(effective_assertions, key=lambda fact: (fact.object_id, fact.attribute_id, fact.fact_id)),
        conflicts_report=conflicts_report,
        duplicate_fact_ids=deduped.duplicate_fact_ids,
        retracted_fact_ids=sorted(tombstones),
    )


def effective_facts(
    base_logs: Sequence[PathLike],
    overlays: Sequence[PathLike] | None = None,
    filters: MaterializeFilters | None = None,
    conflict_resolver: ConflictResolver | None = None,
) -> Iterator[FactV1]:
    snapshot = materialize_snapshot(base_logs=base_logs, overlays=overlays, filters=filters, conflict_resolver=conflict_resolver)
    for fact in snapshot.effective_assertions:
        yield fact
