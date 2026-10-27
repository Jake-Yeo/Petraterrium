from pathlib import Path

import pytest
from pydantic import ValidationError

from petraterrium.compatibility import compatibility_dsl
from petraterrium.contracts import RunConfig
from petraterrium.dsl import ChoiceCondition, ChoiceEvidence, DSLConfig, Evidence, validate_dsl
from petraterrium.markov import (
    CompilationContext,
    ConditionClause,
    EvidenceCatalog,
    InputBinding,
    MarkovModule,
    MarkovProgram,
    ModuleInput,
    ModuleLink,
    ModuleOutput,
    ModuleState,
    ModuleTransition,
    ProbabilityQuery,
    ProgramExit,
    TransitionCondition,
    TransitionEvidence,
    compile_program,
    update_missing_requirements,
    validate_module,
    validate_program,
)


def input_value(identity: str, kind: str, feature_id: str | None = None) -> ModuleInput:
    return ModuleInput(
        id=identity,
        kind=kind,
        value_type="categorical",
        feature_id=feature_id,
    )


def probability(outcome: str, predictors: list[str] | None = None) -> ProbabilityQuery:
    return ProbabilityQuery(
        outcome_id=outcome,
        conditioning_id="friday-adults",
        place_input="place",
        time_input="day",
        predictor_inputs=predictors or [],
    )


def transition(
    identity: str,
    source: str,
    target: str,
    outcome: str,
    predictors: list[str] | None = None,
    clauses: list[ConditionClause] | None = None,
) -> ModuleTransition:
    condition = (
        TransitionCondition(mode="all", clauses=clauses)
        if clauses
        else TransitionCondition(mode="always")
    )
    return ModuleTransition(
        id=identity,
        from_state=source,
        to_state=target,
        condition=condition,
        probability=probability(outcome, predictors),
    )


def choice(
    identity: str,
    action_id: str,
    value: float,
    traits: dict[str, str] | None = None,
) -> ChoiceEvidence:
    return ChoiceEvidence(
        id=identity,
        action_id=action_id,
        conditioning_id="friday-adults",
        conditioning=ChoiceCondition(place="CHN", traits=traits or {}),
        definition=f"Measured probability of {action_id}",
        value=value,
        ci_low=max(0, value - 0.05),
        ci_high=min(1, value + 0.05),
        source_type="representative_survey",
        tier=2,
        sample_size=2_000,
        source_date="2025-01-01",
        population="Chinese adults",
        denominator="Weighted respondents",
        time_unit="friday",
        source_time_unit="friday",
        tier_flag="measured",
        provenance=Evidence(
            source="Weighted time-use survey",
            version="2025-v1",
            status="present",
            uncertainty=0.1,
            source_date="2025-01-01",
        ),
    )


def simple_module(predictors: list[str] | None = None) -> MarkovModule:
    inputs = [input_value("place", "place"), input_value("day", "time")]
    for predictor in predictors or []:
        inputs.append(input_value(predictor, "agent_trait", predictor))
    return MarkovModule(
        id="daily-choice",
        version="1",
        name="Daily choice",
        entry_state="decide",
        exit_states=["stay-home", "go-out"],
        inputs=inputs,
        outputs=[
            ModuleOutput(id="location", kind="location", value_type="categorical")
        ],
        states=[
            ModuleState(id="decide"),
            ModuleState(id="stay-home", effects=["location"]),
            ModuleState(id="go-out", effects=["location"]),
        ],
        transitions=[
            transition("choose-home", "decide", "stay-home", "stay-home", predictors),
            transition("choose-out", "decide", "go-out", "go-out", predictors),
        ],
    )


def modular_program() -> MarkovProgram:
    shared_inputs = [input_value("place", "place"), input_value("day", "time")]
    top = simple_module()
    venues = MarkovModule(
        id="venues",
        version="1",
        name="Venue choice",
        entry_state="choose-venue",
        exit_states=["bar", "soccer", "friends"],
        inputs=shared_inputs,
        outputs=[
            ModuleOutput(id="venue", kind="location", value_type="categorical")
        ],
        states=[
            ModuleState(id="choose-venue"),
            ModuleState(id="bar", effects=["venue"]),
            ModuleState(id="soccer", effects=["venue"]),
            ModuleState(id="friends", effects=["venue"]),
        ],
        transitions=[
            transition("to-bar", "choose-venue", "bar", "bar"),
            transition("to-soccer", "choose-venue", "soccer", "soccer"),
            transition("to-friends", "choose-venue", "friends", "friends"),
        ],
    )
    bar = MarkovModule(
        id="bar-visit",
        version="1",
        name="Bar visit",
        entry_state="at-bar",
        exit_states=["sick", "new-friend", "home"],
        inputs=[
            *shared_inputs,
            input_value("bar-contamination", "place_state"),
            input_value("bar-aversion", "persisted_state"),
        ],
        outputs=[
            ModuleOutput(id="health", kind="health", value_type="categorical"),
            ModuleOutput(id="friends", kind="friends", value_type="identifier"),
            ModuleOutput(id="history", kind="persisted_state", value_type="categorical"),
        ],
        states=[
            ModuleState(id="at-bar"),
            ModuleState(id="sick", effects=["health", "history"]),
            ModuleState(id="new-friend", effects=["friends"]),
            ModuleState(id="home", effects=["history"]),
        ],
        transitions=[
            transition(
                "bar-to-sick",
                "at-bar",
                "sick",
                "get-sick",
                clauses=[
                    ConditionClause(
                        input_id="bar-contamination", operator="gt", value=0.2
                    )
                ],
            ),
            transition("bar-to-friend", "at-bar", "new-friend", "become-friends"),
            transition(
                "bar-to-home",
                "at-bar",
                "home",
                "go-home",
                clauses=[
                    ConditionClause(input_id="bar-aversion", operator="gte", value=0.5)
                ],
            ),
        ],
    )
    bindings = [
        InputBinding(target_input="place", source_kind="input", source_id="place"),
        InputBinding(target_input="day", source_kind="input", source_id="day"),
    ]
    return MarkovProgram(
        id="social-day",
        version="1",
        entry_module="daily-choice",
        modules=[top, venues, bar],
        links=[
            ModuleLink(
                from_module="daily-choice",
                exit_state="go-out",
                to_module="venues",
                bindings=bindings,
            ),
            ModuleLink(
                from_module="venues",
                exit_state="bar",
                to_module="bar-visit",
                bindings=[
                    *bindings,
                    InputBinding(
                        target_input="bar-contamination",
                        source_kind="external",
                        source_id="bar-contamination",
                    ),
                    InputBinding(
                        target_input="bar-aversion",
                        source_kind="external",
                        source_id="bar-aversion",
                    ),
                ],
            ),
        ],
        terminal_exits=[
            ProgramExit(module_id="daily-choice", state_id="stay-home"),
            ProgramExit(module_id="venues", state_id="soccer"),
            ProgramExit(module_id="venues", state_id="friends"),
            ProgramExit(module_id="bar-visit", state_id="sick"),
            ProgramExit(module_id="bar-visit", state_id="new-friend"),
            ProgramExit(module_id="bar-visit", state_id="home"),
        ],
        external_inputs=[
            input_value("bar-contamination", "place_state"),
            input_value("bar-aversion", "persisted_state"),
        ],
    )


def test_transition_schema_rejects_hardcoded_probability():
    with pytest.raises(ValidationError):
        ModuleTransition.model_validate(
            {
                "id": "choose-out",
                "from_state": "decide",
                "to_state": "go-out",
                "condition": {"mode": "always", "clauses": []},
                "probability": 0.5,
            }
        )


def test_evidence_catalog_rejects_marginals_independence_and_unvalidated_fits():
    with pytest.raises(ValidationError):
        EvidenceCatalog.model_validate({"marginal_distributions": []})
    with pytest.raises(ValidationError):
        TransitionEvidence.model_validate(
            {
                "id": "independence-rate",
                "kind": "independence_estimate",
                "outcome_id": "go-out",
                "conditioning_id": "friday-adults",
                "place": "CHN",
                "time_unit": "friday",
                "probability": 0.4,
                "ci_low": 0,
                "ci_high": 1,
                "sample_size": 1_000,
                "population": "Chinese adults",
                "provenance": {
                    "source": "Marginal product",
                    "version": "1",
                    "status": "imputed",
                    "uncertainty": 1,
                    "source_date": "2025-01-01",
                },
            }
        )
    with pytest.raises(ValidationError, match="held-out"):
        TransitionEvidence(
            id="unvalidated-fit",
            kind="fitted_choice",
            outcome_id="go-out",
            conditioning_id="friday-adults",
            place="CHN",
            time_unit="friday",
            probability=0.4,
            ci_low=0.3,
            ci_high=0.5,
            sample_size=1_000,
            population="Chinese adults",
            provenance=Evidence(
                source="Fitted behavior survey",
                version="1",
                status="present",
                uncertainty=0.2,
                source_date="2025-01-01",
            ),
        )


def test_stay_home_venue_and_bar_modules_are_reusable_and_link_compatible():
    result = validate_program(modular_program())

    assert result.valid
    assert result.non_terminating_module_loops == []
    assert result.unlinked_exits == []


def test_stateful_conditions_require_declared_place_or_persisted_state():
    payload = simple_module().model_dump(mode="python")
    payload["inputs"].append(
        input_value("bar-contamination", "context").model_dump(mode="python")
    )
    payload["transitions"][0]["condition"] = {
        "mode": "all",
        "clauses": [{"input_id": "bar-contamination", "operator": "gt", "value": 0.2}],
    }
    result = validate_module(MarkovModule.model_validate(payload))

    assert not result.valid
    assert "place_state" in " ".join(issue.message for issue in result.issues)


def test_unknown_evidence_blocks_compilation_and_writes_an_idempotent_requirement(
    tmp_path: Path,
):
    result = compile_program(
        MarkovProgram(
            id="daily",
            version="1",
            entry_module="daily-choice",
            modules=[simple_module(["age", "extraversion"])],
            terminal_exits=[
                ProgramExit(module_id="daily-choice", state_id="stay-home"),
                ProgramExit(module_id="daily-choice", state_id="go-out"),
            ],
        ),
        EvidenceCatalog(),
        CompilationContext(place="CHN", time_unit="friday"),
    )

    assert not result.executable
    assert len(result.missing_requirements) == 2
    assert all(item.ci_low == 0 and item.ci_high == 1 for item in result.probabilities)
    assert "age" in result.missing_requirements[0].requirement
    assert "extraversion" in result.missing_requirements[0].requirement
    missing_path = tmp_path / "MISSING.md"
    missing_path.write_text("# Missing\n\nExisting content.\n")
    update_missing_requirements(missing_path, result.missing_requirements)
    first = missing_path.read_text()
    update_missing_requirements(missing_path, result.missing_requirements)
    assert missing_path.read_text() == first
    assert first.count(result.missing_requirements[0].key) == 1


def test_measured_choice_evidence_compiles_with_double_buffered_metadata():
    program = MarkovProgram(
        id="daily",
        version="1",
        entry_module="daily-choice",
        modules=[simple_module()],
        terminal_exits=[
            ProgramExit(module_id="daily-choice", state_id="stay-home"),
            ProgramExit(module_id="daily-choice", state_id="go-out"),
        ],
    )
    result = compile_program(
        program,
        EvidenceCatalog(
            choice=[choice("home-choice", "stay-home", 0.6), choice("out-choice", "go-out", 0.4)]
        ),
        CompilationContext(place="CHN", time_unit="friday"),
    )

    assert result.executable
    assert result.outgoing_totals[0].total == pytest.approx(1)
    assert result.modules[0].double_buffer.read_buffer == "current_state"
    assert result.modules[0].double_buffer.write_buffer == "next_state"
    assert result.modules[0].double_buffer.swap_after_batch is True
    assert result.modules[0].vectorized_batch is True


def test_outgoing_probabilities_must_sum_to_one():
    program = MarkovProgram(
        id="daily",
        version="1",
        entry_module="daily-choice",
        modules=[simple_module()],
        terminal_exits=[
            ProgramExit(module_id="daily-choice", state_id="stay-home"),
            ProgramExit(module_id="daily-choice", state_id="go-out"),
        ],
    )
    result = compile_program(
        program,
        EvidenceCatalog(
            choice=[choice("home-choice", "stay-home", 0.7), choice("out-choice", "go-out", 0.4)]
        ),
        CompilationContext(place="CHN", time_unit="friday"),
    )

    assert not result.executable
    assert any(issue.code == "outgoing_probability_sum" for issue in result.issues)


def test_mbti_remains_label_only_without_population_specific_joint_outcome_evidence():
    module = simple_module(["mbti"])
    program = MarkovProgram(
        id="daily",
        version="1",
        entry_module=module.id,
        modules=[module],
        terminal_exits=[
            ProgramExit(module_id=module.id, state_id="stay-home"),
            ProgramExit(module_id=module.id, state_id="go-out"),
        ],
    )
    ordinary_choice = EvidenceCatalog(
        choice=[
            choice("home-choice", "stay-home", 0.6, {"mbti": "ENFP"}),
            choice("out-choice", "go-out", 0.4, {"mbti": "ENFP"}),
        ]
    )
    blocked = compile_program(
        program,
        ordinary_choice,
        CompilationContext(place="CHN", time_unit="friday", strata={"mbti": "ENFP"}),
    )

    assert not blocked.executable
    assert all("population-specific" in item.requirement for item in blocked.missing_requirements)

    joint = [
        TransitionEvidence(
            id=f"joint-{outcome}",
            kind="measured_joint",
            outcome_id=outcome,
            conditioning_id="friday-adults",
            place="CHN",
            time_unit="friday",
            predictor_values={"mbti": "ENFP"},
            probability=value,
            ci_low=value - 0.05,
            ci_high=value + 0.05,
            sample_size=1_200,
            population="Chinese adults reporting MBTI and Friday activity",
            provenance=Evidence(
                source="Population-specific joint survey",
                version="2025-v1",
                status="present",
                uncertainty=0.15,
                source_date="2025-01-01",
            ),
        )
        for outcome, value in (("stay-home", 0.6), ("go-out", 0.4))
    ]
    compiled = compile_program(
        program,
        EvidenceCatalog(transition=joint),
        CompilationContext(place="CHN", time_unit="friday", strata={"mbti": "ENFP"}),
    )

    assert compiled.executable
    assert {item.evidence_kind for item in compiled.probabilities} == {"measured_joint"}


def test_closed_state_loop_and_incompatible_module_binding_are_rejected():
    payload = simple_module().model_dump(mode="python")
    payload["exit_states"] = ["go-out"]
    payload["transitions"] = [
        transition("loop-one", "decide", "stay-home", "stay-home").model_dump(mode="python"),
        transition("loop-two", "stay-home", "decide", "go-out").model_dump(mode="python"),
    ]
    module_result = validate_module(MarkovModule.model_validate(payload))

    assert not module_result.valid
    assert module_result.non_terminating_loops

    program = modular_program()
    payload = program.model_dump(mode="python")
    payload["links"][0]["bindings"][0] = {
        "target_input": "place",
        "source_kind": "input",
        "source_id": "day",
    }
    program_result = validate_program(MarkovProgram.model_validate(payload))

    assert not program_result.valid
    assert any(issue.code == "incompatible_binding" for issue in program_result.issues)


def test_modular_programs_and_confirmed_drafts_are_versioned_dsl_contracts():
    base = compatibility_dsl(
        RunConfig(
            scenario="pandemic",
            countries=["ITA"],
            start_day=0,
            end_day=2,
            seed=9,
        )
    ).model_dump(mode="json")
    base["markov_programs"] = [modular_program().model_dump(mode="json")]
    base["markov_chain_drafts"] = [
        {
            "schema_version": "1",
            "id": "weekend_choice",
            "name": "Weekend choice",
            "source_text": "Decision -> Home or Outside",
            "entry_node": "decision",
            "nodes": [
                {
                    "id": "decision",
                    "label": "Decision",
                    "terminal": False,
                    "origin": "manual_edit",
                    "source_excerpt": None,
                },
                {
                    "id": "home",
                    "label": "Home",
                    "terminal": True,
                    "origin": "manual_edit",
                    "source_excerpt": None,
                },
            ],
            "transitions": [
                {
                    "id": "choose_home",
                    "from_node": "decision",
                    "to_node": "home",
                    "probability": 1,
                    "condition": "always",
                    "origin": "manual_edit",
                    "source_excerpt": None,
                }
            ],
            "revision": 1,
        }
    ]

    config = DSLConfig.model_validate(base)
    result = validate_dsl(config)

    assert result.valid
    assert config.markov_programs[0].id == "social-day"
    assert config.markov_chain_drafts[0].id == "weekend_choice"
    schema = DSLConfig.model_json_schema(mode="serialization")
    assert "markov_programs" in schema["properties"]
    assert "markov_chain_drafts" in schema["properties"]
