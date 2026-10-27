import json

from pydantic import BaseModel, ConfigDict, Field

from .dsl import Evidence


class DataModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HarmonizedValue(DataModel):
    field: str
    original_label: str
    values: dict[str, float]
    status: str
    uncertainty: float = Field(ge=0, le=1)
    mapping_version: str
    provenance: Evidence
    method: str


class MappingDefinition(DataModel):
    dataset: str
    field: str
    version: str
    mappings: dict[str, dict[str, float]]
    provenance: Evidence


class CityFieldValue(DataModel):
    city_id: int
    field: str
    value: object | None
    status: str
    provenance: dict | None
    uncertainty: float | None


class CoverageReport(DataModel):
    field: str
    direct_coverage: float
    direct_plus_inherited_coverage: float
    population_weighted_coverage: float
    missing_cities_by_population: list[dict]


class MappingRegistry:
    def __init__(self, store=None):
        self.definitions: dict[tuple[str, str], MappingDefinition] = {}
        self.store = store

    def stored_definition(self, dataset: str, field: str) -> MappingDefinition | None:
        if self.store is None:
            return None
        with self.store.connection() as conn:
            row = conn.execute(
                """SELECT * FROM label_mappings
                WHERE dataset=? AND field=? AND active=1
                ORDER BY rowid DESC LIMIT 1""",
                (dataset, field),
            ).fetchone()
        if row is None:
            return None
        definition = MappingDefinition(
            dataset=row["dataset"],
            field=row["field"],
            version=row["version"],
            mappings=json.loads(row["mappings_json"]),
            provenance=Evidence.model_validate_json(row["provenance_json"]),
        )
        self.definitions[(dataset, field)] = definition
        return definition

    def register(
        self,
        dataset: str,
        field: str,
        version: str,
        mappings: dict[str, dict[str, float]],
        provenance: Evidence,
    ) -> MappingDefinition:
        normalized = {}
        for label, targets in mappings.items():
            if not targets or any(value < 0 for value in targets.values()):
                raise ValueError(f"Mapping {label} has invalid weights")
            if abs(sum(targets.values()) - 1) > 1e-9:
                raise ValueError(f"Mapping {label} weights must sum to 1")
            normalized[label.casefold().strip()] = targets
        definition = MappingDefinition(
            dataset=dataset,
            field=field,
            version=version,
            mappings=normalized,
            provenance=provenance,
        )
        self.definitions[(dataset, field)] = definition
        if self.store is not None:
            with self.store.connection() as conn:
                conn.execute(
                    "UPDATE label_mappings SET active=0 WHERE dataset=? AND field=?",
                    (dataset, field),
                )
                conn.execute(
                    """INSERT OR REPLACE INTO label_mappings
                    (dataset,field,version,mappings_json,provenance_json,active)
                    VALUES(?,?,?,?,?,1)""",
                    (
                        dataset,
                        field,
                        version,
                        json.dumps(normalized, sort_keys=True),
                        provenance.model_dump_json(),
                    ),
                )
        return definition

    def harmonize(self, dataset: str, field: str, label: str) -> HarmonizedValue:
        definition = self.definitions.get((dataset, field)) or self.stored_definition(
            dataset, field
        )
        if definition is None:
            return unknown_value(field, label, "unregistered")
        values = definition.mappings.get(label.casefold().strip())
        if values is None:
            return unknown_value(field, label, definition.version)
        split = len(values) > 1
        status = "imputed" if split or definition.provenance.status == "imputed" else "present"
        uncertainty = max(definition.provenance.uncertainty, 0.15 if split else 0)
        return HarmonizedValue(
            field=field,
            original_label=label,
            values=values,
            status=status,
            uncertainty=uncertainty,
            mapping_version=definition.version,
            provenance=definition.provenance,
            method="imputed_split" if split else "direct_mapping",
        )


def unknown_value(field: str, label: str, version: str) -> HarmonizedValue:
    provenance = Evidence(
        source="No confirmed mapping",
        version=version,
        status="missing",
        uncertainty=1,
    )
    return HarmonizedValue(
        field=field,
        original_label=label,
        values={"Unknown": 1},
        status="missing",
        uncertainty=1,
        mapping_version=version,
        provenance=provenance,
        method="unknown",
    )


RESTRICTED_COMPOSITIONAL_TRAITS = {
    "income",
    "education",
    "trust_in_government",
    "political_ideology",
    "ideology",
    "criminality",
    "healthcare_access",
    "discrimination",
}


def compositional_estimate(
    trait: str,
    group_distribution: dict[str, float],
    trait_by_group: dict[str, dict[str, float]],
    provenance: Evidence,
) -> HarmonizedValue:
    if trait in RESTRICTED_COMPOSITIONAL_TRAITS:
        return unknown_value(trait, "compositional estimate prohibited", provenance.version)
    if abs(sum(group_distribution.values()) - 1) > 1e-9:
        raise ValueError("Group distribution must sum to 1")
    values = {}
    for group, group_share in group_distribution.items():
        distribution = trait_by_group.get(group)
        if distribution is None:
            return unknown_value(trait, f"missing group {group}", provenance.version)
        if abs(sum(distribution.values()) - 1) > 1e-9:
            raise ValueError(f"Trait distribution for {group} must sum to 1")
        for label, share in distribution.items():
            values[label] = values.get(label, 0) + group_share * share
    values = {label: round(value, 12) for label, value in values.items()}
    estimate_provenance = provenance.model_copy(
        update={"status": "imputed", "uncertainty": max(provenance.uncertainty, 0.25)}
    )
    return HarmonizedValue(
        field=trait,
        original_label="compositional estimate",
        values=values,
        status="imputed",
        uncertainty=estimate_provenance.uncertainty,
        mapping_version=provenance.version,
        provenance=estimate_provenance,
        method="compositional",
    )


def get_city_field(store, city_id: int, field: str, scope="shared") -> CityFieldValue:
    from .atlas.organizer import city_detail

    detail = city_detail(store, city_id, scope)
    value = next(item for item in detail.city.fields if item.field == field)
    uncertainty_by_status = {"present": 0.05, "inherited": 0.2, "imputed": 0.35, "missing": None}
    return CityFieldValue(
        city_id=city_id,
        field=field,
        value=value.value,
        status=value.status,
        provenance=value.provenance.model_dump() if value.provenance else None,
        uncertainty=uncertainty_by_status[value.status],
    )


def coverage_report(store, field: str, scope="shared") -> CoverageReport:
    from .atlas.organizer import overview

    result = overview(store, scope=scope, missing_field=field, page_size=20)
    coverage = next(item for item in result.summary.fields if item.field == field)
    return CoverageReport(
        field=field,
        direct_coverage=coverage.direct_percent,
        direct_plus_inherited_coverage=coverage.direct_plus_inherited_percent,
        population_weighted_coverage=coverage.direct_plus_inherited_population_percent,
        missing_cities_by_population=[
            gap.model_dump() for gap in result.gaps if gap.field == field
        ],
    )
