import hashlib
import json
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from .dsl import DSLConfig, Evidence


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
    provider: Callable | None,
    evidence_table: EvidenceTable,
) -> LeaderDecision:
    if provider:
        raw = provider(leader, aggregated_state, week)
        provider_name = getattr(provider, "__name__", "structured-provider")
    else:
        action = dsl.leader_actions[week % len(dsl.leader_actions)] if dsl.leader_actions else None
        raw = {
            "action": action.id if action else "no_action",
            "target": dsl.population.places[0],
            "parameters": {},
        }
        provider_name = "deterministic-rule-leader"
    action_id = str(raw["action"])
    evidence = evidence_table.resolve(action_id)
    return LeaderDecision(
        leader_id=str(leader.get("id", "leader-0")),
        week=week,
        action=action_id,
        target=raw.get("target"),
        parameters={key: float(value) for key, value in raw.get("parameters", {}).items()},
        evidence=evidence,
        provider=provider_name,
        prompt_version="leader-structured-action-v1",
    )


def anchor_run(
    config: DSLConfig,
    weeks: int,
    provider: Callable | None = None,
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


def influencer_text(influencer: dict, context: dict, provider: Callable | None = None) -> str:
    if provider:
        return str(provider(influencer, context))
    identity = str(influencer.get("id", "influencer"))
    topic = str(context.get("topic", "recorded event"))
    return f"FAKE deterministic message from {identity} about {topic}"


def decide_weekly(snapshot) -> dict[str, float]:
    return {}
