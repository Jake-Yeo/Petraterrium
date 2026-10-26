import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from petraterrium.contracts import (
    Catalog,
    DailySnapshot,
    RunComplete,
    RunCreated,
    RunDetail,
    RunFailed,
    RunList,
)

TARGET = Path(__file__).resolve().parents[2] / "frontend" / "src"


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
        return f"Array<{typescript_type(schema['items'])}>"
    if kind == "object":
        required = schema.get("required", [])
        fields = [
            f"  {name}{'' if name in required else '?'}: {typescript_type(value)};"
            for name, value in schema.get("properties", {}).items()
        ]
        return "{\n" + "\n".join(fields) + "\n}"
    return {
        "integer": "number",
        "number": "number",
        "string": "string",
        "boolean": "boolean",
        "null": "null",
    }[kind]


def artifacts() -> dict[Path, str]:
    adapter = TypeAdapter(
        Catalog | DailySnapshot | RunComplete | RunFailed | RunDetail | RunCreated | RunList
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
            path.write_text(content)


if __name__ == "__main__":
    main()
