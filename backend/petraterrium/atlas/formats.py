import csv
import io
import json
import math
import os
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as parquet

MAX_BYTES = int(os.getenv("ATLAS_MAX_IMPORT_BYTES", str(256 * 1024 * 1024)))
MAX_ROWS = int(os.getenv("ATLAS_MAX_IMPORT_ROWS", "2000000"))


def reject_json_number(value: str):
    raise ValueError(f"Invalid JSON number: {value}")


def serializable_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {str(key): serializable_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serializable_value(item) for item in value]
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def parse_upload(filename: str, contents: bytes) -> list[dict]:
    if len(contents) > MAX_BYTES:
        raise ValueError(f"Upload exceeds the configured {MAX_BYTES} byte limit")
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        text = contents.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("CSV must have unique column headers")
        rows = list(reader)
    elif suffix == ".json":
        rows = json.loads(contents, parse_constant=reject_json_number)
        if isinstance(rows, dict) and isinstance(rows.get("rows"), list):
            rows = rows["rows"]
    elif suffix == ".parquet":
        rows = parquet.read_table(io.BytesIO(contents)).to_pylist()
    else:
        raise ValueError("Choose a CSV, Parquet, or JSON file")
    if not isinstance(rows, list) or not rows or len(rows) > MAX_ROWS:
        raise ValueError(f"Upload must contain 1–{MAX_ROWS} rows")
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or None in row:
            raise ValueError(f"Row {index} must be an object with named columns")
        for key, value in row.items():
            row[key] = serializable_value(value)
    return rows


def preview_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            str(key): json.dumps(value, ensure_ascii=False)
            if isinstance(value, (dict, list))
            else value
            for key, value in row.items()
        }
        for row in rows[:5]
    ]
