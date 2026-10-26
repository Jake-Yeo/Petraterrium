import re
import sqlite3
import struct
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pyarrow as pa
import pycountry
from rasterio.warp import transform
from shapely import STRtree, from_wkb, points, to_wkb

from .parquet import RowWriter, write_rows
from .xlsx import read_sheet

UCDB_URL = (
    "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_UCDB_GLOBE_R2024A/"
    "GHS_UCDB_GLOBE_R2024A/V1-2/GHS_UCDB_GLOBE_R2024A_V1_2.zip"
)
THEME_PREFIX = "GHSL_UCDB_THEME_"
COMMON_COLUMNS = {
    "fid",
    "geom",
    "GC_UCN_MAI_2025",
    "GC_CNT_GAD_2025",
    "GC_UCA_KM2_2025",
    "GC_POP_TOT_2025",
    "GC_DEV_WIG_2025",
    "GC_DEV_USR_2025",
}
COUNTRY_ALIASES = {
    "Bolivia (Plurinational State of)": "BO",
    "Brunei Darussalam": "BN",
    "China, Taiwan Province of China": "TW",
    "Côte d'Ivoire": "CI",
    "Dem. People's Republic of Korea": "KP",
    "Democratic People's Republic of Korea": "KP",
    "Democratic Republic of the Congo": "CD",
    "Iran (Islamic Republic of)": "IR",
    "Kosovo": "XK",
    "Kosovo (under UNSC res. 1244)": "XK",
    "Lao People's Democratic Republic": "LA",
    "Micronesia (Federated States of)": "FM",
    "Northern Cyprus": "CY",
    "Palestine": "PS",
    "Republic of Korea": "KR",
    "Republic of Moldova": "MD",
    "Republic of the Congo": "CG",
    "Russian Federation": "RU",
    "State of Palestine": "PS",
    "Syrian Arab Republic": "SY",
    "Taiwan": "TW",
    "Turkey": "TR",
    "Türkiye": "TR",
    "United Republic of Tanzania": "TZ",
    "United States of America": "US",
    "Venezuela (Bolivarian Republic of)": "VE",
    "Viet Nam": "VN",
}


def decode_name(value: str | None) -> str:
    if value is None:
        return ""
    if "Ã" not in value and "Â" not in value:
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return value


def country_code(name: str) -> str | None:
    name = decode_name(name)
    if name in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[name]
    try:
        return pycountry.countries.lookup(name).alpha_2
    except LookupError:
        return None


def geopackage_wkb(blob: bytes) -> bytes:
    if blob[:2] != b"GP":
        return blob
    flags = blob[3]
    little_endian = bool(flags & 1)
    envelope_code = (flags >> 1) & 7
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    if envelope_code not in envelope_sizes:
        raise ValueError("Unsupported GeoPackage geometry envelope")
    struct.unpack("<i" if little_endian else ">i", blob[4:8])[0]
    return blob[8 + envelope_sizes[envelope_code] :]


def haversine(latitude_a, longitude_a, latitude_b, longitude_b):
    lat_a = np.radians(latitude_a)
    lat_b = np.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = np.radians(longitude_b - longitude_a)
    value = np.sin(delta_lat / 2) ** 2 + np.cos(lat_a) * np.cos(lat_b) * np.sin(
        delta_lon / 2
    ) ** 2
    return 6371.0088 * 2 * np.arctan2(np.sqrt(value), np.sqrt(1 - value))


def match_cities_to_urban_centres(cities, urban_centres, projected=True):
    if not urban_centres or cities.num_rows == 0:
        return pa.table(
            {
                "geonameid": pa.array([], type=pa.int64()),
                "ucdb_id": pa.array([], type=pa.int64()),
                "status": pa.array([], type=pa.string()),
                "match_method": pa.array([], type=pa.string()),
                "distance_km": pa.array([], type=pa.float64()),
            }
        )
    latitudes = np.asarray(cities["latitude"].to_numpy(), dtype=float)
    longitudes = np.asarray(cities["longitude"].to_numpy(), dtype=float)
    if projected:
        xs, ys = transform("EPSG:4326", "ESRI:54009", longitudes.tolist(), latitudes.tolist())
        point_geometries = points(np.asarray(xs), np.asarray(ys))
    else:
        point_geometries = points(longitudes, latitudes)
    polygon_geometries = from_wkb(
        np.asarray([row["geometry"] for row in urban_centres], dtype=object)
    )
    pairs = STRtree(polygon_geometries).query(point_geometries, predicate="intersects")
    city_countries = cities["country_code"].to_pylist()
    choices = {}
    for city_index, urban_index in zip(pairs[0], pairs[1], strict=True):
        urban = urban_centres[int(urban_index)]
        if city_countries[int(city_index)] != urban["country_code"]:
            continue
        rank = float(urban["area_km2"] or float("inf")), int(urban["ucdb_id"])
        previous = choices.get(int(city_index))
        if previous is None or rank < previous[0]:
            choices[int(city_index)] = (rank, urban)
    rows = []
    identities = cities["geonameid"].to_pylist()
    for city_index, (_, urban) in choices.items():
        distance = haversine(
            latitudes[city_index],
            longitudes[city_index],
            urban["centroid_latitude"],
            urban["centroid_longitude"],
        )
        rows.append(
            {
                "geonameid": identities[city_index],
                "ucdb_id": urban["ucdb_id"],
                "status": "imputed",
                "match_method": "inside_urban_centre",
                "distance_km": round(float(distance), 6),
            }
        )
    rows.sort(key=lambda row: row["geonameid"])
    return pa.Table.from_pylist(
        rows,
        schema=pa.schema(
            [
                ("geonameid", pa.int64()),
                ("ucdb_id", pa.int64()),
                ("status", pa.string()),
                ("match_method", pa.string()),
                ("distance_km", pa.float64()),
            ]
        ),
    )


def urban_centres(connection):
    rows = connection.execute(
        """SELECT g.ID_UC_G0,g.GC_UCN_MAI_2025,g.GC_UCN_LIS_2025,
        g.GC_CNT_UNN_2025,g.GC_UCA_KM2_2025,g.GC_POP_TOT_2025,g.geom,
        c.GC_UCC_LON_2025,c.GC_UCC_LAT_2025
        FROM GHSL_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A g
        JOIN UC_centroids c USING(ID_UC_G0) ORDER BY g.ID_UC_G0"""
    ).fetchall()
    longitudes, latitudes = transform(
        "ESRI:54009",
        "EPSG:4326",
        [row[7] for row in rows],
        [row[8] for row in rows],
    )
    result = []
    missing_countries = Counter()
    for row, longitude, latitude in zip(rows, longitudes, latitudes, strict=True):
        code = country_code(row[3])
        if code is None:
            missing_countries[row[3]] += 1
            continue
        result.append(
            {
                "ucdb_id": row[0],
                "name": decode_name(row[1]),
                "alternate_names": decode_name(row[2] or ""),
                "country_code": code,
                "area_km2": row[4],
                "population": row[5],
                "geometry": geopackage_wkb(row[6]),
                "centroid_longitude": longitude,
                "centroid_latitude": latitude,
            }
        )
    if missing_countries:
        missing = ", ".join(f"{name} ({count})" for name, count in missing_countries.items())
        raise ValueError(f"UCDB country names could not be resolved: {missing}")
    return result


def sqlite_arrow_type(type_name: str):
    name = type_name.upper()
    if "INT" in name:
        return pa.int64()
    if any(token in name for token in ("REAL", "FLOA", "DOUB")):
        return pa.float64()
    return pa.string()


def theme_name(table: str) -> str:
    return table.removeprefix(THEME_PREFIX).removesuffix("_GLOBE_R2024A").lower()


def feature_columns(connection, table: str):
    columns = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    selected = []
    for column in columns:
        name = column[1]
        if name in ("fid", "geom") or name.startswith("Unnamed:"):
            continue
        is_general = table == "GHSL_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A"
        if not is_general and name in COMMON_COLUMNS:
            continue
        selected.append((name, sqlite_arrow_type(column[2])))
    return selected


def export_theme(connection, table: str, output_path: Path, counts: Counter):
    columns = feature_columns(connection, table)
    schema = pa.schema(columns)
    names = [name for name, _ in columns]
    quoted = ",".join(f'"{name}"' for name in names)
    cursor = connection.execute(f'SELECT {quoted} FROM "{table}" ORDER BY ID_UC_G0')
    writer = RowWriter(output_path, schema, 256)
    while batch := cursor.fetchmany(256):
        for values in batch:
            row = dict(zip(names, values, strict=True))
            identity = row["ID_UC_G0"]
            counts[identity] += sum(
                value is not None and name != "ID_UC_G0" for name, value in row.items()
            )
            writer.add(row)
    writer.close()
    return names


def index_metadata(archive_path: Path):
    with ZipFile(archive_path) as archive:
        workbook = archive.read("GHS_UCDB_GLOBE_R2024A.xlsx")
    metadata = []
    current_theme = ""
    current_group = ""
    current_source = ""
    for index, row in enumerate(read_sheet(workbook, "Index"), 1):
        if index <= 2:
            continue
        padded = row + [None] * (10 - len(row))
        theme_changed = bool(padded[0])
        group_changed = bool(padded[1])
        if theme_changed:
            current_theme = str(padded[0])
        if group_changed:
            current_group = str(padded[1])
        if theme_changed or group_changed:
            current_source = ""
        if padded[6]:
            current_source = str(padded[6])
        attribute = str(padded[4] or "").strip()
        if not attribute:
            continue
        metadata.append(
            {
                "theme": current_theme,
                "group": current_group,
                "name": str(padded[3] or padded[2] or current_group),
                "attribute_template": attribute,
                "unit": str(padded[5] or ""),
                "source": current_source,
                "methodology": str(padded[7] or ""),
                "note": str(padded[8] or ""),
            }
        )
    return metadata


def attribute_pattern(template: str):
    pattern = re.escape(template).replace("XXXX", r"(\d{4})")
    return re.compile("^" + pattern + "$")


def catalog_rows(feature_tables, metadata):
    patterns = []
    for row in metadata:
        patterns.append((attribute_pattern(row["attribute_template"]), row))
    result = []
    for feature_id, table in sorted(feature_tables.items()):
        match_row = None
        match_year = None
        for pattern, candidate in patterns:
            match = pattern.match(feature_id)
            if match:
                match_row = candidate
                match_year = match.groups()[0] if match.groups() else None
                break
        result.append(
            {
                "feature_id": feature_id,
                "table": table,
                "theme": (
                    match_row["theme"]
                    if match_row
                    else Path(table).stem.replace("_", " ").title()
                ),
                "group": match_row["group"] if match_row else "",
                "name": match_row["name"] if match_row else feature_id,
                "unit": match_row["unit"] if match_row else "",
                "source": (match_row["source"] if match_row else "") or "GHS-UCDB R2024A",
                "methodology": match_row["methodology"] if match_row else "",
                "note": match_row["note"] if match_row else "",
                "year": int(match_year) if match_year else None,
                "license": "European Commission reuse decision 2011/833/EU",
            }
        )
    return result


def export_ucdb(archive_path: Path, geopackage_path: Path, cities, output: Path):
    theme_output = output / "ucdb"
    theme_output.mkdir()
    connection = sqlite3.connect(geopackage_path)
    try:
        centres = urban_centres(connection)
        centre_rows = [
            row | {"geometry": to_wkb(from_wkb(row["geometry"]))} for row in centres
        ]
        write_rows(output / "ucdb_urban_centres.parquet", centre_rows)
        matches = match_cities_to_urban_centres(cities, centres)
        import pyarrow.parquet as pq

        pq.write_table(matches, output / "ucdb_city_matches.parquet", compression="zstd")
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM gpkg_contents WHERE table_name LIKE ? ORDER BY table_name",
                (THEME_PREFIX + "%",),
            )
        ]
        counts = Counter()
        feature_tables = {}
        for table in tables:
            filename = theme_name(table) + ".parquet"
            names = export_theme(connection, table, theme_output / filename, counts)
            for name in names:
                if name != "ID_UC_G0":
                    feature_tables.setdefault(name, filename)
        catalog = catalog_rows(feature_tables, index_metadata(archive_path))
        write_rows(output / "ucdb_feature_catalog.parquet", catalog)
    finally:
        connection.close()
    matched_ids = set(matches["ucdb_id"].to_pylist())
    return {
        "urban_centres": len(centres),
        "urban_centres_matched": len(matched_ids),
        "cities_spatially_matched": matches.num_rows,
        "features": len(feature_tables),
        "features_without_index_metadata": sum(
            row["name"] == row["feature_id"] for row in catalog
        ),
        "theme_tables": len(tables),
        "feature_counts": dict(counts),
        "city_matches": {
            row["geonameid"]: row["ucdb_id"] for row in matches.to_pylist()
        },
        "release_date": "2026-05-15",
    }
