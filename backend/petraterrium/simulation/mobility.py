from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MobilityEvidenceStatus = Literal["measured", "user_defined", "unknown", "imputed"]
MobilityRegistryStatus = Literal["draft", "confirmed"]


class MobilityModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class MobilityEvidence(MobilityModel):
    status: MobilityEvidenceStatus
    source_title: str | None = None
    source_version: str | None = None
    source_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    licence: str | None = None
    evidence_id: str | None = None
    uncertainty: float | None = Field(default=None, ge=0, le=1)
    note: str | None = None

    @property
    def executable(self) -> bool:
        return self.status in {"measured", "user_defined"}

    @model_validator(mode="after")
    def executable_provenance(self):
        if not self.executable:
            return self
        required = (
            "source_title",
            "source_version",
            "source_date",
            "licence",
            "evidence_id",
            "uncertainty",
        )
        missing = [name for name in required if getattr(self, name) is None]
        if missing:
            raise ValueError("Executable mobility evidence requires " + ", ".join(missing))
        return self


class PlaceProfileDefinition(MobilityModel):
    id: str = Field(min_length=1)
    place_id: str | None = Field(default=None, min_length=1)
    place_kind: str = Field(min_length=1)
    accepts_arrivals: bool
    allows_in_person: bool
    capacity: int | None = Field(ge=1)
    state: dict[str, float]
    available_decision_tree_ids: list[str]
    evidence: MobilityEvidence

    @field_validator("place_kind")
    @classmethod
    def normalized_place_kind(cls, value: str) -> str:
        normalized = value.casefold().replace(" ", "_")
        if value != normalized:
            raise ValueError("Place kinds must use normalized lowercase identifiers")
        return value

    @field_validator("state")
    @classmethod
    def finite_state(cls, value: dict[str, float]) -> dict[str, float]:
        if any(not math.isfinite(item) for item in value.values()):
            raise ValueError("Place state values must be finite")
        return value

    @model_validator(mode="after")
    def unique_tree_ids(self):
        if len(set(self.available_decision_tree_ids)) != len(self.available_decision_tree_ids):
            raise ValueError("Available decision tree IDs must be unique")
        return self


class TravelRouteDefinition(MobilityModel):
    id: str = Field(min_length=1)
    from_place_kind: str = Field(min_length=1)
    to_place_kind: str = Field(min_length=1)
    transit_place_kind: str = Field(min_length=1)
    duration_minutes: int = Field(ge=1)
    evidence: MobilityEvidence

    @field_validator("from_place_kind", "to_place_kind", "transit_place_kind")
    @classmethod
    def normalized_place_kind(cls, value: str) -> str:
        normalized = value.casefold().replace(" ", "_")
        if value != normalized:
            raise ValueError("Place kinds must use normalized lowercase identifiers")
        return value

    @model_validator(mode="after")
    def changes_place(self):
        if self.from_place_kind == self.to_place_kind:
            raise ValueError("Travel routes must change place kind")
        return self


class MobilityRegistryDefinition(MobilityModel):
    version: str = Field(min_length=1)
    status: MobilityRegistryStatus
    place_profiles: list[PlaceProfileDefinition]
    routes: list[TravelRouteDefinition]

    @model_validator(mode="after")
    def coherent_registry(self):
        profile_ids = [profile.id for profile in self.place_profiles]
        default_profile_kinds = [
            profile.place_kind for profile in self.place_profiles if profile.place_id is None
        ]
        specific_place_ids = [
            profile.place_id for profile in self.place_profiles if profile.place_id is not None
        ]
        route_ids = [route.id for route in self.routes]
        route_pairs = [(route.from_place_kind, route.to_place_kind) for route in self.routes]
        if len(set(profile_ids)) != len(profile_ids):
            raise ValueError("Mobility place profile IDs must be unique")
        if len(set(default_profile_kinds)) != len(default_profile_kinds):
            raise ValueError("Mobility kind-level place profiles must be unique")
        if len(set(specific_place_ids)) != len(specific_place_ids):
            raise ValueError("Mobility specific place profile targets must be unique")
        if len(set(route_ids)) != len(route_ids):
            raise ValueError("Mobility route IDs must be unique")
        if len(set(route_pairs)) != len(route_pairs):
            raise ValueError("Mobility route pairs must be unique")
        known_kinds = set(default_profile_kinds)
        missing_transit = sorted(
            {
                route.transit_place_kind
                for route in self.routes
                if route.transit_place_kind not in known_kinds
            }
        )
        if missing_transit:
            raise ValueError(
                "Every transit place kind requires a place profile: " + ", ".join(missing_transit)
            )
        if self.status == "confirmed":
            blocked = [
                f"place profile {profile.id}"
                for profile in self.place_profiles
                if not profile.evidence.executable
            ]
            blocked.extend(
                f"travel route {route.id}" for route in self.routes if not route.evidence.executable
            )
            if blocked:
                raise ValueError(
                    "Confirmed mobility entries require executable evidence: " + ", ".join(blocked)
                )
        return self


class ResolvedMobility:
    def __init__(self, definition: MobilityRegistryDefinition):
        if definition.status != "confirmed":
            raise ValueError("Only a confirmed mobility registry can enter the runtime")
        self.definition = definition
        self._default_profiles = {
            profile.place_kind: profile
            for profile in definition.place_profiles
            if profile.place_id is None and profile.evidence.executable
        }
        self._specific_profiles = {
            profile.place_id: profile
            for profile in definition.place_profiles
            if profile.place_id is not None and profile.evidence.executable
        }
        self._routes = {
            (route.from_place_kind, route.to_place_kind): route
            for route in definition.routes
            if route.evidence.executable
        }

    def profile(
        self, place_kind: str, place_id: str | None = None
    ) -> PlaceProfileDefinition | None:
        normalized_kind = place_kind.casefold()
        specific = self._specific_profiles.get(place_id) if place_id is not None else None
        if specific is not None:
            if specific.place_kind != normalized_kind:
                raise ValueError(
                    f"Specific place profile {specific.id!r} targets kind "
                    f"{specific.place_kind!r}, not runtime kind {normalized_kind!r}"
                )
            return specific
        return self._default_profiles.get(normalized_kind)

    def route(self, from_place_kind: str, to_place_kind: str) -> TravelRouteDefinition | None:
        return self._routes.get((from_place_kind.casefold(), to_place_kind.casefold()))

    def travel_ticks(
        self,
        from_place_kind: str,
        to_place_kind: str,
        tick_interval_hours: float,
    ) -> int | None:
        if not math.isfinite(tick_interval_hours) or tick_interval_hours <= 0:
            raise ValueError("Tick interval hours must be positive and finite")
        route = self.route(from_place_kind, to_place_kind)
        if route is None:
            return None
        return max(1, math.ceil(route.duration_minutes / (tick_interval_hours * 60)))


def resolve_mobility(definition: MobilityRegistryDefinition) -> ResolvedMobility:
    return ResolvedMobility(definition)
