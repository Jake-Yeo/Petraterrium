from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field


class MediaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MediaObject(MediaModel):
    id: str
    source: str
    topic: str
    sentiment: float = Field(ge=-1, le=1)
    bias: float = Field(ge=-1, le=1)
    credibility: float = Field(ge=0, le=1)
    reach: float = Field(ge=0, le=1)
    created_tick: int = Field(ge=0)
    text: str | None = None


class MediaResponse(MediaModel):
    action: Literal["post", "repost", "consume", "ignore", "react"]
    opinion_delta: float
    outrage_delta: float
    trust_delta: float


def media_probabilities(agent: dict, media: MediaObject) -> dict[str, float]:
    interests = set(agent.get("interests", []))
    interest = 1 if media.topic in interests else 0.25
    agreement = float(agent.get("agreement", 0.5))
    outrage = float(agent.get("outrage", 0))
    trust = float(agent.get("trust", media.credibility))
    fatigue = float(agent.get("fatigue", 0))
    consume = np.clip((0.2 + 0.45 * interest + 0.2 * trust) * (1 - 0.7 * fatigue), 0, 1)
    repost = np.clip(0.03 + 0.25 * agreement + 0.2 * outrage + 0.15 * trust - 0.25 * fatigue, 0, 1)
    react = np.clip(0.05 + 0.15 * agreement + 0.2 * outrage - 0.1 * fatigue, 0, 1)
    post = np.clip(0.005 + 0.03 * outrage - 0.01 * fatigue, 0, 1)
    ignore = np.clip(1 - consume + 0.75 * fatigue + 0.25 * (1 - trust), 0, 1)
    total = consume + repost + react + post + ignore
    return {
        "post": float(post / total),
        "repost": float(repost / total),
        "consume": float(consume / total),
        "ignore": float(ignore / total),
        "react": float(react / total),
    }


def feed_score(agent: dict, media: MediaObject, current_tick: int | None = None) -> float:
    current_tick = media.created_tick if current_tick is None else current_tick
    interest = 1 if media.topic in set(agent.get("interests", [])) else 0.2
    trust = float(agent.get("trust", 0.5))
    social = float(agent.get("friends_shared", {}).get(media.id, 0))
    recency = 1 / (1 + max(0, current_tick - media.created_tick))
    return interest * 0.4 + social * 0.25 + recency * 0.2 + trust * media.credibility * 0.15


def rank_feed(agent: dict, media_objects: list[MediaObject]) -> list[MediaObject]:
    current_tick = max((media.created_tick for media in media_objects), default=0)
    return sorted(
        media_objects,
        key=lambda media: (-feed_score(agent, media, current_tick), media.id),
    )


def media_response(agent: dict, media: MediaObject, action: str = "consume") -> MediaResponse:
    trust = float(agent.get("trust", 0.5))
    agreement = float(agent.get("agreement", 0.5))
    direction = 1 if agreement >= 0.5 else -1
    opinion_delta = (
        -abs(media.sentiment) * media.credibility * 0.1
        if trust < 0.2
        else direction * media.sentiment * media.credibility * 0.1
    )
    outrage_delta = abs(media.sentiment) * (1 - agreement) * 0.08
    trust_delta = (media.credibility - trust) * 0.03
    return MediaResponse(
        action=action,
        opinion_delta=opinion_delta,
        outrage_delta=outrage_delta,
        trust_delta=trust_delta,
    )


def media_action(
    agent: dict,
    media: MediaObject,
    rng: np.random.Generator,
) -> MediaResponse:
    probabilities = media_probabilities(agent, media)
    actions = list(probabilities)
    action = str(rng.choice(actions, p=[probabilities[item] for item in actions]))
    return media_response(agent, media, action)


def generate_media(tick: int, events: list[dict]) -> list[MediaObject]:
    return [
        MediaObject(
            id=f"event-{tick}-{index}",
            source=str(event.get("source", "event-detector")),
            topic=str(event.get("type", "event")),
            sentiment=float(event.get("sentiment", 0)),
            bias=0,
            credibility=float(event.get("credibility", 1)),
            reach=float(event.get("reach", 0.1)),
            created_tick=tick,
            text=event.get("text"),
        )
        for index, event in enumerate(events)
    ]
