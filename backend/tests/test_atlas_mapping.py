import pytest

from petraterrium.ai_provider import AIGeneration, AIProviderError
from petraterrium.ai_settings import AISourceProvenance
from petraterrium.atlas import llm
from petraterrium.atlas.contracts import ColumnMapping, MappingProposal
from petraterrium.atlas.database import AtlasStore


def source_provenance(prompt_version):
    return AISourceProvenance(
        source="openai_api",
        source_label="OpenAI API",
        model="test-api-model",
        generated_at="2026-10-27T12:00:00Z",
        prompt_version=prompt_version,
        input_tokens=30,
        output_tokens=20,
    )


def test_llm_proposals_are_scoped_cached_and_never_write_observations(tmp_path):
    calls = []

    class Provider:
        def generate_structured(
            self,
            user_prompt,
            response_format,
            *,
            system_prompt,
            prompt_version,
        ):
            calls.append((user_prompt, response_format, system_prompt, prompt_version))
            return AIGeneration(
                output=MappingProposal(
                    mappings=[
                        ColumnMapping(
                            column="hh_mean",
                            target="household_size",
                            ambiguous=False,
                            reason="Proposed mean",
                        )
                    ]
                ),
                provenance=source_provenance(prompt_version),
            )

    store = AtlasStore(tmp_path / "atlas.sqlite")
    args = (["hh_mean"], [{"hh_mean": 2}], True)
    provider = Provider()
    first, audit = llm.propose_mapping(store, "run-a", *args, provider)
    cached, _ = llm.propose_mapping(store, "run-a", *args, provider)
    llm.propose_mapping(store, "run-b", *args, provider)
    assert first == cached and len(calls) == 2
    assert audit.provider == "openai_api" and audit.prompt_version == llm.PROMPT_VERSION
    assert audit.model == "test-api-model"
    assert "2026-10-27T12:00:00+00:00 via OpenAI API" in audit.message
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0


def test_failed_llm_mapping_surfaces_and_does_not_cache_a_fallback(tmp_path):
    attempts = []

    class Provider:
        def generate_structured(
            self,
            user_prompt,
            response_format,
            *,
            system_prompt,
            prompt_version,
        ):
            attempts.append(1)
            if len(attempts) == 1:
                raise AIProviderError("api_failed", "FAKE provider failure")
            return AIGeneration(
                output=MappingProposal(
                    mappings=[ColumnMapping(column="household_size", target="household_size")]
                ),
                provenance=source_provenance(prompt_version),
            )

    store = AtlasStore(tmp_path / "atlas.sqlite")
    args = (store, "run-a", ["household_size"], [{"household_size": 2}], True)
    provider = Provider()
    with pytest.raises(AIProviderError, match="FAKE provider failure"):
        llm.propose_mapping(*args, provider)
    _, recovered = llm.propose_mapping(*args, provider)
    assert recovered.provider == "openai_api"
    assert len(attempts) == 2


def test_llm_mapping_requires_the_selected_source_even_with_an_environment_key(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    store = AtlasStore(tmp_path / "atlas.sqlite")

    with pytest.raises(AIProviderError, match="no fallback was attempted"):
        llm.propose_mapping(store, "run-a", ["income"], [{"income": 1}], True)
