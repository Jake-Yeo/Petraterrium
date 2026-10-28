import hashlib
from bisect import bisect_left
from collections import defaultdict, deque
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .atlas.features import resolve_feature_distribution
from .data import COUNTRY_BY_CODE
from .dsl import (
    DefaultDefinition,
    DSLConfig,
    Evidence,
    FeatureDefinition,
    FeatureDistribution,
    flatten_behaviour_bundles,
)


class PopulationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Relationship(PopulationModel):
    target_id: str
    kind: Literal["family", "household", "friend", "enemy", "workplace", "school"]
    weight: float = Field(ge=-1, le=1)
    trust: float | None = Field(default=None, ge=-1, le=1)
    similarity: float | None = Field(default=None, ge=-1, le=1)
    evidence_id: str | None = Field(default=None, min_length=1)
    evidence_status: Literal[
        "measured_joint",
        "fitted_model",
        "default_estimated",
        "approved_estimate",
        "user_defined",
        "imputed",
        "unknown",
    ] | None = None

    @model_validator(mode="after")
    def complete_interaction_evidence(self):
        fields = (
            self.trust,
            self.similarity,
            self.evidence_id,
            self.evidence_status,
        )
        if any(value is not None for value in fields) and not all(
            value is not None for value in fields
        ):
            raise ValueError(
                "Relationship interaction evidence requires trust, similarity, "
                "evidence_id, and evidence_status"
            )
        return self


class AgentRecord(PopulationModel):
    agent_id: str
    place: str
    latitude: float
    longitude: float
    role: str
    log_tier: Literal["spotlight", "sampled", "mass"]
    traits: dict[str, Any]
    states: dict[str, str]
    behaviour: dict[str, float]
    behaviour_provenance: dict[str, Evidence]
    relationships: list[Relationship]
    weight: float = Field(gt=0)


class PopulationTable(PopulationModel):
    population_id: str
    version: str
    seed: int
    agents: list[AgentRecord]


class WeightedPopulation(PopulationModel):
    weights: list[float]
    iterations: int
    converged: bool
    maximum_error: float


def numeric_value(value: str):
    try:
        number = float(value)
    except ValueError:
        return value
    return int(number) if number.is_integer() else number


def ordered_defaults(defaults: list[DefaultDefinition]) -> list[DefaultDefinition]:
    by_id = {default.id: default for default in defaults}
    incoming = {default.id: set(default.depends_on) for default in defaults}
    outgoing = defaultdict(set)
    for identity, dependencies in incoming.items():
        for dependency in dependencies:
            if dependency not in by_id:
                raise ValueError(f"Unknown default dependency {dependency}")
            outgoing[dependency].add(identity)
    ready = deque(
        sorted(identity for identity, dependencies in incoming.items() if not dependencies)
    )
    result = []
    while ready:
        identity = ready.popleft()
        result.append(by_id[identity])
        for dependent in sorted(outgoing[identity]):
            incoming[dependent].remove(identity)
            if not incoming[dependent]:
                ready.append(dependent)
    if len(result) != len(defaults):
        raise ValueError("Default-state dependency cycle")
    return result


def select_default(
    candidates: list[DefaultDefinition], traits: dict[str, Any], place: str
) -> DefaultDefinition | None:
    eligible = []
    age = traits.get("age")
    for default in candidates:
        if default.place and default.place != place:
            continue
        if default.age_min is not None and (age is None or float(age) < default.age_min):
            continue
        if default.age_max is not None and (age is None or float(age) > default.age_max):
            continue
        if any(str(traits.get(key)) != value for key, value in default.when.items()):
            continue
        specificity = int(default.place is not None) + len(default.when)
        specificity += int(default.age_min is not None or default.age_max is not None)
        eligible.append((specificity, default))
    return max(eligible, key=lambda item: item[0])[1] if eligible else None


def sample_default_states(
    defaults: list[DefaultDefinition],
    place: str,
    rng: np.random.Generator,
) -> dict[str, Any]:
    grouped = defaultdict(list)
    for default in defaults:
        grouped[default.id].append(default)
    ordered = ordered_defaults(
        [max(items, key=lambda item: len(item.depends_on)) for items in grouped.values()]
    )
    traits = {}
    for base in ordered:
        selected = select_default(grouped[base.id], traits, place)
        if selected is None:
            continue
        labels = list(selected.distribution.values)
        probabilities = list(selected.distribution.values.values())
        traits[selected.id] = numeric_value(str(rng.choice(labels, p=probabilities)))
    return traits


def stable_agent_id(population_id: str, seed: int, index: int) -> str:
    return hashlib.sha256(f"{population_id}:{seed}:{index}".encode()).hexdigest()[:20]


def feature_distributions_by_place(
    dsl: DSLConfig,
) -> dict[str, list[tuple[FeatureDefinition, FeatureDistribution]]]:
    registry = dsl.feature_registry
    if registry is None:
        return {}
    definitions = {feature.id: feature for feature in registry.definitions}
    resolved = defaultdict(list)
    for place, hierarchy in dsl.population.place_hierarchy.items():
        for feature_id, feature in definitions.items():
            resolution = resolve_feature_distribution(
                registry,
                feature_id,
                city=hierarchy.city or place,
                country=hierarchy.country,
                subregion=hierarchy.subregion,
                region=hierarchy.region,
            )
            if resolution.distribution is not None:
                resolved[place].append((feature, resolution.distribution))
    return dict(resolved)


def sample_feature_traits(
    distributions: list[tuple[FeatureDefinition, FeatureDistribution]],
    rng: np.random.Generator,
) -> dict[str, Any]:
    traits = {}
    for feature, distribution in distributions:
        if feature.kind in {"categorical", "binary"}:
            labels = list(distribution.values)
            probabilities = list(distribution.values.values())
            traits[feature.id] = str(rng.choice(labels, p=probabilities))
            continue
        if distribution.values:
            labels = list(distribution.values)
            probabilities = list(distribution.values.values())
            selected = str(rng.choice(labels, p=probabilities)).rstrip("+")
            traits[feature.id] = float(selected)
            continue
        value = float(rng.normal(distribution.mean, distribution.standard_deviation))
        traits[feature.id] = float(
            np.clip(value, feature.value_range.minimum, feature.value_range.maximum)
        )
    return traits


def nearest_friend_targets(
    drafts: list[dict[str, Any]],
    indexes_by_place: dict[str, list[int]],
) -> dict[int, int]:
    targets = {}
    for indexes in indexes_by_place.values():
        indexes_by_age = defaultdict(list)
        for index in indexes:
            age = float(drafts[index]["traits"].get("age", 0))
            indexes_by_age[age].append(index)
        ages = sorted(indexes_by_age)
        for members in indexes_by_age.values():
            members.sort(key=lambda index: drafts[index]["agent_id"])
        for index in indexes:
            age = float(drafts[index]["traits"].get("age", 0))
            age_position = bisect_left(ages, age)
            same_age = indexes_by_age[age]
            candidates = []
            if len(same_age) > 1:
                candidates.append(same_age[1] if same_age[0] == index else same_age[0])
            else:
                if age_position > 0:
                    candidates.append(indexes_by_age[ages[age_position - 1]][0])
                if age_position + 1 < len(ages):
                    candidates.append(indexes_by_age[ages[age_position + 1]][0])
            if candidates:
                targets[index] = min(
                    candidates,
                    key=lambda candidate: (
                        abs(
                            float(drafts[candidate]["traits"].get("age", 0))
                            - age
                        ),
                        drafts[candidate]["agent_id"],
                    ),
                )
    return targets


def generate_population(dsl: DSLConfig, data_atlas, seed: int) -> PopulationTable:
    rng = np.random.default_rng(seed)
    feature_rng = np.random.default_rng(np.random.SeedSequence([seed, 2]))
    feature_distributions = feature_distributions_by_place(dsl)
    bundles = {bundle.id: bundle for bundle in dsl.behaviour_bundles}
    selected_bundles = []
    if bundles:
        children = {parent for bundle in bundles.values() for parent in bundle.inherits}
        selected_bundles = sorted(set(bundles) - children)[:1]
    behaviour = flatten_behaviour_bundles(selected_bundles, bundles) if selected_bundles else None
    roles = {role.id for role in dsl.roles}
    default_role = "citizen" if "citizen" in roles else min(roles, default="synthetic_agent")
    drafts = []
    for index in range(dsl.population.size):
        place = dsl.population.places[index % len(dsl.population.places)]
        country = COUNTRY_BY_CODE.get(place)
        coordinates = dsl.population.place_coordinates.get(place)
        latitude = coordinates[0] if coordinates else country.latitude if country else 0
        longitude = coordinates[1] if coordinates else country.longitude if country else 0
        traits = sample_default_states(dsl.default_states, place, rng)
        traits.update(sample_feature_traits(feature_distributions.get(place, []), feature_rng))
        states = {
            state.id: str(
                rng.choice(list(state.initial.values), p=list(state.initial.values.values()))
            )
            for state in dsl.states
        }
        drafts.append(
            {
                "agent_id": stable_agent_id(dsl.population.id, seed, index),
                "place": place,
                "latitude": float(latitude + rng.normal(0, 0.08)),
                "longitude": float(longitude + rng.normal(0, 0.08)),
                "role": default_role,
                "log_tier": "spotlight" if index < 10 else "sampled" if index < 30 else "mass",
                "traits": traits,
                "states": states,
                "behaviour": behaviour.values if behaviour else {},
                "behaviour_provenance": behaviour.provenance if behaviour else {},
                "relationships": [],
                "weight": 1,
            }
        )
    by_place = defaultdict(list)
    for index, agent in enumerate(drafts):
        by_place[agent["place"]].append(index)
    for place, indexes in by_place.items():
        represented = dsl.population.place_populations.get(place, len(indexes))
        weight = represented / len(indexes)
        for index in indexes:
            drafts[index]["weight"] = weight
    friend_targets = nearest_friend_targets(drafts, by_place)
    for index, agent in enumerate(drafts):
        if agent["traits"].get("has_friend") != "yes":
            continue
        friend_index = friend_targets.get(index)
        if friend_index is None:
            continue
        agent["relationships"].append(
            Relationship(
                target_id=drafts[friend_index]["agent_id"],
                kind="friend",
                weight=0.8,
            )
        )
    return PopulationTable(
        population_id=dsl.population.id,
        version=dsl.population.version,
        seed=seed,
        agents=[AgentRecord(**agent) for agent in drafts],
    )


def apply_ipf(
    records: list[dict[str, str]],
    marginals: dict[str, dict[str, float]],
    max_iterations: int = 200,
    tolerance: float = 1e-8,
) -> WeightedPopulation:
    if not records:
        raise ValueError("IPF requires at least one microdata row")
    weights = np.ones(len(records), dtype=float)
    maximum_error = float("inf")
    for iteration in range(1, max_iterations + 1):
        maximum_error = 0.0
        for field, targets in marginals.items():
            total_target = sum(targets.values())
            if total_target <= 0:
                raise ValueError(f"Marginal {field} has no positive mass")
            for category, target in targets.items():
                indexes = np.array(
                    [index for index, row in enumerate(records) if str(row.get(field)) == category],
                    dtype=int,
                )
                if not len(indexes):
                    if target:
                        raise ValueError(f"Microdata has no support for {field}={category}")
                    continue
                current = float(weights[indexes].sum())
                desired = target / total_target * float(weights.sum())
                weights[indexes] *= desired / current
                maximum_error = max(maximum_error, abs(current - desired) / max(desired, 1e-12))
        if maximum_error <= tolerance:
            return WeightedPopulation(
                weights=weights.tolist(),
                iterations=iteration,
                converged=True,
                maximum_error=maximum_error,
            )
    return WeightedPopulation(
        weights=weights.tolist(),
        iterations=max_iterations,
        converged=False,
        maximum_error=maximum_error,
    )
