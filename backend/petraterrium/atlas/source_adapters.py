import gzip
import io
import math
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

from rasterio.io import MemoryFile
from rasterio.warp import transform

from .contracts import ImportMetadata
from .formats import parse_upload
from .validation import country_code, numeric


def distributions(rows, metadata: ImportMetadata, source: str):
    groups = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    scalars = defaultdict(lambda: defaultdict(list))
    missing = defaultdict(int)
    if source == "un_wpp":
        for index, row in enumerate(rows, 1):
            if int(float(row.get("Time", row.get("Year", 0)))) != metadata.source_date.year:
                continue
            raw_code = row.get("ISO3_code", row.get("ISO3", metadata.country_code))
            if not raw_code:
                missing["non_country_aggregate_rows"] += 1
                continue
            variant = str(row.get("Variant", "Medium"))
            if variant not in ("Medium", "Estimates", "Historical", "Medium variant"):
                missing["other_variant_rows"] += 1
                continue
            code = country_code(raw_code)
            label = str(row.get("AgeGrp", row.get("Age", row.get("AgeGrpStart", ""))))
            if not label:
                raise ValueError(f"UN WPP row {index}: missing age-group label")
            for sex, column in [("male", "PopMale"), ("female", "PopFemale")]:
                count = numeric(row.get(column))
                if count < 0:
                    raise ValueError(f"UN WPP row {index}: negative population")
                groups[code]["age_sex"][sex + "_" + label] += count
    else:
        us = source == "us_pums"
        for index, row in enumerate(rows, 1):
            code = (
                "US" if us else country_code(row.get("country_code") or metadata.country_code or "")
            )
            weight_key = "PWGTP" if us else "PERWT"
            if us and "WGTP" in row and "NP" in row and "AGEP" not in row:
                weight, size = numeric(row["WGTP"]), numeric(row["NP"])
                if weight < 0 or not 0 <= size <= 30:
                    raise ValueError(f"Household row {index}: invalid weight or household size")
                if size > 0 and weight > 0:
                    scalars[code]["household_size"].append((size, weight))
                continue
            weight = numeric(row.get(weight_key))
            if weight < 0:
                raise ValueError(f"Microdata row {index}: negative survey weight")
            age_key = "AGEP" if us else "AGE"
            if row.get(age_key) in (None, "") or row.get("SEX") in (None, ""):
                missing["age_sex"] += 1
            else:
                age, sex = numeric(row[age_key]), numeric(row["SEX"])
                if not 0 <= age <= 120 or sex not in (1, 2):
                    raise ValueError(
                        f"Microdata row {index}: unsupported age/sex special code; "
                        "resolve with the source dictionary"
                    )
                groups[code]["age_sex"][
                    ("male" if sex == 1 else "female") + "_" + str(int(age))
                ] += weight
            for field, column in [("education", "SCHL" if us else "EDATTAIN")]:
                if row.get(column) in (None, ""):
                    missing[field] += 1
                else:
                    groups[code][field][column + "_" + str(row[column])] += weight
            income = row.get("PINCP" if us else "INCWAGE")
            if income not in (None, ""):
                scalars[code]["income"].append((numeric(income), weight))
            else:
                missing["income"] += 1
    result = []
    for code in set(groups) | set(scalars):
        output = {"country_code": code}
        for field, counts in groups[code].items():
            total = sum(counts.values())
            if total > 0:
                output[field] = {label: value / total * 100 for label, value in counts.items()}
        for field, values in scalars[code].items():
            total_weight = sum(weight for _, weight in values)
            if total_weight > 0:
                output[field] = sum(value * weight for value, weight in values) / total_weight
        if "income" in output:
            output["unit"] = "USD/year" if source == "us_pums" else metadata.unit
        result.append(output)
    if not result:
        raise ValueError("No observations matched the selected source year/country")
    notes = [
        f"Derived {len(result)} country records from {len(rows)} source rows.",
        f"Native {source} loader: weighted country marginals; "
        "no city-specific observations were asserted.",
        f"Blank microdata values excluded from their field denominators: {dict(missing)}",
    ]
    return result, metadata.model_copy(update={"kind": "marginals", "processing_notes": notes})


def grid_samples(store, contents: bytes, metadata: ImportMetadata):
    if metadata.unit not in ("persons_per_cell", "persons_per_km2"):
        raise ValueError("Select the actual grid units: persons_per_cell or persons_per_km2")
    rows = []
    skipped = 0
    with MemoryFile(contents) as file, file.open() as dataset, store.connection() as conn:
        if not dataset.crs:
            raise ValueError("Population grid must declare its coordinate reference system")
        cities = conn.execute(
            "SELECT geonameid,country_code,longitude,latitude FROM cities"
            + (" WHERE country_code=?" if metadata.country_code else ""),
            (country_code(metadata.country_code),) if metadata.country_code else (),
        ).fetchall()
        xs, ys = transform(
            "EPSG:4326",
            dataset.crs,
            [c["longitude"] for c in cities],
            [c["latitude"] for c in cities],
        )
        selected = [
            (city, x, y)
            for city, x, y in zip(cities, xs, ys, strict=True)
            if dataset.bounds.left <= x < dataset.bounds.right
            and dataset.bounds.bottom < y <= dataset.bounds.top
        ]
        for (city, x, y), sample in zip(
            selected, dataset.sample([(x, y) for _, x, y in selected], masked=True), strict=True
        ):
            if sample.mask is not False and bool(sample.mask.any()):
                skipped += 1
                continue
            value = float(sample[0])
            if not math.isfinite(value) or value <= 0:
                skipped += 1
                continue
            if metadata.unit == "persons_per_cell":
                r, c = dataset.index(x, y)
                corners = [dataset.transform * (c, r), dataset.transform * (c + 1, r + 1)]
                lons, lats = transform(
                    dataset.crs, "EPSG:4326", [p[0] for p in corners], [p[1] for p in corners]
                )
                area = 6371.0088**2 * abs(
                    math.radians(lons[1] - lons[0])
                    * (math.sin(math.radians(lats[1])) - math.sin(math.radians(lats[0])))
                )
                if area <= 0:
                    raise ValueError("Grid cell area could not be resolved")
                value /= area
            rows.append(
                {
                    "geonameid": city["geonameid"],
                    "country_code": city["country_code"],
                    "density_per_km2": value,
                }
            )
    if not rows:
        raise ValueError("No valid positive population-grid samples intersected the city backbone")
    return rows, metadata.model_copy(
        update={
            "kind": "population",
            "processing_notes": [
                (
                    "City-centre cell densities are imputed; they are not city-footprint"
                    " density observations."
                ),
                f"{skipped} nodata/zero/invalid samples remain missing.",
            ],
        }
    )


def source_rows(store, filename: str, contents: bytes, metadata: ImportMetadata):
    source = metadata.source_id
    if filename.endswith(".gz"):
        from .formats import MAX_BYTES

        contents = gzip.GzipFile(fileobj=io.BytesIO(contents)).read(MAX_BYTES + 1)
        if len(contents) > MAX_BYTES:
            raise ValueError("Expanded source exceeds configured byte limit")
        filename = filename[:-3]
    if filename.endswith(".zip"):
        with ZipFile(io.BytesIO(contents)) as archive:
            candidates = [
                name
                for name in archive.namelist()
                if Path(name).suffix.lower() in (".csv", ".parquet", ".json", ".tif", ".tiff")
            ]
            if len(candidates) != 1:
                raise ValueError(
                    "Select a single data file from this source archive; multiple files need"
                    " separate versioned imports"
                )
            info = archive.getinfo(candidates[0])
            from .formats import MAX_BYTES

            if info.file_size > MAX_BYTES:
                raise ValueError("Expanded source exceeds the import byte limit")
            filename, contents = candidates[0], archive.read(candidates[0])
    if source in ("worldpop", "gpw") and Path(filename).suffix.lower() in (".tif", ".tiff"):
        return grid_samples(store, contents, metadata)
    rows = parse_upload(filename, contents)
    headers = set(rows[0])
    if source == "un_wpp" and {"PopMale", "PopFemale"} <= headers:
        return distributions(rows, metadata, source)
    if source == "us_pums" and ("PWGTP" in headers or "WGTP" in headers):
        return distributions(rows, metadata, source)
    if source == "ipums" and {"AGE", "SEX", "PERWT"} <= headers:
        return distributions(rows, metadata, source)
    return rows, metadata
