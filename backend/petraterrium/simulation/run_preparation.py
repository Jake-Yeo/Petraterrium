import hashlib
import json
import math
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..atlas.evidence_receipts import AtlasEvidenceReceiptRegistry
from ..population import AgentRecord
from ..rust_core import RustCoreClient
from .aggregate_statistics import AggregateStatisticsProgram, TimelineSubject
from .coefficient_evidence import (
    load_coefficient_registry,
    load_default_dsl_identity,
    validate_coefficient_registry,
)
from .initial_agent_summary import (
    global_population_evidence_summary,
    is_global_demo_population,
)
from .interaction_trees import AgentRoutineEffect as InteractionTreeAgentRoutineEffect
from .interaction_trees import AgentStateEffect as InteractionTreeAgentStateEffect
from .locations import (
    LocationDecisionTreeAvailability,
    LocationEvidence,
    LocationPlace,
)
from .mobility import MobilityEvidence, ResolvedMobility, resolve_mobility
from .registry_store import SimulationRegistryStore
from .routines import ResolvedRoutineRegistry, resolve_routines
from .run_service import PreparedRustRun, SimulationRunConfig
from .run_warnings import evidence_summary
from .runtime_decision_compiler import (
    RUNTIME_PROGRAM_VERSION,
    RuntimeDecisionCompilation,
    compile_runtime_decisions,
)
from .runtime_state_compiler import compile_runtime_state

WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
CURRENT_PLACE_IDS = {"current", "current_place"}
EXECUTABLE_RELATIONSHIP_EVIDENCE = {
    "measured_joint",
    "fitted_model",
    "default_estimated",
    "approved_estimate",
}


@dataclass(frozen=True)
class _RuntimePlace:
    id: str
    kind: str
    location_id: str


class LazyRustCoreClient:
    def __init__(self):
        self._client: RustCoreClient | None = None
        self._lock = threading.Lock()

    def run_agents(self, request: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._client is None:
                self._client = RustCoreClient()
            client = self._client
        return client.run_agents(request)

    def run_interaction_tree(self, request: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._client is None:
                self._client = RustCoreClient()
            client = self._client
        return client.run_interaction_tree(request)

    def validate_text_dsl(self, source: str) -> dict[str, Any]:
        with self._lock:
            if self._client is None:
                self._client = RustCoreClient()
            client = self._client
        return client.validate_text_dsl(source)

    def run_text_dsl(
        self,
        source: str,
        *,
        seed: int,
        ticks: int,
        continuation: Mapping[str, Any] | None = None,
        population_id: str | None = None,
        composition_id: str | None = None,
        composition_population_id: str | None = None,
        neighbourhood_id: str | None = None,
        neighbourhood_population_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if self._client is None:
                self._client = RustCoreClient()
            client = self._client
        return client.run_text_dsl(
            source,
            seed=seed,
            ticks=ticks,
            continuation=continuation,
            population_id=population_id,
            composition_id=composition_id,
            composition_population_id=composition_population_id,
            neighbourhood_id=neighbourhood_id,
            neighbourhood_population_id=neighbourhood_population_id,
        )

    def evaluate_text_dsl_aggregate(self, source: str, **request: Any) -> dict[str, Any]:
        with self._lock:
            if self._client is None:
                self._client = RustCoreClient()
            client = self._client
        return client.evaluate_text_dsl_aggregate(source, **request)

    def evaluate_cached_composition(self, source: str, **request: Any) -> dict[str, Any]:
        with self._lock:
            if self._client is None:
                self._client = RustCoreClient()
            client = self._client
        return client.evaluate_cached_composition(source, **request)


def _text_trait(agent: AgentRecord, name: str) -> str:
    value = agent.traits.get(name)
    return str(value).strip() if value is not None else ""


def _agent_types(agent: AgentRecord) -> set[str]:
    values = agent.traits.get("agent_types")
    if isinstance(values, list):
        return {str(value) for value in values}
    value = agent.traits.get("agent_type")
    return {str(value)} if value else {agent.role}


def _primary_agent_type(agent: AgentRecord) -> str:
    value = agent.traits.get("agent_type")
    if value is not None and str(value).strip():
        return str(value).strip()
    values = agent.traits.get("agent_types")
    if isinstance(values, list):
        first = next((str(item).strip() for item in values if str(item).strip()), None)
        if first:
            return first
    return agent.role


def _runtime_identifier(prefix: str, value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", value.casefold()).strip("-")
    digest = hashlib.sha256(value.encode()).hexdigest()[:8]
    return f"{prefix}-{normalized or 'unknown'}-{digest}"


def _hour(value: str) -> float:
    hours, minutes = value.split(":")
    return int(hours) + int(minutes) / 60


def _resolved_routines(store: SimulationRegistryStore) -> ResolvedRoutineRegistry | None:
    registry = store.routines()
    if registry is None:
        return None
    known_modules = {module.id for module in store.decision_trees().modules}
    return resolve_routines(registry, known_modules)


def _resolved_mobility(store: SimulationRegistryStore) -> ResolvedMobility | None:
    registry = store.mobility()
    return resolve_mobility(registry) if registry is not None else None


def _mobility_provenance(evidence: MobilityEvidence) -> dict[str, Any]:
    return {
        "source_title": evidence.source_title,
        "source_version": evidence.source_version,
        "source_date": evidence.source_date,
        "licence": evidence.licence,
        "evidence_id": evidence.evidence_id,
        "status": evidence.status,
        "uncertainty": evidence.uncertainty,
    }


def _routine_schedules(
    resolved: ResolvedRoutineRegistry | None,
    timed_action_ids: Mapping[str, str],
    module_ids_by_agent_type: Mapping[str, tuple[str, ...]],
    agents: list[AgentRecord],
    runtime_place_indices: Mapping[str, int],
    runtime_places_by_id: Mapping[str, _RuntimePlace],
    initial_runtime_place_ids: list[str],
    routine_destination_ids: Mapping[tuple[int, str], str | None],
    transit_place_ids: Mapping[tuple[int, str], str],
    runtime_module_by_source_module_by_agent: list[dict[str, str]],
    mobility: ResolvedMobility | None,
    tick_interval_hours: float,
) -> list[dict[str, Any]]:
    if resolved is None:
        return []
    schedules: list[dict[str, Any]] = []
    scheduled_agents_by_step: dict[tuple[str, str, str], set[int]] = {}
    for agent_type in resolved.agent_types:
        module_ids = module_ids_by_agent_type.get(agent_type.agent_type_id)
        if not module_ids:
            continue
        eligible_agent_indices = [
            index
            for index, agent in enumerate(agents)
            if agent_type.agent_type_id in _agent_types(agent)
        ]
        for resolved_routine in agent_type.routines:
            routine = resolved_routine.routine
            if routine.evidence.status not in {
                "measured",
                "user_defined",
                "default_estimated",
            }:
                continue
            expected_origin_ids = list(initial_runtime_place_ids)
            for step in routine.steps:
                existing_timed_action_id = timed_action_ids.get(
                    step.activity.strip().casefold().replace("_", " ")
                )
                timed_action_id = existing_timed_action_id or step.activity
                step_key = (routine.agent_type_id, routine.id, step.id)
                scheduled_agents = scheduled_agents_by_step.setdefault(step_key, set())
                step_agent_indices = [
                    index for index in eligible_agent_indices if index not in scheduled_agents
                ]
                if not step_agent_indices:
                    continue
                activate_module_by_agent: list[str | None] = [None] * len(agents)
                if step.decision_tree_module_id is not None:
                    missing_agents = []
                    for index in step_agent_indices:
                        runtime_module = runtime_module_by_source_module_by_agent[index].get(
                            step.decision_tree_module_id
                        )
                        if runtime_module is None:
                            missing_agents.append(agents[index].agent_id)
                        else:
                            activate_module_by_agent[index] = runtime_module
                    if missing_agents:
                        raise ValueError(
                            f"Routine step {routine.id}.{step.id} calls decision module "
                            f"{step.decision_tree_module_id!r} without an executable "
                            f"evidence-backed runtime module for agents: "
                            + ", ".join(missing_agents)
                        )
                place_ids = [place_id.strip().casefold() for place_id in step.schedule.place_ids]
                destination_place_by_agent: list[int | None] = [None] * len(agents)
                travel_by_agent: list[dict[str, Any] | None] = [None] * len(agents)
                unavailable_reason_by_agent: list[str | None] = [None] * len(agents)
                required_place_indices: set[int] = set()
                if len(place_ids) == 1 and place_ids[0] not in CURRENT_PLACE_IDS:
                    place_id = place_ids[0]
                    destination_ids = [
                        routine_destination_ids.get((index, place_id))
                        for index in step_agent_indices
                    ]
                    if not destination_ids or any(
                        destination_id is None for destination_id in destination_ids
                    ):
                        continue
                    for index, destination_id in zip(
                        step_agent_indices, destination_ids, strict=True
                    ):
                        destination_index = runtime_place_indices[destination_id]
                        destination_place_by_agent[index] = destination_index
                        required_place_indices.add(destination_index)
                        origin_id = expected_origin_ids[index]
                        if origin_id == destination_id:
                            continue
                        origin = runtime_places_by_id[origin_id]
                        destination = runtime_places_by_id[destination_id]
                        route = (
                            mobility.route(origin.kind, destination.kind)
                            if mobility is not None
                            else None
                        )
                        if route is None:
                            unavailable_reason_by_agent[index] = (
                                f"{step.name} unavailable — no confirmed {origin.kind} to "
                                f"{destination.kind} travel evidence"
                            )
                            continue
                        transit_id = transit_place_ids.get((index, route.transit_place_kind))
                        travel_ticks = mobility.travel_ticks(
                            origin.kind,
                            destination.kind,
                            tick_interval_hours,
                        )
                        if transit_id is None or travel_ticks is None:
                            unavailable_reason_by_agent[index] = (
                                f"{step.name} unavailable — confirmed route {route.id} has no "
                                "runtime transit place"
                            )
                            continue
                        travel_by_agent[index] = {
                            "from_place_index": runtime_place_indices[origin_id],
                            "travel_place_index": runtime_place_indices[transit_id],
                            "travel_ticks": travel_ticks,
                            "route_id": route.id,
                            "provenance": _mobility_provenance(route.evidence),
                        }
                        expected_origin_ids[index] = destination_id
                elif len(place_ids) > 1:
                    for index in step_agent_indices:
                        for place_id in place_ids:
                            destination_id = routine_destination_ids.get((index, place_id))
                            if destination_id is not None:
                                required_place_indices.add(runtime_place_indices[destination_id])
                    if not required_place_indices:
                        continue
                schedules.append(
                    {
                        "id": _runtime_identifier(
                            "routine",
                            f"{agent_type.agent_type_id}:{routine.id}:{step.id}",
                        ),
                        "action": step.activity,
                        "timed_action_id": timed_action_id,
                        "timed_action_provenance": (
                            {
                                "source": routine.evidence.source_title
                                or routine.evidence.note
                                or f"Routine {routine.id}",
                                "version": routine.evidence.source_date or "undated",
                                "status": "default_estimated",
                                "uncertainty": 1.0,
                                "source_date": routine.evidence.source_date,
                                "evidence_id": f"routine:{routine.id}:{step.id}",
                                "evidence_kind": routine.evidence.status,
                            }
                            if timed_action_id is not None
                            else None
                        ),
                        "weekdays": [WEEKDAY_INDEX[day] for day in step.schedule.days],
                        "start_hour": _hour(step.schedule.start_time),
                        "end_hour": _hour(step.schedule.end_time),
                        "modules": list(module_ids),
                        "states": [],
                        "eligible_agent_indices": step_agent_indices,
                        "required_place_indices": sorted(required_place_indices),
                        "destination_place_by_agent": destination_place_by_agent,
                        "activate_module_by_agent": activate_module_by_agent,
                        "travel_by_agent": travel_by_agent,
                        "unavailable_reason_by_agent": unavailable_reason_by_agent,
                    }
                )
                scheduled_agents.update(step_agent_indices)
    return schedules


def _timed_action_locations(
    store: SimulationRegistryStore,
    state_program,
    agents: list[AgentRecord],
    runtime_place_indices: Mapping[str, int],
    initial_runtime_place_ids: list[str],
    routine_destination_ids: Mapping[tuple[int, str], str | None],
) -> None:
    time_execution = state_program.state_dynamics.get("time_execution")
    if not isinstance(time_execution, dict):
        return
    compiled_actions = time_execution.get("actions")
    if not isinstance(compiled_actions, list):
        return
    raw_actions = {
        str(action.get("id")): action
        for action in store.payload_snapshot().get("default_actions", [])
        if isinstance(action, dict) and action.get("id")
    }
    for compiled in compiled_actions:
        action_id = str(compiled.get("action_id", ""))
        requirements = raw_actions.get(action_id, {}).get("place_requirements", [])
        locations: list[int | None] = []
        for agent_index, _agent in enumerate(agents):
            destination_id = None
            for raw_requirement in requirements:
                requirement = str(raw_requirement).strip().casefold()
                if requirement in CURRENT_PLACE_IDS:
                    break
                if requirement == "home":
                    destination_id = initial_runtime_place_ids[agent_index]
                else:
                    destination_id = routine_destination_ids.get((agent_index, requirement))
                if destination_id is not None:
                    break
            locations.append(
                runtime_place_indices[destination_id]
                if destination_id in runtime_place_indices
                else None
            )
        compiled["location_place_index_by_agent"] = locations


def _add_scheduled_timed_actions(
    state_program,
    schedules: list[dict[str, Any]],
    agent_count: int,
) -> None:
    time_execution = state_program.state_dynamics.setdefault(
        "time_execution",
        {"idle_category": "idle", "actions": []},
    )
    actions = time_execution.setdefault("actions", [])
    known_actions = {str(action.get("action_id")) for action in actions}
    for schedule in schedules:
        action_id = schedule.get("timed_action_id")
        provenance = schedule.get("timed_action_provenance")
        if not action_id or action_id in known_actions or not isinstance(provenance, dict):
            continue
        start = float(schedule["start_hour"])
        end = float(schedule["end_hour"])
        window = (end - start) % 24
        if math.isclose(window, 0, abs_tol=1e-9):
            window = 24.0
        median = min(1.0, window / 2)
        minimum = max(1 / 3600, median * 0.5)
        maximum = min(window, max(median + 1 / 3600, median * 2))
        locations = schedule.get("destination_place_by_agent", [])
        if not isinstance(locations, list) or len(locations) != agent_count:
            locations = [schedule.get("destination_place_index")] * agent_count
        actions.append(
            {
                "action_id": action_id,
                "category": "routine",
                "duration": {
                    "duration_min_hours": minimum,
                    "duration_median_hours": median,
                    "duration_max_hours": maximum,
                    "shape": "triangular",
                    "shape_parameters": {},
                    "provenance": provenance,
                },
                "duration_overrides": [],
                "location_place_index_by_agent": locations,
                "priority": 0,
                "passive": False,
                "interruptibility": "interruptible",
                "interruption_outcome": "defer",
                "emergency_interruptions": [],
            }
        )
        known_actions.add(str(action_id))


def _program_version(
    store: SimulationRegistryStore,
    module_ids_by_agent_type: Mapping[str, tuple[str, ...]],
) -> str:
    agent_types = store.agent_types()
    routines = store.routines()
    mobility = store.mobility()
    evidence = store.decision_evidence()
    interaction_program = store.interaction_program()
    coefficient_registry = load_coefficient_registry(store)
    registry_payload = store.payload_snapshot()
    payload = {
        "base": RUNTIME_PROGRAM_VERSION,
        "agent_types": agent_types.model_dump(mode="json") if agent_types else None,
        "routines": routines.model_dump(mode="json") if routines else None,
        "mobility": mobility.model_dump(mode="json") if mobility else None,
        "decision_trees": store.decision_trees().model_dump(mode="json"),
        "decision_evidence": evidence.model_dump(mode="json") if evidence else None,
        "coefficient_registry": (
            coefficient_registry.model_dump(mode="json") if coefficient_registry else None
        ),
        "default_actions": registry_payload.get("default_actions"),
        "agent_states": registry_payload.get("agent_states"),
        "interaction_trees": [tree.model_dump(mode="json") for tree in store.interaction_trees()],
        "interaction_program": (
            interaction_program.model_dump(mode="json") if interaction_program else None
        ),
        "aggregate_statistics": registry_payload.get("aggregate_statistics"),
        "runtime_modules": dict(sorted(module_ids_by_agent_type.items())),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"{RUNTIME_PROGRAM_VERSION}:{hashlib.sha256(encoded.encode()).hexdigest()[:16]}"


def _reachable_source_modules_by_tree(
    store: SimulationRegistryStore,
) -> dict[str, set[str]]:
    registry = store.decision_trees()
    modules = {module.id: module for module in registry.modules}
    result: dict[str, set[str]] = {}
    for tree in registry.trees:
        reachable: set[str] = set()
        pending = [tree.root_module_id]
        while pending:
            module_id = pending.pop()
            if module_id in reachable:
                continue
            module = modules.get(module_id)
            if module is None:
                raise ValueError(
                    f"Decision tree {tree.id!r} references missing module {module_id!r}"
                )
            reachable.add(module_id)
            pending.extend(
                node.target_module_id for node in module.nodes if node.target_module_id is not None
            )
        result[tree.id] = reachable
    return result


def _runtime_module_place_kinds(
    store: SimulationRegistryStore,
    mobility: ResolvedMobility | None,
    decision_program: RuntimeDecisionCompilation,
) -> dict[str, list[str]]:
    if mobility is None:
        return {}
    place_kinds_by_tree: dict[str, set[str]] = {}
    for profile in mobility.definition.place_profiles:
        for tree_id in profile.available_decision_tree_ids:
            place_kinds_by_tree.setdefault(tree_id, set()).add(profile.place_kind)
    if not place_kinds_by_tree:
        return {}
    source_modules_by_tree = _reachable_source_modules_by_tree(store)
    allowed: dict[str, set[str]] = {}
    unrestricted: set[str] = set()
    for tree_ids, runtime_by_source in zip(
        decision_program.tree_ids_by_agent,
        decision_program.runtime_module_by_source_module_by_agent,
        strict=True,
    ):
        for tree_id in tree_ids:
            place_kinds = place_kinds_by_tree.get(tree_id)
            for source_module in source_modules_by_tree.get(tree_id, set()):
                runtime_module = runtime_by_source.get(source_module)
                if runtime_module is None:
                    continue
                if place_kinds is None:
                    unrestricted.add(runtime_module)
                else:
                    allowed.setdefault(runtime_module, set()).update(place_kinds)
    return {
        module_id: sorted(place_kinds)
        for module_id, place_kinds in allowed.items()
        if module_id not in unrestricted
    }


def _runtime_module_availability_by_place(
    store: SimulationRegistryStore,
    mobility: ResolvedMobility | None,
    decision_program: RuntimeDecisionCompilation,
    runtime_places: list[_RuntimePlace],
) -> dict[str, list[str]]:
    if mobility is None:
        return {}
    controlled_tree_ids = {
        tree_id
        for profile in mobility.definition.place_profiles
        for tree_id in profile.available_decision_tree_ids
    }
    if not controlled_tree_ids:
        return {}
    source_modules_by_tree = _reachable_source_modules_by_tree(store)
    tree_ids_by_runtime_module: dict[str, set[str]] = {}
    for tree_ids, runtime_by_source in zip(
        decision_program.tree_ids_by_agent,
        decision_program.runtime_module_by_source_module_by_agent,
        strict=True,
    ):
        for tree_id in tree_ids:
            for source_module in source_modules_by_tree.get(tree_id, set()):
                runtime_module = runtime_by_source.get(source_module)
                if runtime_module is not None:
                    tree_ids_by_runtime_module.setdefault(runtime_module, set()).add(tree_id)
    restricted_modules = {
        module_id
        for module_id, tree_ids in tree_ids_by_runtime_module.items()
        if tree_ids and tree_ids <= controlled_tree_ids
    }
    all_modules = {str(module["id"]) for module in decision_program.modules}
    unrestricted_modules = all_modules - restricted_modules
    result: dict[str, list[str]] = {}
    for place in runtime_places:
        profile = mobility.profile(place.kind, place.id)
        available_tree_ids = (
            set(profile.available_decision_tree_ids) if profile is not None else set()
        )
        available_modules = unrestricted_modules | {
            module_id
            for module_id in restricted_modules
            if tree_ids_by_runtime_module[module_id].intersection(available_tree_ids)
        }
        result[place.id] = sorted(available_modules)
    return result


def _matches_scope(agent: AgentRecord, config: SimulationRunConfig) -> bool:
    scope = config.place_scope
    if scope.level == "global":
        return True
    expected = (scope.identifier or "").casefold()
    candidates = {agent.place.casefold()}
    if scope.level == "city":
        candidates.add(_text_trait(agent, "city").casefold())
        candidates.add(_text_trait(agent, "city_id").casefold())
    elif scope.level == "country":
        candidates.add(_text_trait(agent, "country").casefold())
        candidates.add(_text_trait(agent, "country_id").casefold())
    elif scope.level == "region":
        candidates.add(_text_trait(agent, "region").casefold())
    return expected in candidates


def _rank(seed: int, agent: AgentRecord) -> tuple[str, str]:
    digest = hashlib.sha256(f"{seed}:{agent.agent_id}".encode()).hexdigest()
    return digest, agent.agent_id


def _type_counts(population_size: int, mix: dict[str, float]) -> dict[str, int]:
    exact = {name: population_size * share for name, share in mix.items()}
    counts = {name: math.floor(value) for name, value in exact.items()}
    remaining = population_size - sum(counts.values())
    order = sorted(mix, key=lambda name: (-(exact[name] - counts[name]), name))
    for name in order[:remaining]:
        counts[name] += 1
    return counts


def _select_agents(candidates: list[AgentRecord], config: SimulationRunConfig) -> list[AgentRecord]:
    ordered = sorted(candidates, key=lambda agent: _rank(config.seed, agent))
    if not config.agent_type_mix:
        if len(ordered) < config.population_size:
            raise ValueError(
                f"Place scope contains {len(ordered)} initial agents; "
                f"{config.population_size} were requested"
            )
        return ordered[: config.population_size]
    selected: list[AgentRecord] = []
    remaining = {agent.agent_id: agent for agent in ordered}
    requested_counts = _type_counts(config.population_size, config.agent_type_mix)
    for agent_type, count in sorted(requested_counts.items()):
        matching = [
            agent
            for agent in ordered
            if agent.agent_id in remaining and agent_type == _primary_agent_type(agent)
        ]
        if len(matching) < count:
            raise ValueError(
                f"Agent type {agent_type} has {len(matching)} eligible initial agents; "
                f"{count} were requested"
            )
        for agent in matching[:count]:
            selected.append(agent)
            remaining.pop(agent.agent_id)
    return sorted(selected, key=lambda agent: _rank(config.seed, agent))


def _numeric_traits(agents: list[AgentRecord]) -> dict[str, list[float]]:
    names = set.intersection(
        *[
            {
                name
                for name, value in agent.traits.items()
                if isinstance(value, (int, float, bool))
                and not isinstance(value, complex)
                and math.isfinite(float(value))
            }
            for agent in agents
        ]
    )
    return {name: [float(agent.traits[name]) for agent in agents] for name in sorted(names)}


def _numeric_memory(agents: list[AgentRecord]) -> dict[str, list[float]]:
    names = set.intersection(*(set(agent.states) for agent in agents))
    memory: dict[str, list[float]] = {}
    for name in sorted(names):
        values: list[float] = []
        for agent in agents:
            try:
                value = float(agent.states[name])
            except (TypeError, ValueError):
                break
            if not math.isfinite(value):
                break
            values.append(value)
        if len(values) == len(agents):
            memory[name] = values
    return memory


def _interaction_tree_ids(
    store: SimulationRegistryStore,
    root_ids: set[str],
) -> tuple[dict[str, Any], set[str]]:
    trees_by_id = {tree.id: tree for tree in store.interaction_trees()}
    selected: set[str] = set()
    pending = list(sorted(root_ids, reverse=True))
    while pending:
        tree_id = pending.pop()
        if tree_id in selected:
            continue
        tree = trees_by_id.get(tree_id)
        if tree is None:
            raise ValueError(f"Confirmed interaction program references missing tree: {tree_id}")
        selected.add(tree_id)
        pending.extend(
            sorted(
                {
                    node.target_tree_id
                    for node in tree.nodes
                    if node.target_tree_id is not None and node.target_tree_id not in selected
                },
                reverse=True,
            )
        )
    return trees_by_id, selected


def _interaction_payload(
    store: SimulationRegistryStore,
    agents: list[AgentRecord],
    schedules: list[dict[str, Any]],
    runtime_places: list[_RuntimePlace],
    numeric_memory: dict[str, list[float]],
) -> dict[str, Any]:
    program = store.interaction_program()
    if program is None or program.status != "confirmed":
        return {"relationships": [], "trees": {}, "rules": []}
    root_tree_ids = {
        rule.interaction_tree_id for rule in program.rules if rule.interaction_tree_id is not None
    }
    trees_by_id, referenced_tree_ids = _interaction_tree_ids(store, root_tree_ids)
    reachable_actions = {str(schedule["action"]) for schedule in schedules}
    unreachable_rules = sorted(
        rule.id for rule in program.rules if rule.source_action not in reachable_actions
    )
    if unreachable_rules:
        raise ValueError(
            "Confirmed interaction rules have no reachable routine or event action: "
            + ", ".join(unreachable_rules)
        )
    runtime_place_kinds = {place.kind for place in runtime_places}
    unreachable_places = sorted(
        rule.id
        for rule in program.rules
        if rule.allowed_place_kinds
        and not set(rule.allowed_place_kinds).intersection(runtime_place_kinds)
    )
    if unreachable_places:
        raise ValueError(
            "Confirmed interaction rules have no reachable selected place kind: "
            + ", ".join(unreachable_places)
        )
    missing_effect_states = sorted(
        {
            f"{rule.id}:{effect.state}"
            for rule in program.rules
            for effect in rule.agent_effects
            if effect.state not in numeric_memory
        }
    )
    if missing_effect_states:
        raise ValueError(
            "Confirmed interaction effects reference unavailable numeric state: "
            + ", ".join(missing_effect_states)
        )
    missing_tree_effect_states = sorted(
        {
            f"{tree_id}:{effect.field}"
            for tree_id in referenced_tree_ids
            for transition in trees_by_id[tree_id].transitions
            for effect in transition.effects
            if isinstance(effect, InteractionTreeAgentStateEffect)
            and effect.field not in numeric_memory
        }
    )
    if missing_tree_effect_states:
        raise ValueError(
            "Confirmed interaction tree effects reference unavailable numeric state: "
            + ", ".join(missing_tree_effect_states)
        )
    missing_tree_condition_states = sorted(
        {
            f"{tree_id}:{condition.input.rsplit('.', 1)[-1]}"
            for tree_id in referenced_tree_ids
            for transition in trees_by_id[tree_id].transitions
            for condition in transition.conditions
            if condition.input.startswith(("actor.state.", "target.state."))
            and condition.input.rsplit(".", 1)[-1] not in numeric_memory
        }
    )
    if missing_tree_condition_states:
        raise ValueError(
            "Confirmed interaction tree conditions reference unavailable numeric state: "
            + ", ".join(missing_tree_condition_states)
        )
    unsupported_tree_routine_effects = sorted(
        {
            f"{tree_id}:{effect.routine_id}"
            for tree_id in referenced_tree_ids
            for transition in trees_by_id[tree_id].transitions
            for effect in transition.effects
            if isinstance(effect, InteractionTreeAgentRoutineEffect)
        }
    )
    if unsupported_tree_routine_effects:
        raise ValueError(
            "Confirmed interaction tree routine effects are unavailable in numeric runs: "
            + ", ".join(unsupported_tree_routine_effects)
        )
    evidence_by_kind = {item.kind: item for item in program.relationship_evidence}
    selected_relationship_kinds = {
        kind
        for rule in program.rules
        for kind in (
            rule.allowed_relationships
            if rule.allowed_relationships
            else tuple(rule.relationship_factors)
        )
    }
    agent_indices = {agent.agent_id: index for index, agent in enumerate(agents)}
    relationships: dict[tuple[int, int], dict[str, Any]] = {}
    blocked_relationships: list[str] = []
    for source_index, agent in enumerate(agents):
        for relationship in agent.relationships:
            target_index = agent_indices.get(relationship.target_id)
            if target_index is None:
                continue
            if relationship.kind not in selected_relationship_kinds:
                continue
            expected = evidence_by_kind.get(relationship.kind)
            if (
                relationship.trust is None
                or relationship.similarity is None
                or relationship.evidence_id is None
                or relationship.evidence_status not in EXECUTABLE_RELATIONSHIP_EVIDENCE
                or expected is None
                or relationship.evidence_id != expected.provenance.evidence_id
                or relationship.evidence_status != expected.provenance.status
                or not math.isclose(relationship.weight, expected.weight, abs_tol=1e-12)
                or not math.isclose(relationship.trust, expected.trust, abs_tol=1e-12)
                or not math.isclose(
                    relationship.similarity,
                    expected.similarity,
                    abs_tol=1e-12,
                )
            ):
                blocked_relationships.append(
                    f"{agent.agent_id}->{relationship.target_id} ({relationship.kind})"
                )
                continue
            if not (math.isfinite(relationship.trust) and math.isfinite(relationship.similarity)):
                raise ValueError(
                    f"Relationship evidence {relationship.evidence_id!r} must be finite"
                )
            key = (source_index, target_index)
            payload = {
                "source_index": source_index,
                "target_index": target_index,
                "kind": relationship.kind,
                "weight": relationship.weight,
                "trust": relationship.trust,
                "similarity": relationship.similarity,
            }
            existing = relationships.get(key)
            if existing is not None and existing != payload:
                raise ValueError(
                    "Selected population contains conflicting directed relationship evidence"
                )
            relationships[key] = payload
    if blocked_relationships:
        raise ValueError(
            "Confirmed interaction program selected relationships without matching "
            "executable evidence: " + ", ".join(sorted(blocked_relationships))
        )
    return {
        "relationships": [relationships[key] for key in sorted(relationships)],
        "trees": {
            tree_id: trees_by_id[tree_id].model_dump(mode="json")
            for tree_id in sorted(referenced_tree_ids)
        },
        "rules": [rule.rust_payload() for rule in program.rules],
    }


def _evidence_network(
    agent_count: int,
    initial_runtime_place_ids: list[str],
    relationships: list[dict[str, Any]],
) -> dict[str, Any] | None:
    rows: list[list[tuple[int, float]]] = [[] for _ in range(agent_count)]
    for relationship in relationships:
        source = int(relationship["source_index"])
        target = int(relationship["target_index"])
        if initial_runtime_place_ids[source] != initial_runtime_place_ids[target]:
            continue
        weight = (
            float(relationship["weight"])
            * abs(float(relationship["trust"]))
            * abs(float(relationship["similarity"]))
        )
        if abs(weight) <= 1e-15:
            continue
        rows[source].append((target, weight))
    if not any(rows):
        return None
    row_offsets = [0]
    column_indices: list[int] = []
    weights: list[float] = []
    for row in rows:
        for target, weight in sorted(row):
            column_indices.append(target)
            weights.append(weight)
        row_offsets.append(len(column_indices))
    return {
        "rows": agent_count,
        "cols": agent_count,
        "row_offsets": row_offsets,
        "column_indices": column_indices,
        "weights": weights,
    }


def _agent_type_tree_ids_by_agent(
    store: SimulationRegistryStore,
    agents: list[AgentRecord],
) -> list[set[str]]:
    resolved = {agent_type.id: agent_type for agent_type in store.resolved_agent_types().types}
    result: list[set[str]] = []
    for agent in agents:
        tree_ids = {
            member.member.id
            for agent_type_id in _agent_types(agent)
            if (agent_type := resolved.get(agent_type_id)) is not None
            for member in agent_type.decisions
        }
        result.append(tree_ids)
    return result


def _routine_module_ids_by_agent(
    resolved: ResolvedRoutineRegistry | None,
    agents: list[AgentRecord],
) -> list[set[str]]:
    if resolved is None:
        return [set() for _ in agents]
    modules_by_type = {
        agent_type.agent_type_id: {
            step.decision_tree_module_id
            for resolved_routine in agent_type.routines
            if resolved_routine.routine.evidence.status in {"measured", "user_defined"}
            for step in resolved_routine.routine.steps
            if step.decision_tree_module_id is not None
        }
        for agent_type in resolved.agent_types
    }
    return [
        {
            module_id
            for agent_type_id in _agent_types(agent)
            for module_id in modules_by_type.get(agent_type_id, set())
        }
        for agent in agents
    ]


def _location_id(level: str, *parts: str) -> str:
    normalized = "|".join(part.strip().casefold() for part in parts)
    digest = hashlib.sha256(f"{level}|{normalized}".encode()).hexdigest()[:16]
    return f"{level}:{digest}"


def _specific_place(agent: AgentRecord) -> str:
    return str(agent.states.get("location", "")).strip() or _text_trait(agent, "specific_place")


def _store_location(places: dict[str, LocationPlace], place: LocationPlace) -> LocationPlace:
    existing = places.get(place.id)
    if existing is not None and existing != place:
        raise ValueError(f"Location identity {place.id!r} has conflicting definitions")
    places[place.id] = place
    return place


def _geographic_chain(
    agent: AgentRecord,
    places: dict[str, LocationPlace],
    *,
    require_city: bool,
    district_name: str | None = None,
) -> list[str]:
    country = _text_trait(agent, "country") or agent.place
    country_id = _location_id("country", country)
    _store_location(
        places,
        LocationPlace(id=country_id, name=country, level="country"),
    )
    region = _text_trait(agent, "region")
    region_name = region or "Region unavailable"
    region_id = _location_id("region", country, region_name)
    _store_location(
        places,
        LocationPlace(
            id=region_id,
            name=region_name,
            level="region",
            parent_id=country_id,
            state={} if region else {"hierarchy_data_available": 0},
        ),
    )
    chain = [country_id, region_id]
    city = _text_trait(agent, "city")
    if city or require_city:
        city_name = city or "City unavailable"
        city_id = _location_id("city", country, region_name, city_name)
        _store_location(
            places,
            LocationPlace(
                id=city_id,
                name=city_name,
                level="city",
                parent_id=region_id,
                state={} if city else {"hierarchy_data_available": 0},
            ),
        )
        chain.append(city_id)
    if district_name is not None:
        district_id = _location_id("district", country, region_name, chain[-1], district_name)
        _store_location(
            places,
            LocationPlace(
                id=district_id,
                name=district_name,
                level="district",
                parent_id=chain[-1],
                state=(
                    {"hierarchy_data_available": 0}
                    if district_name == "District unavailable"
                    else {}
                ),
            ),
        )
        chain.append(district_id)
    return chain


def _register_runtime_place(
    runtime_places: dict[str, _RuntimePlace], place: _RuntimePlace
) -> _RuntimePlace:
    existing = runtime_places.get(place.id)
    if existing is not None and existing != place:
        raise ValueError(f"Runtime place identity {place.id!r} maps inconsistently")
    runtime_places[place.id] = place
    return place


def _initial_runtime_place(
    agent: AgentRecord,
    places: dict[str, LocationPlace],
    runtime_places: dict[str, _RuntimePlace],
) -> tuple[_RuntimePlace, bool]:
    specific_place = _specific_place(agent)
    if not specific_place:
        chain = _geographic_chain(agent, places, require_city=False)
        location_id = chain[-1]
        location = places[location_id]
        runtime = _RuntimePlace(
            id=_runtime_identifier("place", f"initial:{location_id}"),
            kind=location.level,
            location_id=location_id,
        )
        return _register_runtime_place(runtime_places, runtime), False
    neighbourhood = _text_trait(agent, "neighbourhood")
    district_name = neighbourhood or "District unavailable"
    chain = _geographic_chain(
        agent,
        places,
        require_city=True,
        district_name=district_name,
    )
    country = _text_trait(agent, "country") or agent.place
    region = _text_trait(agent, "region") or "Region unavailable"
    city = _text_trait(agent, "city") or "City unavailable"
    building_id = _location_id("building", country, region, city, district_name, specific_place)
    _store_location(
        places,
        LocationPlace(
            id=building_id,
            name=("Household home" if specific_place.startswith("home:") else specific_place),
            level="building",
            parent_id=chain[-1],
        ),
    )
    runtime = _RuntimePlace(
        id=_runtime_identifier("place", f"initial:{building_id}"),
        kind="home" if specific_place.startswith("home:") else "building",
        location_id=building_id,
    )
    return _register_runtime_place(runtime_places, runtime), True


def _routine_runtime_place(
    agent: AgentRecord,
    place_id: str,
    initial_place: _RuntimePlace,
    has_specific_place: bool,
    places: dict[str, LocationPlace],
    runtime_places: dict[str, _RuntimePlace],
) -> _RuntimePlace | None:
    normalized = place_id.strip().casefold()
    if normalized in CURRENT_PLACE_IDS:
        return None
    if normalized == "home":
        return initial_place if has_specific_place else None
    district_name = "District unavailable"
    chain = _geographic_chain(
        agent,
        places,
        require_city=True,
        district_name=district_name,
    )
    country = _text_trait(agent, "country") or agent.place
    region = _text_trait(agent, "region") or "Region unavailable"
    city = _text_trait(agent, "city") or "City unavailable"
    building_id = _location_id("building", country, region, city, district_name, normalized)
    _store_location(
        places,
        LocationPlace(
            id=building_id,
            name=place_id.replace("_", " ").strip().title(),
            level="building",
            parent_id=chain[-1],
        ),
    )
    runtime = _RuntimePlace(
        id=_runtime_identifier("place", f"routine:{country}:{region}:{city}:{normalized}"),
        kind=normalized,
        location_id=building_id,
    )
    return _register_runtime_place(runtime_places, runtime)


def _transit_runtime_place(
    agent: AgentRecord,
    transit_kind: str,
    places: dict[str, LocationPlace],
    runtime_places: dict[str, _RuntimePlace],
) -> _RuntimePlace:
    district_name = "District unavailable"
    chain = _geographic_chain(
        agent,
        places,
        require_city=True,
        district_name=district_name,
    )
    country = _text_trait(agent, "country") or agent.place
    region = _text_trait(agent, "region") or "Region unavailable"
    city = _text_trait(agent, "city") or "City unavailable"
    location_id = _location_id("building", country, region, city, district_name, transit_kind)
    _store_location(
        places,
        LocationPlace(
            id=location_id,
            name=transit_kind.replace("_", " ").title(),
            level="building",
            parent_id=chain[-1],
        ),
    )
    runtime = _RuntimePlace(
        id=_runtime_identifier("place", f"transit:{country}:{region}:{city}:{transit_kind}"),
        kind=transit_kind,
        location_id=location_id,
    )
    return _register_runtime_place(runtime_places, runtime)


def _runtime_locations(
    agents: list[AgentRecord],
    resolved: ResolvedRoutineRegistry | None,
    module_ids_by_agent_type: Mapping[str, tuple[str, ...]],
    mobility: ResolvedMobility | None,
) -> tuple[
    list[LocationPlace],
    list[str],
    list[_RuntimePlace],
    list[str],
    dict[tuple[int, str], str | None],
    dict[tuple[int, str], str],
]:
    places: dict[str, LocationPlace] = {}
    runtime_places: dict[str, _RuntimePlace] = {}
    initial_places: list[_RuntimePlace] = []
    has_specific_places: list[bool] = []
    for agent in agents:
        initial_place, has_specific_place = _initial_runtime_place(agent, places, runtime_places)
        initial_places.append(initial_place)
        has_specific_places.append(has_specific_place)
    routine_destination_ids: dict[tuple[int, str], str | None] = {}
    transit_place_ids: dict[tuple[int, str], str] = {}
    if mobility is not None:
        transit_kinds = sorted({route.transit_place_kind for route in mobility.definition.routes})
        for index, agent in enumerate(agents):
            for transit_kind in transit_kinds:
                transit = _transit_runtime_place(
                    agent,
                    transit_kind,
                    places,
                    runtime_places,
                )
                transit_place_ids[(index, transit_kind)] = transit.id
    if resolved is not None:
        for agent_type in resolved.agent_types:
            if agent_type.agent_type_id not in module_ids_by_agent_type:
                continue
            agent_indices = [
                index
                for index, agent in enumerate(agents)
                if agent_type.agent_type_id in _agent_types(agent)
            ]
            for resolved_routine in agent_type.routines:
                routine = resolved_routine.routine
                if routine.evidence.status not in {"measured", "user_defined"}:
                    continue
                for step in routine.steps:
                    for configured_place_id in step.schedule.place_ids:
                        normalized = configured_place_id.strip().casefold()
                        for index in agent_indices:
                            destination = _routine_runtime_place(
                                agents[index],
                                configured_place_id,
                                initial_places[index],
                                has_specific_places[index],
                                places,
                                runtime_places,
                            )
                            routine_destination_ids[(index, normalized)] = (
                                destination.id if destination is not None else None
                            )
    level_order = {
        "country": 0,
        "region": 1,
        "state": 1,
        "city": 2,
        "district": 3,
        "building": 4,
        "room": 5,
    }
    ordered_places = sorted(places.values(), key=lambda place: (level_order[place.level], place.id))
    ordered_runtime_places = sorted(runtime_places.values(), key=lambda place: place.id)
    return (
        ordered_places,
        [place.location_id for place in initial_places],
        ordered_runtime_places,
        [place.id for place in initial_places],
        routine_destination_ids,
        transit_place_ids,
    )


def _profiled_location_places(
    places: list[LocationPlace],
    runtime_places: list[_RuntimePlace],
    mobility: ResolvedMobility | None,
    store: SimulationRegistryStore,
) -> list[LocationPlace]:
    if mobility is None:
        return places
    runtime_by_location_id = {place.location_id: place for place in runtime_places}
    ready_trees = {tree.id: tree for tree in store.decision_trees().trees if tree.status == "ready"}
    required_kinds: dict[str, set[str]] = {}
    for profile in mobility.definition.place_profiles:
        for tree_id in profile.available_decision_tree_ids:
            required_kinds.setdefault(tree_id, set()).add(profile.place_kind)
    result: list[LocationPlace] = []
    for place in places:
        runtime = runtime_by_location_id.get(place.id)
        profile = mobility.profile(runtime.kind, runtime.id) if runtime is not None else None
        if runtime is None or profile is None:
            result.append(place)
            continue
        decisions = []
        for tree_id, place_kinds in sorted(required_kinds.items()):
            tree = ready_trees.get(tree_id)
            if tree is None:
                continue
            available = tree_id in profile.available_decision_tree_ids
            decisions.append(
                LocationDecisionTreeAvailability(
                    tree_id=tree.id,
                    tree_name=tree.name,
                    available=available,
                    required_place_kinds=tuple(sorted(place_kinds)),
                    reason=(
                        None if available else f"{tree.name} unavailable — agent is at {place.name}"
                    ),
                )
            )
        evidence = profile.evidence
        result.append(
            place.model_copy(
                update={
                    "accepts_arrivals": profile.accepts_arrivals,
                    "allows_in_person": profile.allows_in_person,
                    "capacity": profile.capacity,
                    "state": dict(profile.state),
                    "evidence": LocationEvidence(
                        source_title=str(evidence.source_title),
                        source_version=str(evidence.source_version),
                        source_date=str(evidence.source_date),
                        licence=str(evidence.licence),
                        evidence_id=str(evidence.evidence_id),
                        status=evidence.status,
                        uncertainty=float(evidence.uncertainty),
                    ),
                    "decision_trees": tuple(decisions),
                }
            )
        )
    return result


def _initial_agent_profiles(
    store: SimulationRegistryStore,
    agents: list[AgentRecord],
    resolved_routines: ResolvedRoutineRegistry | None,
    tree_ids_by_agent: list[tuple[str, ...]],
) -> list[dict[str, Any]]:
    materialization = store.initial_population()
    provenance = materialization.provenance if materialization is not None else {}
    routines_by_type = (
        {
            agent_type.agent_type_id: {routine.routine.id for routine in agent_type.routines}
            for agent_type in resolved_routines.agent_types
        }
        if resolved_routines is not None
        else {}
    )
    profiles: list[dict[str, Any]] = []
    for agent, tree_ids in zip(agents, tree_ids_by_agent, strict=True):
        agent_types = sorted(_agent_types(agent))
        routine_ids = sorted(
            {
                routine_id
                for agent_type_id in agent_types
                for routine_id in routines_by_type.get(agent_type_id, set())
            }
        )
        evidence = provenance.get(agent.agent_id)
        profiles.append(
            {
                "agent_id": agent.agent_id,
                "agent_types": agent_types,
                "role": agent.role,
                "geography": {
                    "place_id": agent.place,
                    "country_id": _text_trait(agent, "country_id"),
                    "country": _text_trait(agent, "country"),
                    "region": _text_trait(agent, "region"),
                    "city_id": _text_trait(agent, "city_id"),
                    "city": _text_trait(agent, "city"),
                    "neighbourhood": _text_trait(agent, "neighbourhood"),
                    "specific_place": _specific_place(agent),
                    "latitude": agent.latitude,
                    "longitude": agent.longitude,
                },
                "household": {
                    "id": _text_trait(agent, "household_id"),
                    "role": _text_trait(agent, "household_role"),
                    "family_status": _text_trait(agent, "family_status"),
                    "family_relationships": agent.traits.get("family_relationships", {}),
                },
                "traits": agent.traits,
                "states": agent.states,
                "relationships": [
                    relationship.model_dump(mode="json") for relationship in agent.relationships
                ],
                "routines": routine_ids,
                "decision_trees": list(tree_ids),
                "provenance": evidence.model_dump(mode="json") if evidence else {},
            }
        )
    return profiles


def prepare_registry_run(
    store: SimulationRegistryStore,
    config: SimulationRunConfig,
    evidence_receipts: AtlasEvidenceReceiptRegistry | None = None,
) -> PreparedRustRun:
    materialization = store.initial_population()
    if materialization is None:
        raise ValueError(
            "No initial population is configured. Materialize validated initial agents first."
        )
    candidates = [
        agent for agent in materialization.population.agents if _matches_scope(agent, config)
    ]
    agents = _select_agents(candidates, config)
    global_demo_summary = (
        global_population_evidence_summary(
            materialization.population.model_copy(update={"agents": agents}),
            store.interaction_program(),
        )
        if config.place_scope.level == "global"
        and is_global_demo_population(materialization.population)
        else None
    )
    resolved_routines = _resolved_routines(store)
    mobility = _resolved_mobility(store)
    numeric_memory = _numeric_memory(agents)
    state_program = compile_runtime_state(store, agents, set(numeric_memory))
    aggregate_payload = store.payload_snapshot().get("aggregate_statistics")
    aggregate_statistics = (
        AggregateStatisticsProgram.model_validate(aggregate_payload)
        if aggregate_payload is not None
        else None
    )
    if aggregate_statistics is not None:
        selected_agent_ids = {agent.agent_id for agent in agents}
        selected_timeline_subjects = tuple(
            subject
            for subject in aggregate_statistics.timeline_subjects
            if subject.agent_id in selected_agent_ids
        )
        if not selected_timeline_subjects and agents:
            selected_timeline_subjects = (
                TimelineSubject(
                    agent_id=agents[0].agent_id,
                    role="spotlight",
                    start_tick=1,
                ),
            )
        aggregate_statistics = aggregate_statistics.model_copy(
            update={"timeline_subjects": selected_timeline_subjects}
        )
        time_execution = state_program.state_dynamics.get("time_execution")
        if isinstance(time_execution, dict):
            timeline_agent_ids = {
                subject.agent_id for subject in selected_timeline_subjects
            }
            time_execution["receipt_agent_indices"] = [
                index
                for index, agent in enumerate(agents)
                if agent.agent_id in timeline_agent_ids
            ]
    coefficient_registry = load_coefficient_registry(store)
    default_dsl_identity = load_default_dsl_identity(store)
    if coefficient_registry is not None:
        validation = validate_coefficient_registry(
            coefficient_registry,
            default_dsl_identity,
            evidence_receipts,
        )
        if not validation.executable:
            detail = "; ".join(
                f"{issue.action_id}/{issue.coefficient_set_id}: {issue.message}"
                for issue in validation.issues
            )
            raise ValueError(f"Run blocked by coefficient evidence: {detail}")
    decision_program = compile_runtime_decisions(
        store.decision_trees(),
        store.decision_evidence(),
        agents,
        config.start_date,
        requested_tree_ids_by_agent=_agent_type_tree_ids_by_agent(store, agents),
        requested_module_ids_by_agent=_routine_module_ids_by_agent(resolved_routines, agents),
        runtime_context_keys=set(numeric_memory),
        coefficient_registry=coefficient_registry,
        default_dsl_identity=default_dsl_identity,
    )
    coefficient_summary, evidence_warnings = evidence_summary(
        decision_program.coefficient_receipts + state_program.coefficient_receipts
    )
    module_ids_by_agent_type: dict[str, tuple[str, ...]] = {}
    for agent_type in sorted(
        {agent_type for agent in agents for agent_type in _agent_types(agent)}
    ):
        module_ids_by_agent_type[agent_type] = tuple(
            sorted(
                {
                    module_id
                    for agent, module_ids in zip(
                        agents, decision_program.module_ids_by_agent, strict=True
                    )
                    if agent_type in _agent_types(agent)
                    for module_id in module_ids
                }
            )
        )
    (
        location_places,
        initial_location_ids,
        runtime_places,
        initial_runtime_place_ids,
        routine_destination_ids,
        transit_place_ids,
    ) = _runtime_locations(
        agents,
        resolved_routines,
        module_ids_by_agent_type,
        mobility,
    )
    runtime_place_indices = {place.id: index for index, place in enumerate(runtime_places)}
    location_places = _profiled_location_places(
        location_places,
        runtime_places,
        mobility,
        store,
    )
    schedules = _routine_schedules(
        resolved_routines,
        {
            key: str(action["id"])
            for action in store.payload_snapshot().get("default_actions", [])
            if isinstance(action, dict) and action.get("id")
            for key in (
                str(action["id"]).strip().casefold().replace("_", " "),
                str(action.get("name", "")).strip().casefold().replace("_", " "),
            )
            if key
        },
        module_ids_by_agent_type,
        agents,
        runtime_place_indices,
        {place.id: place for place in runtime_places},
        initial_runtime_place_ids,
        routine_destination_ids,
        transit_place_ids,
        decision_program.runtime_module_by_source_module_by_agent,
        mobility,
        config.tick_interval_hours,
    )
    _timed_action_locations(
        store,
        state_program,
        agents,
        runtime_place_indices,
        initial_runtime_place_ids,
        routine_destination_ids,
    )
    _add_scheduled_timed_actions(state_program, schedules, len(agents))
    program_version = _program_version(store, module_ids_by_agent_type)
    interactions = _interaction_payload(
        store,
        agents,
        schedules,
        runtime_places,
        numeric_memory,
    )
    runtime_module_place_kinds = _runtime_module_place_kinds(
        store,
        mobility,
        decision_program,
    )
    runtime_module_availability = _runtime_module_availability_by_place(
        store,
        mobility,
        decision_program,
        runtime_places,
    )
    runtime_place_payloads = []
    for place in runtime_places:
        profile = mobility.profile(place.kind, place.id) if mobility is not None else None
        payload = {
            "id": place.id,
            "kind": place.kind,
            "accepts_arrivals": profile.accepts_arrivals if profile is not None else True,
            "allows_in_person": (
                profile.allows_in_person
                if profile is not None
                else place.kind not in {"country", "region", "state", "city", "district"}
            ),
            "capacity": profile.capacity if profile is not None else None,
            "state": dict(profile.state) if profile is not None else {},
        }
        if place.id in runtime_module_availability:
            payload["available_decision_modules"] = runtime_module_availability[place.id]
        runtime_place_payloads.append(payload)
    request = {
        "seed": config.seed,
        "ticks": config.total_ticks,
        "tick_hours": config.tick_interval_hours,
        "start_hour": 0,
        "start_weekday": config.start_date.weekday(),
        "places": runtime_place_payloads,
        "agents": {
            "agent_ids": [agent.agent_id for agent in agents],
            "module": decision_program.agent_modules,
            "state": decision_program.agent_states,
            "place": [runtime_place_indices[place_id] for place_id in initial_runtime_place_ids],
            "traits": _numeric_traits(agents),
            "trait_dictionaries": {},
            "memory": numeric_memory,
        },
        "modules": [
            {
                **module,
                "available_place_kinds": runtime_module_place_kinds.get(str(module["id"]), []),
            }
            for module in decision_program.modules
        ],
        "routes": decision_program.routes,
        "network": _evidence_network(
            len(agents),
            initial_runtime_place_ids,
            interactions["relationships"],
        ),
        "schedules": schedules,
        "meaningful_actions": state_program.meaningful_actions,
        "interactions": interactions,
        "synchronization": {},
        "state_dynamics": state_program.state_dynamics,
    }
    return PreparedRustRun(
        rust_request=request,
        agent_ids=[agent.agent_id for agent in agents],
        data_version=(f"{materialization.population.version}:{materialization.input_hash[:16]}"),
        program_version=program_version,
        default_dsl_version=(
            default_dsl_identity.version if default_dsl_identity is not None else None
        ),
        default_dsl_hash=(
            default_dsl_identity.hash if default_dsl_identity is not None else None
        ),
        location_places=location_places,
        initial_location_ids=initial_location_ids,
        runtime_place_location_ids=[place.location_id for place in runtime_places],
        initial_agent_profiles=_initial_agent_profiles(
            store,
            agents,
            resolved_routines,
            decision_program.tree_ids_by_agent,
        ),
        coefficient_evidence=coefficient_summary,
        evidence_warnings=evidence_warnings,
        global_demo_summary=global_demo_summary,
        aggregate_statistics=aggregate_statistics,
    )
