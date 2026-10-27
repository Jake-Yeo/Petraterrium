import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..dsl import Evidence, FeatureDefinition, FeatureDistribution, FeatureRange, FeatureRegistry
from .database import AtlasStore

FeatureKind = Literal["categorical", "continuous", "binary"]
FeatureDraftStatus = Literal["pending", "awaiting_data"]
FeatureCatalogStatus = Literal["pending", "awaiting_data", "ready"]
FeatureUsageMode = Literal["predictive", "label_only"]


class CatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FeatureCreate(CatalogModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$", max_length=80)
    name: str = Field(min_length=1, max_length=120)
    type: FeatureKind
    canonical_values: list[str] = Field(default_factory=list, max_length=200)
    value_range: FeatureRange | None = None
    description: str = Field(default="", max_length=2000)
    provenance_placeholder: str = Field(min_length=1, max_length=500)
    status: FeatureDraftStatus = "pending"

    @model_validator(mode="after")
    def validate_schema(self):
        values = [value.strip() for value in self.canonical_values]
        if any(not value for value in values):
            raise ValueError("Canonical values cannot be empty")
        if len(values) != len(set(values)):
            raise ValueError("Canonical values must be unique")
        if self.type == "continuous":
            if self.value_range is None:
                raise ValueError("Continuous features need a canonical range")
            if values:
                raise ValueError("Continuous features cannot define canonical values")
        if self.type == "categorical":
            if len(values) < 2:
                raise ValueError("Categorical features need at least two canonical values")
            if self.value_range is not None:
                raise ValueError("Categorical features cannot define a numeric range")
        if self.type == "binary":
            if len(values) != 2:
                raise ValueError("Binary features need exactly two canonical values")
            if self.value_range is not None:
                raise ValueError("Binary features cannot define a numeric range")
        return self


class DescriptionUpdate(CatalogModel):
    description: str = Field(max_length=2000)


class FeatureUsage(CatalogModel):
    name: str
    mode: FeatureUsageMode
    reason: str
    population: str | None = None
    provenance: Evidence | None = None


class CatalogFeature(CatalogModel):
    id: str
    name: str
    type: FeatureKind
    canonical_values: list[str]
    value_range: FeatureRange | None
    description: str
    provenance_placeholder: str
    status: FeatureCatalogStatus
    predictor_blocked: bool
    distributions: list[FeatureDistribution]
    usages: list[FeatureUsage]
    custom: bool
    created_at: str | None = None
    updated_at: str | None = None


class FeatureCatalogView(CatalogModel):
    version: str
    features: list[CatalogFeature]


CATALOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS feature_catalog_definitions(
 feature_id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
 canonical_values_json TEXT NOT NULL, minimum REAL, maximum REAL, unit TEXT,
 provenance_placeholder TEXT NOT NULL, requested_status TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feature_catalog_descriptions(
 feature_id TEXT PRIMARY KEY, description TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feature_catalog_distributions(
 feature_id TEXT NOT NULL, level TEXT NOT NULL, place TEXT NOT NULL,
 source_version TEXT NOT NULL, distribution_json TEXT NOT NULL,
 created_at TEXT NOT NULL,
 PRIMARY KEY(feature_id,level,place,source_version)
);
"""


class FeatureCatalogStore:
    def __init__(self, store: AtlasStore):
        self.store = store
        with self.store.connection() as connection:
            connection.executescript(CATALOG_SCHEMA)

    def create(self, registry: FeatureRegistry, request: FeatureCreate) -> CatalogFeature:
        if self._known_feature(registry, request.id):
            raise ValueError(f"Feature {request.id} already exists")
        now = datetime.now(UTC).isoformat()
        value_range = request.value_range
        with self.store.connection() as connection:
            connection.execute(
                """
                INSERT INTO feature_catalog_definitions VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    request.id,
                    request.name,
                    request.type,
                    json.dumps(request.canonical_values),
                    value_range.minimum if value_range else None,
                    value_range.maximum if value_range else None,
                    value_range.unit if value_range else None,
                    request.provenance_placeholder,
                    request.status,
                    now,
                    now,
                ),
            )
            connection.execute(
                "INSERT INTO feature_catalog_descriptions VALUES(?,?,?)",
                (request.id, request.description, now),
            )
            self.store.bump(connection)
        return self.detail(registry, request.id)

    def update_description(
        self,
        registry: FeatureRegistry,
        feature_id: str,
        request: DescriptionUpdate,
    ) -> CatalogFeature:
        if not self._known_feature(registry, feature_id):
            raise KeyError(feature_id)
        now = datetime.now(UTC).isoformat()
        with self.store.connection() as connection:
            connection.execute(
                """
                INSERT INTO feature_catalog_descriptions VALUES(?,?,?)
                ON CONFLICT(feature_id) DO UPDATE SET
                description=excluded.description,updated_at=excluded.updated_at
                """,
                (feature_id, request.description, now),
            )
            connection.execute(
                "UPDATE feature_catalog_definitions SET updated_at=? WHERE feature_id=?",
                (now, feature_id),
            )
            self.store.bump(connection)
        return self.detail(registry, feature_id)

    def attach_distribution(
        self,
        registry: FeatureRegistry,
        feature_id: str,
        distribution: FeatureDistribution,
    ) -> CatalogFeature:
        if not self._known_feature(registry, feature_id):
            raise KeyError(feature_id)
        if distribution.feature_id != feature_id:
            raise ValueError("Distribution feature_id must match the catalog feature")
        self._validate_distribution(registry, feature_id, distribution)
        now = datetime.now(UTC).isoformat()
        with self.store.connection() as connection:
            connection.execute(
                """
                INSERT INTO feature_catalog_distributions VALUES(?,?,?,?,?,?)
                ON CONFLICT(feature_id,level,place,source_version) DO UPDATE SET
                distribution_json=excluded.distribution_json,created_at=excluded.created_at
                """,
                (
                    feature_id,
                    distribution.level,
                    distribution.place,
                    distribution.provenance.version,
                    distribution.model_dump_json(),
                    now,
                ),
            )
            connection.execute(
                "UPDATE feature_catalog_definitions SET updated_at=? WHERE feature_id=?",
                (now, feature_id),
            )
            self.store.bump(connection)
        return self.detail(registry, feature_id)

    def view(self, registry: FeatureRegistry) -> FeatureCatalogView:
        features = [
            self._feature(registry, feature_id) for feature_id in self._feature_ids(registry)
        ]
        return FeatureCatalogView(version=registry.version, features=features)

    def enriched_registry(self, registry: FeatureRegistry) -> FeatureRegistry:
        with self.store.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM feature_catalog_definitions ORDER BY feature_id"
            ).fetchall()
            stored_distributions = connection.execute(
                "SELECT distribution_json FROM feature_catalog_distributions "
                "ORDER BY feature_id,level,place,created_at DESC"
            ).fetchall()
            revision = self.store.revision(connection)
        definitions = list(registry.definitions)
        known = {definition.id for definition in definitions}
        for row in rows:
            if row["feature_id"] in known:
                continue
            value_range = (
                FeatureRange(
                    minimum=row["minimum"],
                    maximum=row["maximum"],
                    unit=row["unit"],
                )
                if row["minimum"] is not None
                else None
            )
            description, _ = self._description(row["feature_id"])
            definitions.append(
                FeatureDefinition(
                    id=row["feature_id"],
                    name=row["name"],
                    description=description,
                    kind=row["kind"],
                    canonical_values=json.loads(row["canonical_values_json"]),
                    value_range=value_range,
                    provenance=Evidence(
                        source=row["provenance_placeholder"],
                        version="pending",
                        status="label_only",
                        uncertainty=1,
                    ),
                    predictive=False,
                )
            )
        distributions = list(registry.distributions)
        distributions.extend(
            FeatureDistribution.model_validate_json(row["distribution_json"])
            for row in stored_distributions
        )
        return FeatureRegistry(
            version=f"{registry.version}+atlas-{revision}",
            definitions=definitions,
            distributions=distributions,
            joint_data=registry.joint_data,
        )

    def detail(self, registry: FeatureRegistry, feature_id: str) -> CatalogFeature:
        if not self._known_feature(registry, feature_id):
            raise KeyError(feature_id)
        return self._feature(registry, feature_id)

    def _feature_ids(self, registry: FeatureRegistry) -> list[str]:
        ids = {definition.id for definition in registry.definitions}
        with self.store.connection() as connection:
            ids.update(
                row["feature_id"]
                for row in connection.execute(
                    "SELECT feature_id FROM feature_catalog_definitions"
                )
            )
        return sorted(ids)

    def _known_feature(self, registry: FeatureRegistry, feature_id: str) -> bool:
        if any(definition.id == feature_id for definition in registry.definitions):
            return True
        with self.store.connection() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM feature_catalog_definitions WHERE feature_id=?",
                    (feature_id,),
                ).fetchone()
                is not None
            )

    def _custom_row(self, feature_id: str):
        with self.store.connection() as connection:
            return connection.execute(
                "SELECT * FROM feature_catalog_definitions WHERE feature_id=?",
                (feature_id,),
            ).fetchone()

    def _description(self, feature_id: str) -> tuple[str, str | None]:
        with self.store.connection() as connection:
            row = connection.execute(
                """
                SELECT description,updated_at FROM feature_catalog_descriptions
                WHERE feature_id=?
                """,
                (feature_id,),
            ).fetchone()
        return (row["description"], row["updated_at"]) if row else ("", None)

    def _stored_distributions(self, feature_id: str) -> list[FeatureDistribution]:
        with self.store.connection() as connection:
            rows = connection.execute(
                """
                SELECT distribution_json FROM feature_catalog_distributions
                WHERE feature_id=? ORDER BY level,place,source_version
                """,
                (feature_id,),
            ).fetchall()
        return [FeatureDistribution.model_validate_json(row["distribution_json"]) for row in rows]

    def _feature(self, registry: FeatureRegistry, feature_id: str) -> CatalogFeature:
        definition = next(
            (definition for definition in registry.definitions if definition.id == feature_id),
            None,
        )
        custom = self._custom_row(feature_id)
        description, description_updated_at = self._description(feature_id)
        if custom:
            name = custom["name"]
            kind = custom["kind"]
            canonical_values = json.loads(custom["canonical_values_json"])
            value_range = (
                FeatureRange(
                    minimum=custom["minimum"],
                    maximum=custom["maximum"],
                    unit=custom["unit"],
                )
                if custom["minimum"] is not None
                else None
            )
            placeholder = custom["provenance_placeholder"]
            requested_status = custom["requested_status"]
            predictive = True
            created_at = custom["created_at"]
            updated_at = description_updated_at or custom["updated_at"]
        else:
            name = definition.name or feature_id.replace("_", " ").replace("-", " ").title()
            kind = definition.kind
            canonical_values = definition.canonical_values
            value_range = definition.value_range
            placeholder = definition.provenance.source
            requested_status = (
                "pending" if definition.provenance.status == "label_only" else "awaiting_data"
            )
            predictive = definition.predictive
            created_at = None
            updated_at = description_updated_at
            if description_updated_at is None:
                description = definition.description
        distributions = [
            distribution
            for distribution in registry.distributions
            if distribution.feature_id == feature_id
        ]
        distributions.extend(self._stored_distributions(feature_id))
        proofs = [proof for proof in registry.joint_data if proof.feature_id == feature_id]
        status: FeatureCatalogStatus = "ready" if distributions else requested_status
        predictor_ready = status == "ready" and predictive and bool(proofs)
        usages = [
            FeatureUsage(
                name=outcome,
                mode="predictive" if predictor_ready else "label_only",
                reason=(
                    "Joint trait and outcome evidence is attached"
                    if predictor_ready
                    else (
                        "Predictor use is blocked until a distribution and joint evidence "
                        "are attached"
                    )
                ),
                population=proof.population,
                provenance=proof.provenance,
            )
            for proof in proofs
            for outcome in proof.outcomes
        ]
        if not usages:
            usages = [
                FeatureUsage(
                    name="Agent trait",
                    mode="label_only",
                    reason=(
                        "Predictor use is blocked until a distribution and joint evidence "
                        "are attached"
                    ),
                )
            ]
        return CatalogFeature(
            id=feature_id,
            name=name,
            type=kind,
            canonical_values=canonical_values,
            value_range=value_range,
            description=description,
            provenance_placeholder=placeholder,
            status=status,
            predictor_blocked=not predictor_ready,
            distributions=distributions,
            usages=usages,
            custom=custom is not None,
            created_at=created_at,
            updated_at=updated_at,
        )

    def _validate_distribution(
        self,
        registry: FeatureRegistry,
        feature_id: str,
        distribution: FeatureDistribution,
    ) -> None:
        feature = self._feature(registry, feature_id)
        if distribution.provenance.source_date is None:
            raise ValueError("Feature distributions need a source date")
        if feature.type in {"categorical", "binary"}:
            if not distribution.values:
                raise ValueError("Categorical feature distributions need values")
            if abs(sum(distribution.values.values()) - 1) > 1e-9:
                raise ValueError("Distribution probabilities must sum to 1")
            unknown = set(distribution.values) - set(feature.canonical_values)
            if unknown:
                raise ValueError(f"Distribution uses noncanonical values {sorted(unknown)}")
        if feature.type == "continuous":
            if distribution.mean is None or distribution.standard_deviation is None:
                raise ValueError(
                    "Continuous feature distributions need mean and standard deviation"
                )
            if feature.value_range and not (
                feature.value_range.minimum <= distribution.mean <= feature.value_range.maximum
            ):
                raise ValueError("Distribution mean is outside the canonical range")


def create_feature_catalog_router(
    store: AtlasStore,
    registry_provider: Callable[[], FeatureRegistry],
) -> APIRouter:
    catalog = FeatureCatalogStore(store)
    router = APIRouter(prefix="/atlas/feature-catalog", tags=["Feature catalog"])

    def checked(function, *args):
        try:
            return function(*args)
        except KeyError as error:
            raise HTTPException(404, f"Unknown feature {error.args[0]}") from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @router.get("", response_model=FeatureCatalogView)
    def list_features():
        return catalog.view(registry_provider())

    @router.post("", response_model=CatalogFeature, status_code=201)
    def create_feature(request: FeatureCreate):
        return checked(catalog.create, registry_provider(), request)

    @router.get("/{feature_id}", response_model=CatalogFeature)
    def feature_detail(feature_id: str):
        return checked(catalog.detail, registry_provider(), feature_id)

    @router.patch("/{feature_id}/description", response_model=CatalogFeature)
    def edit_description(feature_id: str, request: DescriptionUpdate):
        return checked(catalog.update_description, registry_provider(), feature_id, request)

    @router.post("/{feature_id}/distributions", response_model=CatalogFeature, status_code=201)
    def attach_distribution(feature_id: str, request: FeatureDistribution):
        return checked(
            catalog.attach_distribution,
            registry_provider(),
            feature_id,
            request,
        )

    return router
