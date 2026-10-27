from pathlib import Path

import pytest

from petraterrium.dsl import ChoiceCondition, ChoiceEvidence, Evidence
from petraterrium.markov import (
    CompilationContext,
    EvidenceCatalog,
    MarkovModule,
    MarkovProgram,
    ModuleInput,
    ModuleState,
    ModuleTransition,
    ProbabilityQuery,
    ProgramExit,
    TransitionCondition,
    TransitionEvidence,
    compile_program,
)
from petraterrium.rust_core import RustCoreClient, RustCoreError, compiled_markov_request


@pytest.fixture(scope="module")
def rust_core() -> RustCoreClient:
    return RustCoreClient()


def compiled_program(evidence: bool = True, age: int | None = None):
    inputs = [
        ModuleInput(
            id="place",
            kind="place",
            value_type="identifier",
        ),
        ModuleInput(
            id="day",
            kind="time",
            value_type="categorical",
        ),
    ]
    if age is not None:
        inputs.append(
            ModuleInput(
                id="age",
                kind="agent_trait",
                value_type="continuous",
                feature_id="age",
            )
        )
    module = MarkovModule(
        id="daily-choice",
        version="1",
        name="Daily choice",
        entry_state="decide",
        exit_states=["home"],
        inputs=inputs,
        states=[
            ModuleState(id="decide"),
            ModuleState(id="go-out"),
            ModuleState(id="home"),
        ],
        transitions=[
            ModuleTransition(
                id="choose-out",
                from_state="decide",
                to_state="go-out",
                condition=TransitionCondition(mode="always"),
                probability=ProbabilityQuery(
                    outcome_id="go-out",
                    conditioning_id="friday-adults",
                    place_input="place",
                    time_input="day",
                    predictor_inputs=["age"] if age is not None else [],
                ),
            ),
            ModuleTransition(
                id="return-home",
                from_state="go-out",
                to_state="home",
                condition=TransitionCondition(mode="always"),
                probability=ProbabilityQuery(
                    outcome_id="go-home",
                    conditioning_id="friday-adults",
                    place_input="place",
                    time_input="day",
                    predictor_inputs=["age"] if age is not None else [],
                ),
            ),
        ],
    )
    program = MarkovProgram(
        id="social-day",
        version="1",
        entry_module="daily-choice",
        modules=[module],
        terminal_exits=[ProgramExit(module_id="daily-choice", state_id="home")],
    )
    choices = []
    if evidence:
        for identity, action in (("go-out-rate", "go-out"), ("go-home-rate", "go-home")):
            choices.append(
                ChoiceEvidence(
                    id=identity,
                    action_id=action,
                    conditioning_id="friday-adults",
                    conditioning=ChoiceCondition(
                        place="CHN",
                        traits={"age": str(age)} if age is not None else {},
                    ),
                    definition=f"Measured probability of {action}",
                    value=1,
                    ci_low=0.96,
                    ci_high=1,
                    source_type="time_use_diary",
                    tier=1,
                    sample_size=4_000,
                    source_date="2026-01-15",
                    population="Chinese adults",
                    denominator="Weighted respondents",
                    time_unit="friday",
                    source_time_unit="friday",
                    tier_flag="measured",
                    provenance=Evidence(
                        source="National weighted time-use diary",
                        version="2026-v1",
                        status="present",
                        uncertainty=0.04,
                        source_date="2026-01-15",
                    ),
                )
            )
    compilation = compile_program(
        program,
        EvidenceCatalog(choice=choices),
        CompilationContext(
            place="CHN",
            time_unit="friday",
            strata={"age": age} if age is not None else {},
        ),
    )
    return program, compilation


def compiled_execution() -> dict:
    return {
        "seed": 93,
        "ticks": 1,
        "tick_hours": 1,
        "start_weekday": 4,
        "places": [{"id": "CHN", "state": {}}],
        "agents": {
            "module": ["daily-choice"] * 12,
            "state": ["decide"] * 12,
            "place": [0] * 12,
            "traits": {},
            "memory": {},
        },
    }


def aggregate_dsl(parameter_value: float | None = 0.3) -> dict:
    return {
        "schema_version": "1",
        "id": "rust-fixture",
        "version": "1",
        "states": [
            {
                "id": "health",
                "values": ["well", "sick"],
                "initial": {
                    "values": {"well": 0.9, "sick": 0.1},
                    "provenance": {
                        "source": "Fixture",
                        "version": "1",
                        "status": "present",
                        "uncertainty": 0,
                    },
                },
            }
        ],
        "parameters": [
            {
                "id": "recovery",
                "value": parameter_value,
                "unit": "probability/day",
                "provenance": {
                    "source": "Fixture",
                    "version": "1",
                    "status": "present",
                    "uncertainty": 0,
                },
            }
        ],
        "systems": [
            {
                "id": "illness",
                "state": "health",
                "transitions": [
                    {
                        "id": "recover",
                        "from_state": "sick",
                        "to_state": "well",
                        "probability": {
                            "base": 0,
                            "mode": "probability",
                            "time_unit": "day",
                            "parameter": "recovery",
                            "source_state": None,
                            "mixing_parameter": None,
                            "opportunity": None,
                            "modifiers": {},
                        },
                    }
                ],
            }
        ],
        "tick": {
            "tick_hours": 24,
            "total_ticks": 4,
            "snapshot_every_hours": 24,
            "story_every_days": 7,
            "update_order": "double_buffered",
        },
        "population": {
            "id": "fixture",
            "version": "1",
            "size": 100,
            "places": ["A", "B"],
            "place_populations": {"A": 600, "B": 400},
            "place_coordinates": {},
            "place_hierarchy": {},
            "initial_state_overrides": {},
        },
    }


def test_binary_health_identifies_rust_numeric_core(rust_core: RustCoreClient):
    result = rust_core.health()

    assert result["numeric_core"] == "rust"
    assert result["llm_inside_tick"] is False
    assert result["update_mode"] == "double_buffered"
    assert result["rng"] == "chacha8"
    assert result["protocol_version"] == "1"


def test_current_aggregate_dsl_is_deterministic_and_preserves_mass(
    rust_core: RustCoreClient,
):
    first = rust_core.run_aggregate_dsl(aggregate_dsl(), seed=81)
    second = rust_core.run_aggregate_dsl(aggregate_dsl(), seed=81)

    assert first == second
    assert [snapshot["tick"] for snapshot in first["snapshots"]] == [0, 1, 2, 3, 4]
    assert all(snapshot["state_totals"]["health"] == 1_000 for snapshot in first["snapshots"])


def test_unknown_fitted_parameter_blocks_rust_execution(rust_core: RustCoreClient):
    with pytest.raises(RustCoreError) as captured:
        rust_core.run_aggregate_dsl(aggregate_dsl(None), seed=1)

    assert captured.value.code == "UNKNOWN_PROBABILITY"
    assert "no fitted value" in captured.value.message


def test_csr_bridge_applies_sparse_neighbor_matvec(rust_core: RustCoreClient):
    values = rust_core.csr_matvec(
        {
            "rows": 3,
            "cols": 3,
            "row_offsets": [0, 2, 3, 4],
            "column_indices": [1, 2, 0, 1],
            "weights": [0.5, 0.5, 1, 1],
        },
        [2, 4, 8],
    )

    assert values == [6, 2, 4]


def test_agent_bridge_routes_modules_and_emits_external_sync(rust_core: RustCoreClient):
    evidence = {
        "source": "Weighted activity panel",
        "version": "2026-v1",
        "status": "present",
        "uncertainty": 0.1,
    }
    result = rust_core.run_agents(
        {
            "seed": 5,
            "ticks": 1,
            "tick_hours": 1,
            "start_hour": 18,
            "start_weekday": 4,
            "places": [{"id": "A", "state": {"contamination": 0.2}}],
            "agents": {
                "module": ["daily-choice", "daily-choice"],
                "state": ["decide", "decide"],
                "place": [0, 0],
                "traits": {"age": [20, 40]},
                "memory": {},
            },
            "modules": [
                {
                    "id": "daily-choice",
                    "entry_state": "decide",
                    "exit_states": ["go-out"],
                    "inputs": [],
                    "outputs": ["memory.outings"],
                    "states": ["decide", "go-out"],
                    "transitions": [
                        {
                            "id": "choose-out",
                            "from_state": "decide",
                            "to_state": "go-out",
                            "rules": [
                                {
                                    "conditions": [],
                                    "probability": 1,
                                    "provenance": evidence,
                                }
                            ],
                            "effects": [
                                {
                                    "target": "memory.outings",
                                    "operation": "add",
                                    "value": 1,
                                }
                            ],
                        }
                    ],
                },
                {
                    "id": "venue",
                    "entry_state": "choose",
                    "exit_states": ["home"],
                    "inputs": [],
                    "outputs": [],
                    "states": ["choose", "home"],
                    "transitions": [
                        {
                            "id": "return-home",
                            "from_state": "choose",
                            "to_state": "home",
                            "rules": [
                                {
                                    "conditions": [],
                                    "probability": 1,
                                    "provenance": evidence,
                                }
                            ],
                            "effects": [],
                        }
                    ],
                },
            ],
            "routes": [
                {
                    "from_module": "daily-choice",
                    "exit_state": "go-out",
                    "to_module": "venue",
                }
            ],
            "network": {
                "rows": 2,
                "cols": 2,
                "row_offsets": [0, 1, 2],
                "column_indices": [1, 0],
                "weights": [1, 1],
            },
            "schedules": [
                {
                    "id": "friday-evening",
                    "action": "routine-dinner",
                    "weekdays": [4],
                    "start_hour": 17,
                    "end_hour": 20,
                    "modules": [],
                    "states": [],
                }
            ],
            "meaningful_actions": [
                {
                    "id": "message-friend",
                    "rules": [
                        {
                            "conditions": [],
                            "probability": 1,
                            "provenance": evidence,
                        }
                    ],
                }
            ],
            "synchronization": {
                "border_every_ticks": 1,
                "media_every_ticks": 1,
                "weekly_leader_every_ticks": 1,
                "border_payloads": [{"from": "A", "to": "B"}],
                "media_payloads": [{"item": "m1"}],
                "weekly_leader_payloads": [{"log_id": "external-1"}],
            },
        }
    )

    assert result["agents"]["module"] == ["venue", "venue"]
    assert result["agents"]["state"] == ["choose", "choose"]
    assert result["agents"]["memory"]["outings"] == [1, 1]
    assert [event["agent_index"] for event in result["events"]] == [0, 1]
    assert result["routine_actions"][0]["agent_indices"] == [0, 1]
    assert [item["kind"] for item in result["synchronization"]] == [
        "border",
        "media",
        "weekly_leader",
    ]


def test_compiled_backend_markov_program_executes_in_rust_with_provenance(
    rust_core: RustCoreClient,
):
    program, compilation = compiled_program()
    assert compilation.executable

    first_tick = rust_core.run_compiled_markov(
        program,
        compilation,
        **compiled_execution(),
    )
    two_ticks = rust_core.run_compiled_markov(
        program,
        compilation,
        **{**compiled_execution(), "ticks": 2},
    )

    assert first_tick["agents"]["state"] == ["go-out"] * 12
    assert two_ticks["agents"]["state"] == ["home"] * 12
    evidence = first_tick["transition_evidence"]
    assert {item["provenance"]["evidence_id"] for item in evidence} == {
        "go-out-rate",
        "go-home-rate",
    }
    assert all(
        item["provenance"]
        == {
            "source": "National weighted time-use diary",
            "version": "2026-v1",
            "status": "present",
            "uncertainty": 0.04,
            "source_date": "2026-01-15",
            "evidence_id": item["provenance"]["evidence_id"],
            "evidence_kind": "measured_choice",
            "ci_low": 0.96,
            "ci_high": 1.0,
        }
        for item in evidence
    )


def test_unresolved_compilation_never_reaches_rust(
    rust_core: RustCoreClient,
    monkeypatch: pytest.MonkeyPatch,
):
    program, compilation = compiled_program(evidence=False)
    assert any(item.status == "unknown" for item in compilation.probabilities)

    def unexpected_rust_call(_request):
        raise AssertionError("Rust process must not receive unresolved probabilities")

    monkeypatch.setattr(rust_core, "run_agents", unexpected_rust_call)
    with pytest.raises(RustCoreError) as captured:
        rust_core.run_compiled_markov(
            program,
            compilation,
            **compiled_execution(),
        )

    assert captured.value.code == "UNRESOLVED_MARKOV_PROBABILITY"


def test_compiled_request_contains_only_evidence_resolved_probabilities():
    program, compilation = compiled_program()

    request = compiled_markov_request(
        program,
        compilation,
        **compiled_execution(),
    )

    rules = [
        rule
        for module in request["modules"]
        for transition in module["transitions"]
        for rule in transition["rules"]
    ]
    assert [rule["probability"] for rule in rules] == [1, 1]
    assert all(rule["provenance"]["evidence_id"] for rule in rules)


def test_compiled_request_binds_place_time_and_trait_evidence_context(
    rust_core: RustCoreClient,
):
    program, compilation = compiled_program(age=20)
    execution = compiled_execution()
    execution["agents"]["traits"] = {"age": [20] * 11 + [40]}

    request = compiled_markov_request(program, compilation, **execution)
    conditions = request["modules"][0]["transitions"][0]["rules"][0]["conditions"]
    assert {item["input"] for item in conditions} == {
        "place.index",
        "context.weekday",
        "trait.age",
    }

    with pytest.raises(RustCoreError) as captured:
        rust_core.run_agents(request)
    assert captured.value.code == "UNKNOWN_PROBABILITY"


def test_compiled_categorical_evidence_uses_versioned_dictionary_in_rust(
    rust_core: RustCoreClient,
):
    program, _ = compiled_program(evidence=False)
    payload = program.model_dump(mode="python")
    payload["modules"][0]["inputs"].append(
        {
            "id": "personality",
            "kind": "agent_trait",
            "value_type": "categorical",
            "feature_id": "mbti",
            "required": True,
        }
    )
    for transition in payload["modules"][0]["transitions"]:
        transition["probability"]["predictor_inputs"] = ["personality"]
    categorical_program = MarkovProgram.model_validate(payload)
    transition_evidence = [
        TransitionEvidence(
            id=f"joint-{outcome}",
            kind="measured_joint",
            outcome_id=outcome,
            conditioning_id="friday-adults",
            place="CHN",
            time_unit="friday",
            predictor_values={"mbti": "ENFP"},
            probability=1,
            ci_low=0.96,
            ci_high=1,
            sample_size=1_200,
            population="Chinese adults reporting MBTI and Friday activity",
            provenance=Evidence(
                source="Population-specific joint survey",
                version="2025-v1",
                status="present",
                uncertainty=0.04,
                source_date="2025-01-01",
            ),
        )
        for outcome in ("go-out", "go-home")
    ]
    compilation = compile_program(
        categorical_program,
        EvidenceCatalog(transition=transition_evidence),
        CompilationContext(
            place="CHN",
            time_unit="friday",
            strata={"mbti": "ENFP"},
        ),
    )
    execution = compiled_execution()
    execution["agents"]["traits"] = {"mbti": ["ENFP"] * 12}
    execution["agents"]["trait_dictionaries"] = {
        "mbti": {
            "source": "Petraterrium canonical MBTI labels",
            "version": "1",
            "values": ["ENFP", "INTJ"],
        }
    }

    request = compiled_markov_request(categorical_program, compilation, **execution)
    result = rust_core.run_agents({**request, "ticks": 2})

    assert request["agents"]["traits"]["mbti"] == [0.0] * 12
    assert result["agents"]["state"] == ["home"] * 12
    assert result["agents"]["trait_dictionaries"]["mbti"] == {
        "source": "Petraterrium canonical MBTI labels",
        "version": "1",
        "values": ["ENFP", "INTJ"],
    }

    execution["agents"].pop("trait_dictionaries")
    with pytest.raises(RustCoreError) as captured:
        compiled_markov_request(categorical_program, compilation, **execution)
    assert captured.value.code == "MISSING_CATEGORICAL_DICTIONARY"


def test_missing_binary_never_falls_back_to_python(tmp_path: Path):
    missing = tmp_path / "not-built"

    with pytest.raises(RustCoreError) as captured:
        RustCoreClient(missing, build_if_missing=False)

    assert captured.value.code == "RUST_CORE_NOT_BUILT"
