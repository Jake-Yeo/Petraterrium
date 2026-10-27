import csv
import gzip
from collections import defaultdict
from pathlib import Path

import pycountry

from ..regions import country_region

WPP_AGE_SEX_URL = (
    "https://population.un.org/wpp/assets/Excel%20Files/1_Indicator%20(Standard)/"
    "CSV_FILES/WPP2024_PopulationByAge5GroupSex_Medium.csv.gz"
)
WPP_DEMOGRAPHIC_INDICATORS_URL = (
    "https://population.un.org/wpp/assets/Excel%20Files/1_Indicator%20(Standard)/"
    "CSV_FILES/WPP2024_Demographic_Indicators_Medium.csv.gz"
)
WPP_DEMOGRAPHIC_NOTES_URL = (
    "https://population.un.org/wpp/assets/Excel%20Files/1_Indicator%20(Standard)/"
    "CSV_FILES/WPP2024_Demographic_Indicators_notes.csv"
)
WPP_VERSION = "2024 Revision"
WPP_LICENSE = "CC BY 3.0 IGO"
WPP_ESTIMATE_YEAR = 2023
WPP_COUNTRY_NAME = "Region, subregion, country or area *"
WPP_ISO3 = "ISO3 Alpha-code"
SPECIAL_ISO3_CODES = {"XKX": "XK"}
IDENTITY_COLUMNS = {
    "Index",
    "SortOrder",
    "LocID",
    "ISO3_code",
    "ISO2_code",
    "SDMX_code",
    "LocTypeID",
    "LocTypeName",
    "ParentID",
    "Location",
    "VarID",
    "Variant",
    WPP_COUNTRY_NAME,
    "Notes",
    "Location code",
    WPP_ISO3,
    "ISO2 Alpha-code",
    "SDMX code**",
    "Type",
    "Parent code",
    "Year",
    "Time",
}


def csv_rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
        yield from csv.DictReader(stream)


def parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    normalized = value.strip().replace(" ", "").replace(",", "")
    if not normalized or normalized == "..":
        return None
    return float(normalized)


def row_year(row: dict[str, str]) -> int | None:
    value = row.get("Time") or row.get("Year")
    number = parse_number(value)
    return int(number) if number is not None else None


def country_code(row: dict[str, str]) -> str | None:
    direct = (row.get("ISO2_code") or row.get("ISO2 Alpha-code") or "").strip().upper()
    if len(direct) == 2:
        return direct
    alpha3 = (row.get("ISO3_code") or row.get(WPP_ISO3) or "").strip().upper()
    if alpha3 in SPECIAL_ISO3_CODES:
        return SPECIAL_ISO3_CODES[alpha3]
    country = pycountry.countries.get(alpha_3=alpha3)
    return country.alpha_2 if country is not None else None


def is_country_estimate(row: dict[str, str], estimate_year: int) -> bool:
    if estimate_year > WPP_ESTIMATE_YEAR:
        raise ValueError(
            f"WPP {WPP_VERSION} estimate cutoff is {WPP_ESTIMATE_YEAR}; "
            f"{estimate_year} is projection"
        )
    variant = row.get("Variant", "").strip().casefold()
    location_type = (row.get("LocTypeName") or row.get("Type") or "").strip().casefold()
    return (
        variant in {"estimates", "medium"}
        and location_type == "country/area"
        and row_year(row) == estimate_year
        and country_code(row) is not None
    )


def population_count(value: str | None) -> int:
    number = parse_number(value)
    if number is None:
        raise ValueError("WPP population value is missing")
    if number < 0:
        raise ValueError("WPP population value cannot be negative")
    return round(number * 1_000)


def country_age_sex_rows(path: Path, estimate_year: int = WPP_ESTIMATE_YEAR) -> list[dict]:
    rows = []
    for source in csv_rows(path):
        if not is_country_estimate(source, estimate_year):
            continue
        code = country_code(source)
        country_name = (source.get("Location") or source.get(WPP_COUNTRY_NAME) or "").strip()
        base = {
            "country_code": code,
            "country_name": country_name,
            "region": country_region(code),
            "year": estimate_year,
            "age_group": (source.get("AgeGrp") or source.get("Age") or "").strip(),
            "source_variant": source.get("Variant", "").strip(),
        }
        rows.extend(
            [
                base | {"sex": "female", "population": population_count(source["PopFemale"])},
                base | {"sex": "male", "population": population_count(source["PopMale"])},
            ]
        )
    if not rows:
        raise ValueError(f"WPP age/sex source has no country estimates for {estimate_year}")
    totals = defaultdict(int)
    for row in rows:
        totals[row["country_code"]] += row["population"]
    for row in rows:
        total = totals[row["country_code"]]
        row["population_percent"] = round(row["population"] * 100 / total, 8) if total else 0.0
    return sorted(
        rows, key=lambda row: (row["country_code"], age_order(row["age_group"]), row["sex"])
    )


def country_population_rows(path: Path, estimate_year: int = WPP_ESTIMATE_YEAR) -> list[dict]:
    rows = []
    for source in csv_rows(path):
        if not is_country_estimate(source, estimate_year):
            continue
        code = country_code(source)
        rows.append(
            {
                "country_code": code,
                "country_name": (
                    source.get("Location") or source.get(WPP_COUNTRY_NAME) or ""
                ).strip(),
                "region": country_region(code),
                "year": estimate_year,
                "population": population_count(
                    source.get("TPopulation1July") or source.get("PopTotal")
                ),
                "source_variant": source.get("Variant", "").strip(),
            }
        )
    if not rows:
        raise ValueError(f"WPP demographic source has no country estimates for {estimate_year}")
    global_population = sum(row["population"] for row in rows)
    region_populations = defaultdict(int)
    for row in rows:
        region_populations[row["region"]] += row["population"]
    for row in rows:
        region_population = region_populations[row["region"]]
        row["global_population_percent"] = round(row["population"] * 100 / global_population, 8)
        row["region_population_percent"] = round(row["population"] * 100 / region_population, 8)
    return sorted(rows, key=lambda row: row["country_code"])


def demographic_indicator_rows(
    path: Path,
    estimate_year: int = WPP_ESTIMATE_YEAR,
    metadata_path: Path | None = None,
) -> list[dict]:
    metadata = demographic_indicator_metadata(metadata_path) if metadata_path else {}
    rows = []
    for source in csv_rows(path):
        if not is_country_estimate(source, estimate_year):
            continue
        code = country_code(source)
        for indicator, raw_value in source.items():
            if indicator in IDENTITY_COLUMNS:
                continue
            value = parse_number(raw_value)
            if value is None:
                continue
            details = metadata.get(indicator, {})
            rows.append(
                {
                    "country_code": code,
                    "country_name": (
                        source.get("Location") or source.get(WPP_COUNTRY_NAME) or ""
                    ).strip(),
                    "region": country_region(code),
                    "year": estimate_year,
                    "indicator": indicator,
                    "indicator_name": details.get("indicator_name", indicator),
                    "topic": details.get("topic", ""),
                    "unit": details.get("unit", "source-defined"),
                    "value": value,
                    "source_variant": source.get("Variant", "").strip(),
                }
            )
    return sorted(rows, key=lambda row: (row["country_code"], row["indicator"]))


def demographic_indicator_metadata(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream)
        return {
            row["Indicator"]: {
                "indicator_name": row["IndicatorName"],
                "topic": row["Topic"],
                "unit": row["Unit"],
            }
            for row in rows
            if row.get("Indicator")
        }


def age_order(age_group: str) -> int:
    start = age_group.split("-", 1)[0].rstrip("+")
    return int(start)


def aggregate_region_age_sex(country_rows: list[dict]) -> list[dict]:
    populations = defaultdict(int)
    countries = defaultdict(set)
    region_totals = defaultdict(int)
    source_variants = defaultdict(set)
    for row in country_rows:
        key = row["region"], row["year"], row["age_group"], row["sex"]
        populations[key] += row["population"]
        countries[key].add(row["country_code"])
        source_variants[key].add(row["source_variant"])
        region_totals[(row["region"], row["year"])] += row["population"]
    rows = []
    for (region, year, age_group, sex), population in populations.items():
        total = region_totals[(region, year)]
        rows.append(
            {
                "region": region,
                "year": year,
                "age_group": age_group,
                "sex": sex,
                "population": population,
                "population_percent": round(population * 100 / total, 8) if total else 0.0,
                "countries_covered": len(countries[(region, year, age_group, sex)]),
                "source_variant": ", ".join(
                    sorted(source_variants[(region, year, age_group, sex)])
                ),
            }
        )
    return sorted(rows, key=lambda row: (row["region"], age_order(row["age_group"]), row["sex"]))


def aggregate_region_populations(country_rows: list[dict]) -> list[dict]:
    populations = defaultdict(int)
    countries = defaultdict(set)
    source_variants = defaultdict(set)
    for row in country_rows:
        key = row["region"], row["year"]
        populations[key] += row["population"]
        countries[key].add(row["country_code"])
        source_variants[key].add(row["source_variant"])
    global_population = sum(populations.values())
    return [
        {
            "region": region,
            "year": year,
            "population": population,
            "countries_covered": len(countries[(region, year)]),
            "global_population_percent": round(population * 100 / global_population, 8),
            "source_variant": ", ".join(sorted(source_variants[(region, year)])),
        }
        for (region, year), population in sorted(populations.items())
    ]
