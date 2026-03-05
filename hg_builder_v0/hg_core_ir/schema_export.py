from __future__ import annotations

import json
from pathlib import Path

from hg_builder_v0.hg_core_ir.models import ConstraintV1, FactV1, ManifestV1


def export_schemas(output_dir: str | Path) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    mapping = {
        "fact_v1.json": FactV1.model_json_schema(),
        "constraint_v1.json": ConstraintV1.model_json_schema(),
        "manifest_v1.json": ManifestV1.model_json_schema(),
    }

    written: dict[str, str] = {}
    for filename, schema in mapping.items():
        path = out / filename
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written[filename] = str(path)

    return written
