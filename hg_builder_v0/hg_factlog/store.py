from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, Sequence

from hg_builder_v0.hg_core_ir.models import FactV1


PathLike = str | Path


def _as_paths(paths: PathLike | Sequence[PathLike]) -> list[Path]:
    if isinstance(paths, (str, Path)):
        return [Path(paths)]
    return [Path(path) for path in paths]


def append_fact(path: PathLike, fact: FactV1) -> None:
    append_facts(path, [fact])


def append_facts(path: PathLike, facts: Iterable[FactV1]) -> int:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with out.open("a", encoding="utf-8") as handle:
        for fact in facts:
            handle.write(json.dumps(fact.model_dump(mode="json"), sort_keys=True) + "\n")
            count += 1
    return count


def read_fact_dicts(paths: PathLike | Sequence[PathLike]) -> Iterator[dict]:
    for path in _as_paths(paths):
        if not path.exists():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            raw = line.strip()
            if not raw:
                continue
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError(f"Expected object JSON in {path}:{line_number}")
            yield payload


def read_facts(paths: PathLike | Sequence[PathLike]) -> Iterator[FactV1]:
    for payload in read_fact_dicts(paths):
        yield FactV1.model_validate(payload)


@dataclass
class DedupeResult:
    facts: list[FactV1]
    duplicate_fact_ids: list[str]


def dedupe_by_fact_id(facts: Iterable[FactV1]) -> DedupeResult:
    seen: set[str] = set()
    deduped: list[FactV1] = []
    duplicates: list[str] = []

    for fact in facts:
        if fact.fact_id in seen:
            duplicates.append(fact.fact_id)
            continue
        seen.add(fact.fact_id)
        deduped.append(fact)

    return DedupeResult(facts=deduped, duplicate_fact_ids=sorted(set(duplicates)))


class FactIndex:
    def __init__(self, facts: Iterable[FactV1]) -> None:
        self._facts: list[FactV1] = list(facts)
        self.by_fact_id: Dict[str, FactV1] = {}
        self.by_object: Dict[str, list[FactV1]] = {}
        self.by_attribute: Dict[str, list[FactV1]] = {}
        self.by_pair: Dict[tuple[str, str], list[FactV1]] = {}

        for fact in self._facts:
            self.by_fact_id[fact.fact_id] = fact
            self.by_object.setdefault(fact.object_id, []).append(fact)
            self.by_attribute.setdefault(fact.attribute_id, []).append(fact)
            self.by_pair.setdefault((fact.object_id, fact.attribute_id), []).append(fact)

    @classmethod
    def from_logs(cls, paths: PathLike | Sequence[PathLike]) -> "FactIndex":
        return cls(read_facts(paths))

    def find_fact(self, fact_id: str) -> FactV1 | None:
        return self.by_fact_id.get(fact_id)

    def query(
        self,
        object_ids: set[str] | None = None,
        attribute_ids: set[str] | None = None,
    ) -> list[FactV1]:
        out: list[FactV1] = []
        for fact in self._facts:
            if object_ids is not None and fact.object_id not in object_ids:
                continue
            if attribute_ids is not None and fact.attribute_id not in attribute_ids:
                continue
            out.append(fact)
        return out

    @property
    def facts(self) -> list[FactV1]:
        return list(self._facts)
