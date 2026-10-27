import json
from pathlib import Path

from .downloads import sha256_file

WDI_EDUCATION_MAPPING = {
    "standard": "ISCED 2011",
    "source_population": "Population age 25 and older",
    "method": "Differences between cumulative attainment thresholds",
    "values": {
        "below_primary": "Below completed ISCED 1",
        "primary": "ISCED 1",
        "lower_secondary": "ISCED 2",
        "upper_secondary": "ISCED 3",
        "postsecondary_below_bachelor": "ISCED 4-5 and short-cycle tertiary below bachelor",
        "bachelor_or_higher": "ISCED 6-8",
    },
    "indicators": [
        "SE.PRM.CUAT.ZS",
        "SE.SEC.CUAT.LO.ZS",
        "SE.SEC.CUAT.UP.ZS",
        "SE.SEC.CUAT.PO.ZS",
        "SE.TER.CUAT.BA.ZS",
    ],
    "limitation": "Broad derived bands, not direct microdata-coded ISCED categories",
}
WDI_INCOME_MAPPING = {
    "standard": "World Bank income-share quintiles",
    "indicators": [
        "SI.DST.FRST.20",
        "SI.DST.02ND.20",
        "SI.DST.03RD.20",
        "SI.DST.04TH.20",
        "SI.DST.05TH.20",
    ],
    "limitation": (
        "Income quintile shares measure each fixed population quintile's share of national income; "
        "they do not measure person-level income bands or a city income distribution"
    ),
}


def existing_manifest(data_directory: Path) -> dict:
    path = data_directory / "city_feature_dump" / "manifest.json"
    return json.loads(path.read_text()) if path.exists() else {}


def local_file(data_directory: Path, relative_path: str) -> dict:
    path = data_directory / relative_path
    return {
        "path": relative_path,
        "present": path.exists(),
        "bytes": path.stat().st_size if path.exists() else None,
        "sha256": sha256_file(path) if path.exists() else None,
    }


def registry_file(registry_directory: Path, filename: str) -> dict:
    path = registry_directory / filename
    return {
        "path": f"registry_feature_dump/{filename}",
        "present": path.exists(),
        "bytes": path.stat().st_size if path.exists() else None,
        "sha256": sha256_file(path) if path.exists() else None,
    }


def source_record(
    source_id,
    source,
    scope_order,
    level,
    access_status,
    source_url,
    version,
    source_date,
    license_name,
    mapping,
    restriction_reason="",
    fallback="",
    required_action="",
    files=None,
    coverage=None,
):
    return {
        "source_id": source_id,
        "source": source,
        "scope_order": scope_order,
        "level": level,
        "access_status": access_status,
        "source_url": source_url,
        "version": version,
        "source_date": source_date,
        "license": license_name,
        "mapping": mapping,
        "coverage": coverage or {"imported_geographies": 0},
        "restriction_reason": restriction_reason,
        "fallback": fallback,
        "required_action": required_action,
        "files": files or [],
    }


def source_inventory(data_directory: Path, registry_directory: Path | None = None) -> list[dict]:
    manifest = existing_manifest(data_directory)
    sources = manifest.get("sources", {})
    wdi = sources.get("wdi", {})
    geonames = sources.get("geonames", {})
    ucdb = sources.get("ucdb", {})
    households = sources.get("un_household", {})
    blue = sources.get("blue_db", {})
    registry_directory = registry_directory or data_directory / "registry_feature_dump"
    records = [
        source_record(
            "un_wpp_2024_regions",
            "UN World Population Prospects",
            1,
            "region",
            "imported"
            if (registry_directory / "wpp_region_age_sex.parquet").exists()
            else "pending",
            "https://population.un.org/wpp/",
            "2024 Revision",
            "2024-07-11",
            "CC BY 3.0 IGO",
            {
                "age": "UN five-year age groups",
                "sex": ["female", "male"],
                "population": "persons converted from source thousands",
                "aggregation": "Country counts summed into canonical Petraterrium regions",
            },
            fallback="No projection fallback; 2023 estimates only",
            coverage={
                "regions": (
                    8 if (registry_directory / "wpp_region_population.parquet").exists() else 0
                ),
                "age_sex_percent_of_wpp_universe": (
                    100.0 if (registry_directory / "wpp_region_age_sex.parquet").exists() else 0.0
                ),
            },
            files=[
                registry_file(registry_directory, "wpp_region_age_sex.parquet"),
                registry_file(registry_directory, "wpp_region_population.parquet"),
            ],
        ),
        source_record(
            "un_wpp_2024_countries",
            "UN World Population Prospects",
            2,
            "country",
            "imported"
            if (registry_directory / "wpp_country_age_sex.parquet").exists()
            else "pending",
            "https://population.un.org/wpp/",
            "2024 Revision",
            "2024-07-11",
            "CC BY 3.0 IGO",
            {
                "age": "UN five-year age groups",
                "sex": ["female", "male"],
                "population": (
                    "De facto population on 1 July; source thousands converted to persons"
                ),
                "geography": "UN ISO alpha-3 converted to ISO alpha-2",
            },
            fallback="None",
            coverage={
                "countries_or_areas": (
                    237 if (registry_directory / "wpp_country_population.parquet").exists() else 0
                ),
                "age_sex_percent_of_wpp_universe": (
                    100.0 if (registry_directory / "wpp_country_age_sex.parquet").exists() else 0.0
                ),
            },
            files=[
                registry_file(registry_directory, "wpp_country_age_sex.parquet"),
                registry_file(registry_directory, "wpp_country_population.parquet"),
            ],
        ),
        source_record(
            "world_bank_wdi",
            "World Bank World Development Indicators",
            2,
            "country",
            "imported" if wdi else "missing_local_dump",
            wdi.get(
                "source_url",
                "https://databankfiles.worldbank.org/public/ddpext_download/WDI_CSV.zip",
            ),
            f"sha256:{wdi.get('sha256')}" if wdi.get("sha256") else "unversioned",
            wdi.get("release_date", ""),
            "Per-series license; importer retains CC BY-4.0 and CC BY 3.0 IGO only",
            {"education": WDI_EDUCATION_MAPPING, "income": WDI_INCOME_MAPPING},
            fallback="Country observations inherit to cities and remain flagged inherited",
            files=[local_file(data_directory, "sources/WDI_CSV.zip")],
            coverage={
                "countries": wdi.get("countries", 0),
                "series": wdi.get("series", 0),
                "latest_values": wdi.get("latest_values", 0),
            },
        ),
        source_record(
            "un_desa_households",
            "UN DESA Database on Household Size and Composition",
            2,
            "country",
            "imported" if households else "missing_local_dump",
            households.get(
                "source_url",
                "https://www.un.org/development/desa/pd/data/household-size-and-composition",
            ),
            f"sha256:{households.get('sha256')}" if households.get("sha256") else "unversioned",
            households.get("release_date", ""),
            "UN DESA source workbook terms; provenance retained",
            {
                "household_size": "Country survey estimate with original survey year",
                "inheritance": "Country observation remains inherited at city level",
            },
            fallback="Missing countries remain missing",
            files=[local_file(data_directory, "sources/UN_DESA_household_2026.xlsx")],
            coverage={
                "countries": households.get("countries", 0),
                "features": households.get("features", 0),
                "latest_values": households.get("latest_values", 0),
            },
        ),
        source_record(
            "ipums_international",
            "IPUMS International",
            2,
            "country",
            "unavailable",
            "https://international.ipums.org/international/terms.shtml",
            "User-selected extract required",
            "",
            "Individual registered-user licence; scholarly and educational use only",
            {
                "education": "EDATTAIN/EDUCD to ISCED",
                "occupation": "OCCISCO to ISCO",
                "joint_distributions": "Use PERWT and HHWT; preserve sample and geography metadata",
            },
            restriction_reason=(
                "Account approval is required and the licence prohibits redistribution "
                "of microdata; "
                "each research-team member must be licensed individually"
            ),
            fallback="WDI country marginals only; no measured person-level joint distribution",
            required_action=(
                "A licensed user must create and supply a versioned extract plus codebook "
                "and authorize "
                "local processing; only disclosure-safe aggregates may enter a public dump"
            ),
            coverage={"imported_countries": 0, "measured_joint_distributions": 0},
        ),
        source_record(
            "world_values_survey",
            "World Values Survey",
            2,
            "country",
            "unavailable",
            "https://www.worldvaluessurvey.org/AJDownloadLicense.jsp",
            "User-selected wave required",
            "",
            "Non-profit use with citation; source data files may not be redistributed",
            {
                "values": "Survey items require a versioned harmonization map",
                "trust": "Weighted respondent distribution",
                "ideology_axes": "Separate item sets for economic, state, and cultural axes",
            },
            restriction_reason=(
                "Download requires registration and acceptance of conditions that prohibit "
                "redistribution "
                "of the data files"
            ),
            fallback="No self-reported values or ideology fallback is promoted",
            required_action=(
                "A registered user must supply the selected wave, weights, questionnaire, "
                "and permission "
                "for local aggregate processing"
            ),
            coverage={"imported_countries": 0, "imported_survey_waves": 0},
        ),
        source_record(
            "european_social_survey",
            "European Social Survey",
            2,
            "country",
            "unavailable",
            "https://www.europeansocialsurvey.org/data-portal",
            "User-selected round required",
            "",
            "CC BY-NC-SA 4.0",
            {
                "values": "Round-specific survey items and analysis weights",
                "trust": "Weighted respondent distribution",
                "ideology_axes": "Separate measured item sets; no single-axis split",
            },
            restriction_reason=(
                "No versioned round-specific extract is present; ESS recommends linking to "
                "portal datasets "
                "rather than republishing them on external sites"
            ),
            fallback="No survey values are inferred from European electoral results",
            required_action=(
                "Supply a named ESS round extract and questionnaire, choose a compatible "
                "noncommercial "
                "distribution scope, and retain the adapted-data citation"
            ),
            coverage={"imported_countries": 0, "imported_survey_rounds": 0},
        ),
        source_record(
            "pew_global_attitudes",
            "Pew Research Center Global Attitudes",
            2,
            "country",
            "unavailable",
            "https://www.pewresearch.org/methods-site/datasets/",
            "User-selected survey required",
            "",
            "Pew Research Center survey dataset terms",
            {
                "values": "Survey-specific weighted items",
                "ideology_axes": "Separate item sets where questionnaire coverage supports them",
            },
            restriction_reason=(
                "Dataset download requires a Pew account and full or substantially full dataset "
                "redistribution is not permitted"
            ),
            fallback="No Pew-derived value is present",
            required_action=(
                "An account holder must supply a named dataset, questionnaire, weights, "
                "and authorize "
                "local processing into attributable aggregate outputs"
            ),
            coverage={"imported_countries": 0, "imported_surveys": 0},
        ),
        source_record(
            "geonames_cities500",
            "GeoNames cities500",
            3,
            "city",
            "imported" if geonames else "missing_local_dump",
            geonames.get("source_url", "https://download.geonames.org/export/dump/cities500.zip"),
            f"sha256:{geonames.get('sha256')}" if geonames.get("sha256") else "unversioned",
            geonames.get("source_date", ""),
            "CC BY 4.0",
            {
                "place_id": "geonameid",
                "population": "GeoNames population field",
                "geography": "Point coordinates and admin codes",
            },
            fallback="Population remains missing when GeoNames reports zero",
            files=[local_file(data_directory, "cities500.zip")],
            coverage={
                "cities": geonames.get("cities", 0),
                "countries": geonames.get("countries", 0),
                "cities_without_population": geonames.get("cities_without_population", 0),
            },
        ),
        source_record(
            "ghsl_ucdb",
            "GHS Urban Centre Database",
            3,
            "city",
            "imported" if ucdb else "missing_local_dump",
            ucdb.get(
                "source_url",
                "https://human-settlement.emergency.copernicus.eu/ghs_ucdb_2024.php",
            ),
            "R2024A V1.2",
            ucdb.get("release_date", ""),
            "European Commission reuse decision 2011/833/EU; per-variable sources retained",
            {
                "population": (
                    "Urban-centre polygon values spatially imputed to contained GeoNames points"
                ),
                "place_join": "Point in polygon; never relabelled city-observed",
            },
            fallback="GeoNames population remains the backbone city value",
            files=[local_file(data_directory, "sources/GHS_UCDB_GLOBE_R2024A_V1_2.zip")],
            coverage={
                "urban_centres": ucdb.get("urban_centres", 0),
                "cities_spatially_matched": ucdb.get("cities_spatially_matched", 0),
                "features": ucdb.get("features", 0),
            },
        ),
        source_record(
            "blue_electoral",
            "BLUE electoral database",
            3,
            "city",
            "imported" if blue else "missing_local_dump",
            blue.get("source_url", "https://zenodo.org/records/21434112"),
            blue.get("release", "unversioned"),
            blue.get("published_date", ""),
            blue.get("license", "CC BY 4.0"),
            {
                "electoral_alignment": "LAU valid-ballot party-family shares",
                "place_join": "GeoNames point in GISCO LAU boundary",
                "ideology": (
                    "Legacy single-axis electoral proxy only; never auto-split into economic, "
                    "state, "
                    "and cultural survey axes"
                ),
            },
            fallback="No self-reported ideology or resident distribution is inferred",
            files=[local_file(data_directory, "sources/BLUE_DB.zip")],
            coverage={
                "countries": blue.get("countries", 0),
                "matched_cities": blue.get("matched_cities", 0),
                "cities_with_results": blue.get("cities_with_results", 0),
            },
        ),
        source_record(
            "worldpop",
            "WorldPop Global 2 population counts",
            3,
            "city",
            "available_remote",
            "https://hub.worldpop.org/geodata/summary?id=80030",
            "Global 2 R2025A v1",
            "2025",
            "CC BY 4.0",
            {
                "population": (
                    "One-kilometre global GeoTIFF requires zonal aggregation to city boundaries"
                ),
                "compact_official_dump": "276.02 MB global dataset is available",
            },
            restriction_reason=(
                "Not imported automatically because a raster-to-city boundary definition "
                "is required; "
                "point sampling would not produce city populations"
            ),
            fallback=(
                "GeoNames point populations and GHS-UCDB urban-centre polygons are already imported"
            ),
            required_action=(
                "Approve a city-boundary source and year, then download the compact official "
                "1 km mosaic "
                "and aggregate cells with coverage and method provenance"
            ),
            coverage={
                "global_dataset_available": True,
                "imported_city_populations": 0,
                "compact_download_size_label": "276.02 MB as listed by WorldPop",
            },
        ),
    ]
    return sorted(records, key=lambda record: (record["scope_order"], record["source_id"]))
