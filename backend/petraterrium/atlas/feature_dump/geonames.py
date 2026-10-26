import csv
import io
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

import pyarrow as pa
import pyarrow.parquet as pq

from ..backbone import EXCLUDED_CODES, GEONAMES_URL
from .parquet import RowWriter

CITY_SCHEMA = pa.schema(
    [
        ("geonameid", pa.int64()),
        ("name", pa.string()),
        ("asciiname", pa.string()),
        ("alternatenames", pa.string()),
        ("latitude", pa.float64()),
        ("longitude", pa.float64()),
        ("feature_class", pa.string()),
        ("feature_code", pa.string()),
        ("country_code", pa.string()),
        ("alternate_country_codes", pa.string()),
        ("admin1", pa.string()),
        ("admin2", pa.string()),
        ("admin3", pa.string()),
        ("admin4", pa.string()),
        ("population", pa.int64()),
        ("elevation_m", pa.int64()),
        ("digital_elevation_model_m", pa.int64()),
        ("timezone", pa.string()),
        ("modification_date", pa.string()),
        ("population_status", pa.string()),
        ("simulation_tier", pa.string()),
    ]
)


def optional_integer(value: str):
    return int(value) if value else None


def valid_records(archive_path: Path):
    seen = set()
    with ZipFile(archive_path) as archive, archive.open("cities500.txt") as source:
        reader = csv.reader(io.TextIOWrapper(source, encoding="utf-8"), delimiter="\t")
        for line_number, values in enumerate(reader, 1):
            if len(values) != 19:
                raise ValueError(
                    f"Invalid GeoNames record at line {line_number}: expected 19 columns"
                )
            identity = int(values[0])
            if identity in seen:
                continue
            seen.add(identity)
            if values[6] != "P" or values[7] in EXCLUDED_CODES:
                continue
            yield values


def simulated_cities(archive_path: Path):
    ranked = defaultdict(list)
    for values in valid_records(archive_path):
        population = int(values[14] or 0)
        if population >= 1_000_000:
            ranked[values[8]].append((population, int(values[0])))
    return {
        identity
        for rows in ranked.values()
        for _, identity in sorted(rows, key=lambda item: (-item[0], item[1]))[:3]
    }


def city_row(values, simulated):
    population = int(values[14] or 0)
    identity = int(values[0])
    return {
        "geonameid": identity,
        "name": values[1],
        "asciiname": values[2],
        "alternatenames": values[3],
        "latitude": float(values[4]),
        "longitude": float(values[5]),
        "feature_class": values[6],
        "feature_code": values[7],
        "country_code": values[8],
        "alternate_country_codes": values[9],
        "admin1": values[10],
        "admin2": values[11],
        "admin3": values[12],
        "admin4": values[13],
        "population": population,
        "elevation_m": optional_integer(values[15]),
        "digital_elevation_model_m": optional_integer(values[16]),
        "timezone": values[17],
        "modification_date": values[18],
        "population_status": "present" if population > 0 else "missing",
        "simulation_tier": "simulated" if identity in simulated else "disaggregated",
    }


def export_geonames(archive_path: Path, output: Path):
    simulated = simulated_cities(archive_path)
    writer = RowWriter(output / "cities.parquet", CITY_SCHEMA, 10_000)
    countries = set()
    without_population = 0
    for values in valid_records(archive_path):
        row = city_row(values, simulated)
        countries.add(row["country_code"])
        without_population += row["population"] <= 0
        writer.add(row)
    count = writer.close()
    cities = pq.read_table(
        output / "cities.parquet",
        columns=["geonameid", "country_code", "latitude", "longitude", "population"],
    )
    with ZipFile(archive_path) as archive:
        year, month, day = archive.getinfo("cities500.txt").date_time[:3]
        source_date = f"{year:04d}-{month:02d}-{day:02d}"
    return cities, {
        "cities": count,
        "countries": len(countries),
        "cities_without_population": without_population,
        "simulated_tier": len(simulated),
        "source_date": source_date,
        "source_url": GEONAMES_URL,
    }
