import pytest
from pydantic import ValidationError

from petraterrium.simulation.finance_initialization import (
    CANADA_FINANCE_PROGRAM_ID,
    GLOBAL_FINANCE_PROGRAM_ID,
    FinanceExpression,
    FinanceInitializationCatalog,
    FinanceOutputRule,
    default_finance_initialization_catalog,
    default_global_finance_initialization_program,
    evaluate_finance_initialization,
    select_numeric_bucket,
)
from petraterrium.simulation.global_finance import (
    GlobalFinanceProfile,
    load_global_finance_pack,
    sample_global_finances,
)


def test_finance_initialization_catalog_exposes_global_and_canada_assumptions():
    catalog = default_finance_initialization_catalog()

    assert set(catalog.programs) == {
        GLOBAL_FINANCE_PROGRAM_ID,
        CANADA_FINANCE_PROGRAM_ID,
    }
    global_program = catalog.programs[GLOBAL_FINANCE_PROGRAM_ID]
    canada_program = catalog.programs[CANADA_FINANCE_PROGRAM_ID]
    assert {
        "income",
        "expenses",
        "money",
        "savings",
        "debt",
        "income_quintile_index",
    } <= global_program.outputs.keys()
    assert global_program.outputs["debt"].formula
    assert global_program.assumptions["debt_proxy"].status == "default_estimated"
    assert canada_program.constants["open_income_band_maximum"] == 250_000
    assert canada_program.constants["profile_uncertainty"] == 0.9
    assert canada_program.assumptions["wealth_spread"].status == "default_estimated"
    assert select_numeric_bucket(canada_program, "spending_quintile", 60_000) == (
        "Quatrième quintile"
    )
    assert FinanceInitializationCatalog.model_validate(
        catalog.model_dump(mode="json")
    ) == catalog


def test_expression_schema_rejects_invalid_operator_shape():
    with pytest.raises(ValidationError):
        FinanceExpression(op="divide", args=(FinanceExpression.constant(1),))


def test_interpreter_is_deterministic_and_program_driven():
    program = default_global_finance_initialization_program()
    context = {
        "gni_per_capita_ppp": 10_000.0,
        "income_shares": [5.0, 10.0, 15.0, 25.0, 45.0],
        "household_consumption_per_capita_ppp": 7_000.0,
        "adjusted_net_savings_pct_gni": 12.0,
        "private_credit_pct_gdp": 60.0,
    }

    first = evaluate_finance_initialization(program, context, 7, "agent-1")
    repeated = evaluate_finance_initialization(program, context, 7, "agent-1")
    assert first == repeated
    assert all(first.values[key] >= 0 for key in ("income", "expenses", "money", "savings", "debt"))

    doubled_income = FinanceOutputRule(
        formula="income = 2 × original income expression",
        expression=FinanceExpression(
            op="multiply",
            args=(
                program.outputs["income"].expression,
                FinanceExpression.constant(2),
            ),
        ),
        assumption_ids=program.outputs["income"].assumption_ids,
    )
    modified = program.model_copy(
        update={"outputs": {**program.outputs, "income": doubled_income}}
    )
    changed = evaluate_finance_initialization(modified, context, 7, "agent-1")

    assert changed.values["income"] == first.values["income"] * 2


def test_global_sampler_accepts_the_validated_program_from_the_dsl_hook():
    pack = load_global_finance_pack()
    profile = GlobalFinanceProfile(agent_id="dsl-finance", country_code="IN")
    program = default_global_finance_initialization_program()

    sampled = sample_global_finances(profile, pack, seed=1, program=program)
    replacement = program.outputs["money"].model_copy(
        update={"expression": FinanceExpression.constant(123.45)}
    )
    modified = program.model_copy(
        update={"outputs": {**program.outputs, "money": replacement}}
    )
    changed = sample_global_finances(profile, pack, seed=1, program=modified)

    assert sampled.values["money"] != 123.45
    assert changed.values["money"] == 123.45
    assert changed.values["income"] == sampled.values["income"]
