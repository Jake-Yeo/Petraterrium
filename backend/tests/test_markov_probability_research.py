import subprocess
import sys

from fastapi.testclient import TestClient

from petraterrium.ai_provider import AIProviderError
from petraterrium.main import create_app
from petraterrium.markov import (
    CompilationContext,
    EvidenceCatalog,
    MarkovModule,
    MarkovProgram,
    ModuleInput,
    ModuleState,
    ModuleTransition,
    PipelineEstimateSource,
    PipelineTransitionEstimate,
    ProbabilityQuery,
    ProgramExit,
    TransitionCondition,
    compile_program,
)


def test_simulation_registry_import_does_not_cycle():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from petraterrium.simulation.registry_store import "
                "SimulationRegistryStore; print(SimulationRegistryStore.__name__)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "SimulationRegistryStore"


class UnavailableSynthesisProvider:
    def selected_identity(self):
        return "openai_cli", "test-cli-model"

    def generate_structured(
        self,
        user_prompt,
        response_format,
        *,
        system_prompt,
        prompt_version,
    ):
        raise AIProviderError("test_unavailable", "Synthesis unavailable in this test")


class ChinaOpinionResearchProvider:
    def __init__(self):
        self.steps = []

    def search_transition(self, step, request):
        self.steps.append(step)
        if step.language != "zh" or step.engine != "Baidu":
            return []
        if step.source_kind != "online_opinion":
            return []
        return [
            PipelineEstimateSource(
                id=f"baidu-{request.outcome_id}",
                title=f"Baidu discussion lead for {request.outcome_description}",
                url="https://www.baidu.com/",
                source_kind="online_opinion",
                language="zh",
                excerpt="A public discussion lead relevant to the requested choice.",
                source_version="retrieved-2026-10-27",
                license="Publisher terms apply",
            )
        ]


def request_payload(outcome_id: str) -> dict:
    descriptions = {
        "stay_home": "An adult stays at home on Friday evening",
        "go_out": "An adult goes out on Friday evening",
    }
    return {
        "transition_id": f"choose_{outcome_id}",
        "outcome_id": outcome_id,
        "outcome_description": descriptions[outcome_id],
        "outcomes": [
            {
                "id": identifier,
                "description": description,
                "localized_descriptions": {
                    "zh": "周五晚上待在家里"
                    if identifier == "stay_home"
                    else "周五晚上外出"
                },
            }
            for identifier, description in descriptions.items()
        ],
        "conditioning_id": "friday_adults",
        "conditioning_description": "Adults deciding what to do on Friday evening",
        "localized_conditioning_descriptions": {"zh": "成年人周五晚上的活动选择"},
        "place": {
            "level": "country",
            "place_id": "CHN",
            "place_label": "China",
            "population": 1_409_000_000,
            "country_code": "CN",
            "local_names": {"zh": "中国"},
            "dominant_languages": ["zh", "en"],
        },
        "time_unit": "friday",
        "condition_values": {"weekday": "friday"},
    }


def program() -> MarkovProgram:
    module = MarkovModule(
        id="friday-choice",
        version="1",
        name="Friday choice",
        entry_state="decide",
        exit_states=["stay_home", "go_out"],
        inputs=[
            ModuleInput(id="place", kind="place", value_type="identifier"),
            ModuleInput(id="day", kind="time", value_type="categorical"),
        ],
        states=[
            ModuleState(id="decide"),
            ModuleState(id="stay_home"),
            ModuleState(id="go_out"),
        ],
        transitions=[
            ModuleTransition(
                id=f"choose_{outcome_id}",
                from_state="decide",
                to_state=outcome_id,
                condition=TransitionCondition(mode="always"),
                probability=ProbabilityQuery(
                    outcome_id=outcome_id,
                    conditioning_id="friday_adults",
                    place_input="place",
                    time_input="day",
                ),
            )
            for outcome_id in ("stay_home", "go_out")
        ],
    )
    return MarkovProgram(
        id="friday-program",
        version="1",
        entry_module=module.id,
        modules=[module],
        terminal_exits=[
            ProgramExit(module_id=module.id, state_id=outcome_id)
            for outcome_id in ("stay_home", "go_out")
        ],
    )


def test_probability_research_runs_local_first_and_returns_executable_fallback(tmp_path):
    research_provider = ChinaOpinionResearchProvider()
    application = create_app(
        atlas_path=tmp_path / "atlas.sqlite3",
        ai_provider=UnavailableSynthesisProvider(),
        markov_research_provider=research_provider,
    )

    with TestClient(application) as client:
        estimates = [
            PipelineTransitionEstimate.model_validate_json(
                client.post(
                    "/markov-builder/probability-research",
                    json=request_payload(outcome_id),
                ).content
            )
            for outcome_id in ("stay_home", "go_out")
        ]

    first_log = estimates[0].search_log[0]
    assert first_log.language == "zh"
    assert first_log.engine == "National Bureau of Statistics of China"
    assert first_log.source_kind == "official_statistics"
    assert "中国" in first_log.query_or_source
    assert "周五" in first_log.query_or_source
    assert any(
        entry.language == "zh" and entry.engine == "Baidu"
        for entry in estimates[0].search_log
    )
    assert research_provider.steps[0].language == "zh"
    assert research_provider.steps[0].engine == "National Bureau of Statistics of China"
    assert all(estimate.review_state == "draft" for estimate in estimates)
    assert all(estimate.probability == 0.5 for estimate in estimates)
    assert all((estimate.ci_low, estimate.ci_high) == (0, 1) for estimate in estimates)
    assert all(estimate.pipeline_provider == "openai_cli" for estimate in estimates)
    assert all(estimate.pipeline_model == "test-cli-model" for estimate in estimates)
    assert all(estimate.selected_source_ids[0].startswith("baidu-") for estimate in estimates)
    assert all(estimate.sources[0].retrieved_date == "2026-10-27" for estimate in estimates)

    compiled = compile_program(
        program(),
        EvidenceCatalog(estimated_transition=estimates),
        CompilationContext(
            place="CHN",
            time_unit="friday",
            conditions={"weekday": "friday"},
        ),
    )

    assert compiled.executable
    assert not compiled.issues
    assert len(compiled.warnings) == 2
    assert {item.evidence_kind for item in compiled.probabilities} == {
        "pipeline_estimate"
    }
