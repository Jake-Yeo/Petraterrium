import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from ..atlas.database import AtlasStore
from ..atlas.feature_catalog import FeatureCatalogStore
from ..atlas.features import canonical_feature_registry
from ..atlas.joint_estimates import (
    MeasuredHouseholdMember,
    MeasuredJointData,
    PlaceSelector,
    PopulationPlace,
    resolve_distribution_for_place,
)
from ..atlas.regions import country_region
from ..dsl import Evidence, FeatureDistribution
from .atlas_type_assignment import (
    AtlasAgentTypeAssignment,
    agent_type_counts,
    assign_agent_types,
    validate_type_assignment,
)
from .interactions import RelationshipKindEvidence
from .population_generation import (
    AgentInitialStateProvenance,
    EvidenceReference,
    HouseholdMemberSeed,
    HouseholdSeed,
    InitialPopulationMaterialization,
    InitialPopulationRequest,
    InitialPopulationValidationError,
    materialize_initial_population,
)


class AtlasPopulationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class AtlasPopulationRequest(AtlasPopulationModel):
    population_id: str = Field(default="atlas-population", min_length=1)
    selector: PlaceSelector
    scope: str = Field(default="shared", min_length=1)
    seed: int = 42
    target_agents: int = Field(default=1000, ge=1, le=100_000)
    agent_type_id: str = Field(default="person", pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$")
    type_assignment: AtlasAgentTypeAssignment | None = None


class AtlasPopulationFeatureCoverage(AtlasPopulationModel):
    feature_id: str
    measured_agents: int = Field(ge=0)
    imputed_agents: int = Field(ge=0)
    unknown_agents: int = Field(ge=0)
    sources: list[str]


class AtlasPopulationResult(AtlasPopulationModel):
    selector: PlaceSelector
    scope: str
    materialization: InitialPopulationMaterialization
    feature_coverage: list[AtlasPopulationFeatureCoverage]
    agent_type_counts: dict[str, int]
    warnings: list[str]


@dataclass(frozen=True)
class AtlasCity:
    geonameid: str
    name: str
    country_code: str
    country_name: str
    region: str
    latitude: float
    longitude: float
    population: int


@dataclass(frozen=True)
class SampleSource:
    feature_id: str
    distribution: FeatureDistribution
    evidence: EvidenceReference


@dataclass(frozen=True)
class MeasuredJointTable:
    feature_ids: tuple[str, ...]
    records: tuple[MeasuredJointData, ...]
    evidence: EvidenceReference


FIELD_TO_FEATURE = {
    "income": "income",
    "education": "education_isced",
    "ideology_economic": "ideology_economic",
    "ideology_state": "ideology_state",
    "ideology_cultural": "ideology_cultural",
    "household_size": "household_size",
}


class AtlasPopulationMaterializer:
    def __init__(self, store: AtlasStore):
        self.store = store
        self.registry = FeatureCatalogStore(store).enriched_registry(
            canonical_feature_registry()
        )
        self.definitions = {item.id: item for item in self.registry.definitions}
        self._source_cache: dict[tuple[str, str, str], SampleSource | None] = {}
        self._age_sex_cache: dict[
            tuple[str, str], tuple[dict[str, float], EvidenceReference] | None
        ] = {}
        self._joint_records: tuple[MeasuredJointData, ...] = ()
        self._joint_table_cache: dict[str, tuple[MeasuredJointTable, ...]] = {}
        self._household_table_cache: dict[str, MeasuredJointTable | None] = {}

    def materialize(
        self,
        request: AtlasPopulationRequest,
        relationship_evidence: tuple[RelationshipKindEvidence, ...] = (),
    ) -> AtlasPopulationResult:
        self.registry = FeatureCatalogStore(self.store).enriched_registry(
            canonical_feature_registry()
        )
        self.definitions = {item.id: item for item in self.registry.definitions}
        self._source_cache.clear()
        self._age_sex_cache.clear()
        self._joint_records = self._load_joint_records()
        self._joint_table_cache.clear()
        self._household_table_cache.clear()
        validate_type_assignment(
            request.type_assignment,
            {
                "age",
                "sex",
                "relationship_to_reference",
                "household_role",
                "household_size",
                *self.definitions,
            },
        )
        cities = self._cities(request.selector)
        if request.scope != "shared" and not self._scope_exists(request.scope):
            raise ValueError(f"Atlas scope {request.scope!r} has no committed imports")
        rng = np.random.default_rng(request.seed)
        city_probabilities = self._normalized([city.population for city in cities])
        templates: list[HouseholdSeed] = []
        evidence_by_id: dict[str, EvidenceReference] = {}
        coverage: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"measured": 0, "imputed": 0, "sources": set()}
        )
        remaining = request.target_agents
        member_index = 0
        household_index = 0
        measured_household_agents = 0
        imputed_household_agents = 0
        while remaining:
            city = cities[int(rng.choice(len(cities), p=city_probabilities))]
            household_table = self._household_table(city)
            household_record = (
                self._sample_household_record(household_table, remaining, rng)
                if household_table is not None
                else None
            )
            if household_record is not None:
                size = len(household_record.household_members)
                household_evidence = household_table.evidence
                member_profiles: tuple[MeasuredHouseholdMember, ...] | None = tuple(
                    household_record.household_members
                )
                measured_household_agents += size
            else:
                household_source = self._source(request.scope, city, "household_size")
                if household_source is None:
                    raise ValueError(
                        f"Household-size evidence is missing for {city.country_name}; "
                        "population generation cannot place minors into valid households"
                    )
                size = self._sample_household_size(household_source, remaining, rng)
                household_evidence = self._household_evidence(household_source)
                member_profiles = None
                imputed_household_agents += size
            members = self._sample_household_members(
                request,
                city,
                size,
                member_index,
                rng,
                evidence_by_id,
                coverage,
                member_profiles,
            )
            evidence_by_id[household_evidence.evidence_id] = household_evidence
            for member in members:
                member.field_evidence["household_size"] = household_evidence.evidence_id
                member.field_evidence["household_composition"] = household_evidence.evidence_id
                if household_evidence.status == "measured_joint":
                    member.field_evidence["family_relationships"] = (
                        household_evidence.evidence_id
                    )
                member.traits["household_size"] = size
            self._record_coverage(coverage, "household_size", household_evidence, size)
            templates.append(
                HouseholdSeed(
                    template_id=f"atlas-household-{household_index + 1}",
                    place=city.geonameid,
                    country=city.country_name,
                    country_id=city.country_code,
                    region=city.region,
                    city=city.name,
                    city_id=city.geonameid,
                    latitude=city.latitude,
                    longitude=city.longitude,
                    weight=1,
                    evidence_id=household_evidence.evidence_id,
                    members=members,
                )
            )
            remaining -= size
            member_index += size
            household_index += 1
        revision = self._revision()
        population_request = InitialPopulationRequest(
            population_id=request.population_id,
            version=f"atlas-{revision}-{self.registry.version}",
            seed=request.seed,
            target_agents=request.target_agents,
            household_templates=templates,
            evidence=sorted(evidence_by_id.values(), key=lambda item: item.evidence_id),
        )
        try:
            result = materialize_initial_population(
                population_request,
                relationship_evidence,
            )
        except InitialPopulationValidationError as error:
            if any(item.code == "duplicate_initial_state" for item in error.validation.issues):
                raise ValueError(
                    "The resolved atlas distributions do not contain enough substantive "
                    "variation to create this many unique agents without cloning"
                ) from error
            raise
        result = self._add_unknown_provenance(result)
        summaries = self._coverage(request.target_agents, coverage)
        has_family_evidence = any(
            item.kind == "family" and item.provenance.executable
            for item in relationship_evidence
        )
        warnings = self._household_warnings(
            measured_household_agents,
            imputed_household_agents,
            has_family_evidence,
        )
        if request.selector.level in {"global", "region", "country"}:
            warnings.append(
                "City allocation uses GeoNames cities500 population weights within the "
                "selected place."
            )
        if request.type_assignment is not None:
            warnings.append(
                "Agent types use confirmed deterministic simulation rules evaluated against "
                "Atlas-sampled traits; the rules do not add evidence or behaviour effects."
            )
        return AtlasPopulationResult(
            selector=request.selector,
            scope=request.scope,
            materialization=result,
            feature_coverage=summaries,
            agent_type_counts=agent_type_counts(result),
            warnings=warnings,
        )

    def _cities(self, selector: PlaceSelector) -> list[AtlasCity]:
        query = """SELECT c.geonameid,c.name,c.country_code,COALESCE(n.name,c.country_code)
        country_name,c.latitude,c.longitude,c.population FROM cities c
        LEFT JOIN countries n ON n.code=c.country_code WHERE c.population>0"""
        parameters: list[Any] = []
        if selector.level == "city":
            query += " AND CAST(c.geonameid AS TEXT)=?"
            parameters.append(selector.place)
        elif selector.level == "country":
            query += " AND c.country_code=?"
            parameters.append(selector.place.upper())
        elif selector.level not in {"global", "region"}:
            raise ValueError(
                "Initial population generation supports global, region, country, or city"
            )
        with self.store.connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        cities = [
            AtlasCity(
                geonameid=str(row["geonameid"]),
                name=row["name"],
                country_code=row["country_code"],
                country_name=row["country_name"],
                region=country_region(row["country_code"]),
                latitude=row["latitude"],
                longitude=row["longitude"],
                population=row["population"],
            )
            for row in rows
            if selector.level != "region" or country_region(row["country_code"]) == selector.place
        ]
        if not cities:
            raise ValueError(f"No populated cities found for {selector.label}")
        return sorted(cities, key=lambda city: (city.country_code, city.geonameid))

    def _scope_exists(self, scope: str) -> bool:
        with self.store.connection() as connection:
            return connection.execute(
                "SELECT 1 FROM imports WHERE scope=? AND status='committed' LIMIT 1", (scope,)
            ).fetchone() is not None

    def _revision(self) -> int:
        with self.store.connection() as connection:
            return self.store.revision(connection)

    def _load_joint_records(self) -> tuple[MeasuredJointData, ...]:
        with self.store.connection() as connection:
            rows = connection.execute(
                "SELECT record_id,record_json FROM feature_joint_data ORDER BY record_id"
            ).fetchall()
        records = []
        for row in rows:
            try:
                record = MeasuredJointData.model_validate_json(row["record_json"])
            except ValueError as error:
                raise ValueError(
                    f"Measured joint record {row['record_id']!r} is invalid: {error}"
                ) from error
            if record.population_distribution_id is not None:
                records.append(record)
        return tuple(records)

    @staticmethod
    def _record_specificity(record: MeasuredJointData, city: AtlasCity) -> int | None:
        identities = {
            "city": city.geonameid,
            "country": city.country_code,
            "region": city.region,
        }
        if record.level in identities:
            return (
                ("city", "country", "region").index(record.level)
                if record.place == identities[record.level]
                else None
            )
        if record.level == "global":
            eligible = {
                "*",
                city.geonameid,
                city.country_code,
                city.region,
            }
            if record.explicit_fallback and eligible.intersection(record.fallback_for):
                return 3
        return None

    @staticmethod
    def _joint_values(record: MeasuredJointData) -> dict[str, str | float]:
        values: dict[str, str | float] = {}
        for condition in record.conditions:
            if condition.operator != "eq" or len(condition.values) != 1:
                raise ValueError(
                    f"Population joint distribution {record.population_distribution_id!r} "
                    "contains a non-exact cell"
                )
            if condition.feature_id in values:
                raise ValueError(
                    f"Population joint distribution {record.population_distribution_id!r} "
                    f"repeats feature {condition.feature_id!r} in one cell"
                )
            values[condition.feature_id] = condition.values[0]
        return values

    def _joint_groups(
        self, city: AtlasCity, *, households: bool
    ) -> list[tuple[int, tuple[str, ...], tuple[MeasuredJointData, ...]]]:
        grouped: dict[
            tuple[int, str, tuple[str, ...]], list[MeasuredJointData]
        ] = defaultdict(list)
        for record in self._joint_records:
            if bool(record.household_members) != households:
                continue
            specificity = self._record_specificity(record, city)
            if specificity is None or record.population_distribution_id is None:
                continue
            feature_ids = tuple(sorted(self._joint_values(record)))
            if not households and (
                len(feature_ids) < 2 or set(feature_ids) - set(self.definitions)
            ):
                continue
            grouped[(specificity, record.population_distribution_id, feature_ids)].append(
                record
            )
        return [
            (specificity, feature_ids, tuple(records))
            for (specificity, _, feature_ids), records in grouped.items()
        ]

    def _validated_joint_table(
        self,
        feature_ids: tuple[str, ...],
        records: tuple[MeasuredJointData, ...],
    ) -> MeasuredJointTable:
        if not records:
            raise ValueError("Measured joint distribution has no cells")
        first = records[0]
        identity = first.population_distribution_id
        expected_provenance = (
            first.provenance.source,
            first.provenance.version,
            first.provenance.source_date,
            first.population,
            first.sample_size,
        )
        seen_cells: set[tuple[tuple[str, str], ...]] = set()
        for record in records:
            provenance = (
                record.provenance.source,
                record.provenance.version,
                record.provenance.source_date,
                record.population,
                record.sample_size,
            )
            if provenance != expected_provenance:
                raise ValueError(
                    f"Population joint distribution {identity!r} mixes incompatible sources"
                )
            values = self._joint_values(record)
            if tuple(sorted(values)) != feature_ids:
                raise ValueError(
                    f"Population joint distribution {identity!r} has inconsistent fields"
                )
            cell = tuple(sorted((key, str(value)) for key, value in values.items()))
            if cell in seen_cells:
                raise ValueError(
                    f"Population joint distribution {identity!r} contains a duplicate cell"
                )
            seen_cells.add(cell)
            if not record.household_members:
                self._validate_joint_feature_values(values, identity or "unknown")
        total = sum(record.probability for record in records)
        if abs(total - 1) > 1e-9:
            raise ValueError(
                f"Population joint distribution {identity!r} probabilities must sum to 1; "
                f"received {total:g}"
            )
        evidence = EvidenceReference(
            evidence_id=self._evidence_id(
                "population-joint",
                identity or "unknown",
                first.level,
                first.place,
                first.provenance.source,
                first.provenance.version,
            ),
            source=first.provenance.source,
            source_version=first.provenance.version,
            observed_at=first.provenance.source_date or "unknown",
            licence="See atlas source inventory",
            place=first.place,
            status="measured_joint",
            fields=(
                [
                    "household_size",
                    "household_composition",
                    "family_relationships",
                ]
                if first.household_members
                else list(feature_ids)
            ),
            uncertainty=(
                f"Weighted measured joint distribution {identity}; n={first.sample_size}; "
                f"coverage {first.coverage_percent:g}%; source uncertainty "
                f"{first.provenance.uncertainty:g}"
            ),
        )
        return MeasuredJointTable(feature_ids, records, evidence)

    def _validate_joint_feature_values(
        self, values: dict[str, str | float], identity: str
    ) -> None:
        for feature_id, value in values.items():
            definition = self.definitions[feature_id]
            if definition.kind in {"categorical", "binary"}:
                if str(value) not in definition.canonical_values:
                    raise ValueError(
                        f"Population joint distribution {identity!r} uses noncanonical "
                        f"{feature_id} value {value!r}"
                    )
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Population joint distribution {identity!r} needs numeric "
                    f"{feature_id} values"
                ) from error
            if definition.value_range is not None and not (
                definition.value_range.minimum <= numeric <= definition.value_range.maximum
            ):
                raise ValueError(
                    f"Population joint distribution {identity!r} has out-of-range "
                    f"{feature_id} value {numeric:g}"
                )

    def _joint_tables(self, city: AtlasCity) -> tuple[MeasuredJointTable, ...]:
        if city.geonameid in self._joint_table_cache:
            return self._joint_table_cache[city.geonameid]
        candidates = sorted(
            self._joint_groups(city, households=False),
            key=lambda item: (item[0], -len(item[1]), item[2][0].population_distribution_id or ""),
        )
        claimed: set[str] = set()
        selected = []
        for _, feature_ids, records in candidates:
            if claimed.intersection(feature_ids):
                continue
            table = self._validated_joint_table(feature_ids, records)
            selected.append(table)
            claimed.update(feature_ids)
        result = tuple(selected)
        self._joint_table_cache[city.geonameid] = result
        return result

    def _household_table(self, city: AtlasCity) -> MeasuredJointTable | None:
        if city.geonameid in self._household_table_cache:
            return self._household_table_cache[city.geonameid]
        candidates = sorted(
            self._joint_groups(city, households=True),
            key=lambda item: (item[0], item[2][0].population_distribution_id or ""),
        )
        result = (
            self._validated_joint_table(candidates[0][1], candidates[0][2])
            if candidates
            else None
        )
        self._household_table_cache[city.geonameid] = result
        return result

    def _sample_household_record(
        self,
        table: MeasuredJointTable,
        remaining: int,
        rng: np.random.Generator,
    ) -> MeasuredJointData:
        support = sorted({len(record.household_members) for record in table.records})
        reachable = [False] * (remaining + 1)
        reachable[0] = True
        for total in range(1, remaining + 1):
            reachable[total] = any(size <= total and reachable[total - size] for size in support)
        options = [
            record
            for record in table.records
            if len(record.household_members) <= remaining
            and reachable[remaining - len(record.household_members)]
        ]
        if not options:
            raise ValueError(
                f"Target cannot be formed from measured household composition "
                f"{table.records[0].population_distribution_id!r}"
            )
        weights = self._normalized([record.probability for record in options])
        return options[int(rng.choice(len(options), p=weights))]

    @staticmethod
    def _household_warnings(
        measured_agents: int,
        imputed_agents: int,
        has_family_evidence: bool,
    ) -> list[str]:
        effect_status = (
            "Relationship weights use registered evidence."
            if has_family_evidence
            else "Relationship effects remain unknown without registered interaction evidence."
        )
        if measured_agents and not imputed_agents:
            return [
                "Household membership and family roles use measured household composition "
                f"for all {measured_agents} agents. {effect_status}"
            ]
        if measured_agents:
            return [
                f"Measured household composition supplies roles for {measured_agents} agents; "
                f"household-size marginal imputation supplies {imputed_agents} agents. "
                f"{effect_status}"
            ]
        role_status = (
            "Family roles remain imputed; relationship weights use registered evidence."
            if has_family_evidence
            else "Family roles and relationship effects remain unknown without joint household "
            "microdata."
        )
        return [
            "Household membership is an imputation from household-size marginals. "
            + role_status
        ]

    @staticmethod
    def _normalized(values: list[int | float]) -> np.ndarray:
        weights = np.asarray(values, dtype=np.float64)
        total = float(weights.sum())
        if total <= 0:
            raise ValueError("Population weights must be positive")
        return weights / total

    def _population_place(self, city: AtlasCity) -> PopulationPlace:
        return PopulationPlace(
            place=city.geonameid,
            label=f"{city.name}, {city.country_code}",
            level="city",
            population=city.population,
            city=city.geonameid,
            country=city.country_code,
            region=city.region,
        )

    def _source(self, scope: str, city: AtlasCity, feature_id: str) -> SampleSource | None:
        key = scope, city.geonameid, feature_id
        if key in self._source_cache:
            return self._source_cache[key]
        observed = self._scoped_observation(scope, city, feature_id)
        if observed is not None:
            self._source_cache[key] = observed
            return observed
        resolved = resolve_distribution_for_place(
            self.registry, feature_id, self._population_place(city)
        )
        if resolved is None:
            self._source_cache[key] = None
            return None
        distribution = resolved.distribution
        evidence = self._distribution_evidence(feature_id, distribution, resolved.status)
        result = SampleSource(feature_id, distribution, evidence)
        self._source_cache[key] = result
        return result

    def _scoped_observation(
        self, scope: str, city: AtlasCity, feature_id: str
    ) -> SampleSource | None:
        if scope == "shared":
            return None
        field = next(
            (field for field, value in FIELD_TO_FEATURE.items() if value == feature_id),
            None,
        )
        if field is None:
            return None
        candidates = [
            ("city", city.geonameid),
            ("country", city.country_code),
            ("canonical_region", city.region),
            ("region", city.region),
        ]
        with self.store.connection() as connection:
            for level, place in candidates:
                row = connection.execute(
                    """SELECT o.*,i.source,i.source_date,i.version,i.metadata_json
                    FROM observations o JOIN imports i ON i.import_id=o.import_id
                    WHERE i.scope=? AND i.status='committed' AND o.geo_level=?
                    AND o.geo_key=? AND o.field=? ORDER BY o.id DESC LIMIT 1""",
                    (scope, level, place, field),
                ).fetchone()
                if row is None:
                    continue
                distribution = self._observation_distribution(feature_id, level, place, row)
                if distribution is None:
                    continue
                evidence = self._distribution_evidence(feature_id, distribution, level)
                return SampleSource(feature_id, distribution, evidence)
        return None

    def _observation_distribution(
        self, feature_id: str, level: str, place: str, row: Any
    ) -> FeatureDistribution | None:
        value = json.loads(row["value_json"])
        definition = self.definitions[feature_id]
        values: dict[str, float] = {}
        mean = None
        standard_deviation = None
        if isinstance(value, dict) and {"mean", "standard_deviation"} <= value.keys():
            mean = float(value["mean"])
            standard_deviation = float(value["standard_deviation"])
        elif isinstance(value, dict) and definition.kind in {"categorical", "binary"}:
            if set(value) - set(definition.canonical_values):
                return None
            total = sum(float(item) for item in value.values())
            if total <= 0:
                return None
            values = {key: float(item) / total for key, item in value.items()}
        elif isinstance(value, (int, float)) and definition.kind == "continuous":
            mean = float(value)
            standard_deviation = 0
        else:
            return None
        metadata = json.loads(row["metadata_json"])
        status = "present" if row["evidence_status"] == "measured" else "imputed"
        return FeatureDistribution(
            feature_id=feature_id,
            level=self._distribution_level(level),
            place=place,
            population=f"{place} residents in atlas scope",
            coverage_percent=100,
            values=values,
            mean=mean,
            standard_deviation=standard_deviation,
            provenance=Evidence(
                source=row["source"],
                version=row["version"],
                status=status,
                uncertainty=0 if status == "present" else 1,
                source_date=row["source_date"],
            ),
            method="measured" if status == "present" else "fallback",
        ).model_copy(
            update={"population": metadata.get("population", f"{place} residents")}
        )

    @staticmethod
    def _distribution_level(
        level: str,
    ) -> Literal["global", "region", "subregion", "country", "city"]:
        return "region" if level == "canonical_region" else level

    def _distribution_evidence(
        self, feature_id: str, distribution: FeatureDistribution, resolution: str
    ) -> EvidenceReference:
        continuous_moments = bool(
            not distribution.values
            and distribution.mean is not None
            and distribution.standard_deviation is not None
        )
        measured = distribution.provenance.status in {"present", "inherited"}
        status = "measured_marginal" if measured and not continuous_moments else "imputed"
        method = (
            "normal moment-matching sampler; distribution family is not recorded"
            if continuous_moments and distribution.standard_deviation
            else f"{distribution.method} distribution"
        )
        identity = self._evidence_id(
            feature_id,
            distribution.level,
            distribution.place,
            distribution.provenance.source,
            distribution.provenance.version,
            method,
        )
        return EvidenceReference(
            evidence_id=identity,
            source=distribution.provenance.source,
            source_version=distribution.provenance.version,
            observed_at=distribution.provenance.source_date or "unknown",
            licence="See atlas source inventory",
            place=distribution.place,
            status=status,
            fields=[feature_id],
            uncertainty=(
                f"{method}; resolved from {distribution.level} {distribution.place}; "
                f"status {resolution}; source uncertainty {distribution.provenance.uncertainty:g}"
            ),
        )

    def _household_evidence(self, source: SampleSource) -> EvidenceReference:
        evidence = source.evidence
        return evidence.model_copy(
            update={
                "evidence_id": self._evidence_id(evidence.evidence_id, "household-imputation"),
                "status": "imputed",
                "fields": ["household_size", "household_composition"],
                "uncertainty": (
                    evidence.uncertainty
                    + "; household membership is composed from a size marginal without family roles"
                ),
            }
        )

    @staticmethod
    def _evidence_id(*parts: str) -> str:
        encoded = json.dumps(parts, separators=(",", ":"))
        return "atlas-" + hashlib.sha256(encoded.encode()).hexdigest()[:24]

    def _age_sex(
        self, scope: str, city: AtlasCity
    ) -> tuple[dict[str, float], EvidenceReference] | None:
        key = scope, city.geonameid
        if key in self._age_sex_cache:
            return self._age_sex_cache[key]
        scopes = [scope] if scope == "shared" else [scope, "shared"]
        candidates = [
            ("city", city.geonameid),
            ("country", city.country_code),
            ("canonical_region", city.region),
            ("region", city.region),
        ]
        with self.store.connection() as connection:
            for candidate_scope in scopes:
                for level, place in candidates:
                    rows = connection.execute(
                        """SELECT o.*,i.source,i.source_date,i.version,i.metadata_json
                        FROM observations o JOIN imports i ON i.import_id=o.import_id
                        WHERE i.scope=? AND i.status='committed' AND o.geo_level=?
                        AND o.geo_key=? AND o.field='age_sex' ORDER BY o.id DESC""",
                        (candidate_scope, level, place),
                    ).fetchall()
                    for row in rows:
                        parsed = self._exact_age_sex(json.loads(row["value_json"]))
                        if parsed is None:
                            continue
                        metadata = json.loads(row["metadata_json"])
                        status = (
                            "measured_joint"
                            if row["evidence_status"] == "measured"
                            else "imputed"
                        )
                        evidence = EvidenceReference(
                            evidence_id=self._evidence_id(
                                "age-sex", candidate_scope, level, place, row["version"]
                            ),
                            source=row["source"],
                            source_version=row["version"],
                            observed_at=row["source_date"],
                            licence=metadata.get("license", "See atlas source inventory"),
                            place=place,
                            status=status,
                            fields=["age", "sex"],
                            uncertainty=(
                                f"Joint single-year age and sex distribution resolved from {level} "
                                f"{place}; atlas scope {candidate_scope}"
                            ),
                        )
                        result = parsed, evidence
                        self._age_sex_cache[key] = result
                        return result
        self._age_sex_cache[key] = None
        return None

    @staticmethod
    def _exact_age_sex(value: Any) -> dict[str, float] | None:
        if not isinstance(value, dict) or not value:
            return None
        parsed: dict[str, float] = {}
        for label, raw_probability in value.items():
            text = str(label)
            if "_" not in text:
                return None
            sex, age_label = text.split("_", 1)
            if age_label == "100_plus":
                age = 100
            elif age_label.isdigit():
                age = int(age_label)
            else:
                return None
            parsed[f"{sex}:{age}"] = float(raw_probability)
        total = sum(parsed.values())
        if total <= 0:
            return None
        return {label: value / total for label, value in parsed.items()}

    def _sample_household_size(
        self, source: SampleSource, remaining: int, rng: np.random.Generator
    ) -> int:
        probabilities = self._household_size_probabilities(source.distribution)
        support = sorted(size for size, probability in probabilities.items() if probability > 0)
        reachable = [False] * (remaining + 1)
        reachable[0] = True
        for total in range(1, remaining + 1):
            reachable[total] = any(size <= total and reachable[total - size] for size in support)
        options = [
            size for size in support if size <= remaining and reachable[remaining - size]
        ]
        if not options:
            raise ValueError(
                "Target cannot be formed from household sizes available for "
                f"{source.evidence.place}"
            )
        weights = self._normalized([probabilities[size] for size in options])
        return options[int(rng.choice(len(options), p=weights))]

    def _household_size_probabilities(
        self, distribution: FeatureDistribution
    ) -> dict[int, float]:
        if distribution.values:
            result: dict[int, float] = defaultdict(float)
            for label, probability in distribution.values.items():
                try:
                    size = int(round(float(label.rstrip("+"))))
                except ValueError:
                    continue
                if 1 <= size <= 30:
                    result[size] += probability
            if result:
                return dict(result)
        if distribution.mean is None or distribution.standard_deviation is None:
            raise ValueError("Household-size distribution lacks usable values or moments")
        if distribution.standard_deviation == 0:
            size = int(round(distribution.mean))
            if not 1 <= size <= 30:
                raise ValueError("Household-size mean is outside the supported range")
            return {size: 1}
        sizes = np.arange(1, 31, dtype=np.float64)
        z = (sizes - distribution.mean) / distribution.standard_deviation
        weights = np.exp(-0.5 * z * z)
        return {int(size): float(weight) for size, weight in zip(sizes, weights, strict=True)}

    def _sample_household_members(
        self,
        request: AtlasPopulationRequest,
        city: AtlasCity,
        size: int,
        first_index: int,
        rng: np.random.Generator,
        evidence_by_id: dict[str, EvidenceReference],
        coverage: dict[str, dict[str, Any]],
        profiles: tuple[MeasuredHouseholdMember, ...] | None = None,
    ) -> list[HouseholdMemberSeed]:
        for _ in range(256):
            attempt_evidence: dict[str, EvidenceReference] = {}
            attempt_coverage: dict[str, dict[str, Any]] = defaultdict(
                lambda: {"measured": 0, "imputed": 0, "sources": set()}
            )
            members = [
                self._sample_member(
                    request,
                    city,
                    first_index + offset,
                    rng,
                    attempt_evidence,
                    attempt_coverage,
                )
                for offset in range(size)
            ]
            if profiles is not None and not all(
                self._member_matches_profile(member, profile)
                for member, profile in zip(members, profiles, strict=True)
            ):
                continue
            adults = [index for index, member in enumerate(members) if member.age >= 18]
            if adults:
                if profiles is not None:
                    members = [
                        member.model_copy(
                            update={
                                "relationship_to_reference": profile.relationship_to_reference
                            }
                        )
                        for member, profile in zip(members, profiles, strict=True)
                    ]
                    if not self._valid_family_ages(members):
                        continue
                evidence_by_id.update(attempt_evidence)
                for feature_id, values in attempt_coverage.items():
                    coverage[feature_id]["measured"] += values["measured"]
                    coverage[feature_id]["imputed"] += values["imputed"]
                    coverage[feature_id]["sources"].update(values["sources"])
                reference = (
                    next(
                        index
                        for index, member in enumerate(members)
                        if member.relationship_to_reference == "self"
                    )
                    if profiles is not None
                    else adults[0]
                )
                ordered = [members[reference], *members[:reference], *members[reference + 1 :]]
                related = [
                    member.model_copy(
                        update={
                            "relationship_to_reference": (
                                member.relationship_to_reference
                                if profiles is not None
                                else "self" if index == 0 else "other"
                            )
                        }
                    )
                    for index, member in enumerate(ordered)
                ]
                return assign_agent_types(
                    request.type_assignment,
                    related,
                )
        raise ValueError(
            f"Unable to draw a valid household with an adult for {city.name}; "
            "joint household-age evidence is required"
        )

    @staticmethod
    def _member_matches_profile(
        member: HouseholdMemberSeed, profile: MeasuredHouseholdMember
    ) -> bool:
        return (
            profile.minimum_age <= member.age <= profile.maximum_age
            and (not profile.allowed_sexes or member.sex in profile.allowed_sexes)
        )

    @staticmethod
    def _valid_family_ages(members: list[HouseholdMemberSeed]) -> bool:
        reference = next(
            member for member in members if member.relationship_to_reference == "self"
        )
        spouses = [
            member for member in members if member.relationship_to_reference == "spouse"
        ]
        children = [
            member for member in members if member.relationship_to_reference == "child"
        ]
        parents = [
            reference,
            *spouses,
            *(
                member
                for member in members
                if member.relationship_to_reference == "parent"
            ),
        ]
        return all(abs(reference.age - spouse.age) <= 50 for spouse in spouses) and all(
            parent.age - child.age >= 12 for child in children for parent in parents
        )

    def _sample_member(
        self,
        request: AtlasPopulationRequest,
        city: AtlasCity,
        index: int,
        rng: np.random.Generator,
        evidence_by_id: dict[str, EvidenceReference],
        coverage: dict[str, dict[str, Any]],
    ) -> HouseholdMemberSeed:
        field_evidence: dict[str, str] = {}
        traits: dict[str, Any] = {}
        joint_values: dict[str, str | float] = {}
        for table in self._joint_tables(city):
            record = self._sample_joint_cell(table, rng)
            joint_values.update(self._typed_joint_values(record))
            evidence_by_id[table.evidence.evidence_id] = table.evidence
            for feature_id in table.feature_ids:
                field_evidence[feature_id] = table.evidence.evidence_id
                self._record_coverage(coverage, feature_id, table.evidence)
        age_sex = self._age_sex(request.scope, city)
        if age_sex is not None and ({"age", "sex"} - set(joint_values)):
            values, evidence = age_sex
            label = self._sample_categorical(values, rng)
            sampled_sex, sampled_age = label.split(":", 1)
            age_value = int(round(float(joint_values.get("age", sampled_age))))
            sex_value = str(joint_values.get("sex", sampled_sex))
            evidence_by_id[evidence.evidence_id] = evidence
            for field in {"age", "sex"} - set(joint_values):
                field_evidence[field] = evidence.evidence_id
                self._record_coverage(coverage, field, evidence)
        elif {"age", "sex"} <= set(joint_values):
            age_value = int(round(float(joint_values["age"])))
            sex_value = str(joint_values["sex"])
        else:
            missing_sources = {
                field: self._source(request.scope, city, field)
                for field in {"age", "sex"} - set(joint_values)
            }
            if any(source is None for source in missing_sources.values()):
                raise ValueError(f"Age and sex evidence is missing for {city.country_name}")
            age_value = int(round(float(joint_values["age"]))) if "age" in joint_values else int(
                round(float(self._sample_value(missing_sources["age"], rng)))
            )
            sex_value = (
                str(joint_values["sex"])
                if "sex" in joint_values
                else str(self._sample_value(missing_sources["sex"], rng))
            )
            for field, source in missing_sources.items():
                if source is None:
                    continue
                evidence_by_id[source.evidence.evidence_id] = source.evidence
                field_evidence[field] = source.evidence.evidence_id
                self._record_coverage(coverage, field, source.evidence)
        traits.update(
            {
                feature_id: value
                for feature_id, value in joint_values.items()
                if feature_id not in {"age", "sex"}
            }
        )
        for feature_id in sorted(self.definitions):
            if feature_id in {"age", "sex", "household_size"} or feature_id in joint_values:
                continue
            source = self._source(request.scope, city, feature_id)
            if source is None:
                continue
            traits[feature_id] = self._sample_value(source, rng)
            evidence_by_id[source.evidence.evidence_id] = source.evidence
            field_evidence[feature_id] = source.evidence.evidence_id
            self._record_coverage(coverage, feature_id, source.evidence)
        return HouseholdMemberSeed(
            member_id=f"person-{index + 1}",
            age=age_value,
            sex=sex_value,
            relationship_to_reference="other",
            agent_types=[request.agent_type_id],
            traits=traits,
            states={},
            field_evidence=field_evidence,
        )

    @staticmethod
    def _sample_joint_cell(
        table: MeasuredJointTable, rng: np.random.Generator
    ) -> MeasuredJointData:
        weights = AtlasPopulationMaterializer._normalized(
            [record.probability for record in table.records]
        )
        return table.records[int(rng.choice(len(table.records), p=weights))]

    def _typed_joint_values(
        self, record: MeasuredJointData
    ) -> dict[str, str | float]:
        result: dict[str, str | float] = {}
        for feature_id, value in self._joint_values(record).items():
            definition = self.definitions[feature_id]
            if definition.kind in {"categorical", "binary"}:
                result[feature_id] = str(value)
            else:
                result[feature_id] = float(value)
        return result

    def _sample_value(self, source: SampleSource, rng: np.random.Generator) -> str | float:
        distribution = source.distribution
        definition = self.definitions[source.feature_id]
        if distribution.values:
            label = self._sample_categorical(distribution.values, rng)
            if definition.kind != "continuous":
                return label
            return float(label.rstrip("+"))
        if distribution.mean is None or distribution.standard_deviation is None:
            raise ValueError(f"Distribution for {source.feature_id} has no sampleable values")
        value = (
            distribution.mean
            if distribution.standard_deviation == 0
            else float(rng.normal(distribution.mean, distribution.standard_deviation))
        )
        if definition.value_range is not None:
            value = float(
                np.clip(value, definition.value_range.minimum, definition.value_range.maximum)
            )
        return value

    @staticmethod
    def _sample_categorical(values: dict[str, float], rng: np.random.Generator) -> str:
        labels = sorted(values)
        weights = AtlasPopulationMaterializer._normalized([values[label] for label in labels])
        return labels[int(rng.choice(len(labels), p=weights))]

    @staticmethod
    def _record_coverage(
        coverage: dict[str, dict[str, Any]],
        feature_id: str,
        evidence: EvidenceReference,
        count: int = 1,
    ) -> None:
        key = "imputed" if evidence.status in {"imputed", "unknown"} else "measured"
        coverage[feature_id][key] += count
        coverage[feature_id]["sources"].add(evidence.source)

    def _add_unknown_provenance(
        self, result: InitialPopulationMaterialization
    ) -> InitialPopulationMaterialization:
        feature_ids = set(self.definitions)
        provenance: dict[str, AgentInitialStateProvenance] = {}
        for agent_id, value in result.provenance.items():
            known = set(value.field_evidence)
            provenance[agent_id] = value.model_copy(
                update={"unknown_fields": sorted(set(value.unknown_fields) | (feature_ids - known))}
            )
        return result.model_copy(update={"provenance": provenance})

    def _coverage(
        self, target: int, coverage: dict[str, dict[str, Any]]
    ) -> list[AtlasPopulationFeatureCoverage]:
        result = []
        for feature_id in sorted(self.definitions):
            measured = min(target, int(coverage[feature_id]["measured"]))
            imputed = min(target - measured, int(coverage[feature_id]["imputed"]))
            result.append(
                AtlasPopulationFeatureCoverage(
                    feature_id=feature_id,
                    measured_agents=measured,
                    imputed_agents=imputed,
                    unknown_agents=target - measured - imputed,
                    sources=sorted(coverage[feature_id]["sources"]),
                )
            )
        return result
