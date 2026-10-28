import pytest

from petraterrium.atlas.feature_dump.priority_features import PRIORITY_COUNTRY_CODES
from petraterrium.atlas.regions import CANONICAL_REGIONS
from petraterrium.simulation.global_demo_population import (
    GLOBAL_DEMO_COUNTRIES,
    GlobalFinanceAssignment,
    build_global_demo_population,
)


def test_global_demo_has_one_thousand_population_weighted_agents_across_all_regions() -> None:
    result = build_global_demo_population()

    assert len(result.population.agents) == 1_000
    assert result.summary.total_agents == 1_000
    assert result.summary.country_agent_counts == {
        "AU": 6,
        "BD": 36,
        "BR": 45,
        "CA": 8,
        "CN": 304,
        "ID": 60,
        "IN": 307,
        "MX": 28,
        "NG": 49,
        "PK": 53,
        "RU": 31,
        "US": 73,
    }
    assert set(result.summary.country_agent_counts) == set(GLOBAL_DEMO_COUNTRIES)
    assert set(result.summary.region_agent_counts) == set(CANONICAL_REGIONS)
    assert result.summary.region_agent_counts["Rest / unassigned"] == 0
    assert all(
        result.summary.region_agent_counts[region] > 0
        for region in CANONICAL_REGIONS
        if region != "Rest / unassigned"
    )
    populations = {
        country: next(
            int(agent.traits["country_population"])
            for agent in result.population.agents
            if agent.traits["country_id"] == country
        )
        for country in GLOBAL_DEMO_COUNTRIES
    }
    represented_population = sum(populations.values())
    assert all(
        abs(
            result.summary.country_agent_counts[country]
            - 1_000 * populations[country] / represented_population
        )
        < 1
        for country in GLOBAL_DEMO_COUNTRIES
    )


def test_global_demo_is_deterministic_and_contains_no_names() -> None:
    first = build_global_demo_population()
    repeated = build_global_demo_population()
    changed = build_global_demo_population(seed=2)

    assert first.model_dump(mode="json") == repeated.model_dump(mode="json")
    assert first.model_dump(mode="json") != changed.model_dump(mode="json")
    assert all("name" not in agent.traits for agent in first.population.agents)
    assert len({agent.agent_id for agent in first.population.agents}) == 1_000
    assert [agent.log_tier for agent in first.population.agents[:3]] == [
        "spotlight",
        "spotlight",
        "sampled",
    ]


def test_global_demo_reports_country_regional_and_estimated_evidence_without_cross_country_fallback(
) -> None:
    result = build_global_demo_population()
    fields = result.summary.major_fields

    assert fields["age"].country_measured == sorted(GLOBAL_DEMO_COUNTRIES)
    assert fields["sex"].country_measured == sorted(GLOBAL_DEMO_COUNTRIES)
    assert fields["personality"].country_measured == sorted(PRIORITY_COUNTRY_CODES)
    assert fields["personality"].regional_imputed == ["AU", "CA"]
    assert set(fields["specialization"].country_measured) | set(
        fields["specialization"].estimated
    ) == set(GLOBAL_DEMO_COUNTRIES)
    assert fields["specialization"].regional_imputed == []
    assert sum(fields["specialization"].agent_counts.values()) == 1_000
    assert fields["finance"].country_measured == sorted(GLOBAL_DEMO_COUNTRIES)
    assert fields["finance"].agent_counts == {
        "country_measured": 1_000,
        "regional_imputed": 0,
        "estimated": 0,
    }
    for field in (
        "money",
        "income",
        "expenses",
        "savings",
        "debt",
        "wages",
        "prices",
        "costs",
        "currency",
    ):
        assert sum(fields[field].agent_counts.values()) == 1_000
        assert set(fields[field].country_measured) | set(
            fields[field].regional_imputed
        ) | set(fields[field].estimated) == set(GLOBAL_DEMO_COUNTRIES)
    comparisons = result.summary.distribution_comparisons
    assert {
        "age",
        "sex",
        "education_isced",
        "occupation_isco",
        "specialization",
        "openness",
        "ideology_economic",
    } <= comparisons.keys()
    assert set(comparisons["age"].country_distributions) == set(GLOBAL_DEMO_COUNTRIES)
    assert set(comparisons["age"].region_distributions) == (
        set(CANONICAL_REGIONS) - {"Rest / unassigned"}
    )
    assert comparisons["age"].global_distribution.agent_count == 1_000
    assert result.summary.cross_country_relationships.relationship_count == 0
    assert any(
        item.id == "interactions:cross-country-missing"
        for item in result.summary.deviations
    )
    canada = next(
        agent for agent in result.population.agents if agent.traits["country_id"] == "CA"
    )
    india = next(
        agent for agent in result.population.agents if agent.traits["country_id"] == "IN"
    )
    assert canada.traits["education_evidence_scope"] == "regional_imputed"
    assert canada.traits["education_source_place"] == "Northern America"
    assert india.traits["education_evidence_scope"] == "country_measured"
    assert india.traits["education_source_place"] == "IN"
    assert india.traits["feature_provenance"]["education_isced"]["sampling_status"] == (
        "imputed_individual_draw"
    )
    assert india.traits["age_source_status"] == "present"
    assert all(
        agent.traits["specialization_status"] == (
            "not_applicable"
            if agent.traits["years_of_education"]
            < agent.traits["specialization_threshold_years"]
            else "present"
        )
        for agent in result.population.agents
    )
    assert {agent.traits["specialization_status"] for agent in result.population.agents} == {
        "not_applicable",
        "present",
    }
    assert all(
        agent.traits["specialization_evidence_scope"] in {
            "country_measured",
            "estimated",
        }
        and agent.traits["specialization_pipeline_attempt_id"]
        and agent.traits["specialization_search_log_count"] > 0
        for agent in result.population.agents
    )
    assert not any(
        item.field == "specialization" and item.status == "default_estimated"
        for item in result.summary.deviations
    )


def test_finance_callback_blocks_a_canadian_source_for_non_canadian_agents() -> None:
    def canadian_fallback(_profile):
        return GlobalFinanceAssignment(
            evidence_scope="country_measured",
            source_place="Canada",
            source_id="statscan-canada-only",
            source_status="present",
            source="Statistics Canada",
            source_version="test",
            source_date="2023-12-31",
            uncertainty=0.1,
            currency="CAD",
            money=1,
            annual_income=1,
            annual_expenses=1,
            savings=1,
            debt=1,
        )

    with pytest.raises(ValueError, match="does not match agent country IN"):
        build_global_demo_population(finance_resolver=canadian_fallback)


def test_finance_callback_blocks_disguised_canadian_source_for_non_canadian_agents() -> None:
    def canadian_fallback(profile):
        return GlobalFinanceAssignment(
            evidence_scope="country_measured",
            source_place=profile.country_code,
            source_id="statscan-canada-only",
            source_status="present",
            source="Statistics Canada",
            source_version="test",
            source_date="2023-12-31",
            uncertainty=0.1,
            currency="CAD",
            money=1,
            annual_income=1,
            annual_expenses=1,
            savings=1,
            debt=1,
        )

    with pytest.raises(
        ValueError,
        match="Canadian finance source cannot be assigned to agent country IN",
    ):
        build_global_demo_population(finance_resolver=canadian_fallback)


def test_finance_summary_separates_components_currency_and_estimated_rates() -> None:
    def own_country_finance(profile):
        return GlobalFinanceAssignment(
            evidence_scope="country_measured",
            source_place=profile.country_code,
            source_id=f"finance:{profile.country_code}",
            source_status="imputed",
            source="Own-country finance fixture",
            source_version="test",
            source_date="2026-10-27",
            uncertainty=1,
            currency=f"{profile.country_code}C",
            money=100,
            annual_income=1_000,
            annual_expenses=800,
            savings=50,
            debt=25,
        )

    result = build_global_demo_population(
        target_agents=len(GLOBAL_DEMO_COUNTRIES),
        finance_resolver=own_country_finance,
    )
    fields = result.summary.major_fields

    for field in (
        "finance",
        "money",
        "income",
        "expenses",
        "savings",
        "debt",
        "costs",
        "currency",
    ):
        assert fields[field].country_measured == sorted(GLOBAL_DEMO_COUNTRIES)
        assert fields[field].regional_imputed == []
    for field in ("wages", "prices"):
        assert fields[field].estimated == sorted(GLOBAL_DEMO_COUNTRIES)
    assert set(
        result.summary.distribution_comparisons["finance_annual_income"]
        .country_distributions
    ) == set(GLOBAL_DEMO_COUNTRIES)
    assert set(
        result.summary.distribution_comparisons["finance_currency"].country_distributions
    ) == set(GLOBAL_DEMO_COUNTRIES)
    assert any(
        item.id == "finance:person-level-imputation"
        for item in result.summary.deviations
    )


def test_ppp_accounting_unit_does_not_claim_to_be_a_local_currency() -> None:
    def ppp_finance(profile):
        return GlobalFinanceAssignment(
            evidence_scope="country_measured",
            source_place=profile.country_code,
            source_id=f"wdi:{profile.country_code}",
            source_status="imputed",
            source="World Bank World Development Indicators",
            source_version="test",
            source_date="2026-10-27",
            uncertainty=1,
            currency="PPP",
            money=100,
            annual_income=1_000,
            annual_expenses=800,
            savings=50,
            debt=25,
        )

    result = build_global_demo_population(
        target_agents=len(GLOBAL_DEMO_COUNTRIES),
        finance_resolver=ppp_finance,
    )

    assert result.summary.major_fields["currency"].estimated == sorted(
        GLOBAL_DEMO_COUNTRIES
    )
    assert all(
        agent.traits["finance_local_currency"] == "PPP"
        and agent.traits["finance_accounting_unit"] == "PPP"
        for agent in result.population.agents
    )


def test_default_global_finance_uses_each_country_or_its_own_region() -> None:
    result = build_global_demo_population(target_agents=len(GLOBAL_DEMO_COUNTRIES))

    for agent in result.population.agents:
        country = agent.traits["country_id"]
        source_place = agent.traits["finance_source_place"]
        assert source_place in {country, agent.traits["region"]}
        if country != "CA":
            assert "Statistics Canada" not in agent.traits["finance_source"]
        assert agent.traits["finance_local_currency"]
        assert agent.traits["finance_price_level_ratio"] > 0
        assert agent.traits["finance_wage_per_workday"] >= 0
