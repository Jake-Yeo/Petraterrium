import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .dsl import DSLConfig


class EventModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Event(EventModel):
    event_id: str
    definition_id: str
    place: str
    day: int = Field(ge=0)
    metric: str
    previous_value: float
    value: float
    change: float
    severity: float = Field(ge=0)
    cause: str
    previous_event_id: str | None = None


class Story(EventModel):
    story_id: str
    event_id: str
    place: str
    day: int
    headline: str
    body: str
    metrics: dict[str, float]
    template: bool
    arc_id: str


class Cause(EventModel):
    name: str
    magnitude: float


class CausalDeepDive(EventModel):
    causes: list[Cause]
    total: float


def threshold_fired(direction: str, value: float, previous: float, threshold: float) -> bool:
    if direction == "above":
        return value >= threshold and previous < threshold
    if direction == "below":
        return value <= threshold and previous > threshold
    if direction == "increase":
        return value - previous >= threshold
    return previous - value >= threshold


def detect_events(
    dsl: DSLConfig,
    snapshot: dict[str, dict[str, float]],
    previous_snapshot: dict[str, dict[str, float]],
    day: int,
) -> list[Event]:
    events = []
    for place, metrics in sorted(snapshot.items()):
        previous_metrics = previous_snapshot.get(place, {})
        for definition in dsl.events:
            value = float(metrics.get(definition.metric, 0))
            previous = float(previous_metrics.get(definition.metric, 0))
            if not threshold_fired(definition.direction, value, previous, definition.threshold):
                continue
            raw_id = f"{dsl.id}:{definition.id}:{place}:{day}:{value}"
            events.append(
                Event(
                    event_id=hashlib.sha256(raw_id.encode()).hexdigest()[:20],
                    definition_id=definition.id,
                    place=place,
                    day=day,
                    metric=definition.metric,
                    previous_value=previous,
                    value=value,
                    change=value - previous,
                    severity=abs(value - previous),
                    cause=f"threshold:{definition.id}",
                )
            )
    return events


def plan_week(events: list[Event], user_interest: set[str] | None = None) -> list[Event]:
    interest = user_interest or set()
    return sorted(
        events,
        key=lambda event: (
            -(event.severity * (1.5 if event.metric in interest else 1)),
            event.place,
            event.event_id,
        ),
    )


def generate_story(event: Event, snapshot: dict[str, dict[str, float]]) -> Story:
    value = float(snapshot[event.place][event.metric])
    displayed = int(value) if value.is_integer() else round(value, 3)
    headline = f"{event.place}: {event.metric} reached {displayed}"
    return Story(
        story_id=f"story-{event.event_id}",
        event_id=event.event_id,
        place=event.place,
        day=event.day,
        headline=headline,
        body=(
            f"Recorded {event.metric} moved from {event.previous_value:g} to {value:g} on day "
            f"{event.day}. Cause receipt: {event.cause}."
        ),
        metrics={event.metric: value},
        template=True,
        arc_id=f"{event.place}:{event.definition_id}",
    )


def validate_story(story: Story, snapshot: dict[str, dict[str, float]]) -> bool:
    return all(
        snapshot.get(story.place, {}).get(metric) == value
        for metric, value in story.metrics.items()
    )


def causal_deep_dive(logs: list[dict[str, Any]], state_change: float) -> CausalDeepDive:
    causes = [Cause(name=str(item["cause"]), magnitude=float(item["magnitude"])) for item in logs]
    total = sum(cause.magnitude for cause in causes)
    if abs(total - state_change) > 1e-9:
        raise ValueError("Logged causes do not sum to the recorded state change")
    return CausalDeepDive(
        causes=sorted(causes, key=lambda cause: -abs(cause.magnitude)), total=total
    )
