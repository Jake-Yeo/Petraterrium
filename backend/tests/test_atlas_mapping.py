from types import SimpleNamespace

from petraterrium.atlas import llm
from petraterrium.atlas.contracts import ColumnMapping, MappingProposal
from petraterrium.atlas.database import AtlasStore


def test_llm_proposals_are_scoped_cached_and_never_write_observations(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "FAKE-test-key")
    calls = []

    class Client:
        def __init__(self, **kwargs):
            self.responses = self

        def parse(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                output_parsed=MappingProposal(
                    mappings=[
                        ColumnMapping(
                            column="hh_mean",
                            target="household_size",
                            ambiguous=False,
                            reason="Proposed mean",
                        )
                    ]
                ),
                usage=SimpleNamespace(input_tokens=30, output_tokens=20),
            )

    monkeypatch.setattr(llm, "OpenAI", Client)
    store = AtlasStore(tmp_path / "atlas.sqlite")
    args = (["hh_mean"], [{"hh_mean": 2}], True)
    first, audit = llm.propose_mapping(store, "run-a", *args)
    cached, _ = llm.propose_mapping(store, "run-a", *args)
    llm.propose_mapping(store, "run-b", *args)
    assert first == cached and len(calls) == 2
    assert audit.provider == "openai" and audit.prompt_version == llm.PROMPT_VERSION
    assert calls[0]["store"] is False
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0


def test_failed_llm_mapping_does_not_cache_a_permanent_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "FAKE-test-key")
    attempts = []

    class Client:
        def __init__(self, **kwargs):
            self.responses = self

        def parse(self, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("FAKE provider failure")
            return SimpleNamespace(
                output_parsed=MappingProposal(
                    mappings=[ColumnMapping(column="household_size", target="household_size")]
                ),
                usage=None,
            )

    monkeypatch.setattr(llm, "OpenAI", Client)
    store = AtlasStore(tmp_path / "atlas.sqlite")
    args = (store, "run-a", ["household_size"], [{"household_size": 2}], True)
    _, failed = llm.propose_mapping(*args)
    _, recovered = llm.propose_mapping(*args)
    assert failed.provider == "exact-headers" and recovered.provider == "openai"
    assert len(attempts) == 2
