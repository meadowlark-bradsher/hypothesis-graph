from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from hg_builder_v0.hg_core_ir.models import Polarity
from hg_builder_v0.hg_materialize.materialize import MaterializedSnapshot


class CompilePolicy(str, Enum):
    OPEN_WORLD = "open_world"
    CLOSED_WORLD = "closed_world"
    THREE_VALUED = "three_valued"


@dataclass
class CompiledMasks:
    policy: CompilePolicy
    objects: list[str]
    attributes: list[str]
    mask_present: dict[str, str]
    mask_absent: dict[str, str]
    mask_unknown: dict[str, str] | None

    def to_dict(self) -> dict:
        payload = {
            "version": "compiled_masks_v1",
            "policy": self.policy.value,
            "objects": self.objects,
            "attributes": self.attributes,
            "mask_present": self.mask_present,
            "mask_absent": self.mask_absent,
        }
        if self.mask_unknown is not None:
            payload["mask_unknown"] = self.mask_unknown
        return payload


def _pack_bits(bits: list[int]) -> str:
    out = bytearray((len(bits) + 7) // 8)
    for idx, bit in enumerate(bits):
        if bit:
            out[idx // 8] |= 1 << (idx % 8)
    return base64.b64encode(bytes(out)).decode("ascii")


def compile_masks(
    snapshot: MaterializedSnapshot,
    policy: CompilePolicy = CompilePolicy.OPEN_WORLD,
    objects: list[str] | None = None,
    attributes: list[str] | None = None,
) -> CompiledMasks:
    pair_to_polarity = snapshot.polarity_by_pair()

    if objects is None:
        objects = sorted({fact.object_id for fact in snapshot.effective_assertions})
    else:
        objects = list(objects)

    if attributes is None:
        attributes = sorted({fact.attribute_id for fact in snapshot.effective_assertions})
    else:
        attributes = list(attributes)

    present_masks: dict[str, str] = {}
    absent_masks: dict[str, str] = {}
    unknown_masks: dict[str, str] = {}

    for attribute_id in attributes:
        present_bits: list[int] = []
        absent_bits: list[int] = []
        unknown_bits: list[int] = []

        for object_id in objects:
            polarity = pair_to_polarity.get((object_id, attribute_id))

            is_present = 1 if polarity == Polarity.PRESENT else 0
            is_absent = 1 if polarity == Polarity.ABSENT else 0
            is_unknown = 1 if polarity in {None, Polarity.UNKNOWN} else 0

            if policy == CompilePolicy.CLOSED_WORLD and polarity is None:
                is_absent = 1
                is_unknown = 0

            present_bits.append(is_present)
            absent_bits.append(is_absent)
            unknown_bits.append(is_unknown)

        present_masks[attribute_id] = _pack_bits(present_bits)
        absent_masks[attribute_id] = _pack_bits(absent_bits)
        unknown_masks[attribute_id] = _pack_bits(unknown_bits)

    return CompiledMasks(
        policy=policy,
        objects=objects,
        attributes=attributes,
        mask_present=present_masks,
        mask_absent=absent_masks,
        mask_unknown=unknown_masks if policy == CompilePolicy.THREE_VALUED else None,
    )


def write_compiled_masks(path: str | Path, compiled: CompiledMasks) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(compiled.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
