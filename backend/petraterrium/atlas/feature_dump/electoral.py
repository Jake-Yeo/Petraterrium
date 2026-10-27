import csv
import io
import json
import sqlite3
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pyarrow as pa
from shapely import STRtree, from_wkb, points

from .electoral_sources import export_electoral_source_catalog
from .parquet import RowWriter, write_rows

BLUE_DB_URL = "https://zenodo.org/api/records/21434112/files/BLUE_DB.zip/content"
BLUE_DB_RECORD_URL = "https://zenodo.org/records/21434112"
BLUE_DB_RELEASE = "v2025.1"
BLUE_DB_PUBLISHED_DATE = "2026-07-18"
GISCO_LAU_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/lau/gpkg/LAU_RG_01M_2024_4326.gpkg"
)
GISCO_LAU_YEAR = 2024

ALIGNMENT_KEYS = (
    "radical_left",
    "left_or_center_left",
    "center_or_center_right",
    "radical_right",
    "other",
    "unknown",
)
IDEOLOGY_LABELS = {
    "radical left": "radical_left",
    "left or center-left, including non-radical greens": "left_or_center_left",
    "center, center-right or moderate right": "center_or_center_right",
    "radical right": "radical_right",
    "other": "other",
    "unknown": "unknown",
    "": "unknown",
}
ELECTION_METADATA_COLUMNS = {
    "gisco_id",
    "name",
    "registered",
    "turnout",
    "invalid",
    "blank",
}
GEONAMES_TO_GISCO_COUNTRY = {"GR": "EL"}
GISCO_TO_GEONAMES_COUNTRY = {value: key for key, value in GEONAMES_TO_GISCO_COUNTRY.items()}

RESULT_SCHEMA = pa.schema(
    [
        ("election_id", pa.string()),
        ("country_code", pa.string()),
        ("geonames_country_code", pa.string()),
        ("parliament_name", pa.string()),
        ("election_date", pa.string()),
        ("round", pa.int32()),
        ("vote_type", pa.string()),
        ("source_file", pa.string()),
        ("gisco_id", pa.string()),
        ("geography_name", pa.string()),
        ("registered", pa.int64()),
        ("turnout", pa.int64()),
        ("invalid", pa.int64()),
        ("blank", pa.int64()),
        ("valid_votes", pa.int64()),
        ("classified_votes", pa.int64()),
        ("unknown_votes", pa.int64()),
        ("turnout_percent", pa.float64()),
        ("classified_vote_percent", pa.float64()),
        ("radical_left_votes", pa.int64()),
        ("left_or_center_left_votes", pa.int64()),
        ("center_or_center_right_votes", pa.int64()),
        ("radical_right_votes", pa.int64()),
        ("other_votes", pa.int64()),
        ("unknown_alignment_votes", pa.int64()),
        ("radical_left_percent", pa.float64()),
        ("left_or_center_left_percent", pa.float64()),
        ("center_or_center_right_percent", pa.float64()),
        ("radical_right_percent", pa.float64()),
        ("other_percent", pa.float64()),
        ("unknown_alignment_percent", pa.float64()),
        ("party_votes_json", pa.string()),
        ("ballot_reconciliation_difference", pa.int64()),
        ("source_validation_issue_count", pa.int32()),
        ("source", pa.string()),
        ("source_url", pa.string()),
        ("source_version", pa.string()),
        ("source_published_date", pa.string()),
    ]
)

ELECTION_SCHEMA = pa.schema(
    [
        ("election_id", pa.string()),
        ("country_code", pa.string()),
        ("geonames_country_code", pa.string()),
        ("parliament_name", pa.string()),
        ("election_date", pa.string()),
        ("round", pa.int32()),
        ("vote_type", pa.string()),
        ("source_file", pa.string()),
        ("party_ids_json", pa.string()),
        ("geography_rows", pa.int64()),
        ("source", pa.string()),
        ("source_url", pa.string()),
        ("source_version", pa.string()),
        ("source_published_date", pa.string()),
    ]
)

GEOGRAPHY_SCHEMA = pa.schema(
    [
        ("geography_type", pa.string()),
        ("gisco_id", pa.string()),
        ("id", pa.string()),
        ("name", pa.string()),
        ("level", pa.string()),
        ("start_year", pa.string()),
        ("end_year", pa.string()),
        ("predecessors_json", pa.string()),
        ("parent", pa.string()),
        ("historical_names_json", pa.string()),
        ("special_type", pa.string()),
    ]
)

CITY_MATCH_SCHEMA = pa.schema(
    [
        ("geonameid", pa.int64()),
        ("gisco_id", pa.string()),
        ("status", pa.string()),
        ("match_method", pa.string()),
    ]
)

CITY_AVAILABILITY_SCHEMA = pa.schema(
    [
        ("geonameid", pa.int64()),
        ("gisco_id", pa.string()),
        ("election_count", pa.int32()),
        ("latest_election_date", pa.string()),
        ("measurement", pa.string()),
        ("status", pa.string()),
    ]
)


def optional_count(value):
    if value in (None, ""):
        return None
    number = Decimal(str(value))
    if number != number.to_integral_value():
        raise ValueError(f"Expected an integer count, received {value}")
    return int(number)


def optional_round(value):
    if value in (None, ""):
        return None
    return optional_count(value)


def aggregate_election_row(row, party_columns, ideologies):
    alignment_votes = {key: 0 for key in ALIGNMENT_KEYS}
    party_votes = {}
    validation_issues = 0
    for party_id in party_columns:
        count = optional_count(row.get(party_id))
        if count is None:
            validation_issues += 1
            continue
        if count:
            party_votes[party_id] = count
        if count < 0:
            validation_issues += 1
            continue
        alignment = ideologies.get(party_id, "unknown")
        if alignment not in ALIGNMENT_KEYS:
            alignment = "unknown"
        alignment_votes[alignment] += count
    valid_votes = sum(alignment_votes.values())
    classified_votes = valid_votes - alignment_votes["unknown"]
    counts = {
        field: optional_count(row.get(field))
        for field in ("registered", "turnout", "invalid", "blank")
    }
    validation_issues += sum(value is not None and value < 0 for value in counts.values())
    registered = counts["registered"]
    turnout = counts["turnout"]
    turnout_percent = None
    if registered is not None and turnout is not None and registered > 0 and turnout >= 0:
        turnout_percent = turnout * 100.0 / registered
    classified_percent = None
    alignment_percent = {key: None for key in ALIGNMENT_KEYS}
    if valid_votes > 0:
        classified_percent = classified_votes * 100.0 / valid_votes
        alignment_percent = {
            key: alignment_votes[key] * 100.0 / valid_votes for key in ALIGNMENT_KEYS
        }
    reconciliation = None
    if all(value is not None and value >= 0 for value in counts.values()):
        reconciliation = turnout - counts["invalid"] - counts["blank"] - valid_votes
    return {
        **counts,
        "valid_votes": valid_votes,
        "classified_votes": classified_votes,
        "unknown_votes": alignment_votes["unknown"],
        "turnout_percent": turnout_percent,
        "classified_vote_percent": classified_percent,
        "alignment_votes": alignment_votes,
        "alignment_percent": alignment_percent,
        "party_votes": party_votes,
        "ballot_reconciliation_difference": reconciliation,
        "source_validation_issue_count": validation_issues,
    }


def read_csv_member(archive, member):
    with archive.open(member) as source:
        return list(csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig")))


def party_ideologies(rows):
    candidates = defaultdict(set)
    for row in rows:
        candidates[(row["region"], row["party_id"])].add(
            IDEOLOGY_LABELS.get(row["ideology"], "unknown")
        )
    by_country = defaultdict(dict)
    for (country_code, party_id), values in candidates.items():
        by_country[country_code][party_id] = next(iter(values)) if len(values) == 1 else "unknown"
    return by_country


def export_party_catalogs(archive, output):
    members = {
        "blue_parties.parquet": "BLUE_DB/dist/parties/parties.csv",
        "blue_eu_parties.parquet": "BLUE_DB/dist/parties/eu_parties.csv",
        "blue_ep_groups.parquet": "BLUE_DB/dist/parties/ep_groups.csv",
    }
    counts = {}
    rows_by_file = {}
    for filename, member in members.items():
        rows = read_csv_member(archive, member)
        rows_by_file[filename] = rows
        counts[filename] = write_rows(output / filename, rows)
    return rows_by_file, counts


def export_geographies(archive, output):
    members = {
        "lau": "BLUE_DB/dist/geo/laus.csv",
        "nuts": "BLUE_DB/dist/geo/nuts.csv",
        "special": "BLUE_DB/dist/geo/special.csv",
    }
    rows = []
    counts = {}
    for geography_type, member in members.items():
        source_rows = read_csv_member(archive, member)
        counts[geography_type] = len(source_rows)
        for row in source_rows:
            rows.append(
                {
                    "geography_type": geography_type,
                    "gisco_id": row.get("gisco_id") or row.get("id"),
                    "id": row.get("id") or row.get("gisco_id"),
                    "name": row.get("name_or", ""),
                    "level": row.get("level", ""),
                    "start_year": row.get("start_year", ""),
                    "end_year": row.get("end_year", ""),
                    "predecessors_json": row.get("predecessors", ""),
                    "parent": row.get("parent", ""),
                    "historical_names_json": row.get("names", ""),
                    "special_type": row.get("type", ""),
                }
            )
    write_rows(output / "blue_geographies.parquet", rows, GEOGRAPHY_SCHEMA)
    return counts


def geopackage_wkb(blob):
    if blob[:2] != b"GP":
        raise ValueError("Invalid GeoPackage geometry header")
    envelope_code = (blob[3] >> 1) & 7
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    if envelope_code not in envelope_sizes:
        raise ValueError("Unsupported GeoPackage geometry envelope")
    return blob[8 + envelope_sizes[envelope_code] :]


def load_lau_geometries(path, country_codes):
    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        table_name, geometry_column = connection.execute(
            "SELECT table_name,column_name FROM gpkg_geometry_columns"
        ).fetchone()
        placeholders = ",".join("?" for _ in country_codes)
        quoted_table = table_name.replace('"', '""')
        quoted_geometry = geometry_column.replace('"', '""')
        query = (
            f'SELECT "{quoted_geometry}",GISCO_ID,CNTR_CODE FROM "{quoted_table}" '
            f"WHERE CNTR_CODE IN ({placeholders})"
        )
        return [
            {
                "gisco_id": gisco_id,
                "country_code": country_code,
                "geometry": from_wkb(geopackage_wkb(blob)),
            }
            for blob, gisco_id, country_code in connection.execute(query, sorted(country_codes))
        ]


def match_city_points_to_laus(cities, laus):
    laus_by_country = defaultdict(list)
    for lau in laus:
        laus_by_country[lau["country_code"]].append(lau)
    cities_by_country = defaultdict(list)
    for city in cities.select(["geonameid", "country_code", "latitude", "longitude"]).to_pylist():
        gisco_country = GEONAMES_TO_GISCO_COUNTRY.get(city["country_code"], city["country_code"])
        cities_by_country[gisco_country].append(city)
    matches = []
    for country_code, country_cities in cities_by_country.items():
        country_laus = laus_by_country.get(country_code, [])
        if not country_laus:
            continue
        tree = STRtree([row["geometry"] for row in country_laus])
        city_points = points(
            np.array([row["longitude"] for row in country_cities]),
            np.array([row["latitude"] for row in country_cities]),
        )
        pairs = tree.query(city_points, predicate="within")
        candidates = defaultdict(list)
        for city_index, lau_index in zip(pairs[0], pairs[1], strict=True):
            candidates[int(city_index)].append(country_laus[int(lau_index)]["gisco_id"])
        for city_index, gisco_ids in candidates.items():
            if len(gisco_ids) == 1:
                matches.append(
                    {
                        "geonameid": country_cities[city_index]["geonameid"],
                        "gisco_id": gisco_ids[0],
                        "status": "imputed",
                        "match_method": "inside_lau_2024",
                    }
                )
    return pa.Table.from_pylist(
        sorted(matches, key=lambda row: row["geonameid"]), schema=CITY_MATCH_SCHEMA
    )


def result_row(metadata, source_row, aggregate):
    alignment_votes = aggregate["alignment_votes"]
    alignment_percent = aggregate["alignment_percent"]
    return {
        "election_id": metadata["file_path"],
        "country_code": metadata["country_code"],
        "geonames_country_code": GISCO_TO_GEONAMES_COUNTRY.get(
            metadata["country_code"], metadata["country_code"]
        ),
        "parliament_name": metadata["parliament_name"],
        "election_date": metadata["election_date"],
        "round": optional_round(metadata["round"]),
        "vote_type": metadata["vote_type"],
        "source_file": metadata["file_path"],
        "gisco_id": source_row["gisco_id"],
        "geography_name": source_row.get("name", ""),
        "registered": aggregate["registered"],
        "turnout": aggregate["turnout"],
        "invalid": aggregate["invalid"],
        "blank": aggregate["blank"],
        "valid_votes": aggregate["valid_votes"],
        "classified_votes": aggregate["classified_votes"],
        "unknown_votes": aggregate["unknown_votes"],
        "turnout_percent": aggregate["turnout_percent"],
        "classified_vote_percent": aggregate["classified_vote_percent"],
        "radical_left_votes": alignment_votes["radical_left"],
        "left_or_center_left_votes": alignment_votes["left_or_center_left"],
        "center_or_center_right_votes": alignment_votes["center_or_center_right"],
        "radical_right_votes": alignment_votes["radical_right"],
        "other_votes": alignment_votes["other"],
        "unknown_alignment_votes": alignment_votes["unknown"],
        "radical_left_percent": alignment_percent["radical_left"],
        "left_or_center_left_percent": alignment_percent["left_or_center_left"],
        "center_or_center_right_percent": alignment_percent["center_or_center_right"],
        "radical_right_percent": alignment_percent["radical_right"],
        "other_percent": alignment_percent["other"],
        "unknown_alignment_percent": alignment_percent["unknown"],
        "party_votes_json": json.dumps(
            aggregate["party_votes"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
        "ballot_reconciliation_difference": aggregate["ballot_reconciliation_difference"],
        "source_validation_issue_count": aggregate["source_validation_issue_count"],
        "source": "BLUE_DB Electoral Bulletins of the European Union",
        "source_url": BLUE_DB_RECORD_URL,
        "source_version": BLUE_DB_RELEASE,
        "source_published_date": BLUE_DB_PUBLISHED_DATE,
    }


def export_blue_results(archive, output, index_rows, ideologies):
    writer = RowWriter(output / "blue_electoral_results.parquet", RESULT_SCHEMA, 20_000)
    election_rows = []
    result_counts = defaultdict(int)
    latest_dates = {}
    geography_ids = set()
    total_valid_votes = 0
    total_classified_votes = 0
    validation_issue_rows = 0
    for metadata in index_rows:
        member = "BLUE_DB/dist/" + metadata["file_path"]
        with archive.open(member) as source:
            reader = csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig"))
            party_columns = [
                column for column in reader.fieldnames if column not in ELECTION_METADATA_COLUMNS
            ]
            geography_rows = 0
            country_ideologies = ideologies.get(metadata["country_code"], {})
            for source_row in reader:
                aggregate = aggregate_election_row(source_row, party_columns, country_ideologies)
                writer.add(result_row(metadata, source_row, aggregate))
                geography_rows += 1
                geography_id = source_row["gisco_id"]
                geography_ids.add(geography_id)
                result_counts[geography_id] += 1
                election_date = metadata["election_date"]
                if election_date and election_date > latest_dates.get(geography_id, ""):
                    latest_dates[geography_id] = election_date
                total_valid_votes += aggregate["valid_votes"]
                total_classified_votes += aggregate["classified_votes"]
                validation_issue_rows += aggregate["source_validation_issue_count"] > 0
        election_rows.append(
            {
                "election_id": metadata["file_path"],
                "country_code": metadata["country_code"],
                "geonames_country_code": GISCO_TO_GEONAMES_COUNTRY.get(
                    metadata["country_code"], metadata["country_code"]
                ),
                "parliament_name": metadata["parliament_name"],
                "election_date": metadata["election_date"],
                "round": optional_round(metadata["round"]),
                "vote_type": metadata["vote_type"],
                "source_file": metadata["file_path"],
                "party_ids_json": json.dumps(
                    party_columns, ensure_ascii=False, separators=(",", ":")
                ),
                "geography_rows": geography_rows,
                "source": "BLUE_DB Electoral Bulletins of the European Union",
                "source_url": BLUE_DB_RECORD_URL,
                "source_version": BLUE_DB_RELEASE,
                "source_published_date": BLUE_DB_PUBLISHED_DATE,
            }
        )
    result_rows = writer.close()
    write_rows(output / "blue_elections.parquet", election_rows, ELECTION_SCHEMA)
    classified_percent = (
        total_classified_votes * 100.0 / total_valid_votes if total_valid_votes else None
    )
    return {
        "results": result_rows,
        "elections": len(election_rows),
        "geographies_with_results": len(geography_ids),
        "total_valid_votes": total_valid_votes,
        "classified_votes": total_classified_votes,
        "classified_vote_percent": classified_percent,
        "source_validation_issue_rows": validation_issue_rows,
        "result_counts": result_counts,
        "latest_dates": latest_dates,
    }


def export_city_electoral_availability(output, matches, result_counts, latest_dates):
    rows = []
    city_matches = {}
    city_result_counts = {}
    city_latest_dates = {}
    for match in matches.to_pylist():
        geonameid = match["geonameid"]
        gisco_id = match["gisco_id"]
        count = int(result_counts.get(gisco_id, 0))
        latest_date = latest_dates.get(gisco_id)
        city_matches[geonameid] = gisco_id
        city_result_counts[geonameid] = count
        city_latest_dates[geonameid] = latest_date
        rows.append(
            {
                "geonameid": geonameid,
                "gisco_id": gisco_id,
                "election_count": count,
                "latest_election_date": latest_date,
                "measurement": "electoral_alignment_among_valid_ballots",
                "status": "imputed" if count else "missing",
            }
        )
    write_rows(
        output / "blue_city_electoral_availability.parquet",
        rows,
        CITY_AVAILABILITY_SCHEMA,
    )
    return city_matches, city_result_counts, city_latest_dates


def export_blue(archive_path: Path, boundary_path: Path, cities, output: Path):
    with ZipFile(archive_path) as archive:
        party_catalogs, party_counts = export_party_catalogs(archive, output)
        geography_counts = export_geographies(archive, output)
        index_rows = read_csv_member(archive, "BLUE_DB/dist/elections/index.csv")
        ideologies = party_ideologies(party_catalogs["blue_parties.parquet"])
        results = export_blue_results(archive, output, index_rows, ideologies)
    countries = {row["country_code"] for row in index_rows}
    laus = load_lau_geometries(boundary_path, countries)
    matches = match_city_points_to_laus(cities, laus)
    write_rows(output / "blue_city_matches.parquet", matches.to_pylist(), CITY_MATCH_SCHEMA)
    city_matches, city_result_counts, city_latest_dates = export_city_electoral_availability(
        output, matches, results["result_counts"], results["latest_dates"]
    )
    source_catalog_rows = export_electoral_source_catalog(output)
    result = {
        key: value for key, value in results.items() if key not in ("result_counts", "latest_dates")
    }
    result.update(
        {
            "countries": len(countries),
            "country_codes": sorted(countries),
            "party_catalogs": party_counts,
            "geographies": geography_counts,
            "lau_boundaries": len(laus),
            "matched_cities": matches.num_rows,
            "cities_with_results": sum(count > 0 for count in city_result_counts.values()),
            "source_catalog_rows": source_catalog_rows,
            "release": BLUE_DB_RELEASE,
            "published_date": BLUE_DB_PUBLISHED_DATE,
            "license": "CC BY 4.0",
            "boundary_year": GISCO_LAU_YEAR,
            "boundary_source_url": GISCO_LAU_URL,
            "city_matches": city_matches,
            "city_result_counts": city_result_counts,
            "city_latest_dates": city_latest_dates,
        }
    )
    return result
