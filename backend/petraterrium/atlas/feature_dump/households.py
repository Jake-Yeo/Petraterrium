import re
from collections import Counter
from pathlib import Path

import pyarrow as pa

from .parquet import RowWriter, write_rows
from .xlsx import read_sheet

HOUSEHOLD_URL = (
    "https://www.un.org/development/desa/pd/sites/www.un.org.development.desa.pd/files/"
    "undesa_pd_2026_hh-size-composition.xlsx"
)


def identifier(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return "un_household." + normalized


def numeric(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip() not in ("", ".."):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def latest_household_rows(rows):
    latest = {}
    for row in rows:
        key = row["country_code"]
        previous = latest.get(key)
        rank = int(row["year"]), str(row.get("source_catalog_id", ""))
        if previous is None or rank > (
            int(previous["year"]),
            str(previous.get("source_catalog_id", "")),
        ):
            latest[key] = row
    return [latest[key] for key in sorted(latest)]


def latest_household_values(records):
    latest = {}
    for record in records:
        for feature_id, value in record["features"].items():
            key = record["country_code"], feature_id
            rank = int(record["year"]), str(record.get("source_catalog_id", ""))
            previous = latest.get(key)
            if previous is None or rank > previous[0]:
                latest[key] = (
                    rank,
                    {
                        key: record.get(key, "")
                        for key in (
                            "country_code",
                            "year",
                            "source_category",
                            "source_catalog_id",
                            "source_name",
                        )
                    }
                    | {"feature_id": feature_id, "value": value},
                )
    return [latest[key][1] for key in sorted(latest)]


def household_records(workbook_path: Path):
    rows = read_sheet(workbook_path, "HH size and composition 2026")
    headers = None
    for index, values in enumerate(rows, 1):
        if index < 5:
            continue
        if index == 5:
            headers = [str(value or "") for value in values]
            continue
        if headers is None or not values:
            continue
        padded = values + [None] * (len(headers) - len(values))
        source = dict(zip(headers, padded, strict=True))
        country_code = str(source.get("ISO2 Code") or "").upper()
        year = numeric(source.get("Reference year"))
        if len(country_code) != 2 or year is None:
            continue
        features = {}
        for header in headers[10:]:
            value = numeric(source.get(header))
            if header and value is not None:
                features[identifier(header)] = value
        yield {
            "country_code": country_code,
            "year": int(year),
            "source_category": str(source.get("Data source category") or ""),
            "source_catalog_id": str(source.get("Data source catalog ID") or ""),
            "source_name": str(source.get("Data source detailed name") or ""),
            "average_household_size": features.get(
                identifier("Average household size (number of members)")
            ),
            "features": features,
        }


def household_catalog(workbook_path: Path, feature_names: list[str]):
    definitions = {
        str(row[0]): str(row[1])
        for row in read_sheet(workbook_path, "Definitions")
        if len(row) >= 2 and row[0] and row[1]
    }
    return [
        {
            "feature_id": identifier(name),
            "name": name,
            "definition": definitions.get(name, ""),
            "unit": "members" if name.startswith("Average household size") else "percent",
            "source": "UN DESA Database on Household Size and Composition 2026",
            "license": "CC BY 3.0 IGO",
        }
        for name in feature_names
    ]


def export_households(workbook_path: Path, output: Path):
    records = list(household_records(workbook_path))
    feature_names = []
    for row in read_sheet(workbook_path, "HH size and composition 2026"):
        if row and row[0] == "Country and area":
            feature_names = [str(value) for value in row[10:] if value]
            break
    write_rows(
        output / "un_household_feature_catalog.parquet",
        household_catalog(workbook_path, feature_names),
    )
    schema = pa.schema(
        [
            ("country_code", pa.string()),
            ("feature_id", pa.string()),
            ("year", pa.int16()),
            ("value", pa.float64()),
            ("source_category", pa.string()),
            ("source_catalog_id", pa.string()),
            ("source_name", pa.string()),
        ]
    )
    history_writer = RowWriter(output / "un_household_country_history.parquet", schema, 25_000)
    for record in records:
        for feature_id, value in record["features"].items():
            history_writer.add(
                {
                    key: record[key]
                    for key in (
                        "country_code",
                        "year",
                        "source_category",
                        "source_catalog_id",
                        "source_name",
                    )
                }
                | {"feature_id": feature_id, "value": value}
            )
    history_count = history_writer.close()
    latest_rows = latest_household_values(records)
    write_rows(output / "un_household_country_latest.parquet", latest_rows, schema)
    latest_records = latest_household_rows(
        [row for row in records if row["average_household_size"] is not None]
    )
    canonical = [
        {
            "country_code": row["country_code"],
            "field": "household_size",
            "year": row["year"],
            "value": row["average_household_size"],
            "unit": "members",
        }
        for row in latest_records
        if row["average_household_size"] is not None
    ]
    latest_counts = Counter(row["country_code"] for row in latest_rows)
    return {
        "features": len(feature_names),
        "countries": len({row["country_code"] for row in latest_rows}),
        "source_records": len(records),
        "historical_values": history_count,
        "latest_values": len(latest_rows),
        "latest_counts": dict(latest_counts),
        "canonical": canonical,
        "release_date": "2026-08-19",
    }
