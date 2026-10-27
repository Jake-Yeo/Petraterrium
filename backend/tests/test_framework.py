from copy import deepcopy
from datetime import date

import numpy as np
import yaml

from petraterrium.actions import (
    AgentActionContext,
    chain_step,
    chain_step_with_log,
    chain_transition_matrix,
    change_role,
    check_eligibility,
    choose_bundle,
    eligible_actions,
    resolve_conflict,
)
from petraterrium.atlas.database import AtlasStore
from petraterrium.backtesting import backtest
from petraterrium.dsl import (
    ActionDefinition,
    AggregateBenchmark,
    BehaviourBundle,
    ChainBranch,
    ChainDefinition,
    CouplingDefinition,
    DefaultDefinition,
    Distribution,
    DSLConfig,
    EventDefinition,
    Evidence,
    LeaderActionDefinition,
    MediaRule,
    NetworkDefinition,
    OutputSpec,
    ParameterDefinition,
    PopulationReference,
    ProbabilitySpec,
    RoleDefinition,
    StateDefinition,
    SystemDefinition,
    TickConfig,
    TransitionDefinition,
    flatten_behaviour_bundles,
    load_dsl,
    render_plain_language,
    render_sliders,
    validate_dsl,
)
from petraterrium.ensembles import ensemble_replay
from petraterrium.events import causal_deep_dive, detect_events, generate_story
from petraterrium.framework_data import MappingRegistry, compositional_estimate
from petraterrium.leaders import EvidenceTable, anchor_run
from petraterrium.media import MediaObject, media_probabilities, media_response, rank_feed
from petraterrium.network import influence_update
from petraterrium.population import generate_population


def evidence(source="FAKE framework fixture", status="present", uncertainty=0.05):
    return Evidence(
        source=source,
        version="test-v1",
        status=status,
        uncertainty=uncertainty,
    )


def framework_dsl() -> DSLConfig:
    return DSLConfig(
        id="framework-smoke",
        version="1",
        states=[
            StateDefinition(
                id="awareness",
                values=["unaware", "aware"],
                initial=Distribution(
                    values={"unaware": 0.98, "aware": 0.02}, provenance=evidence()
                ),
            )
        ],
        place_states=["pressure"],
        parameters=[
            ParameterDefinition(
                id="spread_rate",
                value=0.2,
                unit="per_day",
                provenance=evidence(),
            )
        ],
        systems=[
            SystemDefinition(
                id="awareness-system",
                state="awareness",
                transitions=[
                    TransitionDefinition(
                        id="notice",
                        from_state="unaware",
                        to_state="aware",
                        probability=ProbabilitySpec(
                            base=0.2,
                            mode="hazard",
                            time_unit="day",
                            parameter="spread_rate",
                            source_state="aware",
                        ),
                    )
                ],
            )
        ],
        actions=[
            ActionDefinition(
                id="sleep",
                probability=ProbabilitySpec(base=1, time_unit="hour"),
                duration_minutes=60,
                priority=0,
                meaningful=False,
                loser_outcome="continues",
            ),
            ActionDefinition(
                id="work",
                probability=ProbabilitySpec(base=1, time_unit="hour"),
                duration_minutes=60,
                priority=8,
                interruptible=False,
                loser_outcome="deferred",
            ),
            ActionDefinition(
                id="talk",
                probability=ProbabilitySpec(base=0.4, time_unit="hour"),
                duration_minutes=30,
                priority=3,
                priority_modifiers={"family": 2, "boss": 5, "stranger": -1, "enemy": -2},
                compatible_with=["commute"],
                loser_outcome="relationship_cost",
            ),
            ActionDefinition(
                id="negotiate_merger",
                probability=ProbabilitySpec(base=0.1, time_unit="week"),
                duration_minutes=45,
                priority=7,
                requires_role="company_owner",
                target_requires_role="company_owner",
                loser_outcome="cancelled",
            ),
            ActionDefinition(
                id="impose_sanctions",
                probability=ProbabilitySpec(base=0.05, time_unit="week"),
                duration_minutes=30,
                priority=9,
                requires_role="country_leader",
                target_requires_role="country_leader",
                loser_outcome="cancelled",
            ),
            ActionDefinition(
                id="scroll",
                probability=ProbabilitySpec(base=0.5, time_unit="hour"),
                duration_minutes=10,
                priority=1,
                loser_outcome="cancelled",
            ),
            ActionDefinition(
                id="repost",
                probability=ProbabilitySpec(base=0.2, time_unit="event"),
                duration_minutes=2,
                priority=1,
                loser_outcome="cancelled",
            ),
            ActionDefinition(
                id="ignore",
                probability=ProbabilitySpec(base=0.8, time_unit="event"),
                duration_minutes=0,
                priority=0,
                meaningful=False,
                loser_outcome="continues",
            ),
        ],
        chains=[
            ChainDefinition(
                id="share-chain",
                trigger="scroll",
                branches=[
                    ChainBranch(action="repost", probability=0.2),
                    ChainBranch(action="ignore", probability=0.8),
                ],
                max_length=2,
            )
        ],
        roles=[
            RoleDefinition(id="company_owner", actions=["negotiate_merger"]),
            RoleDefinition(id="country_leader", actions=["impose_sanctions"]),
            RoleDefinition(id="citizen", actions=["scroll", "repost"]),
        ],
        default_states=[
            DefaultDefinition(
                id="age",
                distribution=Distribution(
                    values={"20": 0.25, "25": 0.25, "55": 0.25, "60": 0.25},
                    provenance=evidence(),
                ),
            ),
            DefaultDefinition(
                id="has_friend",
                distribution=Distribution(values={"yes": 0.99, "no": 0.01}, provenance=evidence()),
            ),
        ],
        behaviour_bundles=[
            BehaviourBundle(
                id="human",
                layer=0,
                values={"trust": 0.5, "compliance": 0.5},
                provenance=evidence(),
            ),
            BehaviourBundle(
                id="conservative",
                layer=1,
                inherits=["human"],
                values={"protest_threshold": 0.7},
                provenance=evidence(),
            ),
            BehaviourBundle(
                id="japanese_conservative",
                layer=2,
                inherits=["conservative"],
                values={"trust": 0.78, "group_harmony": 0.84},
                provenance=evidence("FAKE fitted Japan fixture"),
            ),
            BehaviourBundle(
                id="american_conservative",
                layer=2,
                inherits=["conservative"],
                values={"trust": 0.34, "individual_liberty": 0.86},
                provenance=evidence("FAKE fitted USA fixture"),
            ),
        ],
        networks=[NetworkDefinition(id="social", max_depth=5, friend_weight=0.6)],
        media_rules=[
            MediaRule(
                id="default-feed",
                interest_weight=0.4,
                social_weight=0.3,
                recency_weight=0.2,
                trust_weight=0.1,
            )
        ],
        leader_actions=[
            LeaderActionDefinition(
                id="address",
                parameter_effects={"spread_rate": -0.01},
                evidence=evidence(),
            )
        ],
        events=[
            EventDefinition(
                id="awareness-spike",
                metric="aware",
                threshold=10,
                direction="above",
            )
        ],
        couplings=[
            CouplingDefinition(
                id="media-awareness",
                source_system="media",
                target_system="awareness-system",
                source_metric="reach",
                target_parameter="spread_rate",
                scale=0.01,
            )
        ],
        tick=TickConfig(tick_hours=1, total_ticks=48),
        outputs=OutputSpec(),
        population=PopulationReference(
            id="FAKE-town",
            version="test-v1",
            size=240,
            places=["ITA", "FRA"],
        ),
        benchmarks=[
            AggregateBenchmark(
                action_id="talk",
                population=1000,
                observed_annual_count=4_000_000,
                tolerance_factor=10,
            )
        ],
    )


def test_dsl_contract_loads_renders_and_rejects_invalid_configs():
    dsl = framework_dsl()
    assert validate_dsl(dsl).valid
    assert load_dsl(dsl.model_dump()).id == dsl.id
    assert load_dsl(yaml.safe_dump(dsl.model_dump(mode="json"))).id == dsl.id
    assert "awareness-system" in render_plain_language(dsl)
    assert {slider.parameter for slider in render_sliders(dsl)} == {"spread_rate"}

    missing_reference = deepcopy(dsl.model_dump())
    missing_reference["systems"][0]["transitions"][0]["to_state"] = "absent"
    assert "missing state" in " ".join(validate_dsl(missing_reference).error_messages).lower()

    probability = deepcopy(dsl.model_dump())
    probability["actions"][0]["probability"]["base"] = 1.1
    assert "probability" in " ".join(validate_dsl(probability).error_messages).lower()

    distribution = deepcopy(dsl.model_dump())
    distribution["states"][0]["initial"]["values"] = {"unaware": 0.9, "aware": 0.2}
    assert "sum" in " ".join(validate_dsl(distribution).error_messages).lower()

    chain = deepcopy(dsl.model_dump())
    chain["chains"][0]["max_length"] = None
    chain["chains"][0]["continue_probability"] = 1
    assert "termination" in " ".join(validate_dsl(chain).error_messages).lower()

    role = deepcopy(dsl.model_dump())
    role["actions"][3]["requires_role"] = None
    assert "role" in " ".join(validate_dsl(role).error_messages).lower()

    aggregate = deepcopy(dsl.model_dump())
    aggregate["benchmarks"][0] = {
        "action_id": "talk",
        "population": 1_000_000,
        "observed_annual_count": 50,
        "tolerance_factor": 10,
    }
    result = validate_dsl(aggregate)
    assert not result.valid

    graph = deepcopy(dsl.model_dump())
    graph["rules"] = [
        {
            "id": "unbounded-reference",
            "traversal": {"primitive": "neighbors", "network": "absent", "depth": 5},
            "effects": {"spread_rate": 0.1},
        }
    ]
    assert "missing network" in " ".join(validate_dsl(graph).error_messages).lower()
    assert result.implied_aggregates[0].implied_annual_count > 1_000_000


def test_population_is_deterministic_homophilic_and_bundle_provenance_is_retained():
    dsl = framework_dsl()
    first = generate_population(dsl, None, 42)
    second = generate_population(dsl, None, 42)
    assert first.model_dump() == second.model_dump()
    by_id = {agent.agent_id: agent for agent in first.agents}
    gaps = [
        abs(
            float(agent.traits["age"])
            - float(by_id[agent.relationships[0].target_id].traits["age"])
        )
        for agent in first.agents
        if agent.relationships
    ]
    assert np.median(gaps) <= 5
    bundles = {bundle.id: bundle for bundle in dsl.behaviour_bundles}
    japan = flatten_behaviour_bundles(["japanese_conservative"], bundles)
    america = flatten_behaviour_bundles(["american_conservative"], bundles)
    assert japan.values != america.values
    assert japan.provenance["trust"].source == "FAKE fitted Japan fixture"
    assert america.provenance["trust"].source == "FAKE fitted USA fixture"


def test_action_bundles_conflicts_chains_and_role_changes_are_explicit():
    dsl = framework_dsl()
    actions = {action.id: action for action in dsl.actions}
    idle = choose_bundle(
        AgentActionContext(agent_id="a", role="citizen"),
        [actions["sleep"]],
        np.random.default_rng(1),
        tick_hours=1,
    )
    assert not idle.primary and not idle.secondaries

    friend = resolve_conflict(
        actions["work"], actions["talk"], AgentActionContext(agent_id="a", relationship="friend")
    )
    boss = resolve_conflict(
        actions["work"], actions["talk"], AgentActionContext(agent_id="a", relationship="boss")
    )
    assert friend.winner == "work" and friend.loser_outcome == "relationship_cost"
    assert boss.winner == "talk" and boss.loser_outcome == "deferred"
    protected_talk = actions["talk"].model_copy(update={"protected": True})
    protected = resolve_conflict(
        protected_talk,
        actions["work"],
        AgentActionContext(agent_id="a", relationship="friend"),
    )
    assert protected.winner == "talk"

    chain = dsl.chains[0]
    rng = np.random.default_rng(11)
    choices = [chain_step(chain, "scroll", rng) for _ in range(10_000)]
    repost_rate = choices.count("repost") / len(choices)
    assert 0.18 < repost_rate < 0.22
    chain_result = chain_step_with_log(chain, "scroll", np.random.default_rng(2))
    assert chain_result.chain_id == "share-chain"
    assert "share-chain" in chain_result.log
    matrix = chain_transition_matrix([chain], ["scroll", "repost", "ignore"])
    np.testing.assert_allclose(matrix[0], [0, 0.2, 0.8])

    citizen = AgentActionContext(agent_id="a", role="citizen")
    owner = AgentActionContext(agent_id="a", role="company_owner")
    leader = AgentActionContext(agent_id="a", role="country_leader")
    assert not check_eligibility(actions["negotiate_merger"], citizen, citizen)
    assert check_eligibility(actions["negotiate_merger"], owner, owner)
    assert not check_eligibility(actions["impose_sanctions"], citizen, leader)
    assert check_eligibility(actions["impose_sanctions"], leader, leader)
    assert "negotiate_merger" not in {item.id for item in eligible_actions(dsl.actions, citizen)}
    assert "negotiate_merger" in {item.id for item in eligible_actions(dsl.actions, owner)}
    promoted = change_role(citizen, "company_owner")
    demoted = change_role(promoted, "citizen")
    assert "negotiate_merger" in {item.id for item in eligible_actions(dsl.actions, promoted)}
    assert "negotiate_merger" not in {item.id for item in eligible_actions(dsl.actions, demoted)}


def test_harmonization_composition_network_media_leaders_and_stories_are_auditable():
    registry = MappingRegistry()
    registry.register(
        dataset="german-eye-survey",
        field="eye_colour",
        version="v1",
        mappings={"braun": {"Brown": 1}, "blau": {"Blue": 1}, "gemischt": {"Hazel": 1}},
        provenance=evidence("German eye survey"),
    )
    registry.register(
        dataset="irisplex",
        field="eye_colour",
        version="v1",
        mappings={"intermediate": {"Green": 0.4, "Hazel": 0.4, "Grey": 0.2}},
        provenance=evidence("Joint IrisPlex reference", status="imputed", uncertainty=0.2),
    )
    assert registry.harmonize("german-eye-survey", "eye_colour", "braun").values == {"Brown": 1}
    intermediate = registry.harmonize("irisplex", "eye_colour", "intermediate")
    assert intermediate.status == "imputed" and intermediate.uncertainty == 0.2
    estimate = compositional_estimate(
        "eye_colour",
        {"group-a": 0.75, "group-b": 0.25},
        {"group-a": {"Brown": 0.8, "Blue": 0.2}, "group-b": {"Brown": 0.4, "Blue": 0.6}},
        evidence("Composition fixture", status="imputed", uncertainty=0.3),
    )
    assert estimate.values == {"Brown": 0.7, "Blue": 0.3}
    assert compositional_estimate("ideology", {"group-a": 1}, {}, evidence()).status == "missing"

    update = influence_update(
        opinion=0.2,
        neighbours=[
            {"kind": "friend", "opinion": 0.8, "weight": 1},
            {"kind": "stranger", "opinion": 0.8, "weight": 1},
            {"kind": "enemy", "opinion": 0.8, "weight": 1},
        ],
        place_delta=0.1,
    )
    assert update.causes["friend"] > update.causes["stranger"] > 0
    assert update.causes["enemy"] < 0 and update.causes["place"] > 0

    media = MediaObject(
        id="m1",
        source="outlet",
        topic="policy",
        sentiment=0.7,
        bias=0.2,
        credibility=0.9,
        reach=0.8,
        created_tick=4,
    )
    engaged = media_probabilities(
        {"interests": ["policy"], "agreement": 0.9, "outrage": 0.8, "trust": 0.9, "fatigue": 0.0},
        media,
    )
    fatigued = media_probabilities(
        {"interests": ["policy"], "agreement": 0.9, "outrage": 0.8, "trust": 0.9, "fatigue": 0.9},
        media,
    )
    distrusted = media_response({"trust": 0.05, "agreement": 0.1}, media)
    assert engaged["repost"] > 0.2 and fatigued["ignore"] > engaged["ignore"]
    assert distrusted.opinion_delta < 0
    assert rank_feed({"interests": ["policy"], "trust": 0.9}, [media])[0].id == "m1"

    calls = []

    def provider(leader, state, week):
        calls.append(week)
        return {"action": "address", "target": "ITA", "parameters": {}}

    table = EvidenceTable({"address": evidence("Evidence table")})
    anchor = anchor_run(framework_dsl(), weeks=3, provider=provider, evidence_table=table)
    replay = ensemble_replay(anchor, seeds=[1, 2, 3], distributions={"spread_rate": (0.1, 0.3)})
    assert calls == [0, 1, 2]
    assert all(sample.timeline == anchor.timeline for sample in replay.samples)
    assert replay.population_version == framework_dsl().population.version
    research_table = EvidenceTable()
    research = []
    first_evidence = research_table.resolve(
        "new-action",
        lambda action: research.append(action) or evidence("FAKE offline research"),
    )
    second_evidence = research_table.resolve(
        "new-action",
        lambda action: research.append(action) or evidence("unused"),
    )
    assert first_evidence == second_evidence and research == ["new-action"]

    before = {"ITA": {"aware": 9}}
    after = {"ITA": {"aware": 14}}
    event = detect_events(framework_dsl(), after, before, day=7)[0]
    story = generate_story(event, after)
    assert "14" in story.headline and story.metrics["aware"] == 14
    deep_dive = causal_deep_dive(
        [
            {"cause": "news", "magnitude": 0.4},
            {"cause": "friend", "magnitude": 0.3},
        ],
        state_change=0.7,
    )
    assert deep_dive.total == 0.7 and {cause.name for cause in deep_dive.causes} == {
        "news",
        "friend",
    }


def test_mapping_versions_persist_and_backtests_reject_hindsight(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite")
    registry = MappingRegistry(store)
    registry.register(
        "german-survey",
        "eye_colour",
        "mapping-v1",
        {"braun": {"Brown": 1}, "blau": {"Blue": 1}},
        evidence("FAKE confirmed codebook"),
    )
    loaded = MappingRegistry(store).harmonize("german-survey", "eye_colour", "braun")
    assert loaded.values == {"Brown": 1}
    assert loaded.mapping_version == "mapping-v1"
    comparison = backtest(
        "aware",
        [1, 3, 5],
        [1, 2, 7],
        date(2025, 1, 1),
        [date(2024, 12, 1)],
        "FAKE historical fixture",
        tolerance=2,
    )
    assert comparison.outcome == "hit"
    with np.testing.assert_raises_regex(ValueError, "after cutoff"):
        backtest(
            "aware",
            [1],
            [1],
            date(2025, 1, 1),
            [date(2025, 1, 2)],
            "FAKE future fixture",
            tolerance=0,
        )
