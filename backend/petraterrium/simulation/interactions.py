from __future__ import annotations

import hashlib
import heapq
import json
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date
from math import ceil
from threading import RLock
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .interaction_trees import InteractionPathStep

InteractionChannel = Literal["in_person", "phone_message", "online"]
InteractionDirection = Literal["either", "initiator", "target"]
FactorStatus = Literal[
    "measured_joint",
    "fitted_model",
    "default_estimated",
    "approved_estimate",
    "unknown",
    "label_only",
    "ambiguous",
    "legacy",
]


class InteractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class InteractionFactorProvenance(InteractionModel):
    source: str = Field(min_length=1)
    version: str = Field(min_length=1)
    source_date: date | None = None
    evidence_id: str | None = Field(default=None, min_length=1)
    licence: str | None = Field(default=None, min_length=1)
    status: FactorStatus
    uncertainty: float = Field(ge=0, allow_inf_nan=False)
    user_approved: bool = False

    @property
    def executable(self) -> bool:
        if self.status in {"measured_joint", "fitted_model"}:
            return self.source_date is not None and self.evidence_id is not None
        if self.status == "default_estimated":
            return self.evidence_id is not None
        return (
            self.status == "approved_estimate"
            and self.user_approved
            and self.source_date is not None
            and self.evidence_id is not None
        )


class InteractionFactor(InteractionModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    value: float = Field(ge=0, le=1, allow_inf_nan=False)
    provenance: InteractionFactorProvenance

    def rust_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "value": self.value,
            "provenance": {
                "source": self.provenance.source,
                "version": self.provenance.version,
                "status": self.provenance.status,
                "uncertainty": self.provenance.uncertainty,
            },
        }


class EvaluatedInteractionFactor(InteractionModel):
    kind: Literal["base", "relationship", "co_location", "place", "time", "context"]
    factor: InteractionFactor


class InteractionPlace(InteractionModel):
    id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    allows_in_person: bool
    states: dict[str, float] = Field(default_factory=dict)


class InteractionRelationship(InteractionModel):
    source_index: int = Field(ge=0)
    target_index: int = Field(ge=0)
    kind: str = Field(min_length=1)
    weight: float = Field(ge=-1, le=1, allow_inf_nan=False)
    trust: float = Field(ge=-1, le=1, allow_inf_nan=False)
    similarity: float = Field(ge=-1, le=1, allow_inf_nan=False)


class RelationshipProfile(InteractionModel):
    kind: str = Field(min_length=1)
    weight: float = Field(ge=-1, le=1, allow_inf_nan=False)
    trust: float = Field(ge=-1, le=1, allow_inf_nan=False)
    similarity: float = Field(ge=-1, le=1, allow_inf_nan=False)


class RelationshipKindEvidence(RelationshipProfile):
    provenance: InteractionFactorProvenance


class TimeFactorWindow(InteractionModel):
    weekdays: tuple[int, ...] = Field(min_length=1)
    start_hour: float = Field(ge=0, le=24, allow_inf_nan=False)
    end_hour: float = Field(ge=0, le=24, allow_inf_nan=False)
    factor: InteractionFactor

    @model_validator(mode="after")
    def valid_window(self):
        if self.start_hour == self.end_hour:
            raise ValueError("Interaction time window boundaries must differ")
        if any(weekday < 0 or weekday > 6 for weekday in self.weekdays):
            raise ValueError("Interaction weekdays must be between 0 and 6")
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("Interaction weekdays must be unique")
        return self


class AgentStateEffect(InteractionModel):
    recipient: Literal["initiator", "target"]
    state: str = Field(min_length=1)
    delta: float = Field(allow_inf_nan=False)
    minimum: float = Field(allow_inf_nan=False)
    maximum: float = Field(allow_inf_nan=False)
    scale_by: tuple[Literal["relationship_weight", "trust", "similarity"], ...] = ()

    @model_validator(mode="after")
    def valid_bounds(self):
        if self.minimum > self.maximum:
            raise ValueError("Interaction state effect bounds must be ordered")
        if len(set(self.scale_by)) != len(self.scale_by):
            raise ValueError("Interaction state effect scales must be unique")
        return self


class RelationshipStateEffect(InteractionModel):
    direction: Literal["initiator_to_target", "target_to_initiator"]
    field: Literal["weight", "trust", "similarity"]
    delta: float = Field(allow_inf_nan=False)
    minimum: float = Field(ge=-1, le=1, allow_inf_nan=False)
    maximum: float = Field(ge=-1, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_bounds(self):
        if self.minimum > self.maximum:
            raise ValueError("Interaction relationship effect bounds must be ordered")
        return self


class InteractionRule(InteractionModel):
    id: str = Field(min_length=1)
    source_action: str = Field(min_length=1)
    interaction_type: str = Field(min_length=1)
    channel: InteractionChannel
    max_targets_per_initiator: int = Field(ge=1)
    allowed_relationships: tuple[str, ...] = ()
    allowed_place_kinds: tuple[str, ...] = ()
    base_factor: InteractionFactor
    relationship_factors: dict[str, InteractionFactor] = Field(min_length=1)
    colocation_factors: dict[str, InteractionFactor] = Field(min_length=1)
    place_factors: dict[str, InteractionFactor] = Field(min_length=1)
    time_factors: tuple[TimeFactorWindow, ...] = Field(min_length=1)
    context_factors: tuple[InteractionFactor, ...] = ()
    unrelated_relationship: RelationshipProfile | None = None
    agent_effects: tuple[AgentStateEffect, ...] = ()
    relationship_effects: tuple[RelationshipStateEffect, ...] = ()
    interaction_tree_id: str | None = Field(default=None, min_length=1)
    interaction_tree_context: dict[str, str | float | bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_evidence_tables(self):
        if self.channel == "in_person" and "same_specific_place" not in self.colocation_factors:
            raise ValueError("In-person rules require a same-specific-place factor")
        if self.unrelated_relationship is not None and (
            self.unrelated_relationship.kind not in self.relationship_factors
        ):
            raise ValueError("Unrelated relationship profiles require a matching factor")
        return self

    def rust_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_action": self.source_action,
            "interaction_type": self.interaction_type,
            "channel": self.channel,
            "max_targets_per_initiator": self.max_targets_per_initiator,
            "allowed_relationships": list(self.allowed_relationships),
            "allowed_place_kinds": list(self.allowed_place_kinds),
            "base_factor": self.base_factor.rust_payload(),
            "relationship_factors": {
                key: value.rust_payload() for key, value in self.relationship_factors.items()
            },
            "colocation_factors": {
                key: value.rust_payload() for key, value in self.colocation_factors.items()
            },
            "place_factors": {
                key: value.rust_payload() for key, value in self.place_factors.items()
            },
            "time_factors": [
                {
                    "weekdays": list(window.weekdays),
                    "start_hour": window.start_hour,
                    "end_hour": window.end_hour,
                    "factor": window.factor.rust_payload(),
                }
                for window in self.time_factors
            ],
            "context_factors": [factor.rust_payload() for factor in self.context_factors],
            "unrelated_relationship": (
                self.unrelated_relationship.model_dump(mode="json")
                if self.unrelated_relationship is not None
                else None
            ),
            "agent_effects": [effect.model_dump(mode="json") for effect in self.agent_effects],
            "relationship_effects": [
                effect.model_dump(mode="json") for effect in self.relationship_effects
            ],
            "interaction_tree_id": self.interaction_tree_id,
            "interaction_tree_context": self.interaction_tree_context,
        }


class InteractionProgramDefinition(InteractionModel):
    version: str = Field(min_length=1)
    status: Literal["draft", "confirmed"]
    relationship_evidence: tuple[RelationshipKindEvidence, ...] = ()
    rules: tuple[InteractionRule, ...] = ()

    @model_validator(mode="after")
    def valid_program(self):
        rule_ids = [rule.id for rule in self.rules]
        if len(set(rule_ids)) != len(rule_ids):
            raise ValueError("Interaction rule IDs must be unique")
        relationship_kinds = [item.kind for item in self.relationship_evidence]
        if len(set(relationship_kinds)) != len(relationship_kinds):
            raise ValueError("Interaction relationship evidence kinds must be unique")
        if self.status == "confirmed":
            if not self.rules:
                raise ValueError("A confirmed interaction program requires at least one rule")
            evidence_by_kind = {item.kind: item for item in self.relationship_evidence}
            blocked_relationships = [
                item.kind for item in self.relationship_evidence if not item.provenance.executable
            ]
            if blocked_relationships:
                raise ValueError(
                    "Confirmed interaction relationship evidence is blocked: "
                    + ", ".join(sorted(blocked_relationships))
                )
            for rule in self.rules:
                factors = [
                    rule.base_factor,
                    *rule.relationship_factors.values(),
                    *rule.colocation_factors.values(),
                    *rule.place_factors.values(),
                    *(window.factor for window in rule.time_factors),
                    *rule.context_factors,
                ]
                unavailable = [factor.id for factor in factors if not factor.provenance.executable]
                if unavailable:
                    labels = ", ".join(sorted(unavailable))
                    raise ValueError(
                        f"Confirmed interaction rule {rule.id} has non-executable factors: {labels}"
                    )
                missing_relationship_factors = sorted(
                    set(rule.allowed_relationships) - rule.relationship_factors.keys()
                )
                if missing_relationship_factors:
                    raise ValueError(
                        f"Confirmed interaction rule {rule.id} has no probability factor for: "
                        + ", ".join(missing_relationship_factors)
                    )
                relationship_kinds = set(rule.relationship_factors)
                relationship_kinds.update(rule.allowed_relationships)
                missing_relationship_evidence = sorted(relationship_kinds - evidence_by_kind.keys())
                if missing_relationship_evidence:
                    raise ValueError(
                        f"Confirmed interaction rule {rule.id} has no relationship evidence for: "
                        + ", ".join(missing_relationship_evidence)
                    )
                if rule.unrelated_relationship is not None:
                    profile = evidence_by_kind.get(rule.unrelated_relationship.kind)
                    expected = rule.unrelated_relationship
                    if profile is None or (
                        profile.weight,
                        profile.trust,
                        profile.similarity,
                    ) != (expected.weight, expected.trust, expected.similarity):
                        raise ValueError(
                            f"Confirmed interaction rule {rule.id} unrelated relationship "
                            "must match its registered relationship evidence"
                        )
        return self


class InteractionAgentColumns(InteractionModel):
    agent_ids: tuple[str, ...] = Field(min_length=1)
    place: tuple[int, ...]
    actions: tuple[tuple[str, ...], ...]
    states: dict[str, tuple[float, ...]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def aligned_columns(self):
        size = len(self.agent_ids)
        if len(set(self.agent_ids)) != size:
            raise ValueError("Interaction agent IDs must be unique")
        if len(self.place) != size or len(self.actions) != size:
            raise ValueError("Interaction agent columns must have equal lengths")
        if any(len(values) != size for values in self.states.values()):
            raise ValueError("Interaction state columns must have one value per agent")
        return self


class InteractionRequest(InteractionModel):
    seed: int = Field(ge=0)
    tick: int = Field(ge=1)
    hour: float = Field(ge=0, lt=24, allow_inf_nan=False)
    weekday: int = Field(ge=0, le=6)
    agents: InteractionAgentColumns
    places: tuple[InteractionPlace, ...] = Field(min_length=1)
    relationships: tuple[InteractionRelationship, ...] = ()
    trees: dict[str, Any] = Field(default_factory=dict)
    rules: tuple[InteractionRule, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_references(self):
        agent_count = len(self.agents.agent_ids)
        if any(place >= len(self.places) for place in self.agents.place):
            raise ValueError("Interaction agent place index is outside the place table")
        endpoints = set()
        for relationship in self.relationships:
            pair = (relationship.source_index, relationship.target_index)
            if max(pair) >= agent_count or relationship.source_index == relationship.target_index:
                raise ValueError("Interaction relationship endpoints must name two agents")
            if pair in endpoints:
                raise ValueError("Directed interaction relationships must be unique")
            endpoints.add(pair)
        if len({rule.id for rule in self.rules}) != len(self.rules):
            raise ValueError("Interaction rule IDs must be unique")
        missing_trees = sorted(
            {
                rule.interaction_tree_id
                for rule in self.rules
                if rule.interaction_tree_id is not None
                and rule.interaction_tree_id not in self.trees
            }
        )
        if missing_trees:
            raise ValueError(
                f"Interaction rules reference missing trees: {', '.join(missing_trees)}"
            )
        predictive_statuses = {
            "measured_joint",
            "fitted_model",
            "default_estimated",
            "approved_estimate",
        }
        incomplete_factors = sorted(
            factor.id
            for rule in self.rules
            for factor in (
                rule.base_factor,
                *rule.relationship_factors.values(),
                *rule.colocation_factors.values(),
                *rule.place_factors.values(),
                *(window.factor for window in rule.time_factors),
                *rule.context_factors,
            )
            if factor.provenance.status in predictive_statuses and not factor.provenance.executable
        )
        if incomplete_factors:
            raise ValueError(
                "Executable interaction factors require source date, evidence id, and "
                "explicit approval for estimates: " + ", ".join(incomplete_factors)
            )
        return self

    def rust_payload(self) -> dict[str, Any]:
        value = self.model_dump(mode="json", exclude={"rules"})
        value["rules"] = [rule.rust_payload() for rule in self.rules]
        return value


class AppliedStateDelta(InteractionModel):
    agent_id: str = Field(min_length=1)
    state: str = Field(min_length=1)
    before: float = Field(allow_inf_nan=False)
    delta: float = Field(allow_inf_nan=False)
    after: float = Field(allow_inf_nan=False)


class AppliedRelationshipDelta(InteractionModel):
    source_agent_id: str = Field(min_length=1)
    target_agent_id: str = Field(min_length=1)
    field: Literal["weight", "trust", "similarity"]
    before: float = Field(allow_inf_nan=False)
    delta: float = Field(allow_inf_nan=False)
    after: float = Field(allow_inf_nan=False)


class InteractionListItem(InteractionModel):
    event_id: str
    tick: int = Field(ge=1)
    hour: float = Field(ge=0, lt=24)
    weekday: int = Field(ge=0, le=6)
    rule_id: str
    interaction_type: str
    channel: InteractionChannel
    initiator_id: str
    target_id: str
    place_id: str
    relationship_type: str
    probability: float = Field(ge=0, le=1)
    effect_count: int = Field(ge=0)


class InteractionTreeTrace(InteractionModel):
    tree_id: str
    tree_version: str
    outcome_node: str
    outcome: str
    path: tuple[InteractionPathStep, ...]


class InteractionEventDetail(InteractionListItem):
    relationship_weight: float = Field(ge=-1, le=1)
    trust: float = Field(ge=-1, le=1)
    similarity: float = Field(ge=-1, le=1)
    factors: tuple[EvaluatedInteractionFactor, ...] = Field(min_length=2)
    state_deltas: tuple[AppliedStateDelta, ...]
    relationship_deltas: tuple[AppliedRelationshipDelta, ...]
    interaction_tree: InteractionTreeTrace | None = None


class InteractionFacets(InteractionModel):
    agents: tuple[str, ...]
    interaction_types: tuple[str, ...]
    channels: tuple[InteractionChannel, ...]
    relationships: tuple[str, ...]
    places: tuple[str, ...]


class InteractionBreakdown(InteractionModel):
    by_relationship: dict[str, int]
    by_channel: dict[str, int]
    by_place: dict[str, int]
    by_counterparty: dict[str, int]


class InteractionQuery(InteractionModel):
    search: str = ""
    agent_id: str | None = None
    direction: InteractionDirection = "either"
    interaction_type: str | None = None
    channel: InteractionChannel | None = None
    relationship_type: str | None = None
    place_id: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class InteractionPage(InteractionModel):
    items: tuple[InteractionListItem, ...]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    pages: int = Field(ge=0)
    facets: InteractionFacets
    breakdown: InteractionBreakdown


class InteractionCatalog:
    def __init__(self, events: Sequence[InteractionEventDetail]):
        by_id = {event.event_id: event for event in events}
        if len(by_id) != len(events):
            raise ValueError("Interaction event IDs must be unique")
        self._events = tuple(
            sorted(events, key=lambda event: (event.tick, event.event_id), reverse=True)
        )
        self._by_id = by_id
        agent_ids = {
            agent_id
            for event in self._events
            for agent_id in (event.initiator_id, event.target_id)
        }
        self._facets = InteractionFacets(
            agents=tuple(sorted(agent_ids)),
            interaction_types=tuple(sorted({event.interaction_type for event in self._events})),
            channels=tuple(sorted({event.channel for event in self._events})),
            relationships=tuple(sorted({event.relationship_type for event in self._events})),
            places=tuple(sorted({event.place_id for event in self._events})),
        )

    @property
    def events(self) -> tuple[InteractionEventDetail, ...]:
        return self._events

    @classmethod
    def from_rust_output(
        cls,
        output: Mapping[str, Any],
    ) -> InteractionCatalog:
        raw_events = output.get("events", [])
        if not isinstance(raw_events, Sequence) or isinstance(raw_events, (str, bytes)):
            raise ValueError("Rust interaction output events must be a list")
        events = [cls._parse_event(raw, index) for index, raw in enumerate(raw_events)]
        return cls(events)

    @staticmethod
    def _parse_event(
        raw: Any,
        index: int,
    ) -> InteractionEventDetail:
        if not isinstance(raw, Mapping):
            raise ValueError(f"Rust interaction event {index} must be an object")
        identity = hashlib.sha256(
            json.dumps(
                raw,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()[:20]
        state_deltas = raw.get("state_deltas", [])
        relationship_deltas = raw.get("relationship_deltas", [])
        payload = dict(raw)
        payload.update(
            {
                "event_id": identity,
                "effect_count": len(state_deltas) + len(relationship_deltas),
            }
        )
        payload.pop("initiator_index", None)
        payload.pop("target_index", None)
        payload.pop("place_index", None)
        return InteractionEventDetail.model_validate(payload)

    def query(self, query: InteractionQuery) -> InteractionPage:
        events = [event for event in self._events if self._matches(event, query)]
        total = len(events)
        start = (query.page - 1) * query.page_size
        end = start + query.page_size
        fields = InteractionListItem.model_fields
        items = tuple(
            InteractionListItem(**{field: getattr(event, field) for field in fields})
            for event in events[start:end]
        )
        return InteractionPage(
            items=items,
            total=total,
            page=query.page,
            page_size=query.page_size,
            pages=ceil(total / query.page_size) if total else 0,
            facets=self._facets,
            breakdown=self._breakdown(events, query.agent_id),
        )

    def detail(self, event_id: str) -> InteractionEventDetail:
        try:
            return self._by_id[event_id]
        except KeyError as error:
            raise KeyError(f"Unknown interaction event {event_id}") from error

    @staticmethod
    def _matches(event: InteractionEventDetail, query: InteractionQuery) -> bool:
        if query.agent_id:
            if query.direction == "initiator" and event.initiator_id != query.agent_id:
                return False
            if query.direction == "target" and event.target_id != query.agent_id:
                return False
            if query.direction == "either" and query.agent_id not in {
                event.initiator_id,
                event.target_id,
            }:
                return False
        if query.interaction_type and event.interaction_type != query.interaction_type:
            return False
        if query.channel and event.channel != query.channel:
            return False
        if query.relationship_type and event.relationship_type != query.relationship_type:
            return False
        if query.place_id and event.place_id != query.place_id:
            return False
        search = query.search.casefold().strip()
        if search and not any(
            search in value.casefold()
            for value in (
                event.initiator_id,
                event.target_id,
                event.interaction_type,
                event.place_id,
                event.relationship_type,
            )
        ):
            return False
        return True

    def _breakdown(
        self,
        events: Sequence[InteractionEventDetail],
        selected_agent: str | None,
    ) -> InteractionBreakdown:
        counterparties = Counter()
        if selected_agent:
            for event in events:
                other_id = (
                    event.target_id if event.initiator_id == selected_agent else event.initiator_id
                )
                counterparties[other_id] += 1
        return InteractionBreakdown(
            by_relationship=dict(Counter(event.relationship_type for event in events)),
            by_channel=dict(Counter(event.channel for event in events)),
            by_place=dict(Counter(event.place_id for event in events)),
            by_counterparty=dict(counterparties),
        )


class StreamingInteractionCatalog:
    def __init__(self, events: Callable[[], Iterable[Mapping[str, Any]]]):
        self._events = events

    def query(self, query: InteractionQuery) -> InteractionPage:
        agents = set()
        interaction_types = set()
        channels = set()
        relationships = set()
        places = set()
        relationship_counts = Counter()
        channel_counts = Counter()
        place_counts = Counter()
        counterparty_counts = Counter()
        total = 0
        end = query.page * query.page_size
        retained: list[tuple[tuple[int, str], int, InteractionEventDetail]] = []
        for index, raw in enumerate(self._events()):
            event = InteractionCatalog._parse_event(raw, index)
            agents.update((event.initiator_id, event.target_id))
            interaction_types.add(event.interaction_type)
            channels.add(event.channel)
            relationships.add(event.relationship_type)
            places.add(event.place_id)
            if not InteractionCatalog._matches(event, query):
                continue
            total += 1
            relationship_counts[event.relationship_type] += 1
            channel_counts[event.channel] += 1
            place_counts[event.place_id] += 1
            if query.agent_id:
                other_id = (
                    event.target_id
                    if event.initiator_id == query.agent_id
                    else event.initiator_id
                )
                counterparty_counts[other_id] += 1
            retained_event = ((event.tick, event.event_id), index, event)
            if len(retained) < end:
                heapq.heappush(retained, retained_event)
            elif retained_event[:2] > retained[0][:2]:
                heapq.heapreplace(retained, retained_event)
        start = (query.page - 1) * query.page_size
        selected = [
            entry[2]
            for entry in sorted(retained, key=lambda entry: entry[:2], reverse=True)[
                start:end
            ]
        ]
        fields = InteractionListItem.model_fields
        return InteractionPage(
            items=tuple(
                InteractionListItem(
                    **{field: getattr(event, field) for field in fields}
                )
                for event in selected
            ),
            total=total,
            page=query.page,
            page_size=query.page_size,
            pages=ceil(total / query.page_size) if total else 0,
            facets=InteractionFacets(
                agents=tuple(sorted(agents)),
                interaction_types=tuple(sorted(interaction_types)),
                channels=tuple(sorted(channels)),
                relationships=tuple(sorted(relationships)),
                places=tuple(sorted(places)),
            ),
            breakdown=InteractionBreakdown(
                by_relationship=dict(relationship_counts),
                by_channel=dict(channel_counts),
                by_place=dict(place_counts),
                by_counterparty=dict(counterparty_counts),
            ),
        )

    def detail(self, event_id: str) -> InteractionEventDetail:
        for index, raw in enumerate(self._events()):
            event = InteractionCatalog._parse_event(raw, index)
            if event.event_id == event_id:
                return event
        raise KeyError(f"Unknown interaction event {event_id}")


class InteractionRunRegistry:
    def __init__(self):
        self._catalogs: dict[
            str, InteractionCatalog | StreamingInteractionCatalog
        ] = {}
        self._loaders: dict[str, Callable[[], Mapping[str, Any]]] = {}
        self._lock = RLock()

    def record(
        self,
        run_id: str,
        rust_output: Mapping[str, Any],
    ) -> InteractionCatalog:
        catalog = InteractionCatalog.from_rust_output(rust_output)
        with self._lock:
            existing = self._catalogs.get(run_id)
            if isinstance(existing, InteractionCatalog):
                events = {event.event_id: event for event in existing.events}
                events.update({event.event_id: event for event in catalog.events})
                catalog = InteractionCatalog(tuple(events.values()))
            self._catalogs[run_id] = catalog
            self._loaders.pop(run_id, None)
        return catalog

    def register_loader(
        self,
        run_id: str,
        loader: Callable[[], Mapping[str, Any]],
    ) -> None:
        with self._lock:
            if run_id not in self._catalogs:
                self._loaders[run_id] = loader

    def register_event_loader(
        self,
        run_id: str,
        loader: Callable[[], Iterable[Mapping[str, Any]]],
    ) -> None:
        with self._lock:
            if run_id not in self._catalogs:
                self._catalogs[run_id] = StreamingInteractionCatalog(loader)
                self._loaders.pop(run_id, None)

    def catalog(
        self, run_id: str
    ) -> InteractionCatalog | StreamingInteractionCatalog:
        with self._lock:
            catalog = self._catalogs.get(run_id)
            loader = self._loaders.get(run_id)
            if catalog is not None:
                return catalog
            if loader is not None:
                loader()
                catalog = self._catalogs.get(run_id)
                if catalog is not None:
                    return catalog
        raise KeyError(f"No interactions recorded for run {run_id}")

    def discard(self, run_id: str) -> None:
        with self._lock:
            self._catalogs.pop(run_id, None)
            self._loaders.pop(run_id, None)


def create_interaction_router(registry: InteractionRunRegistry) -> APIRouter:
    router = APIRouter(prefix="/simulation/runs", tags=["simulation-interactions"])

    @router.get("/{run_id}/interactions", response_model=InteractionPage)
    def list_interactions(
        run_id: str,
        search: str = "",
        agent_id: str | None = None,
        direction: InteractionDirection = "either",
        interaction_type: str | None = None,
        channel: InteractionChannel | None = None,
        relationship_type: str | None = None,
        place_id: str | None = None,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
    ) -> InteractionPage:
        try:
            catalog = registry.catalog(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return catalog.query(
            InteractionQuery(
                search=search,
                agent_id=agent_id,
                direction=direction,
                interaction_type=interaction_type,
                channel=channel,
                relationship_type=relationship_type,
                place_id=place_id,
                page=page,
                page_size=page_size,
            )
        )

    @router.get("/{run_id}/interactions/{event_id}", response_model=InteractionEventDetail)
    def interaction_detail(run_id: str, event_id: str) -> InteractionEventDetail:
        try:
            return registry.catalog(run_id).detail(event_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    return router
