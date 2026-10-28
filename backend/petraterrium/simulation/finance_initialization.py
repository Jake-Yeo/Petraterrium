from __future__ import annotations

import hashlib
import math
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FinanceOperator = Literal[
    "constant",
    "input",
    "draw",
    "add",
    "subtract",
    "multiply",
    "divide",
    "minimum",
    "maximum",
    "sum",
    "floor",
    "round",
    "exp",
    "log",
    "less_than_or_equal",
    "if_else",
    "index",
    "coalesce",
]
FinanceAssumptionStatus = Literal["measured", "imputed", "default_estimated"]


class FinanceInitializationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FinanceExpression(FinanceInitializationModel):
    op: FinanceOperator
    args: tuple[FinanceExpression, ...] = ()
    value: float | int | bool | str | None = None
    name: str | None = None
    draw_key: tuple[str, ...] = ()
    decimals: int = Field(default=2, ge=0, le=8)

    @classmethod
    def constant(cls, value: float | int | bool | str) -> FinanceExpression:
        return cls(op="constant", value=value)

    @classmethod
    def input(cls, name: str) -> FinanceExpression:
        return cls(op="input", name=name)

    @classmethod
    def draw(cls, *draw_key: str) -> FinanceExpression:
        return cls(op="draw", draw_key=draw_key)

    @model_validator(mode="after")
    def validate_shape(self) -> FinanceExpression:
        if self.op == "constant":
            if self.value is None or self.args or self.name or self.draw_key:
                raise ValueError("constant requires only value")
            return self
        if self.op == "input":
            if not self.name or self.args or self.value is not None or self.draw_key:
                raise ValueError("input requires only name")
            return self
        if self.op == "draw":
            if not self.draw_key or self.args or self.value is not None or self.name:
                raise ValueError("draw requires only a non-empty draw_key")
            return self
        arity = len(self.args)
        exact_arities = {
            "subtract": 2,
            "divide": 2,
            "floor": 1,
            "round": 1,
            "exp": 1,
            "log": 1,
            "less_than_or_equal": 2,
            "if_else": 3,
            "index": 2,
        }
        if self.op in exact_arities and arity != exact_arities[self.op]:
            raise ValueError(f"{self.op} requires {exact_arities[self.op]} arguments")
        if self.op in {"add", "multiply", "minimum", "maximum", "coalesce"} and arity < 2:
            raise ValueError(f"{self.op} requires at least two arguments")
        if self.op == "sum" and arity < 1:
            raise ValueError("sum requires at least one argument")
        if self.value is not None or self.name or self.draw_key:
            raise ValueError(f"{self.op} accepts arguments only")
        return self


class FinanceOutputRule(FinanceInitializationModel):
    formula: str = Field(min_length=1)
    expression: FinanceExpression
    assumption_ids: tuple[str, ...] = Field(min_length=1)


class FinanceInitializationAssumption(FinanceInitializationModel):
    status: FinanceAssumptionStatus
    description: str = Field(min_length=1)
    uncertainty: float = Field(ge=0, le=1)


class NumericBucket(FinanceInitializationModel):
    label: str = Field(min_length=1)
    maximum_exclusive: float | None = None


class FinanceInitializationProgram(FinanceInitializationModel):
    schema_version: Literal[1] = 1
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    required_inputs: tuple[str, ...]
    optional_inputs: tuple[str, ...] = ()
    outputs: dict[str, FinanceOutputRule]
    assumptions: dict[str, FinanceInitializationAssumption]
    numeric_buckets: dict[str, tuple[NumericBucket, ...]] = Field(default_factory=dict)
    categorical_aliases: dict[str, dict[str, str]] = Field(default_factory=dict)
    constants: dict[str, float | str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_program(self) -> FinanceInitializationProgram:
        required_outputs = {"income", "expenses", "money", "savings", "debt"}
        if missing := required_outputs - self.outputs.keys():
            raise ValueError(f"Finance program lacks outputs {sorted(missing)}")
        declared_inputs = set(self.required_inputs) | set(self.optional_inputs)
        if len(declared_inputs) != len(self.required_inputs) + len(self.optional_inputs):
            raise ValueError("Finance program input ids must be unique")
        referenced_inputs = {
            name
            for output in self.outputs.values()
            for name in _expression_inputs(output.expression)
        }
        if undeclared := referenced_inputs - declared_inputs:
            raise ValueError(f"Finance program uses undeclared inputs {sorted(undeclared)}")
        for output_id, output in self.outputs.items():
            if unknown := set(output.assumption_ids) - self.assumptions.keys():
                raise ValueError(
                    f"Finance output {output_id} uses unknown assumptions {sorted(unknown)}"
                )
        for selector_id, buckets in self.numeric_buckets.items():
            if not buckets or buckets[-1].maximum_exclusive is not None:
                raise ValueError(f"Numeric selector {selector_id} needs an unbounded last bucket")
            finite_bounds = [
                bucket.maximum_exclusive
                for bucket in buckets
                if bucket.maximum_exclusive is not None
            ]
            if finite_bounds != sorted(set(finite_bounds)):
                raise ValueError(f"Numeric selector {selector_id} bounds must increase")
        return self


class FinanceInitializationCatalog(FinanceInitializationModel):
    schema_version: Literal[1] = 1
    programs: dict[str, FinanceInitializationProgram]

    @model_validator(mode="after")
    def validate_program_ids(self) -> FinanceInitializationCatalog:
        for program_id, program in self.programs.items():
            if program.id != program_id:
                raise ValueError(f"Catalog key {program_id} does not match {program.id}")
        return self


class FinanceInitializationResult(FinanceInitializationModel):
    values: dict[str, float | int | bool | str]
    draws: dict[str, float]


GLOBAL_FINANCE_PROGRAM_ID = "global-wdi-finance-initialization"
CANADA_FINANCE_PROGRAM_ID = "canada-statscan-finance-initialization"


def _expression_inputs(expression: FinanceExpression) -> set[str]:
    names = {expression.name} if expression.op == "input" and expression.name else set()
    for argument in expression.args:
        names.update(_expression_inputs(argument))
    return names


def deterministic_unit_interval(
    seed: int, agent_id: str, draw_key: tuple[str, ...]
) -> float:
    encoded = "\x1f".join((str(seed), agent_id, *draw_key)).encode()
    integer = int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big")
    return (integer + 0.5) / 2**64


def deterministic_weighted_index(
    weights: tuple[float, ...],
    seed: int,
    agent_id: str,
    draw_key: tuple[str, ...],
) -> int:
    if not weights or any(weight < 0 for weight in weights):
        raise ValueError("Weighted selection needs non-negative weights")
    total = sum(weights)
    if total <= 0:
        raise ValueError("Weighted selection needs positive total weight")
    selection = deterministic_unit_interval(seed, agent_id, draw_key) * total
    cumulative = 0.0
    for index, weight in enumerate(weights):
        cumulative += weight
        if selection <= cumulative:
            return index
    return len(weights) - 1


def select_numeric_bucket(
    program: FinanceInitializationProgram, selector_id: str, value: float
) -> str:
    buckets = program.numeric_buckets.get(selector_id)
    if buckets is None:
        raise ValueError(f"Unknown numeric selector {selector_id}")
    for bucket in buckets:
        if bucket.maximum_exclusive is None or value < bucket.maximum_exclusive:
            return bucket.label
    raise ValueError(f"Numeric selector {selector_id} has no matching bucket")


def resolve_categorical_alias(
    program: FinanceInitializationProgram, selector_id: str, value: str
) -> str:
    aliases = program.categorical_aliases.get(selector_id)
    if aliases is None:
        raise ValueError(f"Unknown categorical selector {selector_id}")
    return aliases.get(value.casefold(), aliases["*"])


def _number(value: Any, operator: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{operator} requires numeric values")
    return float(value)


def _evaluate_expression(
    expression: FinanceExpression,
    context: dict[str, Any],
    optional_inputs: set[str],
    seed: int,
    agent_id: str,
    draws: dict[str, float],
) -> Any:
    if expression.op == "constant":
        return expression.value
    if expression.op == "input":
        if expression.name in context:
            return context[expression.name]
        if expression.name in optional_inputs:
            return None
        raise ValueError(f"Missing required finance input {expression.name}")
    if expression.op == "draw":
        draw_id = "|".join(expression.draw_key)
        draw = deterministic_unit_interval(seed, agent_id, expression.draw_key)
        draws[draw_id] = draw
        return draw
    if expression.op == "coalesce":
        for argument in expression.args:
            value = _evaluate_expression(
                argument, context, optional_inputs, seed, agent_id, draws
            )
            if value is not None:
                return value
        raise ValueError("coalesce found no available value")
    condition = None
    if expression.op == "if_else":
        condition = _evaluate_expression(
            expression.args[0], context, optional_inputs, seed, agent_id, draws
        )
        branch = expression.args[1] if condition else expression.args[2]
        return _evaluate_expression(branch, context, optional_inputs, seed, agent_id, draws)
    values = [
        _evaluate_expression(argument, context, optional_inputs, seed, agent_id, draws)
        for argument in expression.args
    ]
    if expression.op == "add":
        return sum(_number(value, expression.op) for value in values)
    if expression.op == "subtract":
        return _number(values[0], expression.op) - _number(values[1], expression.op)
    if expression.op == "multiply":
        return math.prod(_number(value, expression.op) for value in values)
    if expression.op == "divide":
        return _number(values[0], expression.op) / _number(values[1], expression.op)
    if expression.op == "minimum":
        return min(_number(value, expression.op) for value in values)
    if expression.op == "maximum":
        return max(_number(value, expression.op) for value in values)
    if expression.op == "sum":
        summands = values[0] if len(values) == 1 and isinstance(values[0], list) else values
        return sum(_number(value, expression.op) for value in summands)
    if expression.op == "floor":
        return math.floor(_number(values[0], expression.op))
    if expression.op == "round":
        return round(_number(values[0], expression.op), expression.decimals)
    if expression.op == "exp":
        return math.exp(_number(values[0], expression.op))
    if expression.op == "log":
        return math.log(_number(values[0], expression.op))
    if expression.op == "less_than_or_equal":
        return _number(values[0], expression.op) <= _number(values[1], expression.op)
    if expression.op == "index":
        collection = values[0]
        if not isinstance(collection, (list, tuple)):
            raise ValueError("index requires a list or tuple")
        return collection[int(_number(values[1], expression.op))]
    raise ValueError(f"Unsupported finance operator {expression.op}")


def evaluate_finance_initialization(
    program: FinanceInitializationProgram,
    context: dict[str, Any],
    seed: int,
    agent_id: str,
    output_ids: tuple[str, ...] | None = None,
) -> FinanceInitializationResult:
    selected_outputs = output_ids or tuple(program.outputs)
    if unknown := set(selected_outputs) - program.outputs.keys():
        raise ValueError(f"Unknown finance outputs {sorted(unknown)}")
    required_inputs = {
        name
        for output_id in selected_outputs
        for name in _expression_inputs(program.outputs[output_id].expression)
        if name not in program.optional_inputs
    }
    missing = required_inputs - context.keys()
    if missing:
        raise ValueError(f"Missing required finance inputs {sorted(missing)}")
    draws: dict[str, float] = {}
    values = {
        output_id: _evaluate_expression(
            rule.expression,
            context,
            set(program.optional_inputs),
            seed,
            agent_id,
            draws,
        )
        for output_id in selected_outputs
        for rule in (program.outputs[output_id],)
    }
    return FinanceInitializationResult(values=values, draws=draws)


def _op(op: FinanceOperator, *args: FinanceExpression, decimals: int = 2) -> FinanceExpression:
    return FinanceExpression(op=op, args=args, decimals=decimals)


def _global_outputs() -> dict[str, FinanceOutputRule]:
    constant = FinanceExpression.constant
    input_value = FinanceExpression.input
    draw = FinanceExpression.draw
    quintile = _op(
        "minimum",
        constant(4),
        _op("floor", _op("multiply", draw("income-quintile"), constant(5))),
    )
    normalized_share = _op(
        "divide",
        _op(
            "multiply",
            _op("index", input_value("income_shares"), quintile),
            constant(100),
        ),
        _op("sum", input_value("income_shares")),
    )
    income = _op(
        "round",
        _op(
            "maximum",
            constant(0),
            _op(
                "multiply",
                input_value("gni_per_capita_ppp"),
                _op("divide", normalized_share, constant(20)),
                _op(
                    "add",
                    constant(0.7),
                    _op("multiply", constant(0.6), draw("income-within-quintile")),
                ),
            ),
        ),
    )
    retained_rate = _op(
        "minimum",
        constant(50),
        _op(
            "maximum", constant(-25), input_value("adjusted_net_savings_pct_gni")
        ),
    )
    expense_fallback = _op(
        "multiply",
        input_value("gni_per_capita_ppp"),
        _op("subtract", constant(1), _op("divide", retained_rate, constant(100))),
    )
    expenses = _op(
        "round",
        _op(
            "maximum",
            constant(0),
            _op(
                "multiply",
                _op(
                    "coalesce",
                    input_value("household_consumption_per_capita_ppp"),
                    expense_fallback,
                ),
                _op("add", constant(0.8), _op("multiply", constant(0.4), draw("expenses"))),
            ),
        ),
    )
    money = _op(
        "round",
        _op(
            "divide",
            _op(
                "multiply",
                expenses,
                _op("add", constant(1), _op("multiply", constant(11), draw("liquid-weeks"))),
            ),
            constant(52),
        ),
    )
    savings = _op(
        "round",
        _op(
            "multiply",
            income,
            _op(
                "divide",
                _op(
                    "maximum",
                    constant(0),
                    input_value("adjusted_net_savings_pct_gni"),
                ),
                constant(100),
            ),
            _op("add", constant(0.5), draw("savings-stock")),
        ),
    )
    debt_probability = _op(
        "minimum",
        constant(0.85),
        _op(
            "maximum",
            constant(0.05),
            _op(
                "add",
                constant(0.15),
                _op("divide", input_value("private_credit_pct_gdp"), constant(300)),
            ),
        ),
    )
    debt_scale = _op(
        "minimum",
        constant(2),
        _op(
            "maximum",
            constant(0),
            _op("divide", input_value("private_credit_pct_gdp"), constant(100)),
        ),
    )
    debt = _op(
        "round",
        _op(
            "if_else",
            _op("less_than_or_equal", draw("debt-holding"), debt_probability),
            _op(
                "multiply",
                income,
                debt_scale,
                _op(
                    "add",
                    constant(0.1),
                    _op("multiply", constant(0.9), draw("debt-stock")),
                ),
            ),
            constant(0),
        ),
    )
    return {
        "income_quintile_index": FinanceOutputRule(
            formula="quintile = min(4, floor(U[income-quintile] × 5))",
            expression=quintile,
            assumption_ids=("equal_quintile_selection",),
        ),
        "income": FinanceOutputRule(
            formula=(
                "income = max(0, GNI PPP × selected quintile share / 20 "
                "× uniform(0.7, 1.3))"
            ),
            expression=income,
            assumption_ids=("equal_quintile_selection", "within_quintile_variation"),
        ),
        "expenses": FinanceOutputRule(
            formula=(
                "expenses = max(0, coalesce(household consumption PPP, "
                "GNI PPP × (1 - clamp(savings rate, -25, 50) / 100)) "
                "× uniform(0.8, 1.2))"
            ),
            expression=expenses,
            assumption_ids=("expense_variation", "expense_macro_fallback"),
        ),
        "money": FinanceOutputRule(
            formula="money = annual expenses × uniform(1, 12) / 52",
            expression=money,
            assumption_ids=("liquid_money_weeks",),
        ),
        "savings": FinanceOutputRule(
            formula=(
                "savings = income × max(0, adjusted net savings rate) / 100 "
                "× uniform(0.5, 1.5)"
            ),
            expression=savings,
            assumption_ids=("savings_stock_proxy",),
        ),
        "debt": FinanceOutputRule(
            formula=(
                "debt holding probability = clamp(0.15 + private credit / 300, "
                "0.05, 0.85); debt = income × clamp(private credit / 100, 0, 2) "
                "× uniform(0.1, 1.0) when held"
            ),
            expression=debt,
            assumption_ids=("debt_proxy",),
        ),
    }


@lru_cache(maxsize=1)
def default_global_finance_initialization_program() -> FinanceInitializationProgram:
    return FinanceInitializationProgram(
        id=GLOBAL_FINANCE_PROGRAM_ID,
        version="global-wdi-finance-initialization-v1",
        required_inputs=(
            "gni_per_capita_ppp",
            "income_shares",
            "adjusted_net_savings_pct_gni",
            "private_credit_pct_gdp",
        ),
        optional_inputs=("household_consumption_per_capita_ppp",),
        outputs=_global_outputs(),
        assumptions={
            "equal_quintile_selection": FinanceInitializationAssumption(
                status="imputed",
                description=(
                    "Each equal-population income quintile has probability 0.2 for a "
                    "synthetic agent because WDI supplies quintile shares, not microdata."
                ),
                uncertainty=0.8,
            ),
            "within_quintile_variation": FinanceInitializationAssumption(
                status="default_estimated",
                description=(
                    "Income varies uniformly from 0.7 to 1.3 of the selected "
                    "quintile mean."
                ),
                uncertainty=0.9,
            ),
            "expense_variation": FinanceInitializationAssumption(
                status="default_estimated",
                description="Expenses vary uniformly from 0.8 to 1.2 of the macro base.",
                uncertainty=0.9,
            ),
            "expense_macro_fallback": FinanceInitializationAssumption(
                status="default_estimated",
                description=(
                    "When household consumption is unavailable, expenses use GNI less "
                    "a savings rate clamped from -25 to 50 percent."
                ),
                uncertainty=0.96,
            ),
            "liquid_money_weeks": FinanceInitializationAssumption(
                status="default_estimated",
                description="Liquid money spans a uniform one to twelve weeks of expenses.",
                uncertainty=0.99,
            ),
            "savings_stock_proxy": FinanceInitializationAssumption(
                status="default_estimated",
                description=(
                    "A macro adjusted-net-savings flow proxies one year of person-level "
                    "savings stock with a uniform 0.5 to 1.5 multiplier."
                ),
                uncertainty=0.97,
            ),
            "debt_proxy": FinanceInitializationAssumption(
                status="default_estimated",
                description=(
                    "Private credit determines a bounded holding probability and an "
                    "income-scaled debt amount because household debt microdata are absent."
                ),
                uncertainty=0.99,
            ),
        },
    )


def _wealth_expression(asset: str, draw_asset: str) -> FinanceExpression:
    constant = FinanceExpression.constant
    input_value = FinanceExpression.input
    draw = FinanceExpression.draw
    return _op(
        "round",
        _op(
            "if_else",
            _op(
                "less_than_or_equal",
                _op("multiply", draw(draw_asset, "holds"), constant(100)),
                input_value(f"{asset}_holding_percent"),
            ),
            _op(
                "multiply",
                input_value(f"{asset}_median"),
                _op(
                    "exp",
                    _op(
                        "multiply",
                        _op("subtract", draw(draw_asset, "amount"), constant(0.5)),
                        _op("log", constant(16)),
                    ),
                ),
            ),
            constant(0),
        ),
    )


@lru_cache(maxsize=1)
def default_canada_finance_initialization_program() -> FinanceInitializationProgram:
    constant = FinanceExpression.constant
    input_value = FinanceExpression.input
    draw = FinanceExpression.draw
    income = _op(
        "round",
        _op(
            "add",
            input_value("income_band_minimum"),
            _op(
                "multiply",
                draw("income-value"),
                _op(
                    "subtract",
                    input_value("income_band_maximum"),
                    input_value("income_band_minimum"),
                ),
            ),
        ),
    )
    money = _wealth_expression(
        "deposits", "Dépôts dans des institutions financières"
    )
    financial_assets = _wealth_expression(
        "financial_assets", "Actifs financiers hors pension"
    )
    debt = _wealth_expression("debt", "Dette totale")
    expenses = _op("round", input_value("annual_expenses"))
    savings = _op(
        "round",
        _op("maximum", constant(0), _op("subtract", financial_assets, money)),
    )
    outputs = {
        "income": FinanceOutputRule(
            formula="income = uniform(income band minimum, income band maximum)",
            expression=income,
            assumption_ids=("within_income_band", "open_income_band_cap"),
        ),
        "expenses": FinanceOutputRule(
            formula="expenses = selected official spending-quintile mean",
            expression=expenses,
            assumption_ids=("spending_quintile_mapping",),
        ),
        "money": FinanceOutputRule(
            formula=(
                "money = 0 when the holding draw exceeds the official holding rate; "
                "otherwise deposit median × exp((U - 0.5) × log(16))"
            ),
            expression=money,
            assumption_ids=("wealth_holding_draw", "wealth_spread"),
        ),
        "financial_assets": FinanceOutputRule(
            formula=(
                "financial assets = 0 when the holding draw exceeds the official holding "
                "rate; otherwise median × exp((U - 0.5) × log(16))"
            ),
            expression=financial_assets,
            assumption_ids=("wealth_holding_draw", "wealth_spread"),
        ),
        "savings": FinanceOutputRule(
            formula="savings = max(0, financial assets - deposits)",
            expression=savings,
            assumption_ids=("savings_identity",),
        ),
        "debt": FinanceOutputRule(
            formula=(
                "debt = 0 when the holding draw exceeds the official holding rate; "
                "otherwise debt median × exp((U - 0.5) × log(16))"
            ),
            expression=debt,
            assumption_ids=("wealth_holding_draw", "wealth_spread"),
        ),
    }
    return FinanceInitializationProgram(
        id=CANADA_FINANCE_PROGRAM_ID,
        version="canada-statscan-finance-initialization-v1",
        required_inputs=(
            "income_band_minimum",
            "income_band_maximum",
            "annual_expenses",
            "deposits_holding_percent",
            "deposits_median",
            "financial_assets_holding_percent",
            "financial_assets_median",
            "debt_holding_percent",
            "debt_median",
        ),
        outputs=outputs,
        assumptions={
            "within_income_band": FinanceInitializationAssumption(
                status="imputed",
                description="An individual income is drawn uniformly within its measured band.",
                uncertainty=0.65,
            ),
            "open_income_band_cap": FinanceInitializationAssumption(
                status="default_estimated",
                description="The open 100,000 CAD and above band is capped at 250,000 CAD.",
                uncertainty=0.9,
            ),
            "wealth_holding_draw": FinanceInitializationAssumption(
                status="imputed",
                description="Individual holding status is sampled from the measured holding rate.",
                uncertainty=0.65,
            ),
            "wealth_spread": FinanceInitializationAssumption(
                status="default_estimated",
                description=(
                    "Held wealth and debt vary around the measured median over a factor-of-four "
                    "range in either direction."
                ),
                uncertainty=0.9,
            ),
            "spending_quintile_mapping": FinanceInitializationAssumption(
                status="default_estimated",
                description=(
                    "Personal income thresholds map agents to household spending quintile means."
                ),
                uncertainty=0.85,
            ),
            "savings_identity": FinanceInitializationAssumption(
                status="default_estimated",
                description=(
                    "Savings are represented as non-pension financial assets net of deposits."
                ),
                uncertainty=0.8,
            ),
        },
        numeric_buckets={
            "income_age": (
                NumericBucket(label="15 à 19 ans", maximum_exclusive=20),
                NumericBucket(label="20 à 24 ans", maximum_exclusive=25),
                NumericBucket(label="25 à 29 ans", maximum_exclusive=30),
                NumericBucket(label="30 à 34 ans", maximum_exclusive=35),
                NumericBucket(label="35 à 44 ans", maximum_exclusive=45),
                NumericBucket(label="45 à 54 ans", maximum_exclusive=55),
                NumericBucket(label="55 à 64 ans", maximum_exclusive=65),
                NumericBucket(label="65 à 74 ans", maximum_exclusive=75),
                NumericBucket(label="75 ans et plus"),
            ),
            "wealth_age": (
                NumericBucket(label="Moins de 35 ans", maximum_exclusive=35),
                NumericBucket(label="35 à 44 ans", maximum_exclusive=45),
                NumericBucket(label="45 à 54 ans", maximum_exclusive=55),
                NumericBucket(label="55 à 64 ans", maximum_exclusive=65),
                NumericBucket(label="65 ans et plus"),
            ),
            "education": (
                NumericBucket(
                    label="Aucun certificat, diplôme ou grade", maximum_exclusive=12
                ),
                NumericBucket(
                    label="Diplôme d'études secondaires ou attestation d'équivalence",
                    maximum_exclusive=13,
                ),
                NumericBucket(
                    label=(
                        "Certificat ou diplôme d’études postsecondaires inférieur "
                        "au baccalauréat"
                    ),
                    maximum_exclusive=15,
                ),
                NumericBucket(
                    label="Certificat ou diplôme universitaire inférieur au baccalauréat",
                    maximum_exclusive=16,
                ),
                NumericBucket(label="Baccalauréat", maximum_exclusive=17),
                NumericBucket(
                    label="Certificat ou diplôme universitaire supérieur au baccalauréat",
                    maximum_exclusive=18,
                ),
                NumericBucket(label="Maîtrise", maximum_exclusive=19),
                NumericBucket(label="Doctorat acquis"),
            ),
            "spending_quintile": (
                NumericBucket(label="Quintile inférieur", maximum_exclusive=20_000),
                NumericBucket(label="Deuxième quintile", maximum_exclusive=40_000),
                NumericBucket(label="Troisième quintile", maximum_exclusive=60_000),
                NumericBucket(label="Quatrième quintile", maximum_exclusive=100_000),
                NumericBucket(label="Quintile supérieur"),
            ),
        },
        categorical_aliases={
            "sex": {
                "female": "Femmes+",
                "woman": "Femmes+",
                "femme": "Femmes+",
                "f": "Femmes+",
                "male": "Hommes+",
                "man": "Hommes+",
                "homme": "Hommes+",
                "m": "Hommes+",
                "*": "Total - Genre",
            }
        },
        constants={
            "open_income_band_label": "100 000 $ et plus[15]",
            "open_income_band_maximum": 250_000,
            "income_sex_fallback": "Total - Genre",
            "profile_uncertainty": 0.9,
        },
    )


@lru_cache(maxsize=1)
def default_finance_initialization_catalog() -> FinanceInitializationCatalog:
    global_program = default_global_finance_initialization_program()
    canada_program = default_canada_finance_initialization_program()
    return FinanceInitializationCatalog(
        programs={
            global_program.id: global_program,
            canada_program.id: canada_program,
        }
    )
