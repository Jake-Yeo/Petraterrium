import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

from ...dsl import Evidence, FeatureDistribution
from ..database import AtlasStore
from ..feature_catalog import FeatureCatalogStore
from ..features import canonical_feature_registry
from ..validation import validate_value

INSTALL_VERSION = "registry-dump-install-v1"


def normalized_probabilities(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values())
    if total <= 0:
        raise ValueError("A registry distribution needs positive population")
    values = {key: value / total for key, value in sorted(counts.items())}
    last = next(reversed(values))
    values[last] += 1 - sum(values.values())
    return values


def percentage_distribution(counts: dict[str, int]) -> dict[str, float]:
    probabilities = normalized_probabilities(counts)
    values = {key: value * 100 for key, value in probabilities.items()}
    last = next(reversed(values))
    values[last] += 100 - sum(values.values())
    return values


def grouped_age_sex(rows: list[dict], level: str) -> dict[str, list[dict]]:
    place_key = "country_code" if level == "country" else "region"
    grouped = defaultdict(list)
    for row in rows:
        grouped[row[place_key]].append(row)
    return dict(grouped)


def feature_distributions(
    rows: list[dict],
    level: str,
    version: str,
    source_date: str,
) -> list[FeatureDistribution]:
    result = []
    for place, place_rows in grouped_age_sex(rows, level).items():
        age_counts = defaultdict(int)
        sex_counts = defaultdict(int)
        for row in place_rows:
            age_counts[row["age_group"]] += row["population"]
            sex_counts[row["sex"]] += row["population"]
        evidence = Evidence(
            source="UN World Population Prospects",
            version=version,
            status="present",
            uncertainty=1,
            source_date=source_date,
        )
        population = "De facto population on 1 July 2023"
        result.extend(
            [
                FeatureDistribution(
                    feature_id="age_band",
                    level=level,
                    place=place,
                    population=population,
                    coverage_percent=100,
                    values=normalized_probabilities(age_counts),
                    provenance=evidence,
                ),
                FeatureDistribution(
                    feature_id="sex",
                    level=level,
                    place=place,
                    population=population,
                    coverage_percent=100,
                    values=normalized_probabilities(sex_counts),
                    provenance=evidence,
                ),
            ]
        )
    return result


def registry_import_id(manifest: dict) -> str:
    wpp = manifest["wpp"]
    source_digests = sorted(
        (source["role"], source["sha256"]) for source in wpp.get("source_files", [])
    )
    identity = json.dumps(
        [wpp["version"], wpp["estimate_year"], source_digests, INSTALL_VERSION],
        separators=(",", ":"),
    )
    return "registry-" + hashlib.sha256(identity.encode()).hexdigest()[:28]


def install_marginal_observations(
    store: AtlasStore,
    manifest: dict,
    country_rows: list[dict],
) -> tuple[str, int]:
    wpp = manifest["wpp"]
    import_id = registry_import_id(manifest)
    version = f"{wpp['version']};transform:{INSTALL_VERSION}"
    grouped = grouped_age_sex(country_rows, "country")
    prepared = []
    for country_code, rows in sorted(grouped.items()):
        counts = {
            f"{row['sex']}_{row['age_group']}": row["population"] for row in rows
        }
        value = percentage_distribution(counts)
        validate_value("age_sex", value, "percent")
        prepared.append(
            {
                "geo_level": "country",
                "geo_key": country_code,
                "field": "age_sex",
                "value": value,
                "unit": "percent",
            }
        )
    metadata = {
        "run_id": "shared",
        "kind": "marginals",
        "source": "UN World Population Prospects",
        "source_url": "https://population.un.org/wpp/",
        "source_date": f"{wpp['estimate_year']}-07-01",
        "published_date": wpp["published_date"],
        "version": version,
        "uploader": "bulk-source-loader",
        "license": wpp["license"],
        "mapping": wpp["mapping"],
        "redistribution_allowed": True,
        "processing_notes": [
            "Country observations resolve as inherited city archetypes.",
            "Five-year age groups and source sex categories remain separate.",
            "No projection rows are installed.",
        ],
    }
    with store.connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute(
            "SELECT 1 FROM imports WHERE import_id=?", (import_id,)
        ).fetchone():
            return import_id, 0
        now = datetime.now(UTC).isoformat()
        connection.execute(
            """INSERT INTO imports(import_id,source,source_date,published_date,version,scope,
            uploader,kind,filename,row_count,status,metadata_json,rows_json,mapping_json,
            audit_json,validation_json,validated_json,promoted_from,redistribution_allowed,
            created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                import_id,
                metadata["source"],
                metadata["source_date"],
                metadata["published_date"],
                version,
                "shared",
                metadata["uploader"],
                "marginals",
                "wpp_country_age_sex.parquet",
                len(prepared),
                "committed",
                json.dumps(metadata, sort_keys=True),
                "[]",
                "[]",
                json.dumps(
                    {
                        "provider": "deterministic-loader",
                        "model": "none",
                        "prompt_version": INSTALL_VERSION,
                        "message": "No LLM mapping was used",
                    }
                ),
                json.dumps({"valid": True, "observations": len(prepared)}),
                json.dumps(prepared, separators=(",", ":"), allow_nan=False),
                None,
                1,
                now,
            ),
        )
        connection.executemany(
            """INSERT INTO observations(import_id,geo_level,geo_key,field,value_json,unit)
            VALUES(?,?,?,?,?,?)""",
            [
                (
                    import_id,
                    row["geo_level"],
                    row["geo_key"],
                    row["field"],
                    json.dumps(row["value"], separators=(",", ":"), allow_nan=False),
                    row["unit"],
                )
                for row in prepared
            ],
        )
        store.bump(connection)
    return import_id, len(prepared)


def install_feature_distributions(
    store: AtlasStore,
    distributions: list[FeatureDistribution],
) -> int:
    catalog = FeatureCatalogStore(store)
    registry = canonical_feature_registry()
    for distribution in distributions:
        catalog._validate_distribution(registry, distribution.feature_id, distribution)
    now = datetime.now(UTC).isoformat()
    with store.connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.executemany(
            """INSERT INTO feature_catalog_distributions VALUES(?,?,?,?,?,?)
            ON CONFLICT(feature_id,level,place,source_version) DO UPDATE SET
            distribution_json=excluded.distribution_json,created_at=excluded.created_at""",
            [
                (
                    distribution.feature_id,
                    distribution.level,
                    distribution.place,
                    distribution.provenance.version,
                    distribution.model_dump_json(),
                    now,
                )
                for distribution in distributions
            ],
        )
        if distributions:
            store.bump(connection)
    return len(distributions)


def install_population_weights(
    store: AtlasStore,
    rows_by_level: list[tuple[str, list[dict]]],
    version: str,
    license_name: str,
) -> int:
    values = [
        (
            level,
            row["country_code"] if level == "country" else row["region"],
            row["population"],
            "UN World Population Prospects",
            f"{row['year']}-07-01",
            version,
            license_name,
        )
        for level, rows in rows_by_level
        for row in rows
    ]
    with store.connection() as connection:
        connection.executemany(
            """INSERT INTO registry_population_weights VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(level,place,version) DO UPDATE SET
            population=excluded.population,source=excluded.source,
            source_date=excluded.source_date,license=excluded.license""",
            values,
        )
    return len(values)


def install_inventory(store: AtlasStore, inventory: list[dict]) -> int:
    with store.connection() as connection:
        connection.executemany(
            """INSERT INTO registry_source_inventory VALUES(?,?,?,?,?)
            ON CONFLICT(source_id) DO UPDATE SET scope_order=excluded.scope_order,
            level=excluded.level,access_status=excluded.access_status,
            record_json=excluded.record_json""",
            [
                (
                    row["source_id"],
                    row["scope_order"],
                    row["level"],
                    row["access_status"],
                    json.dumps(row, sort_keys=True),
                )
                for row in inventory
            ],
        )
    return len(inventory)


def install_place_indicators(
    store: AtlasStore,
    rows: list[dict],
    version: str,
) -> int:
    with store.connection() as connection:
        connection.executemany(
            """INSERT INTO registry_place_indicators VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(source_id,level,place,indicator,source_date,version) DO UPDATE SET
            indicator_name=excluded.indicator_name,topic=excluded.topic,
            unit=excluded.unit,value=excluded.value""",
            [
                (
                    "un_wpp_2024_countries",
                    "country",
                    row["country_code"],
                    row["indicator"],
                    row["indicator_name"],
                    row["topic"],
                    row["unit"],
                    row["value"],
                    f"{row['year']}-12-31",
                    version,
                )
                for row in rows
            ],
        )
    return len(rows)


def install_registry_dump(store: AtlasStore, dump_directory: Path) -> dict:
    manifest = json.loads((dump_directory / "manifest.json").read_text())
    if manifest.get("format_version") != 1:
        raise ValueError("Unsupported registry dump format")
    inventory = json.loads((dump_directory / "source_inventory.json").read_text())
    country_age_sex = pq.read_table(dump_directory / "wpp_country_age_sex.parquet").to_pylist()
    region_age_sex = pq.read_table(dump_directory / "wpp_region_age_sex.parquet").to_pylist()
    country_population = pq.read_table(
        dump_directory / "wpp_country_population.parquet"
    ).to_pylist()
    region_population = pq.read_table(
        dump_directory / "wpp_region_population.parquet"
    ).to_pylist()
    indicators = pq.read_table(
        dump_directory / "wpp_country_demographic_indicators.parquet"
    ).to_pylist()
    wpp = manifest["wpp"]
    version = f"{wpp['version']};transform:{INSTALL_VERSION}"
    source_date = f"{wpp['estimate_year']}-07-01"
    distributions = [
        *feature_distributions(country_age_sex, "country", version, source_date),
        *feature_distributions(region_age_sex, "region", version, source_date),
    ]
    import_id, observations = install_marginal_observations(store, manifest, country_age_sex)
    return {
        "import_id": import_id,
        "marginal_observations": observations,
        "feature_distributions": install_feature_distributions(store, distributions),
        "population_weights": install_population_weights(
            store,
            [("country", country_population), ("region", region_population)],
            version,
            wpp["license"],
        ),
        "place_indicators": install_place_indicators(store, indicators, version),
        "source_inventory": install_inventory(store, inventory),
    }
