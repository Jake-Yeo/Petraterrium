import pytest

from petraterrium.simulation.global_demo_interactions import (
    attach_global_demo_cross_country_relationships,
    global_demo_interaction_program,
)
from petraterrium.simulation.global_demo_population import (
    GLOBAL_DEMO_COUNTRIES,
    DistributionSlice,
    build_global_demo_population,
)
from petraterrium.simulation.initial_agent_summary import _distribution_bins
from petraterrium.simulation.initial_agents import InitialAgentCatalog, InitialAgentQuery


@pytest.fixture(scope="module")
def global_population():
    population = build_global_demo_population(
        target_agents=len(GLOBAL_DEMO_COUNTRIES)
    ).population
    return attach_global_demo_cross_country_relationships(population)


@pytest.fixture(scope="module")
def global_summary(global_population):
    catalog = InitialAgentCatalog.from_population(
        global_population,
        interaction_program=global_demo_interaction_program(),
    )
    return catalog.search(InitialAgentQuery(page_size=1)).evidence_summary


def test_initial_agent_global_summary_exposes_place_counts_and_source_provenance(
    global_summary,
) -> None:
    assert global_summary.total_agents == len(GLOBAL_DEMO_COUNTRIES)
    assert set(global_summary.country_agent_counts) == {
        "Australia",
        "Bangladesh",
        "Brazil",
        "Canada",
        "China",
        "India",
        "Indonesia",
        "Mexico",
        "Nigeria",
        "Pakistan",
        "Russian Federation",
        "United States of America",
    }
    assert len(global_summary.region_agent_counts) == 8
    assert set(global_summary.fields) >= {
        "age",
        "sex",
        "education",
        "specialization",
        "occupation",
        "personality",
        "values",
        "money",
        "income",
        "expenses",
        "wages",
        "prices",
        "costs",
        "currency",
    }
    age = global_summary.fields["age"]
    assert age.measured == []
    assert age.own_country_inherited == sorted(global_summary.country_agent_counts)
    assert age.estimated == []
    india_age = next(
        evidence for evidence in age.place_evidence if evidence.country_code == "IN"
    )
    assert india_age.status == "own_country_inherited"
    assert india_age.source_place == "IN"
    assert india_age.source_level == "country"
    assert india_age.source == (
        "United Nations, Department of Economic and Social Affairs, Population Division"
    )
    assert india_age.source_version == "2024 Revision"
    canada_personality = next(
        evidence
        for evidence in global_summary.fields["personality"].place_evidence
        if evidence.country_code == "CA"
    )
    assert canada_personality.status == "regional_imputed"
    assert canada_personality.source_place == "Northern America"
    assert global_summary.fields["finance"].own_country_inherited == sorted(
        global_summary.country_agent_counts
    )
    specialization = global_summary.fields["specialization"]
    assert set(specialization.own_country_inherited) | set(specialization.estimated) == set(
        global_summary.country_agent_counts
    )
    assert global_summary.fields["specialization"].regional_imputed == []


def test_initial_agent_global_summary_exposes_weighted_distribution_comparisons(
    global_population,
    global_summary,
) -> None:
    global_comparison = next(
        comparison
        for comparison in global_summary.comparisons
        if comparison.level == "global"
    )
    assert global_comparison.agent_count == len(GLOBAL_DEMO_COUNTRIES)
    global_sex = next(
        distribution
        for distribution in global_comparison.distributions
        if distribution.field_id == "sex"
    )
    assert sum(item.percentage for item in global_sex.bins) == pytest.approx(100)
    assert sum(item.estimated_agents for item in global_sex.bins) == len(
        GLOBAL_DEMO_COUNTRIES
    )
    global_age = next(
        distribution
        for distribution in global_comparison.distributions
        if distribution.field_id == "age"
    )
    expected_ages = sorted({int(agent.traits["age"]) for agent in global_population.agents})
    assert [bin_.label for bin_ in global_age.bins] == [
        f"Age {age}" for age in expected_ages
    ]
    assert sum(item.percentage for item in global_age.bins) == pytest.approx(100)
    assert "Population-weighted mean" in global_age.summary
    china_comparison = next(
        comparison
        for comparison in global_summary.comparisons
        if comparison.comparison_id == "country:CN"
    )
    china_age = next(
        distribution
        for distribution in china_comparison.distributions
        if distribution.field_id == "age"
    )
    china_ages = sorted(
        {
            int(agent.traits["age"])
            for agent in global_population.agents
            if agent.traits["country_id"] == "CN"
        }
    )
    assert [bin_.label for bin_ in china_age.bins] == [
        f"Age {age}" for age in china_ages
    ]
    assert all(bin_.estimated_agents >= 1 for bin_ in china_age.bins)
    persisted = global_summary.model_dump(mode="json")
    persisted_china = next(
        comparison
        for comparison in persisted["comparisons"]
        if comparison["comparison_id"] == "country:CN"
    )
    persisted_china_age = next(
        distribution
        for distribution in persisted_china["distributions"]
        if distribution["field_id"] == "age"
    )
    assert persisted_china_age["bins"] == [
        bin_.model_dump(mode="json") for bin_ in china_age.bins
    ]
    for comparison in global_summary.comparisons:
        selected_agents = [
            agent
            for agent in global_population.agents
            if comparison.level == "global"
            or (
                comparison.level == "country"
                and agent.traits["country"] == comparison.place
            )
            or (
                comparison.level == "region"
                and agent.traits["region"] == comparison.place
            )
        ]
        age_distribution = next(
            distribution
            for distribution in comparison.distributions
            if distribution.field_id == "age"
        )
        assert [bin_.label for bin_ in age_distribution.bins] == [
            f"Age {age}"
            for age in sorted({int(agent.traits["age"]) for agent in selected_agents})
        ]
    assert all(
        any(
            distribution.field_id == "age"
            for distribution in comparison.distributions
        )
        for comparison in global_summary.comparisons
    )


def test_categorical_distribution_display_clamps_float_drift_at_one_hundred_percent():
    bins = _distribution_bins(
        DistributionSlice(
            agent_count=6,
            represented_population=26_451_124,
            distribution_type="categorical",
            categories={"Australian dollar": 1.0000000000000002},
        )
    )

    assert bins[0].percentage == 100
    assert bins[0].estimated_agents == 6


def test_initial_agent_global_summary_registers_gaps_and_configured_interactions(
    global_summary,
) -> None:
    assert not any(deviation.field == "currency" for deviation in global_summary.deviations)
    assert any(
        deviation.field == "personality"
        and deviation.status == "regional_imputed"
        and "Canada" in deviation.places
        for deviation in global_summary.deviations
    )
    specialization_gap = next(
        deviation
        for deviation in global_summary.deviations
        if deviation.field == "specialization"
    )
    assert specialization_gap.status == "estimated"
    assert set(specialization_gap.places) == set(
        global_summary.fields["specialization"].estimated
    )
    assert "confirmed" in specialization_gap.full_requirement
    assert "ISCED-F-compatible" in specialization_gap.full_requirement
    assert global_summary.interactions.status == "configured"
    assert global_summary.interactions.run_id is None
    assert global_summary.interactions.cross_country_interactions == len(
        GLOBAL_DEMO_COUNTRIES
    )
    assert global_summary.interactions.cross_region_interactions > 0
    assert set(global_summary.interactions.participating_countries) == set(
        global_summary.country_agent_counts
    )
    for field, coverage in global_summary.fields.items():
        for place in coverage.regional_imputed + coverage.estimated:
            assert any(
                deviation.field == field and place in deviation.places
                for deviation in global_summary.deviations
            )
        for evidence in coverage.place_evidence:
            if evidence.country_code == "CA":
                continue
            assert evidence.source_place not in {"CA", "Canada"}
            assert "Statistics Canada" not in (evidence.source or "")
