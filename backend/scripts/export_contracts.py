import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from petraterrium.atlas.contracts import (
    AtlasOverview,
    AtlasScopes,
    ChoiceEvidenceCatalog,
    CityDetail,
    FieldCoverage,
    HierarchyOverview,
    ImportCommit,
    ImportHistory,
    ImportMetadata,
    ImportPreview,
    ImportVersion,
    MappingConfirmation,
    Promotion,
    SourceCatalog,
    SourceFetch,
    UniversalFeatureOverview,
    ValidationReport,
)
from petraterrium.contracts import (
    ActionLogEntry,
    AgentDetail,
    AgentPointList,
    Catalog,
    DailySnapshot,
    DecisionGraph,
    DSLRender,
    EnsembleUpdate,
    PlaceDetail,
    RunComplete,
    RunCreated,
    RunDetail,
    RunFailed,
    RunList,
    StoryDetail,
    StoryList,
)
from petraterrium.dsl import DSLConfig, DSLValidationResult

TARGET = Path(__file__).resolve().parents[2] / "frontend" / "src"
DSL_TARGET = Path(__file__).resolve().parents[2] / "shared" / "dsl-schema"
SHARED_TYPES_TARGET = Path(__file__).resolve().parents[2] / "shared" / "types"


def typescript_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    if "anyOf" in schema:
        return " | ".join(typescript_type(item) for item in schema["anyOf"])
    kind = schema.get("type")
    if kind == "array":
        if "prefixItems" in schema:
            return "[" + ", ".join(typescript_type(item) for item in schema["prefixItems"]) + "]"
        return f"Array<{typescript_type(schema['items'])}>"
    if kind == "object":
        required = schema.get("required", [])
        fields = [
            f"  {name}{'' if name in required else '?'}: {typescript_type(value)};"
            for name, value in schema.get("properties", {}).items()
        ]
        if isinstance(schema.get("additionalProperties"), dict):
            fields.append(f"  [key: string]: {typescript_type(schema['additionalProperties'])};")
        return "{\n" + "\n".join(fields) + "\n}"
    if kind is None:
        return "unknown"
    return {
        "integer": "number",
        "number": "number",
        "string": "string",
        "boolean": "boolean",
        "null": "null",
    }[kind]


def artifacts() -> dict[Path, str]:
    adapter = TypeAdapter(
        Catalog
        | ActionLogEntry
        | AgentDetail
        | AgentPointList
        | DailySnapshot
        | DecisionGraph
        | DSLRender
        | EnsembleUpdate
        | PlaceDetail
        | RunComplete
        | RunFailed
        | RunDetail
        | RunCreated
        | RunList
        | StoryDetail
        | StoryList
        | DSLConfig
        | DSLValidationResult
        | AtlasOverview
        | AtlasScopes
        | ChoiceEvidenceCatalog
        | CityDetail
        | FieldCoverage
        | HierarchyOverview
        | ImportCommit
        | ImportHistory
        | ImportMetadata
        | ImportPreview
        | ImportVersion
        | MappingConfirmation
        | Promotion
        | SourceCatalog
        | SourceFetch
        | UniversalFeatureOverview
        | ValidationReport
    )
    schema = adapter.json_schema(mode="serialization")
    schema["$id"] = "petraterrium-contracts"
    definitions = schema["$defs"]
    types = "\n\n".join(
        f"export type {name} = {typescript_type(value)};"
        for name, value in sorted(definitions.items())
    )
    return {
        TARGET / "contracts.schema.json": json.dumps(schema, indent=2) + "\n",
        TARGET / "contracts.generated.ts": types + "\n",
        SHARED_TYPES_TARGET / "contracts.generated.ts": types + "\n",
        DSL_TARGET / "petraterrium-dsl.schema.json": json.dumps(
            DSLConfig.model_json_schema(mode="serialization"), indent=2
        )
        + "\n",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args()
    for path, content in artifacts().items():
        if options.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(
                    f"Outdated contracts: {path}. Run python scripts/export_contracts.py"
                )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)


if __name__ == "__main__":
    main()
