import pytest
from pydantic import ValidationError

from petraterrium.dsl import Evidence
from petraterrium.markov import (
    CompilationContext,
    EvidenceCatalog,
    MarkovModule,
    MarkovProgram,
    ModuleInput,
    ModuleState,
    ModuleTransition,
    PipelineEstimateSource,
    PipelineResearchLog,
    PipelineTransitionEstimate,
    ProbabilityQuery,
    ProgramExit,
    TransitionCondition,
    TransitionEvidence,
    compile_program,
)
from petraterrium.rust_core import RustCoreClient, compiled_markov_request


def program(predictors: list[str] | None = None) -> MarkovProgram:
    inputs = [
        ModuleInput(id="place", kind="place", value_type="identifier"),
        ModuleInput(id="day", kind="time", value_type="categorical"),
    ]
    for predictor in predictors or []:
        inputs.append(
            ModuleInput(
                id=predictor,
                kind="agent_trait",
                value_type="categorical",
                feature_id=predictor,
            )
        )
    module = MarkovModule(
        id="daily-choice",
        version="1",
        name="Daily choice",
        entry_state="decide",
        exit_states=["stay-home", "go-out"],
        inputs=inputs,
        states=[
            ModuleState(id="decide"),
            ModuleState(id="stay-home"),
            ModuleState(id="go-out"),
        ],
        transitions=[
            ModuleTransition(
                id="choose-home",
                from_state="decide",
                to_state="stay-home",
                condition=TransitionCondition(mode="always"),
                probability=ProbabilityQuery(
                    outcome_id="stay-home",
                    conditioning_id="friday-adults",
                    place_input="place",
                    time_input="day",
                    predictor_inputs=predictors or [],
                ),
            ),
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
                    predictor_inputs=predictors or [],
                ),
            ),
        ],
    )
    return MarkovProgram(
        id="social-day",
        version="1",
        entry_module=module.id,
        modules=[module],
        terminal_exits=[
            ProgramExit(module_id=module.id, state_id="stay-home"),
            ProgramExit(module_id=module.id, state_id="go-out"),
        ],
    )


def source(*, joint: bool = False) -> PipelineEstimateSource:
    return PipelineEstimateSource(
        id="survey-report",
        title="National activity survey report",
        url="https://statistics.example/activity-report",
        source_kind="government_report",
        observation_date="2024-12-31",
        published_date="2025-03-10",
        language="en",
        excerpt="The report describes Friday social activity rates.",
        source_version="2025-v1",
        license="Open government licence",
        supports_joint_outcome=joint,
    )


def estimate(
    outcome: str,
    probability: float,
    *,
    predictors: dict[str, str] | None = None,
    joint: bool = False,
) -> PipelineTransitionEstimate:
    return PipelineTransitionEstimate(
        id=f"estimate-{outcome}",
        pipeline_attempt_id=f"attempt-{outcome}",
        outcome_id=outcome,
        conditioning_id="friday-adults",
        place="CHN",
        time_unit="friday",
        predictor_values=predictors or {},
        condition_values={},
        probability=probability,
        ci_low=max(0, probability - 0.35),
        ci_high=min(1, probability + 0.35),
        population="Chinese adults",
        reasoning="The app research pipeline synthesized the reported activity rate.",
        assumptions=("The published population applies to the requested Friday context.",),
        method="joint_outcome_synthesis" if joint else "source_synthesis",
        sources=(source(joint=joint),),
        selected_source_ids=("survey-report",),
        search_log=(
            PipelineResearchLog(
                sequence=1,
                origin="automatic",
                language="zh",
                engine="National Bureau of Statistics of China",
                query_or_source="中国 周五 社交活动 调查",
                source_kind="official_statistics",
                outcome="candidate",
                source_ids=("survey-report",),
            ),
        ),
        pipeline_provider="openai_cli",
        pipeline_model="gpt-6.1-sol",
        prompt_version="markov-transition-research-v1",
    )


def measured(outcome: str, probability: float) -> TransitionEvidence:
    return TransitionEvidence(
        id=f"measured-{outcome}",
        kind="measured_joint",
        outcome_id=outcome,
        conditioning_id="friday-adults",
        place="CHN",
        time_unit="friday",
        probability=probability,
        ci_low=max(0, probability - 0.05),
        ci_high=min(1, probability + 0.05),
        sample_size=2_000,
        population="Chinese adults",
        provenance=Evidence(
            source="Weighted time-use survey",
            version="2025-v1",
            status="present",
            uncertainty=0.1,
            source_date="2025-03-10",
        ),
    )


def test_pipeline_estimates_compile_as_draft_executable_evidence_with_warnings():
    compiled = compile_program(
        program(),
        EvidenceCatalog(
            estimated_transition=[
                estimate("stay-home", 0.6),
                estimate("go-out", 0.4),
            ]
        ),
        CompilationContext(place="CHN", time_unit="friday"),
    )

    assert compiled.executable
    assert not compiled.issues
    assert len(compiled.warnings) == 2
    assert {warning.code for warning in compiled.warnings} == {
        "estimated_probability_evidence"
    }
    assert {item.evidence_kind for item in compiled.probabilities} == {
        "pipeline_estimate"
    }
    assert all(item.estimate.review_state == "draft" for item in compiled.probabilities)
    assert all(item.ci_high - item.ci_low >= 0.3 for item in compiled.probabilities)


def test_measured_evidence_has_priority_over_pipeline_estimates():
    compiled = compile_program(
        program(),
        EvidenceCatalog(
            transition=[measured("stay-home", 0.7), measured("go-out", 0.3)],
            estimated_transition=[estimate("stay-home", 0.6), estimate("go-out", 0.4)],
        ),
        CompilationContext(place="CHN", time_unit="friday"),
    )

    assert compiled.executable
    assert not compiled.warnings
    assert {item.evidence_kind for item in compiled.probabilities} == {
        "measured_joint"
    }
    assert [item.probability for item in compiled.probabilities] == [0.7, 0.3]


def test_independence_products_and_unlinked_mbti_estimates_are_rejected():
    payload = estimate("go-out", 0.4).model_dump(mode="python")
    payload["method"] = "independence_product"
    with pytest.raises(ValidationError):
        PipelineTransitionEstimate.model_validate(payload)

    with pytest.raises(ValidationError, match="joint outcome"):
        estimate("go-out", 0.4, predictors={"mbti": "ENFP"})


def test_joint_mbti_pipeline_estimate_can_execute_but_remains_estimated():
    compiled = compile_program(
        program(["mbti"]),
        EvidenceCatalog(
            estimated_transition=[
                estimate(
                    "stay-home",
                    0.6,
                    predictors={"mbti": "ENFP"},
                    joint=True,
                ),
                estimate(
                    "go-out",
                    0.4,
                    predictors={"mbti": "ENFP"},
                    joint=True,
                ),
            ]
        ),
        CompilationContext(
            place="CHN",
            time_unit="friday",
            strata={"mbti": "ENFP"},
        ),
    )

    assert compiled.executable
    assert len(compiled.warnings) == 2
    assert all(item.provenance.status == "literature_estimate" for item in compiled.probabilities)


def test_rust_request_marks_pipeline_estimates_as_default_estimated():
    markov_program = program()
    compiled = compile_program(
        markov_program,
        EvidenceCatalog(
            estimated_transition=[
                estimate("stay-home", 0.6),
                estimate("go-out", 0.4),
            ]
        ),
        CompilationContext(place="CHN", time_unit="friday"),
    )
    request = compiled_markov_request(
        markov_program,
        compiled,
        seed=12,
        ticks=1,
        tick_hours=1,
        start_weekday=4,
        places=[{"id": "CHN", "state": {}}],
        agents={
            "module": ["daily-choice"],
            "state": ["decide"],
            "place": [0],
            "traits": {},
            "memory": {},
        },
    )

    provenance = request["modules"][0]["transitions"][0]["rules"][0]["provenance"]
    assert provenance["status"] == "default_estimated"
    assert provenance["evidence_kind"] == "pipeline_estimate"
    assert provenance["ci_high"] - provenance["ci_low"] >= 0.3
    result = RustCoreClient().run_agents(request)
    assert result["transition_evidence"][0]["provenance"]["status"] == "default_estimated"
