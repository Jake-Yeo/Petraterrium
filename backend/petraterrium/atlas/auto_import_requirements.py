from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CanonicalFeatureId = Literal[
    "age_sex",
    "income",
    "education",
    "ideology_economic",
    "ideology_state",
    "ideology_cultural",
    "household_size",
]


class RequirementModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CanonicalFieldRequirement(RequirementModel):
    feature_id: CanonicalFeatureId
    name: str
    value_specification: str
    canonical_values: tuple[str, ...]
    denominator: str
    accepted_denominators: tuple[str, ...]
    time_unit: str
    accepted_units: tuple[str, ...]
    distribution_total: float = Field(default=100, gt=0)
    allows_source_categories: bool = False
    better_data_needed: str
    feature_aliases: tuple[str, ...]
    label_aliases: dict[str, str]


AGE_BANDS = (
    "0_4",
    "5_9",
    "10_14",
    "15_19",
    "20_24",
    "25_29",
    "30_34",
    "35_39",
    "40_44",
    "45_49",
    "50_54",
    "55_59",
    "60_64",
    "65_69",
    "70_74",
    "75_79",
    "80_84",
    "85_89",
    "90_94",
    "95_99",
    "100_plus",
)
AGE_SEX_VALUES = tuple(
    f"{sex}_{age_band}" for sex in ("female", "male") for age_band in AGE_BANDS
)
EDUCATION_VALUES = tuple(str(level) for level in range(9)) + ("unknown",)


def _requirement(
    feature_id: CanonicalFeatureId,
    name: str,
    value_specification: str,
    canonical_values: tuple[str, ...],
    denominator: str,
    accepted_denominators: tuple[str, ...],
    time_unit: str,
    accepted_units: tuple[str, ...],
    better_data_needed: str,
    feature_aliases: tuple[str, ...],
    label_aliases: dict[str, str],
    allows_source_categories: bool = False,
) -> CanonicalFieldRequirement:
    return CanonicalFieldRequirement(
        feature_id=feature_id,
        name=name,
        value_specification=value_specification,
        canonical_values=canonical_values,
        denominator=denominator,
        accepted_denominators=accepted_denominators,
        time_unit=time_unit,
        accepted_units=accepted_units,
        better_data_needed=better_data_needed,
        feature_aliases=feature_aliases,
        label_aliases=label_aliases,
        allows_source_categories=allows_source_categories,
    )


CANONICAL_FIELD_REQUIREMENTS: dict[CanonicalFeatureId, CanonicalFieldRequirement] = {
    "age_sex": _requirement(
        "age_sex",
        "Age and sex structure",
        "Population shares by sex and five-year age band",
        AGE_SEX_VALUES,
        "resident population",
        ("resident population", "usual resident population", "population"),
        "point-in-time population estimate or census date",
        ("percent", "percentage", "%"),
        "A census or representative population estimate for this exact place and date",
        ("age sex", "age and sex", "population by age and sex", "sex by age"),
        {
            "women": "female",
            "woman": "female",
            "girls": "female",
            "female": "female",
            "men": "male",
            "man": "male",
            "boys": "male",
            "male": "male",
        },
    ),
    "income": _requirement(
        "income",
        "Income",
        "Annual individual income distribution with currency and price year",
        (),
        "people with stated income universe",
        (
            "people with stated income universe",
            "persons",
            "adults",
            "employed people",
            "households",
        ),
        "annual",
        ("percent", "percentage", "%"),
        "A representative microdata or tabulation for the same income universe and place",
        (
            "income",
            "annual income",
            "personal income",
            "household income",
            "earnings",
        ),
        {},
        True,
    ),
    "education": _requirement(
        "education",
        "Education",
        "Highest educational attainment mapped to ISCED 2011 levels 0 through 8",
        EDUCATION_VALUES,
        "population at or above the source's stated education age",
        (
            "population at or above the source's stated education age",
            "persons aged 15 and older",
            "persons aged 25 and older",
            "adults",
            "respondents",
        ),
        "point-in-time census or survey wave",
        ("percent", "percentage", "%"),
        "A census or representative survey with education codes convertible to ISCED 2011",
        (
            "education",
            "educational attainment",
            "highest education",
            "isced",
        ),
        {
            "no schooling": "0",
            "early childhood": "0",
            "primary": "1",
            "lower secondary": "2",
            "upper secondary": "3",
            "post secondary non tertiary": "4",
            "short cycle tertiary": "5",
            "bachelor": "6",
            "bachelors": "6",
            "master": "7",
            "masters": "7",
            "doctorate": "8",
            "doctoral": "8",
            "unknown": "unknown",
        },
    ),
    "ideology_economic": _requirement(
        "ideology_economic",
        "Economic ideology",
        "Weighted distribution on planned economy (-1) to free market (+1)",
        (),
        "eligible survey respondents",
        ("eligible survey respondents", "respondents", "adults"),
        "survey wave",
        ("percent", "percentage", "%"),
        "Representative place-level responses to validated economic-policy survey items",
        ("economic ideology", "planned economy free market", "economic values"),
        {},
        True,
    ),
    "ideology_state": _requirement(
        "ideology_state",
        "State ideology",
        "Weighted distribution on authoritarian (-1) to anti-authoritarian (+1)",
        (),
        "eligible survey respondents",
        ("eligible survey respondents", "respondents", "adults"),
        "survey wave",
        ("percent", "percentage", "%"),
        "Representative place-level responses to validated authority and self-rule items",
        ("state ideology", "authoritarian democratic", "authority self rule"),
        {},
        True,
    ),
    "ideology_cultural": _requirement(
        "ideology_cultural",
        "Cultural ideology",
        "Weighted distribution on traditional (-1) to progressive (+1)",
        (),
        "eligible survey respondents",
        ("eligible survey respondents", "respondents", "adults"),
        "survey wave",
        ("percent", "percentage", "%"),
        "Representative place-level responses to validated cultural-values survey items",
        ("cultural ideology", "traditional progressive", "cultural values"),
        {},
        True,
    ),
    "household_size": _requirement(
        "household_size",
        "Household size",
        "Household share by number of usual residents, one through 30 people",
        tuple(str(size) for size in range(1, 31)),
        "occupied private households",
        ("occupied private households", "households", "private households"),
        "point-in-time census or survey wave",
        ("percent", "percentage", "%"),
        "A census or representative household survey for this exact place",
        ("household size", "persons per household", "household members"),
        {str(size): str(size) for size in range(1, 31)},
    ),
}


def canonical_requirement(feature_id: str) -> CanonicalFieldRequirement:
    try:
        return CANONICAL_FIELD_REQUIREMENTS[feature_id]
    except KeyError as error:
        raise KeyError(f"No auto-import requirement exists for {feature_id}") from error

