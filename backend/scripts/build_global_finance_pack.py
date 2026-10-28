import csv
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

from petraterrium.atlas.regions import CANONICAL_REGIONS, country_region

ARCHIVE_DIGEST = "1cbb81b7e8e656e05fe9236f201d6d59a82d62a77f96c147c1bc63940a7b0c0c"
ARCHIVE_RELEASE_DATE = "2026-10-08"
PACK_VERSION = "wdi-global-finance-2026-10-08-v1"
MEANINGFUL_REGIONS = tuple(
    region for region in CANONICAL_REGIONS if region != "Rest / unassigned"
)
PRIORITY_COUNTRIES = (
    "IN",
    "CN",
    "US",
    "ID",
    "PK",
    "NG",
    "BR",
    "BD",
    "RU",
    "MX",
    "CA",
    "AU",
)
INDICATORS = {
    "population": "SP.POP.TOTL",
    "gni_per_capita_ppp": "NY.GNP.PCAP.PP.CD",
    "gdp_per_capita_ppp": "NY.GDP.PCAP.PP.CD",
    "household_consumption_total_ppp": "NE.CON.PRVT.PP.CD",
    "gini": "SI.POV.GINI",
    "income_share_lowest_20": "SI.DST.FRST.20",
    "income_share_second_20": "SI.DST.02ND.20",
    "income_share_third_20": "SI.DST.03RD.20",
    "income_share_fourth_20": "SI.DST.04TH.20",
    "income_share_highest_20": "SI.DST.05TH.20",
    "adjusted_net_savings_pct_gni": "NY.ADJ.SVNG.GN.ZS",
    "gross_domestic_savings_pct_gdp": "NY.GDS.TOTL.ZS",
    "private_credit_pct_gdp": "FS.AST.PRVT.GD.ZS",
    "official_exchange_rate": "PA.NUS.FCRF",
    "ppp_conversion_factor": "PA.NUS.PPP",
}
DERIVED_CONSUMPTION_KEY = "household_consumption_per_capita_ppp"


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def archive_rows(archive: ZipFile, member: str):
    with io.TextIOWrapper(
        archive.open(member), encoding="utf-8-sig", newline=""
    ) as stream:
        yield from csv.DictReader(stream)


def country_catalog(archive: ZipFile) -> dict[str, dict[str, str]]:
    countries = {}
    for row in archive_rows(archive, "WDICountry.csv"):
        alpha2 = row.get("2-alpha code", "").upper()
        if not row.get("Region") or len(alpha2) != 2:
            continue
        region = country_region(alpha2)
        if region not in MEANINGFUL_REGIONS:
            continue
        countries[row["Country Code"]] = {
            "country_code": alpha2,
            "iso3": row["Country Code"],
            "name": row["Short Name"],
            "region": region,
            "currency_name": row["Currency Unit"],
        }
    return countries


def series_catalog(archive: ZipFile) -> dict[str, dict[str, str]]:
    selected = set(INDICATORS.values())
    result = {}
    for row in archive_rows(archive, "WDISeries.csv"):
        indicator_id = row["Series Code"]
        if indicator_id not in selected:
            continue
        license_name = row["License Type"]
        if license_name not in {"CC BY-4.0", "CC BY 3.0 IGO"}:
            raise ValueError(f"Indicator {indicator_id} is not redistributable")
        result[indicator_id] = {
            "name": row["Indicator Name"],
            "unit": row["Unit of measure"],
            "license": license_name,
            "source": row["Source"],
        }
    missing = selected - result.keys()
    if missing:
        raise ValueError(f"WDI archive lacks required indicator metadata: {sorted(missing)}")
    return result


def latest_observations(
    archive: ZipFile, countries: dict[str, dict[str, str]]
) -> dict[str, dict[str, dict[str, float | int]]]:
    indicator_names = {indicator_id: name for name, indicator_id in INDICATORS.items()}
    result: dict[str, dict[str, dict[str, float | int]]] = defaultdict(dict)
    for row in archive_rows(archive, "WDICSV.csv"):
        country = countries.get(row["Country Code"])
        metric_name = indicator_names.get(row["Indicator Code"])
        if country is None or metric_name is None:
            continue
        values = [
            (int(year), float(raw_value))
            for year, raw_value in row.items()
            if year.isdigit() and raw_value not in (None, "")
        ]
        if not values:
            continue
        year, value = values[-1]
        result[country["country_code"]][metric_name] = {
            "indicator_id": row["Indicator Code"],
            "year": year,
            "value": value,
        }
    return result


def add_consumption_per_capita(metrics: dict[str, dict[str, float | int]]) -> None:
    consumption = metrics.get("household_consumption_total_ppp")
    population = metrics.get("population")
    if consumption is None or population is None or float(population["value"]) <= 0:
        return
    metrics[DERIVED_CONSUMPTION_KEY] = {
        "indicator_id": "NE.CON.PRVT.PP.CD/SP.POP.TOTL",
        "component_years": {
            "NE.CON.PRVT.PP.CD": int(consumption["year"]),
            "SP.POP.TOTL": int(population["year"]),
        },
        "year": min(int(consumption["year"]), int(population["year"])),
        "value": float(consumption["value"]) / float(population["value"]),
    }


def add_price_level_ratio(metrics: dict[str, dict[str, float | int]]) -> None:
    ppp = metrics.get("ppp_conversion_factor")
    exchange = metrics.get("official_exchange_rate")
    if ppp is None or exchange is None or float(exchange["value"]) <= 0:
        return
    metrics["price_level_ratio"] = {
        "indicator_id": "PA.NUS.PPP/PA.NUS.FCRF",
        "component_years": {
            "PA.NUS.PPP": int(ppp["year"]),
            "PA.NUS.FCRF": int(exchange["year"]),
        },
        "year": min(int(ppp["year"]), int(exchange["year"])),
        "value": float(ppp["value"]) / float(exchange["value"]),
    }


def weighted_metric(
    members: list[dict[str, object]], metric_name: str
) -> dict[str, object] | None:
    total_population = sum(
        float(member["metrics"]["population"]["value"])
        for member in members
        if "population" in member["metrics"]
    )
    covered = [
        member
        for member in members
        if "population" in member["metrics"] and metric_name in member["metrics"]
    ]
    covered_population = sum(
        float(member["metrics"]["population"]["value"]) for member in covered
    )
    if covered_population <= 0:
        return None
    value = sum(
        float(member["metrics"][metric_name]["value"])
        * float(member["metrics"]["population"]["value"])
        for member in covered
    ) / covered_population
    years = [int(member["metrics"][metric_name]["year"]) for member in covered]
    indicator_ids = sorted(
        {str(member["metrics"][metric_name]["indicator_id"]) for member in covered}
    )
    return {
        "aggregation": "population_weighted_mean",
        "indicator_ids": indicator_ids,
        "observation_year_min": min(years),
        "observation_year_max": max(years),
        "value": value,
        "covered_population": round(covered_population),
        "total_population": round(total_population),
        "coverage_percent": (
            round(100 * covered_population / total_population, 6)
            if total_population
            else 0
        ),
        "country_count": len(covered),
    }


def regional_aggregates(countries: list[dict[str, object]]) -> dict[str, object]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for country in countries:
        grouped[str(country["region"])].append(country)
    metric_names = sorted(
        {
            metric_name
            for country in countries
            for metric_name in country["metrics"]
            if metric_name not in {"population", "household_consumption_total_ppp"}
        }
    )
    result = {}
    for region in MEANINGFUL_REGIONS:
        members = grouped[region]
        population = sum(
            round(float(member["metrics"]["population"]["value"]))
            for member in members
            if "population" in member["metrics"]
        )
        metrics = {
            metric_name: aggregate
            for metric_name in metric_names
            if (aggregate := weighted_metric(members, metric_name)) is not None
        }
        result[region] = {
            "population": population,
            "country_count": len(members),
            "metrics": metrics,
        }
    return result


def build_pack(archive_path: Path) -> dict[str, object]:
    digest = file_digest(archive_path)
    if digest != ARCHIVE_DIGEST:
        raise ValueError(
            f"WDI archive digest mismatch: expected {ARCHIVE_DIGEST}, found {digest}"
        )
    with ZipFile(archive_path) as archive:
        country_metadata = country_catalog(archive)
        series = series_catalog(archive)
        observations = latest_observations(archive, country_metadata)
    countries = []
    for _iso3, metadata in sorted(
        country_metadata.items(), key=lambda item: item[1]["country_code"]
    ):
        metrics = observations.get(metadata["country_code"], {})
        if "population" not in metrics:
            continue
        add_consumption_per_capita(metrics)
        add_price_level_ratio(metrics)
        countries.append({**metadata, "metrics": metrics})
    country_codes = {country["country_code"] for country in countries}
    missing_priority = set(PRIORITY_COUNTRIES) - country_codes
    if missing_priority:
        raise ValueError(f"Priority countries missing from pack: {sorted(missing_priority)}")
    regions = regional_aggregates(countries)
    missing_regions = set(MEANINGFUL_REGIONS) - regions.keys()
    if missing_regions:
        raise ValueError(f"Canonical regions missing from pack: {sorted(missing_regions)}")
    return {
        "schema_version": 1,
        "version": PACK_VERSION,
        "source": {
            "publisher": "World Bank",
            "dataset": "World Development Indicators",
            "dataset_url": "https://databank.worldbank.org/source/world-development-indicators",
            "archive_url": "https://databankfiles.worldbank.org/public/ddpext_download/WDI_CSV.zip",
            "archive_sha256": digest,
            "archive_release_date": ARCHIVE_RELEASE_DATE,
            "license": "CC BY 4.0 or CC BY 3.0 IGO by retained series",
            "license_url": "https://datacatalog.worldbank.org/public-licenses",
            "indicators": series,
        },
        "accounting_unit": "current international dollars (PPP)",
        "priority_countries": list(PRIORITY_COUNTRIES),
        "methodology": {
            "country_values": "Latest available observation per retained WDI indicator.",
            "regional_values": (
                "Population-weighted means of available country observations using "
                "each country's latest WDI population."
            ),
            "income_distribution": (
                "Each person is assigned deterministically to one equal-population "
                "quintile. The quintile mean is GNI per capita PPP multiplied by that "
                "quintile's WDI income share and divided by 20 percent. Within-quintile "
                "variation is an explicit bounded imputation, not a measured "
                "microdistribution."
            ),
            "consumption": (
                "Household consumption per capita divides WDI household consumption "
                "PPP by WDI population. Where absent, the sampler uses that country's "
                "GNI and adjusted net savings as an explicit high-uncertainty fallback."
            ),
            "price_level": (
                "Country price level is the WDI PPP conversion factor divided by the "
                "official market exchange rate. It is a derived relative level, not a "
                "basket price or household cost-of-living observation."
            ),
            "stocks": (
                "WDI supplies macro flows and private-credit context, not person-level "
                "liquid balances, savings stocks, or household debt. Sampler stock "
                "values are explicit high-uncertainty model estimates and never "
                "measured claims."
            ),
        },
        "limitations": [
            "Observation years differ by country and indicator.",
            (
                "Income quintile shares are marginals and contain no age, education, "
                "occupation, or behavior joint distribution."
            ),
            "GNI per capita is a national-account aggregate rather than observed personal income.",
            (
                "Private credit as a percent of GDP is not household debt and is "
                "retained only as macro context."
            ),
            (
                "Regional aggregates cover countries with available indicators and "
                "report population coverage for every metric."
            ),
        ],
        "countries": countries,
        "regions": regions,
    }


def main() -> None:
    backend = Path(__file__).resolve().parents[1]
    archive_path = backend / "data" / "sources" / "WDI_CSV.zip"
    output_path = (
        backend
        / "petraterrium"
        / "simulation"
        / "defaults"
        / "global-finance-wdi-v1.json"
    )
    pack = build_pack(archive_path)
    output_path.write_text(
        json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
