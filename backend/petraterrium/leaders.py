import hashlib
import json
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from .ai_settings import AISourceProvenance
from .dsl import DSLConfig, Evidence
from .llm_gateway import SelectedAIProvider

LEADER_PROMPT_VERSION = "leader-structured-action-v2"
LEADER_SYSTEM_PROMPT = (
    "Choose one allowed leader action from the supplied simulation state. Return only the "
    "structured action. Do not alter agents or reported metrics."
)
INFLUENCER_PROMPT_VERSION = "influencer-message-v2"
INFLUENCER_SYSTEM_PROMPT = (
    "Write the requested in-simulation influencer message from the supplied recorded context. "
    "Do not invent measurements or events."
)


class LeaderModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LeaderDecision(LeaderModel):
    leader_id: str
    week: int
    action: str
    target: str | None
    parameters: dict[str, float]
    evidence: Evidence
    provider: str
    prompt_version: str
    ai_provenance: AISourceProvenance | None = None


class LeaderActionProposal(LeaderModel):
    action: str
    target: str | None = None
    parameters: dict[str, float]


class InfluencerMessage(LeaderModel):
    text: str
    provider: str
    prompt_version: str
    ai_provenance: AISourceProvenance | None = None


class AnchorTimeline(LeaderModel):
    config_id: str
    evidence_version: str
    population_version: str
    timeline: list[LeaderDecision]


class EvidenceTable:
    def __init__(self, entries: dict[str, Evidence] | None = None):
        self.entries = dict(entries or {})
        self.research_calls = 0

    @property
    def version(self) -> str:
        payload = {key: value.model_dump() for key, value in sorted(self.entries.items())}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]

    def resolve(
        self,
        action: str,
        researcher: Callable[[str], Evidence] | None = None,
    ) -> Evidence:
        if action in self.entries:
            return self.entries[action]
        if researcher is None:
            evidence = Evidence(
                source="No evidence-table entry",
                version=self.version,
                status="unknown",
                uncertainty=1,
            )
        else:
            self.research_calls += 1
            evidence = researcher(action)
        self.entries[action] = evidence
        return evidence


def leader_decision(
    leader: dict,
    aggregated_state: dict,
    week: int,
    dsl: DSLConfig,
    provider: Callable | SelectedAIProvider | None,
    evidence_table: EvidenceTable,
) -> LeaderDecision:
    provenance = None
    if provider is None:
        raise ValueError(
            "Leader decisions require the selected AI source or an explicit scripted provider"
        )
    if hasattr(provider, "generate_structured"):
        generation = provider.generate_structured(
            json.dumps(
                {
                    "leader": leader,
                    "aggregated_state": aggregated_state,
                    "week": week,
                    "allowed_actions": [
                        action.model_dump(mode="json") for action in dsl.leader_actions
                    ],
                },
                sort_keys=True,
            ),
            LeaderActionProposal,
            system_prompt=LEADER_SYSTEM_PROMPT,
            prompt_version=LEADER_PROMPT_VERSION,
        )
        raw = generation.output.model_dump(mode="python")
        provenance = generation.provenance
        provider_name = provenance.source_label
    else:
        raw = provider(leader, aggregated_state, week)
        provider_name = getattr(provider, "__name__", "structured-provider")
    action_id = str(raw["action"])
    allowed_action_ids = {action.id for action in dsl.leader_actions}
    if action_id not in allowed_action_ids and not (
        action_id == "no_action" and not allowed_action_ids
    ):
        raise ValueError(f"Leader provider returned unknown action {action_id!r}")
    evidence = evidence_table.resolve(action_id)
    return LeaderDecision(
        leader_id=str(leader.get("id", "leader-0")),
        week=week,
        action=action_id,
        target=raw.get("target"),
        parameters={key: float(value) for key, value in raw.get("parameters", {}).items()},
        evidence=evidence,
        provider=provider_name,
        prompt_version=LEADER_PROMPT_VERSION,
        ai_provenance=provenance,
    )


def anchor_run(
    config: DSLConfig,
    weeks: int,
    provider: Callable | SelectedAIProvider | None = None,
    evidence_table: EvidenceTable | None = None,
) -> AnchorTimeline:
    table = evidence_table or EvidenceTable()
    state = {"places": config.population.places, "systems": [item.id for item in config.systems]}
    timeline = [
        leader_decision({"id": "leader-0"}, state, week, config, provider, table)
        for week in range(weeks)
    ]
    return AnchorTimeline(
        config_id=config.id,
        evidence_version=table.version,
        population_version=config.population.version,
        timeline=timeline,
    )


def influencer_message(
    influencer: dict,
    context: dict,
    provider: Callable | SelectedAIProvider | None,
) -> InfluencerMessage:
    if provider is None:
        raise ValueError(
            "Influencer generation requires the selected AI source or an explicit scripted provider"
        )
    if hasattr(provider, "generate_text"):
        generation = provider.generate_text(
            json.dumps(
                {"influencer": influencer, "recorded_context": context},
                sort_keys=True,
            ),
            system_prompt=INFLUENCER_SYSTEM_PROMPT,
            prompt_version=INFLUENCER_PROMPT_VERSION,
        )
        return InfluencerMessage(
            text=generation.output,
            provider=generation.provenance.source_label,
            prompt_version=INFLUENCER_PROMPT_VERSION,
            ai_provenance=generation.provenance,
        )
    return InfluencerMessage(
        text=str(provider(influencer, context)),
        provider=getattr(provider, "__name__", "scripted-provider"),
        prompt_version=INFLUENCER_PROMPT_VERSION,
    )


def influencer_text(
    influencer: dict,
    context: dict,
    provider: Callable | SelectedAIProvider | None = None,
) -> str:
    return influencer_message(influencer, context, provider).text


def decide_weekly(snapshot) -> dict[str, float]:
    return {}
