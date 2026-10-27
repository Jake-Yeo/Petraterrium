from collections import defaultdict

from pydantic import ValidationError

from .models import DSLConfig, DSLValidationResult, ImpliedAggregate, ValidationIssue

ANNUAL_PERIODS = {"event": 1, "hour": 8760, "day": 365, "week": 52, "year": 1}


def issue(path: str, message: str) -> ValidationIssue:
    return ValidationIssue(path=path, message=message)


def parsed_config(value) -> tuple[DSLConfig | None, list[ValidationIssue]]:
    if isinstance(value, DSLConfig):
        return value, []
    try:
        return DSLConfig.model_validate(value), []
    except ValidationError as error:
        return None, [
            issue(".".join(str(part) for part in item["loc"]), item["msg"])
            for item in error.errors()
        ]


def cycle_members(graph: dict[str, set[str]]) -> set[str]:
    visiting = set()
    visited = set()
    cycles = set()

    def visit(node: str) -> None:
        if node in visiting:
            cycles.add(node)
            return
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.get(node, set()):
            visit(dependency)
            if dependency in cycles:
                cycles.add(node)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
    return cycles


def validate_dsl(value) -> DSLValidationResult:
    config, errors = parsed_config(value)
    if config is None:
        return DSLValidationResult(
            valid=False,
            errors=errors,
            warnings=[],
            implied_aggregates=[],
        )
    state_by_id = {state.id: state for state in config.states}
    parameter_ids = {parameter.id for parameter in config.parameters}
    action_by_id = {action.id: action for action in config.actions}
    role_ids = {role.id for role in config.roles}
    network_ids = {network.id for network in config.networks}
    event_ids = {event.id for event in config.events}
    system_ids = {system.id for system in config.systems} | {"media", "leaders", "places"}
    seen_ids = defaultdict(list)
    for collection_name, collection in (
        ("states", config.states),
        ("attributes", config.attributes),
        ("parameters", config.parameters),
        ("systems", config.systems),
        ("scenarios", config.scenarios),
        ("rules", config.rules),
        ("actions", config.actions),
        ("chains", config.chains),
        ("roles", config.roles),
        ("defaults", config.default_states),
        ("bundles", config.behaviour_bundles),
    ):
        for item in collection:
            seen_ids[(collection_name, item.id)].append(item)
    for (collection_name, identity), items in seen_ids.items():
        if len(items) > 1:
            errors.append(issue(collection_name, f"Duplicate {collection_name} id {identity}"))
    for attribute_index, attribute in enumerate(config.attributes):
        if attribute.provenance.status != "label_only" and attribute.distribution is None:
            errors.append(
                issue(
                    f"attributes.{attribute_index}.distribution",
                    f"Attribute {attribute.id} needs a measured distribution or label-only status",
                )
            )
    for system_index, system in enumerate(config.systems):
        state = state_by_id.get(system.state)
        if state is None:
            errors.append(
                issue(
                    f"systems.{system_index}.state",
                    f"System {system.id} references missing state {system.state}",
                )
            )
            continue
        for transition_index, transition in enumerate(system.transitions):
            for key, state_value in (
                ("from_state", transition.from_state),
                ("to_state", transition.to_state),
            ):
                if state_value not in state.values:
                    errors.append(
                        issue(
                            f"systems.{system_index}.transitions.{transition_index}.{key}",
                            f"Transition {transition.id} references missing state value "
                            f"{state_value}",
                        )
                    )
            probability = transition.probability
            if probability.parameter and probability.parameter not in parameter_ids:
                errors.append(
                    issue(
                        f"systems.{system_index}.transitions.{transition_index}.probability.parameter",
                        f"Transition {transition.id} references missing parameter "
                        f"{probability.parameter}",
                    )
                )
            if probability.mixing_parameter and probability.mixing_parameter not in parameter_ids:
                errors.append(
                    issue(
                        f"systems.{system_index}.transitions.{transition_index}.probability.mixing_parameter",
                        f"Transition {transition.id} references missing mixing parameter "
                        f"{probability.mixing_parameter}",
                    )
                )
            if probability.source_state and probability.source_state not in state.values:
                errors.append(
                    issue(
                        f"systems.{system_index}.transitions.{transition_index}.probability.source_state",
                        f"Transition {transition.id} references missing state value "
                        f"{probability.source_state}",
                    )
                )
    for action_index, action in enumerate(config.actions):
        if action.requires_role and action.requires_role not in role_ids:
            errors.append(
                issue(
                    f"actions.{action_index}.requires_role",
                    f"Action {action.id} references missing role {action.requires_role}",
                )
            )
        if action.target_requires_role and action.target_requires_role not in role_ids:
            errors.append(
                issue(
                    f"actions.{action_index}.target_requires_role",
                    f"Action {action.id} references missing target role "
                    f"{action.target_requires_role}",
                )
            )
        if action.target_requires_role and not action.requires_role:
            errors.append(
                issue(
                    f"actions.{action_index}.requires_role",
                    f"Role-gated action {action.id} has a target role but no actor role",
                )
            )
    for role_index, role in enumerate(config.roles):
        for action_id in role.actions:
            if action_id not in action_by_id:
                errors.append(
                    issue(
                        f"roles.{role_index}.actions",
                        f"Role {role.id} references missing action {action_id}",
                    )
                )
    for scenario_index, scenario in enumerate(config.scenarios):
        for system_id in scenario.systems:
            if system_id not in system_ids:
                errors.append(
                    issue(
                        f"scenarios.{scenario_index}.systems",
                        f"Scenario {scenario.id} references missing system {system_id}",
                    )
                )
        for action_id in scenario.actions:
            if action_id not in action_by_id:
                errors.append(
                    issue(
                        f"scenarios.{scenario_index}.actions",
                        f"Scenario {scenario.id} references missing action {action_id}",
                    )
                )
        for event_id in scenario.events:
            if event_id not in event_ids:
                errors.append(
                    issue(
                        f"scenarios.{scenario_index}.events",
                        f"Scenario {scenario.id} references missing event {event_id}",
                    )
                )
    effect_targets = parameter_ids | set(state_by_id) | set(config.place_states)
    for rule_index, rule in enumerate(config.rules):
        if rule.traversal and rule.traversal.network not in network_ids:
            errors.append(
                issue(
                    f"rules.{rule_index}.traversal.network",
                    f"Rule {rule.id} references missing network {rule.traversal.network}",
                )
            )
        if rule.action and rule.action not in action_by_id:
            errors.append(
                issue(
                    f"rules.{rule_index}.action",
                    f"Rule {rule.id} references missing action {rule.action}",
                )
            )
        for target in rule.effects:
            if target not in effect_targets:
                errors.append(
                    issue(
                        f"rules.{rule_index}.effects",
                        f"Rule {rule.id} references missing effect target {target}",
                    )
                )
    for chain_index, chain in enumerate(config.chains):
        if chain.trigger not in action_by_id:
            errors.append(
                issue(
                    f"chains.{chain_index}.trigger",
                    f"Chain {chain.id} references missing trigger {chain.trigger}",
                )
            )
        for branch in chain.branches:
            if branch.action not in action_by_id:
                errors.append(
                    issue(
                        f"chains.{chain_index}.branches",
                        f"Chain {chain.id} references missing action {branch.action}",
                    )
                )
        if chain.max_length is None and chain.continue_probability >= 1:
            errors.append(
                issue(
                    f"chains.{chain_index}",
                    f"Chain {chain.id} has no termination bound",
                )
            )
    default_ids = {default.id for default in config.default_states}
    for default_index, default in enumerate(config.default_states):
        for dependency in default.depends_on:
            if dependency not in default_ids:
                errors.append(
                    issue(
                        f"default_states.{default_index}.depends_on",
                        f"Default {default.id} references missing dependency {dependency}",
                    )
                )
    default_cycles = cycle_members(
        {default.id: set(default.depends_on) for default in config.default_states}
    )
    if default_cycles:
        errors.append(
            issue(
                "default_states",
                f"Default-state dependency cycle includes {sorted(default_cycles)}",
            )
        )
    bundle_ids = {bundle.id for bundle in config.behaviour_bundles}
    for bundle_index, bundle in enumerate(config.behaviour_bundles):
        for parent in bundle.inherits:
            if parent not in bundle_ids:
                errors.append(
                    issue(
                        f"behaviour_bundles.{bundle_index}.inherits",
                        f"Bundle {bundle.id} references missing parent {parent}",
                    )
                )
    bundle_cycles = cycle_members(
        {bundle.id: set(bundle.inherits) for bundle in config.behaviour_bundles}
    )
    if bundle_cycles:
        errors.append(
            issue(
                "behaviour_bundles",
                f"Behaviour inheritance cycle includes {sorted(bundle_cycles)}",
            )
        )
    population_places = set(config.population.places)
    unknown_populations = set(config.population.place_populations) - population_places
    if unknown_populations:
        errors.append(
            issue(
                "population.place_populations",
                f"Population totals reference missing places {sorted(unknown_populations)}",
            )
        )
    unknown_coordinates = set(config.population.place_coordinates) - population_places
    if unknown_coordinates:
        errors.append(
            issue(
                "population.place_coordinates",
                f"Coordinates reference missing places {sorted(unknown_coordinates)}",
            )
        )
    for place, (latitude, longitude) in config.population.place_coordinates.items():
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            errors.append(
                issue(
                    "population.place_coordinates",
                    f"Coordinates for {place} are outside latitude or longitude bounds",
                )
            )
    state_values = {state.id: set(state.values) for state in config.states}
    for place, overrides in config.population.initial_state_overrides.items():
        if place not in population_places:
            errors.append(
                issue(
                    "population.initial_state_overrides",
                    f"Initial states reference missing place {place}",
                )
            )
        for state_id, values in overrides.items():
            if state_id not in state_values:
                errors.append(
                    issue(
                        "population.initial_state_overrides",
                        f"Initial states reference missing state {state_id}",
                    )
                )
                continue
            unknown_values = set(values) - state_values[state_id]
            if unknown_values:
                errors.append(
                    issue(
                        "population.initial_state_overrides",
                        f"Initial state {state_id} references missing values "
                        f"{sorted(unknown_values)}",
                    )
                )
            expected = config.population.place_populations.get(place)
            if expected is not None and sum(values.values()) != expected:
                errors.append(
                    issue(
                        "population.initial_state_overrides",
                        f"Initial state {state_id} for {place} sums to "
                        f"{sum(values.values())}, expected {expected}",
                    )
                )
    for coupling_index, coupling in enumerate(config.couplings):
        if coupling.source_system not in system_ids:
            errors.append(
                issue(
                    f"couplings.{coupling_index}.source_system",
                    f"Coupling {coupling.id} references missing system {coupling.source_system}",
                )
            )
        if coupling.target_system not in system_ids:
            errors.append(
                issue(
                    f"couplings.{coupling_index}.target_system",
                    f"Coupling {coupling.id} references missing system {coupling.target_system}",
                )
            )
        if coupling.target_parameter not in parameter_ids:
            errors.append(
                issue(
                    f"couplings.{coupling_index}.target_parameter",
                    f"Coupling {coupling.id} references missing parameter "
                    f"{coupling.target_parameter}",
                )
            )
    implied = []
    for benchmark in config.benchmarks:
        action = action_by_id.get(benchmark.action_id)
        if action is None:
            errors.append(
                issue("benchmarks", f"Benchmark references missing action {benchmark.action_id}")
            )
            continue
        periods = ANNUAL_PERIODS[action.probability.time_unit]
        implied_count = action.probability.base * periods * benchmark.population
        ratio = implied_count / benchmark.observed_annual_count
        implied.append(
            ImpliedAggregate(
                action_id=action.id,
                implied_annual_count=implied_count,
                observed_annual_count=benchmark.observed_annual_count,
                ratio=ratio,
            )
        )
        if ratio > benchmark.tolerance_factor or ratio < 1 / benchmark.tolerance_factor:
            errors.append(
                issue(
                    "benchmarks",
                    f"Action {action.id} implied aggregate differs from observed by {ratio:.2f}x",
                )
            )
    warnings = []
    for parameter in config.parameters:
        if parameter.value is None or parameter.provenance.status in {
            "missing",
            "unknown",
            "label_only",
        }:
            warnings.append(
                issue(
                    f"parameters.{parameter.id}",
                    f"Parameter {parameter.id} is {parameter.provenance.status}",
                )
            )
    return DSLValidationResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        implied_aggregates=implied,
    )
