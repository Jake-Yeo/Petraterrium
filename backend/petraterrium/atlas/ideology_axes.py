from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..dsl import Evidence, FeatureDefinition, FeatureRange, RuleCondition

IdeologyAxisId = Literal[
    "ideology_economic",
    "ideology_state",
    "ideology_cultural",
]
IdeologyOperator = Literal["eq", "ne", "gt", "gte", "lt", "lte"]
IDEOLOGY_AXIS_IDS: tuple[IdeologyAxisId, ...] = (
    "ideology_economic",
    "ideology_state",
    "ideology_cultural",
)


class IdeologyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IdeologyAxis(IdeologyModel):
    definition: FeatureDefinition
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    negative_pole: str = Field(min_length=1)
    positive_pole: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_definition(self):
        if self.definition.id not in IDEOLOGY_AXIS_IDS:
            raise ValueError("Ideology axis definition needs a canonical axis id")
        if self.definition.kind != "continuous":
            raise ValueError("Ideology axes must be continuous")
        value_range = self.definition.value_range
        if value_range is None or value_range.minimum != -1 or value_range.maximum != 1:
            raise ValueError("Ideology axes must use the inclusive -1 to 1 range")
        return self


class IdeologySurveyItemMapping(IdeologyModel):
    axis_id: IdeologyAxisId
    survey_id: str = Field(min_length=1)
    variable: str = Field(min_length=1)
    question: str = Field(min_length=1)
    negative_anchor: str = Field(min_length=1)
    positive_anchor: str = Field(min_length=1)
    response_min: float = Field(allow_inf_nan=False)
    response_max: float = Field(allow_inf_nan=False)
    reverse_scored: bool = False
    provenance: Evidence

    @property
    def identity(self) -> str:
        return f"{self.survey_id}:{self.variable}"

    @model_validator(mode="after")
    def valid_response_scale(self):
        if self.response_max <= self.response_min:
            raise ValueError("Survey item response maximum must exceed its minimum")
        return self


class IdeologyAxisFit(IdeologyModel):
    axis_id: IdeologyAxisId
    items: list[IdeologySurveyItemMapping] = Field(min_length=1)
    coefficients: dict[str, float] = Field(min_length=1)
    intercept: float = Field(allow_inf_nan=False)
    sample_size: int = Field(gt=0)
    provenance: Evidence

    @model_validator(mode="after")
    def separate_axis_inputs(self):
        if any(item.axis_id != self.axis_id for item in self.items):
            raise ValueError("Each ideology axis must be fitted from its own survey items")
        item_ids = [item.identity for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("Survey items must be unique within an ideology axis fit")
        if set(self.coefficients) != set(item_ids):
            raise ValueError("Ideology fit coefficients must exactly match its survey items")
        return self


class IdeologyAxisFitSet(IdeologyModel):
    fits: list[IdeologyAxisFit]

    @model_validator(mode="after")
    def separate_complete_fits(self):
        axis_ids = [fit.axis_id for fit in self.fits]
        if len(set(axis_ids)) != len(IDEOLOGY_AXIS_IDS) or set(axis_ids) != set(IDEOLOGY_AXIS_IDS):
            raise ValueError("Each ideology axis needs one separate fit")
        item_ids = [item.identity for fit in self.fits for item in fit.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("A survey item cannot be reused across ideology axis fits")
        return self


class LegacyIdeologyObservation(IdeologyModel):
    feature_id: Literal["ideology"] = "ideology"
    value: str | float | dict[str, float]
    provenance: Evidence
    status: Literal["legacy_only"] = "legacy_only"
    predictive: Literal[False] = False
    axis_values: None = None


def axis_definition(feature_id: IdeologyAxisId) -> FeatureDefinition:
    return FeatureDefinition(
        id=feature_id,
        kind="continuous",
        value_range=FeatureRange(minimum=-1, maximum=1, unit="normalized axis score"),
        provenance=Evidence(
            source="Petraterrium canonical ideology axis schema",
            version="ideology-axes-v1",
            status="present",
            uncertainty=0,
        ),
    )


def canonical_ideology_axes() -> tuple[IdeologyAxis, ...]:
    axes = (
        IdeologyAxis(
            definition=axis_definition("ideology_economic"),
            name="Economic ideology",
            description=(
                "Economic organization from planned-economy preferences at -1 to "
                "free-market preferences at +1, fitted only from economic survey items."
            ),
            negative_pole="Planned economy",
            positive_pole="Free market",
        ),
        IdeologyAxis(
            definition=axis_definition("ideology_state"),
            name="State ideology",
            description=(
                "State authority from authoritarian preferences at -1 to an anti-authoritarian "
                "+1 end covering democratic and anarchist self-rule. Democratic and anarchist "
                "self-rule are not identical and must remain distinguishable in source items."
            ),
            negative_pole="Authoritarian",
            positive_pole="Democratic or anarchist self-rule",
        ),
        IdeologyAxis(
            definition=axis_definition("ideology_cultural"),
            name="Cultural ideology",
            description=(
                "Cultural values from traditional or conservative preferences at -1 to "
                "progressive or modern preferences at +1, fitted only from cultural survey items."
            ),
            negative_pole="Traditional or conservative",
            positive_pole="Progressive or modern",
        ),
    )
    return tuple(
        axis.model_copy(
            update={
                "definition": axis.definition.model_copy(
                    update={"name": axis.name, "description": axis.description}
                )
            }
        )
        for axis in axes
    )


def require_ideology_axis(feature_id: str) -> IdeologyAxisId:
    if feature_id == "ideology":
        raise ValueError(
            "The single ideology field is legacy-only and cannot be split or predictive"
        )
    if feature_id not in IDEOLOGY_AXIS_IDS:
        raise ValueError(f"Unknown ideology axis: {feature_id}")
    return cast(IdeologyAxisId, feature_id)


def ideology_rule_condition(
    axis_id: str,
    operator: IdeologyOperator,
    value: float,
) -> RuleCondition:
    canonical_axis_id = require_ideology_axis(axis_id)
    if not -1 <= value <= 1:
        raise ValueError("Ideology rule values must be between -1 and 1")
    return RuleCondition(attribute=canonical_axis_id, operator=operator, value=value)
