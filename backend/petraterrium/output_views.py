import hashlib

from .contracts import (
    AgentDetail,
    AgentPoint,
    AgentPointList,
    AgentRelationship,
    AgentTimelineEntry,
    PlaceDetail,
    StoryDetail,
)
from .population import AgentRecord
from .recorder import RunRecord

PALETTE = (
    "#4f8fba",
    "#e4874f",
    "#5eaf7b",
    "#b86bb5",
    "#dfbd4c",
    "#cf5a68",
    "#7d87d5",
    "#73b7ae",
)


def require_population(record: RunRecord):
    if record.population is None:
        raise ValueError("Population has not been generated yet")
    return record.population


def selected_snapshot(record: RunRecord, day: int | None = None):
    if not record.snapshots:
        raise ValueError("Run has no recorded snapshots")
    if day is None:
        return record.snapshots[-1]
    return min(record.snapshots, key=lambda snapshot: (abs(snapshot.day - day), snapshot.day))


def projected_states(record: RunRecord, agent: AgentRecord, day: int | None = None):
    snapshot = selected_snapshot(record, day)
    place = next((item for item in snapshot.places if item.country == agent.place), None)
    if place is None or not place.states:
        return dict(agent.states)
    result = {}
    percentile = int(
        hashlib.sha256(f"{record.run_id}:{agent.agent_id}".encode()).hexdigest()[:14], 16
    ) / float(16**14)
    for state_id, values in place.states.items():
        total = sum(values.values())
        cursor = 0.0
        selected = next(iter(values))
        for value, count in values.items():
            cursor += count / max(1, total)
            if percentile <= cursor:
                selected = value
                break
        result[state_id] = selected
    return result


def primary_state(states: dict[str, str]) -> str:
    return next(iter(states.values()), "unknown")


def state_color(state: str) -> str:
    index = int(hashlib.sha256(state.encode()).hexdigest()[:8], 16) % len(PALETTE)
    return PALETTE[index]


def point_for(record: RunRecord, agent: AgentRecord, day: int | None = None) -> AgentPoint:
    state = primary_state(projected_states(record, agent, day))
    return AgentPoint(
        agent_id=agent.agent_id,
        place=agent.place,
        latitude=agent.latitude,
        longitude=agent.longitude,
        state=state,
        color=state_color(state),
        log_tier=agent.log_tier,
    )


def agent_points(
    record: RunRecord,
    place: str,
    day: int | None,
    state: str,
    action: str,
    limit: int,
    offset: int,
) -> AgentPointList:
    population = require_population(record)
    agents = [agent for agent in population.agents if agent.place == place]
    points = [point_for(record, agent, day) for agent in agents]
    if state:
        points = [point for point in points if point.state == state]
    if action:
        points = points if action in {"routine", "state_update", "initial_state"} else []
    selected = points[offset : offset + limit]
    return AgentPointList(
        agents=selected,
        total=len(points),
        returned=len(selected),
        representative=True,
    )


def find_agent(record: RunRecord, agent_id: str) -> AgentRecord | None:
    population = record.population
    if population is None:
        return None
    return next((agent for agent in population.agents if agent.agent_id == agent_id), None)


def agent_detail(record: RunRecord, agent: AgentRecord) -> AgentDetail:
    states = projected_states(record, agent)
    final = selected_snapshot(record)
    timeline = [
        AgentTimelineEntry(
            tick=0,
            day=record.snapshots[0].day,
            action="initial_state",
            state_after=agent.states,
        )
    ]
    if states != agent.states:
        timeline.append(
            AgentTimelineEntry(
                tick=final.tick,
                day=final.day,
                action="FAKE representative state projection",
                state_after=states,
            )
        )
    scope = {
        "spotlight": "Full synthetic log from tick 0; representative projection is labelled FAKE.",
        "sampled": "Sampled cohort log with recorded high-impact changes.",
        "mass": "Representative segment view; routine per-tick actions were not logged.",
    }[agent.log_tier]
    return AgentDetail(
        agent_id=agent.agent_id,
        run_id=record.run_id,
        place=agent.place,
        role=agent.role,
        log_tier=agent.log_tier,
        log_scope=scope,
        traits=agent.traits,
        states=states,
        behaviour=agent.behaviour,
        relationships=[
            AgentRelationship(
                target_id=relationship.target_id,
                kind=relationship.kind,
                weight=relationship.weight,
            )
            for relationship in agent.relationships
        ],
        timeline=timeline,
        media=[],
    )


def place_detail(record: RunRecord, place_id: str) -> PlaceDetail:
    snapshot = selected_snapshot(record)
    place = next((item for item in snapshot.places if item.country == place_id), None)
    if place is None:
        raise KeyError(place_id)
    stories = [story for story in record.stories if story.place == place_id]
    return PlaceDetail(
        place_id=place_id,
        run_id=record.run_id,
        status=record.status,
        metrics=place.metrics,
        events=[story.event_id for story in stories],
        arc=[story.story_id for story in stories],
    )


def story_detail(record: RunRecord, story_id: str) -> StoryDetail:
    story = next((item for item in record.stories if item.story_id == story_id), None)
    if story is None:
        raise KeyError(story_id)
    place = place_detail(record, story.place)
    agents = agent_points(record, story.place, story.day, "", "", 12, 0).agents
    arc = [item for item in record.stories if item.arc_id == story.arc_id]
    return StoryDetail(story=story, place_metrics=place.metrics, agents=agents, arc=arc)
