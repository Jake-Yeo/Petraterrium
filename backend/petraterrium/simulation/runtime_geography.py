from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .locations import LocationPlace


@dataclass(frozen=True)
class RuntimeAgentGeography:
    country_id: str
    country_label: str
    region_id: str | None
    region_label: str | None
    city_id: str | None
    city_label: str | None
    latitude: float | None
    longitude: float | None
    location_id: str


def resolve_runtime_agent_geographies(
    *,
    profiles: Sequence[Mapping[str, Any]],
    output: Mapping[str, Any],
    location_places: Sequence[LocationPlace] = (),
    initial_location_ids: Sequence[str] = (),
    runtime_place_location_ids: Sequence[str] = (),
) -> tuple[RuntimeAgentGeography, ...]:
    fallback = tuple(_profile_geography(profile) for profile in profiles)
    if not profiles:
        return fallback
    if not location_places and not initial_location_ids and not runtime_place_location_ids:
        return fallback
    if not location_places or not initial_location_ids or not runtime_place_location_ids:
        raise ValueError("Runtime geography requires complete prepared location data")
    if len(initial_location_ids) != len(profiles):
        raise ValueError("Runtime geography initial locations must match the population")
    agents = output.get("agents")
    places = agents.get("place") if isinstance(agents, Mapping) else None
    if not isinstance(places, Sequence) or isinstance(places, (str, bytes)):
        raise ValueError("Runtime geography requires recorded agent place columns")
    if len(places) != len(profiles):
        raise ValueError("Runtime geography place columns must match the population")

    place_by_id = {place.id: place for place in location_places}
    if len(place_by_id) != len(location_places):
        raise ValueError("Runtime geography location identities must be unique")
    identities: dict[str, dict[str, tuple[str, str]]] = {
        "country": {},
        "region": {},
        "city": {},
    }
    coordinate_samples: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for profile, initial_location_id in zip(profiles, initial_location_ids, strict=True):
        profile_geography = _profile_geography(profile)
        for place in _ancestry(initial_location_id, place_by_id):
            identity = _identity_for_level(profile_geography, place)
            if identity is not None:
                previous = identities[place.level].setdefault(place.id, identity)
                if previous != identity:
                    raise ValueError(
                        f"Runtime geography location {place.id!r} maps to conflicting identities"
                    )
            if profile_geography.latitude is not None and profile_geography.longitude is not None:
                coordinate_samples[place.id].append(
                    (profile_geography.latitude, profile_geography.longitude)
                )
    coordinates = {
        place_id: _coordinate_centroid(samples)
        for place_id, samples in coordinate_samples.items()
    }

    resolved: list[RuntimeAgentGeography] = []
    for index, raw_runtime_index in enumerate(places):
        if isinstance(raw_runtime_index, bool) or not isinstance(raw_runtime_index, int):
            raise ValueError(f"Runtime geography place index {raw_runtime_index!r} is invalid")
        if not 0 <= raw_runtime_index < len(runtime_place_location_ids):
            raise ValueError(f"Runtime geography place index {raw_runtime_index} is out of range")
        location_id = runtime_place_location_ids[raw_runtime_index]
        ancestry = _ancestry(location_id, place_by_id)
        current = {place.level: place for place in ancestry}
        country_id, country_label = _resolved_identity(
            "country", current.get("country"), identities, fallback[index]
        )
        region = _optional_resolved_identity("region", current.get("region"), identities)
        city = _optional_resolved_identity("city", current.get("city"), identities)
        coordinate = next(
            (coordinates[place.id] for place in ancestry if place.id in coordinates),
            (fallback[index].latitude, fallback[index].longitude),
        )
        resolved.append(
            RuntimeAgentGeography(
                country_id=country_id,
                country_label=country_label,
                region_id=region[0] if region is not None else None,
                region_label=region[1] if region is not None else None,
                city_id=city[0] if city is not None else None,
                city_label=city[1] if city is not None else None,
                latitude=coordinate[0],
                longitude=coordinate[1],
                location_id=location_id,
            )
        )
    return tuple(resolved)


def _profile_geography(profile: Mapping[str, Any]) -> RuntimeAgentGeography:
    raw = profile.get("geography")
    geography = raw if isinstance(raw, Mapping) else {}
    country_id = _text(geography.get("country_id") or geography.get("country"))
    country_label = _text(geography.get("country") or country_id)
    region = _text(geography.get("region")) or None
    city_id = _text(geography.get("city_id")) or None
    city_label = _text(geography.get("city") or city_id) or None
    location_id = _text(geography.get("place_id") or city_id or country_id or "global")
    return RuntimeAgentGeography(
        country_id=country_id,
        country_label=country_label,
        region_id=region,
        region_label=region,
        city_id=city_id,
        city_label=city_label,
        latitude=_coordinate(geography.get("latitude"), -90, 90),
        longitude=_coordinate(geography.get("longitude"), -180, 180),
        location_id=location_id,
    )


def _ancestry(
    location_id: str,
    place_by_id: Mapping[str, LocationPlace],
) -> tuple[LocationPlace, ...]:
    current = place_by_id.get(location_id)
    if current is None:
        raise ValueError(f"Runtime geography location {location_id!r} is not prepared")
    result: list[LocationPlace] = []
    visited: set[str] = set()
    while current is not None:
        if current.id in visited:
            raise ValueError(f"Runtime geography location cycle includes {current.id!r}")
        visited.add(current.id)
        result.append(current)
        current = place_by_id.get(current.parent_id or "")
    return tuple(result)


def _identity_for_level(
    geography: RuntimeAgentGeography,
    place: LocationPlace,
) -> tuple[str, str] | None:
    if place.level == "country":
        return (geography.country_id, geography.country_label)
    if place.level == "region" and geography.region_id is not None:
        return (geography.region_id, geography.region_label or geography.region_id)
    if place.level == "city" and geography.city_id is not None:
        return (geography.city_id, geography.city_label or geography.city_id)
    return None


def _resolved_identity(
    level: str,
    place: LocationPlace | None,
    identities: Mapping[str, Mapping[str, tuple[str, str]]],
    fallback: RuntimeAgentGeography,
) -> tuple[str, str]:
    identity = _optional_resolved_identity(level, place, identities)
    if identity is not None:
        return identity
    return fallback.country_id, fallback.country_label


def _optional_resolved_identity(
    level: str,
    place: LocationPlace | None,
    identities: Mapping[str, Mapping[str, tuple[str, str]]],
) -> tuple[str, str] | None:
    if place is None:
        return None
    return identities[level].get(place.id, (place.id, place.name))


def _coordinate_centroid(samples: Sequence[tuple[float, float]]) -> tuple[float, float]:
    latitude = sum(item[0] for item in samples) / len(samples)
    sine = sum(math.sin(math.radians(item[1])) for item in samples)
    cosine = sum(math.cos(math.radians(item[1])) for item in samples)
    longitude = math.degrees(math.atan2(sine, cosine))
    return latitude, longitude


def _coordinate(value: Any, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and minimum <= parsed <= maximum else None


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
