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

INSTALL_VERSION = "registry-dump-install-v4"

PRIORITY_MARGINAL_FIELDS = {
    "income": ("income", "world_bank_wdi"),
    "education_isced": ("education", "world_bank_wdi"),
    "household_size": ("household_size", "un_desa_households"),
    "ideology_economic": ("ideology_economic", "world_values_survey"),
    "ideology_state": ("ideology_state", "world_values_survey"),
    "ideology_cultural": ("ideology_cultural", "world_values_survey"),
}


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
            age_counts[row["age"]] += row["population"]
            sex_counts[row["sex"]] += row["population"]
        source_population = sum(age_counts.values())
        population_count = int(
            place_rows[0].get("distribution_population") or source_population
        )
        imputed = any(row.get("evidence_status") == "imputed" for row in place_rows)
        age_probabilities = normalized_probabilities(age_counts)
        age_moments = [
            (100 if age.rstrip("+") == "100" else int(age.rstrip("+")), probability)
            for age, probability in age_probabilities.items()
        ]
        age_mean = sum(age * probability for age, probability in age_moments)
        age_variance = sum(
            probability * (age - age_mean) ** 2 for age, probability in age_moments
        )
        evidence = Evidence(
            source=(
                "UN World Population Prospects global age and sex fallback"
                if imputed
                else "UN World Population Prospects"
            ),
            version=version,
            status="imputed" if imputed else "present",
            uncertainty=1,
            source_date=source_date,
        )
        population = (
            f"{place} residents; global 2023 WPP distribution"
            if imputed
            else "De facto population on 1 July 2023"
        )
        coverage_percent = 0 if imputed else 100
        method = "fallback" if imputed else "measured"
        result.extend(
            [
                FeatureDistribution(
                    feature_id="age",
                    level=level,
                    place=place,
                    population=population,
                    population_count=population_count,
                    coverage_percent=coverage_percent,
                    values=age_probabilities,
                    mean=age_mean,
                    standard_deviation=age_variance**0.5,
                    provenance=evidence,
                    method=method,
                ),
                FeatureDistribution(
                    feature_id="sex",
                    level=level,
                    place=place,
                    population=population,
                    population_count=population_count,
                    coverage_percent=coverage_percent,
                    values=normalized_probabilities(sex_counts),
                    provenance=evidence,
                    method=method,
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
    region_rows: list[dict],
) -> tuple[str, int]:
    wpp = manifest["wpp"]
    import_id = registry_import_id(manifest)
    version = f"{wpp['version']};transform:{INSTALL_VERSION}"
    prepared = []
    for geo_level, level, source_rows in (
        ("country", "country", country_rows),
        ("canonical_region", "region", region_rows),
    ):
        for place, rows in sorted(grouped_age_sex(source_rows, level).items()):
            counts = {}
            for row in rows:
                age = "100_plus" if row["age"].rstrip("+") == "100" else row["age"]
                counts[f"{row['sex']}_{age}"] = row["population"]
            value = percentage_distribution(counts)
            validate_value("age_sex", value, "percent")
            prepared.append(
                {
                    "geo_level": geo_level,
                    "geo_key": place,
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
            "Canonical region observations resolve as imputed fallbacks.",
            "Single-year ages and source sex categories remain separate.",
            (
                "A canonical region absent from WPP uses an explicit global WPP "
                "distribution fallback."
            ),
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
                "wpp_country_and_region_age_sex.parquet",
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


def priority_marginal_value(distribution: FeatureDistribution) -> tuple[object, str]:
    definition = next(
        item
        for item in canonical_feature_registry().definitions
        if item.id == distribution.feature_id
    )
    if distribution.values:
        values = {label: probability * 100 for label, probability in distribution.values.items()}
        last = next(reversed(values))
        values[last] += 100 - sum(values.values())
        return values, "percent"
    return {
        "mean": distribution.mean,
        "standard_deviation": distribution.standard_deviation,
    }, definition.value_range.unit if definition.value_range else "score"


def priority_marginal_import_id(source_id: str, rows: list[dict]) -> str:
    identity = json.dumps(
        [source_id, INSTALL_VERSION, rows],
        sort_keys=True,
        separators=(",", ":"),
    )
    return "registry-feature-" + hashlib.sha256(identity.encode()).hexdigest()[:20]


def install_priority_marginal_observations(
    store: AtlasStore,
    distributions: list[FeatureDistribution],
    inventory: list[dict],
) -> int:
    inventory_by_id = {record["source_id"]: record for record in inventory}
    groups = defaultdict(list)
    for distribution in distributions:
        field_mapping = PRIORITY_MARGINAL_FIELDS.get(distribution.feature_id)
        if field_mapping is None or distribution.level not in {"country", "region"}:
            continue
        field, source_id = field_mapping
        value, unit = priority_marginal_value(distribution)
        evidence_status = (
            "measured"
            if distribution.level == "region" or distribution.provenance.status == "present"
            else "estimated"
        )
        groups[
            (
                source_id,
                distribution.provenance.version,
                distribution.provenance.source_date,
            )
        ].append(
            {
                "geo_level": "country"
                if distribution.level == "country"
                else "canonical_region",
                "geo_key": distribution.place,
                "field": field,
                "value": value,
                "unit": unit,
                "evidence_status": evidence_status,
            }
        )
    installed = 0
    now = datetime.now(UTC).isoformat()
    with store.connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        for (source_id, version, source_date), rows in sorted(groups.items()):
            source = inventory_by_id[source_id]
            import_id = priority_marginal_import_id(source_id, rows)
            if connection.execute(
                "SELECT 1 FROM imports WHERE import_id=?", (import_id,)
            ).fetchone():
                continue
            published_date = source["source_date"] or source_date
            metadata = {
                "run_id": "shared",
                "kind": "marginals",
                "source": source["source"],
                "source_url": source["source_url"],
                "source_date": source_date,
                "published_date": published_date,
                "version": version,
                "uploader": "bulk-source-loader",
                "license": source["license"],
                "mapping": source["mapping"],
                "redistribution_allowed": True,
                "processing_notes": [
                    "Country distributions resolve as inherited city archetypes.",
                    "Canonical region distributions resolve as imputed fallbacks.",
                    "Evidence status and uncertainty remain in the feature registry.",
                ],
            }
            connection.execute(
                """INSERT INTO imports(import_id,source,source_date,published_date,version,scope,
                uploader,kind,filename,row_count,status,metadata_json,rows_json,mapping_json,
                audit_json,validation_json,validated_json,promoted_from,redistribution_allowed,
                created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    import_id,
                    source["source"],
                    source_date,
                    published_date,
                    version,
                    "shared",
                    "bulk-source-loader",
                    "marginals",
                    "priority_feature_distributions.parquet",
                    len(rows),
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
                    json.dumps({"valid": True, "observations": len(rows)}),
                    json.dumps(rows, separators=(",", ":"), allow_nan=False),
                    None,
                    1,
                    now,
                ),
            )
            connection.executemany(
                """INSERT INTO observations(
                import_id,geo_level,geo_key,field,value_json,unit,evidence_status
                ) VALUES(?,?,?,?,?,?,?)""",
                [
                    (
                        import_id,
                        row["geo_level"],
                        row["geo_key"],
                        row["field"],
                        json.dumps(row["value"], separators=(",", ":"), allow_nan=False),
                        row["unit"],
                        row["evidence_status"],
                    )
                    for row in rows
                ],
            )
            installed += len(rows)
        if installed:
            store.bump(connection)
    return installed


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
        connection.execute("DELETE FROM feature_catalog_distributions WHERE feature_id='age_band'")
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
    priority_path = dump_directory / "priority_feature_distributions.parquet"
    priority_rows = pq.read_table(priority_path).to_pylist() if priority_path.exists() else []
    wpp = manifest["wpp"]
    version = f"{wpp['version']};transform:{INSTALL_VERSION}"
    source_date = f"{wpp['estimate_year']}-07-01"
    distributions = [
        *feature_distributions(country_age_sex, "country", version, source_date),
        *feature_distributions(region_age_sex, "region", version, source_date),
        *[
            FeatureDistribution.model_validate_json(row["distribution_json"])
            for row in priority_rows
        ],
    ]
    import_id, observations = install_marginal_observations(
        store, manifest, country_age_sex, region_age_sex
    )
    return {
        "import_id": import_id,
        "marginal_observations": observations,
        "priority_marginal_observations": install_priority_marginal_observations(
            store, distributions, inventory
        ),
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
