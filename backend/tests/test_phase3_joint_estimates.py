import pytest

from petraterrium.atlas.joint_estimates import (
    FeatureFilter,
    MeasuredJointData,
    PlaceSelector,
    PopulationPlace,
    estimate_joined_filters,
    feature_inheritance,
)
from petraterrium.dsl import (
    Evidence,
    FeatureDefinition,
    FeatureDistribution,
    FeatureRange,
    FeatureRegistry,
)


def evidence(source: str) -> Evidence:
    return Evidence(
        source=source,
        version="fixture-v1",
        status="present",
        uncertainty=0.1,
        source_date="2025-01-01",
    )


def feature_registry() -> FeatureRegistry:
    return FeatureRegistry(
        version="joint-filter-test-v1",
        definitions=[
            FeatureDefinition(
                id="sex",
                kind="categorical",
                canonical_values=["female", "male"],
                provenance=evidence("Sex schema"),
            ),
            FeatureDefinition(
                id="education_isced",
                kind="categorical",
                canonical_values=["tertiary", "other"],
                provenance=evidence("Education schema"),
            ),
            FeatureDefinition(
                id="income",
                kind="continuous",
                value_range=FeatureRange(minimum=0, maximum=1_000_000, unit="CAD/year"),
                provenance=evidence("Income schema"),
            ),
        ],
        distributions=[
            FeatureDistribution(
                feature_id="sex",
                level="city",
                place="Toronto",
                population="Toronto residents",
                coverage_percent=95,
                values={"female": 0.6, "male": 0.4},
                provenance=evidence("Toronto census"),
            ),
            FeatureDistribution(
                feature_id="sex",
                level="country",
                place="CAN",
                population="Canadian residents",
                coverage_percent=98,
                values={"female": 0.4, "male": 0.6},
                provenance=evidence("Canada census"),
            ),
            FeatureDistribution(
                feature_id="education_isced",
                level="country",
                place="CAN",
                population="Canadian adults",
                coverage_percent=90,
                values={"tertiary": 0.25, "other": 0.75},
                provenance=evidence("Canada education table"),
            ),
            FeatureDistribution(
                feature_id="income",
                level="country",
                place="CAN",
                population="Canadian earners",
                coverage_percent=80,
                mean=100_000,
                standard_deviation=50_000,
                provenance=evidence("Canada income survey"),
            ),
        ],
    )


def places() -> list[PopulationPlace]:
    return [
        PopulationPlace(
            place="Toronto",
            label="Toronto",
            level="city",
            population=100,
            city="Toronto",
            country="CAN",
            region="Northern America",
        ),
        PopulationPlace(
            place="Vancouver",
            label="Vancouver",
            level="city",
            population=300,
            city="Vancouver",
            country="CAN",
            region="Northern America",
        ),
    ]


def region_selector() -> PlaceSelector:
    return PlaceSelector(
        level="region",
        place="Northern America",
        label="Northern America",
    )


def joined_filters() -> list[FeatureFilter]:
    return [
        FeatureFilter(feature_id="sex", operator="eq", values=["female"]),
        FeatureFilter(feature_id="education_isced", operator="eq", values=["tertiary"]),
    ]


def test_inheritance_uses_most_specific_distribution_and_population_weights():
    view = feature_inheritance(feature_registry(), places(), region_selector(), "sex")

    female = next(value for value in view.values if value.value == "female")
    assert female.agent_percent == pytest.approx(45)
    assert female.estimated_count == 180
    assert {(source.place, source.status) for source in female.sources} == {
        ("Toronto", "present"),
        ("CAN", "inherited"),
    }
    country_source = next(source for source in female.sources if source.place == "CAN")
    assert country_source.applied_population == 300
    assert view.selected_population == 400
    assert view.represented_population == 400
    assert view.unresolved_population == 0


def test_place_selector_limits_inheritance_to_the_selected_city():
    selector = PlaceSelector(level="city", place="Vancouver", label="Vancouver")
    view = feature_inheritance(feature_registry(), places(), selector, "sex")

    female = next(value for value in view.values if value.value == "female")
    assert female.agent_percent == pytest.approx(40)
    assert female.estimated_count == 120
    assert female.sources[0].place == "CAN"
    assert female.sources[0].status == "inherited"


def test_joined_marginals_are_explicitly_an_independence_estimate():
    estimate = estimate_joined_filters(
        feature_registry(), places(), region_selector(), joined_filters()
    )

    assert estimate.method == "independence_estimate"
    assert estimate.method_label == "independence estimate — not measured"
    assert estimate.agent_percent == pytest.approx(11.25)
    assert estimate.estimated_count == 45
    assert estimate.ci_low == 0
    assert estimate.ci_high == 1
    assert estimate.coefficient_fit_eligible is False
    assert estimate.missing_requirement == (
        "Joint distribution for sex = female AND education_isced = tertiary in Northern "
        "America, measured on the same weighted respondents, including source, version, date, "
        "sample size, survey weights, and confidence interval"
    )
    expected_markdown = (
        f"- [ ] {estimate.missing_requirement}. Current result is an independence estimate only."
    )
    assert estimate.missing_md_entry == expected_markdown


def test_measured_joint_data_replaces_the_independence_estimate_with_provenance():
    measured = MeasuredJointData(
        level="country",
        place="CAN",
        conditions=joined_filters(),
        probability=0.18,
        sample_size=2_400,
        ci_low=0.14,
        ci_high=0.22,
        population="Canadian adults",
        coverage_percent=88,
        provenance=evidence("Weighted Canadian microdata"),
    )

    estimate = estimate_joined_filters(
        feature_registry(), places(), region_selector(), joined_filters(), [measured]
    )

    assert estimate.method == "measured_joint"
    assert estimate.method_label == "measured joint"
    assert estimate.agent_percent == pytest.approx(18)
    assert estimate.estimated_count == 72
    assert estimate.ci_low == pytest.approx(0.14)
    assert estimate.ci_high == pytest.approx(0.22)
    assert estimate.measured_population_percent == 100
    assert estimate.missing_requirement is None
    assert estimate.missing_md_entry is None
    assert estimate.sources[0].source == "Weighted Canadian microdata"
    assert estimate.sources[0].sample_size == 2_400
    assert estimate.sources[0].source_date == "2025-01-01"


def test_continuous_threshold_uses_the_resolved_distribution():
    filters = [
        FeatureFilter(feature_id="income", operator="gte", values=[100_000]),
        FeatureFilter(feature_id="education_isced", operator="eq", values=["tertiary"]),
    ]

    estimate = estimate_joined_filters(feature_registry(), places(), region_selector(), filters)

    assert estimate.method == "independence_estimate"
    assert estimate.agent_percent == pytest.approx(12.5)
    assert estimate.estimated_count == 50


def test_measured_joint_requires_date_sample_and_valid_interval():
    with pytest.raises(ValueError, match="source date"):
        MeasuredJointData(
            level="country",
            place="CAN",
            conditions=joined_filters(),
            probability=0.18,
            sample_size=2_400,
            ci_low=0.14,
            ci_high=0.22,
            population="Canadian adults",
            coverage_percent=88,
            provenance=Evidence(
                source="Undated survey",
                version="fixture-v1",
                status="present",
                uncertainty=0.1,
            ),
        )
