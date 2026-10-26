from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTRACT_VERSION = "1"
CountryCode = Literal["ITA", "FRA", "DEU", "ESP"]
RunStatus = Literal["queued", "running", "done", "failed"]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, json_schema_serialization_defaults_required=True
    )


class Parameters(Contract):
    transmission: float = Field(default=0.38, ge=0, le=3, allow_inf_nan=False)
    progression: float = Field(default=0.2, ge=0, le=3, allow_inf_nan=False)
    recovery: float = Field(default=0.09, ge=0, le=3, allow_inf_nan=False)
    mixing: float = Field(default=0.04, ge=0, le=1, allow_inf_nan=False)
    initial_infected: int = Field(default=40, ge=1, le=10000, strict=True)


class RunConfig(Contract):
    scenario: Literal["pandemic"] = "pandemic"
    countries: list[CountryCode] = Field(min_length=1, max_length=4)
    start_day: int = Field(default=0, ge=0, le=10000, strict=True)
    end_day: int = Field(default=160, ge=1, le=10730, strict=True)
    seed: int = Field(default=42, ge=0, le=4294967295, strict=True)
    parameters: Parameters = Field(default_factory=Parameters)

    @field_validator("countries")
    @classmethod
    def canonical_countries(cls, value: list[CountryCode]) -> list[CountryCode]:
        if len(set(value)) != len(value):
            raise ValueError("Select each country only once")
        return sorted(value)

    @model_validator(mode="after")
    def valid_window(self) -> "RunConfig":
        if not 1 <= self.end_day - self.start_day <= 730:
            raise ValueError("End day must be 1 to 730 days after start day")
        return self


class PlaceSnapshot(Contract):
    country: CountryCode
    susceptible: int = Field(ge=0)
    exposed: int = Field(ge=0)
    infected: int = Field(ge=0)
    recovered: int = Field(ge=0)


class DailySnapshot(Contract):
    run_id: str = Field(min_length=1)
    day: int = Field(ge=0)
    places: list[PlaceSnapshot] = Field(min_length=1, max_length=4)
    seed: int = Field(ge=0)
    engine_version: str = Field(min_length=1)
    data_version: str = Field(min_length=1)


class Totals(Contract):
    population: int = Field(ge=0)
    susceptible: int = Field(ge=0)
    exposed: int = Field(ge=0)
    infected: int = Field(ge=0)
    recovered: int = Field(ge=0)


class Metrics(Contract):
    totals: Totals
    peak_day: int
    peak_infected: int = Field(ge=0)
    days_recorded: int = Field(ge=1)


class RunError(Contract):
    code: str
    message: str


class RunSummary(Contract):
    run_id: str
    config_hash: str
    config: RunConfig
    status: RunStatus
    created_at: str
    last_sequence: int = Field(ge=0)
    metrics: Metrics | None = None
    error: RunError | None = None


class RunDetail(RunSummary):
    snapshots: list[DailySnapshot]


class RunCreated(RunDetail):
    cached: bool


class RunList(Contract):
    runs: list[RunSummary]


class RunComplete(Contract):
    run_id: str
    status: Literal["done"] = "done"
    metrics: Metrics


class RunFailed(Contract):
    run_id: str
    status: Literal["failed"] = "failed"
    error: RunError


class Country(Contract):
    country: CountryCode
    name: str
    population: int = Field(gt=0)
    latitude: float
    longitude: float
    fake: Literal[True] = True


class Catalog(Contract):
    countries: list[Country]
    engine_version: str
    data_version: str
    contract_version: str = CONTRACT_VERSION
    notice: str
