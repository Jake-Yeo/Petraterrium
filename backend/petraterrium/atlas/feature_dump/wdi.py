import csv
import io
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

import pyarrow as pa

from .parquet import RowWriter, write_rows

WDI_URL = "https://databankfiles.worldbank.org/public/ddpext_download/WDI_CSV.zip"
REDISTRIBUTABLE_LICENSES = {"CC BY-4.0", "CC BY 3.0 IGO"}
AGE_SEX_CODES = [
    ("SP.POP.0014.FE.IN", "female_0_14"),
    ("SP.POP.0014.MA.IN", "male_0_14"),
    ("SP.POP.1564.FE.IN", "female_15_64"),
    ("SP.POP.1564.MA.IN", "male_15_64"),
    ("SP.POP.65UP.FE.IN", "female_65_plus"),
    ("SP.POP.65UP.MA.IN", "male_65_plus"),
]
INCOME_CODES = [
    ("SI.DST.FRST.20", "lowest_20_percent"),
    ("SI.DST.02ND.20", "second_20_percent"),
    ("SI.DST.03RD.20", "third_20_percent"),
    ("SI.DST.04TH.20", "fourth_20_percent"),
    ("SI.DST.05TH.20", "highest_20_percent"),
]
EDUCATION_CODES = [
    "SE.PRM.CUAT.ZS",
    "SE.SEC.CUAT.LO.ZS",
    "SE.SEC.CUAT.UP.ZS",
    "SE.SEC.CUAT.PO.ZS",
    "SE.TER.CUAT.BA.ZS",
]
CANONICAL_CODES = {code for code, _ in AGE_SEX_CODES + INCOME_CODES} | set(EDUCATION_CODES)


def csv_rows(archive: ZipFile, name: str):
    with io.TextIOWrapper(archive.open(name), encoding="utf-8-sig", newline="") as stream:
        yield from csv.DictReader(stream)


def redistributable_series(rows):
    return [row for row in rows if row.get("License Type") in REDISTRIBUTABLE_LICENSES]


def latest_complete(values, codes):
    return all(code in values for code in codes)


def derive_wdi_marginals(observations):
    by_country_year = defaultdict(dict)
    for row in observations:
        if row["feature_id"] in CANONICAL_CODES:
            by_country_year[(row["country_code"], int(row["year"]))][row["feature_id"]] = float(
                row["value"]
            )
    candidates = []
    for (country_code, year), values in by_country_year.items():
        age_codes = [code for code, _ in AGE_SEX_CODES]
        if latest_complete(values, age_codes):
            total = sum(values[code] for code in age_codes)
            if total > 0 and all(values[code] >= 0 for code in age_codes):
                candidates.append(
                    {
                        "country_code": country_code,
                        "field": "age_sex",
                        "year": year,
                        "value": {
                            label: values[code] * 100 / total for code, label in AGE_SEX_CODES
                        },
                        "unit": "percent",
                    }
                )
        income_codes = [code for code, _ in INCOME_CODES]
        if latest_complete(values, income_codes):
            income_total = sum(values[code] for code in income_codes)
            if abs(income_total - 100) <= 0.01 and all(
                0 <= values[code] <= 100 for code in income_codes
            ):
                candidates.append(
                    {
                        "country_code": country_code,
                        "field": "income",
                        "year": year,
                        "value": {label: values[code] for code, label in INCOME_CODES},
                        "unit": "percent",
                    }
                )
        if latest_complete(values, EDUCATION_CODES):
            primary, lower, upper, postsecondary, bachelor = (
                values[code] for code in EDUCATION_CODES
            )
            if 100 >= primary >= lower >= upper >= postsecondary >= bachelor >= 0:
                candidates.append(
                    {
                        "country_code": country_code,
                        "field": "education",
                        "year": year,
                        "value": {
                            "below_primary": 100 - primary,
                            "primary": primary - lower,
                            "lower_secondary": lower - upper,
                            "upper_secondary": upper - postsecondary,
                            "postsecondary_below_bachelor": postsecondary - bachelor,
                            "bachelor_or_higher": bachelor,
                        },
                        "unit": "percent",
                    }
                )
    latest = {}
    for candidate in candidates:
        key = candidate["country_code"], candidate["field"]
        previous = latest.get(key)
        if previous is None or candidate["year"] > previous["year"]:
            latest[key] = candidate
    return sorted(latest.values(), key=lambda row: (row["country_code"], row["field"]))


def catalog_row(row):
    return {
        "feature_id": row["Series Code"],
        "name": row["Indicator Name"],
        "topic": row["Topic"],
        "short_definition": row["Short definition"],
        "long_definition": row["Long definition"],
        "unit": row["Unit of measure"],
        "periodicity": row["Periodicity"],
        "source": row["Source"],
        "methodology": row["Statistical concept and methodology"],
        "limitations": row["Limitations and exceptions"],
        "license": row["License Type"],
    }


def export_wdi(archive_path: Path, output: Path):
    history_schema = pa.schema(
        [
            ("country_code", pa.string()),
            ("feature_id", pa.string()),
            ("year", pa.int16()),
            ("value", pa.float64()),
        ]
    )
    with ZipFile(archive_path) as archive:
        all_series = list(csv_rows(archive, "WDISeries.csv"))
        allowed_rows = redistributable_series(all_series)
        allowed = {row["Series Code"] for row in allowed_rows}
        country_codes = {
            row["Country Code"]: row["2-alpha code"].upper()
            for row in csv_rows(archive, "WDICountry.csv")
            if row.get("Region") and len(row.get("2-alpha code", "")) == 2
        }
        write_rows(
            output / "wdi_feature_catalog.parquet",
            [catalog_row(row) for row in allowed_rows],
        )
        latest = {}
        canonical = []
        history_path = output / "wdi_country_history.parquet"
        writer = RowWriter(history_path, history_schema)
        for source_row in csv_rows(archive, "WDICSV.csv"):
            country_code = country_codes.get(source_row["Country Code"])
            feature_id = source_row["Indicator Code"]
            if country_code is None or feature_id not in allowed:
                continue
            for year_text, raw_value in source_row.items():
                if not year_text.isdigit() or raw_value in (None, ""):
                    continue
                row = {
                    "country_code": country_code,
                    "feature_id": feature_id,
                    "year": int(year_text),
                    "value": float(raw_value),
                }
                writer.add(row)
                key = country_code, feature_id
                if key not in latest or row["year"] > latest[key]["year"]:
                    latest[key] = row
                if feature_id in CANONICAL_CODES:
                    canonical.append(row)
        history_count = writer.close()
        latest_rows = sorted(
            latest.values(), key=lambda row: (row["country_code"], row["feature_id"])
        )
        write_rows(output / "wdi_country_latest.parquet", latest_rows, history_schema)
        year, month, day = archive.getinfo("WDICSV.csv").date_time[:3]
        release_date = f"{year:04d}-{month:02d}-{day:02d}"
    latest_counts = Counter(row["country_code"] for row in latest_rows)
    return {
        "series": len(allowed_rows),
        "restricted_series_omitted": len(all_series) - len(allowed_rows),
        "countries": len({row["country_code"] for row in latest_rows}),
        "historical_values": history_count,
        "latest_values": len(latest_rows),
        "release_date": release_date,
        "latest_counts": dict(latest_counts),
        "canonical": derive_wdi_marginals(canonical),
    }
