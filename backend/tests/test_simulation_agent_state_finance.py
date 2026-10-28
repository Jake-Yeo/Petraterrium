from datetime import date

from petraterrium.simulation.agent_state import (
    CashFlow,
    CountryEducationMapping,
    EducationLabel,
    FinanceAmountRange,
    FinanceCondition,
    FinanceDistribution,
    FinanceDistributionCell,
    FinanceEvidence,
    FinanceProfileInput,
    StateDecisionModifier,
    StateEvidence,
    StateLinearRule,
    StateTransitionPlan,
    advance_finances,
    advance_state_vector,
    core_agent_state_catalog,
    evaluate_decision_probability,
    initialize_finances,
    relationship_state_catalog,
    resolve_education_profile,
    state_vector_from_values,
)


def evidence(status: str = "measured_joint") -> StateEvidence:
    return StateEvidence(
        status=status,
        source="Imported Canadian education and labour joint table",
        source_version="2023-v1",
        source_date=date(2023, 12, 31),
        place="CA",
        population="Canadian residents represented by the imported table",
        language="en",
        original_title="Imported Canadian education and labour joint table",
        english_title="Imported Canadian education and labour joint table",
        search_source="Statistics Canada",
        uncertainty=0.04,
    )


def education_mapping() -> CountryEducationMapping:
    return CountryEducationMapping(
        country_code="CA",
        version="ca-school-labels-2023-v1",
        labels=(
            EducationLabel(years=0, isced_level=0, label="No schooling yet"),
            EducationLabel(years=1, isced_level=0, label="Preschool"),
            EducationLabel(years=2, isced_level=0, label="Kindergarten"),
            EducationLabel(years=3, isced_level=1, label="Grade 1"),
            EducationLabel(years=12, isced_level=3, label="Secondary completion"),
            EducationLabel(years=16, isced_level=6, label="Bachelor's degree"),
        ),
        specialization_threshold_years=12,
        provenance=evidence("measured_marginal"),
    )


def test_country_education_mapping_and_specialization_threshold_are_explicit() -> None:
    mapping = education_mapping()

    assert resolve_education_profile(1, "CA", None, mapping).country_label == "Preschool"
    assert resolve_education_profile(2, "CA", None, mapping).country_label == "Kindergarten"
    assert resolve_education_profile(3, "CA", None, mapping).country_label == "Grade 1"
    below = resolve_education_profile(11, "CA", "engineering", mapping)
    qualified = resolve_education_profile(16, "CA", "engineering", mapping)

    assert below.specialization is None
    assert below.specialization_status == "not_applicable"
    assert qualified.specialization == "engineering"
    assert qualified.specialization_status == "present"
    assert qualified.specialization_threshold_years == 12
    assert qualified.provenance == mapping.provenance


def finance_evidence() -> FinanceEvidence:
    return FinanceEvidence(
        status="measured_joint",
        source="Imported financial microdata fixture",
        source_version="2023-v1",
        source_date=date(2023, 12, 31),
        place="CA",
        population="Canadian residents represented by the imported joint table",
        currency="CAD",
        uncertainty=0.03,
    )


def amount(minimum: float, median: float, maximum: float) -> FinanceAmountRange:
    return FinanceAmountRange(minimum=minimum, median=median, maximum=maximum)


def finance_distribution() -> FinanceDistribution:
    return FinanceDistribution(
        id="ca-finance-joint-2023",
        place="CA",
        currency="CAD",
        evidence=finance_evidence(),
        cells=(
            FinanceDistributionCell(
                id="student-20",
                condition=FinanceCondition(
                    age_min=18,
                    age_max=24,
                    education_years_min=12,
                    education_years_max=15,
                    occupations=("student",),
                    specializations=("none",),
                ),
                weight=1,
                money=amount(500, 1_500, 4_000),
                income=amount(6_000, 12_000, 24_000),
                expenses=amount(12_000, 18_000, 28_000),
                savings=amount(0, 500, 2_000),
                debt=amount(0, 5_000, 20_000),
            ),
            FinanceDistributionCell(
                id="owner-40",
                condition=FinanceCondition(
                    age_min=35,
                    age_max=49,
                    education_years_min=16,
                    occupations=("business_owner",),
                    specializations=("business",),
                ),
                weight=1,
                money=amount(20_000, 60_000, 140_000),
                income=amount(80_000, 130_000, 250_000),
                expenses=amount(45_000, 70_000, 120_000),
                savings=amount(40_000, 180_000, 600_000),
                debt=amount(0, 40_000, 300_000),
            ),
        ),
    )


def test_finance_initialization_is_conditioned_deterministic_and_auditable() -> None:
    distribution = finance_distribution()
    student_input = FinanceProfileInput(
        agent_id="agent-student",
        place="CA",
        age=20,
        sex="female",
        years_of_education=12,
        specialization=None,
        occupation="student",
    )
    owner_input = FinanceProfileInput(
        agent_id="agent-owner",
        place="CA",
        age=40,
        sex="male",
        years_of_education=16,
        specialization="business",
        occupation="business_owner",
    )

    student = initialize_finances(student_input, (distribution,), seed=77)
    repeated = initialize_finances(student_input, (distribution,), seed=77)
    owner = initialize_finances(owner_input, (distribution,), seed=77)

    assert student == repeated
    assert student.source_cell_id == "student-20"
    assert owner.source_cell_id == "owner-40"
    assert owner.money.value is not None and student.money.value is not None
    assert owner.money.value > student.money.value
    assert owner.income.value is not None and student.income.value is not None
    assert owner.income.value > student.income.value
    assert owner.evidence.status == "measured_joint"


def test_finance_without_a_matching_distribution_stays_unknown() -> None:
    profile = initialize_finances(
        FinanceProfileInput(
            agent_id="agent-unknown",
            place="JP",
            age=30,
            sex="female",
            years_of_education=14,
            specialization=None,
            occupation="worker",
        ),
        (),
        seed=1,
    )

    assert profile.status == "unknown"
    assert profile.money.value is None
    assert profile.income.value is None
    assert "No matching imported finance distribution" in profile.evidence.source


def test_generic_state_and_finance_ticks_apply_data_rules_without_scenario_branches() -> None:
    measured = evidence()
    plan = StateTransitionPlan(
        rules=(
            StateLinearRule(
                target_state_id="health",
                intercept=0,
                coefficients={"stress": -0.05},
                minimum=0,
                maximum=1,
                formula="health[t+1] = clamp(health[t] - 0.05 × stress[t], 0, 1)",
                evidence=measured,
            ),
        ),
        decision_modifiers=(
            StateDecisionModifier(
                decision_id="skip_lunch",
                state_id="stress",
                formula="factor = clamp(1 + 0.8 × (stress - 0.5), 0.1, 2)",
                coefficient=0.8,
                center=0.5,
                minimum_factor=0.1,
                maximum_factor=2,
                direction="increases",
                evidence=measured,
            ),
            StateDecisionModifier(
                decision_id="go_to_gym",
                state_id="stress",
                formula="factor = clamp(1 + 0.4 × (stress - 0.5), 0.1, 2)",
                coefficient=0.4,
                center=0.5,
                minimum_factor=0.1,
                maximum_factor=2,
                direction="increases",
                evidence=measured,
            ),
        ),
    )
    initial = {"stress": 0.5, "health": 0.9}
    after_work = advance_state_vector(initial, plan, {"stress": 0.3})
    later = advance_state_vector(after_work.values, plan, {})
    after_gym = advance_state_vector(later.values, plan, {"stress": -0.25})

    assert after_work.values["stress"] == 0.8
    assert later.values["health"] < after_work.values["health"]
    assert after_gym.values["stress"] < later.values["stress"]
    assert evaluate_decision_probability(0.2, after_work.values, plan, "skip_lunch") > 0.2
    assert evaluate_decision_probability(0.2, after_work.values, plan, "go_to_gym") > 0.2
    assert after_work.receipts[0].formula == plan.rules[0].formula

    finance = initialize_finances(
        FinanceProfileInput(
            agent_id="agent-owner",
            place="CA",
            age=40,
            sex="male",
            years_of_education=16,
            specialization="business",
            occupation="business_owner",
        ),
        (finance_distribution(),),
        seed=77,
    )
    updated = advance_finances(
        finance,
        CashFlow(
            wages=2_000,
            business_income=1_000,
            transfers=100,
            housing=900,
            food=250,
            transport=100,
            other_expenses=200,
            taxes=600,
            savings_contribution=300,
            savings_withdrawal=0,
            debt_draw=0,
            debt_repayment=250,
        ),
    )

    assert updated.money.value == finance.money.value + 500
    assert updated.income.value == 3_100
    assert updated.expenses.value == 2_050
    assert updated.savings.value == finance.savings.value + 300
    assert updated.debt.value == max(0, finance.debt.value - 250)
    assert "wages + business_income + transfers" in updated.formula


def test_core_catalog_documents_groups_loops_and_directed_love() -> None:
    catalog = core_agent_state_catalog()
    by_id = {definition.id: definition for definition in catalog.definitions}

    assert {definition.group for definition in catalog.definitions} == {
        "emotion",
        "slow_trait",
        "health_body",
        "life_social",
        "social_economic",
    }
    assert {
        "stress",
        "outrage",
        "fear",
        "happiness",
        "sadness",
        "anger",
        "generalized_trust",
        "grief",
        "depression_level",
        "loneliness",
        "impulsivity",
        "extraversion",
        "conscientiousness",
        "risk_aversion",
        "work_ethic",
        "patience",
        "health",
        "sleep_quality",
        "hunger",
        "fatigue",
        "illness_severity",
        "is_employed",
        "is_married",
        "is_parent",
        "is_student",
        "is_retired",
        "social_status",
        "reputation",
        "financial_stress",
        "job_satisfaction",
        "political_engagement",
    } <= set(by_id)
    assert "love" not in by_id
    assert relationship_state_catalog().definitions[0].id == "love"
    stress_formulas = {
        modifier.formula for modifier in by_id["stress"].decision_modifiers
    }
    assert any(
        "skip_lunch" in modifier.decision_id
        for modifier in by_id["stress"].decision_modifiers
    )
    assert any(
        "go_to_gym" in modifier.decision_id
        for modifier in by_id["stress"].decision_modifiers
    )
    assert stress_formulas
    assert any(loop.target_state_id == "health" for loop in by_id["stress"].propagation)
    assert any(effect.event_id == "exercise" for effect in by_id["stress"].event_effects)


def test_state_vector_preserves_default_and_per_state_provenance() -> None:
    vector = state_vector_from_values(
        "CA",
        {
            "state_status": "default_estimated",
            "state_source": "Shipped default state initialization",
            "state_source_version": "base-1.0.0",
            "state_source_population": "Synthetic default population",
            "state_uncertainty": 1,
            "state_default_reason": "No matching promoted marginal was available",
            "state_provenance": {
                "stress": {
                    "status": "measured_marginal",
                    "source": "Imported stress distribution",
                    "source_version": "2022-v1",
                    "source_date": "2022-12-31",
                    "population": "Canadian adults",
                    "uncertainty": 0.08,
                }
            },
        },
        {"stress": "0.7", "health": "0.8"},
    )
    by_id = {value.state_id: value for value in vector.values}

    assert by_id["stress"].evidence.status == "measured_marginal"
    assert by_id["stress"].evidence.source == "Imported stress distribution"
    assert by_id["health"].evidence.status == "default_estimated"
    assert by_id["health"].evidence.default_reason == (
        "No matching promoted marginal was available"
    )

