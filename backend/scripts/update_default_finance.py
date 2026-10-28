import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from petraterrium.population import AgentRecord
from petraterrium.simulation.default_finance import (
    CanadaFinanceProfile,
    load_canada_finance_dataset,
    sample_canada_finances,
)
from petraterrium.simulation.finance_initialization import (
    CANADA_FINANCE_PROGRAM_ID,
    GLOBAL_FINANCE_PROGRAM_ID,
    FinanceInitializationProgram,
    default_finance_initialization_catalog,
)
from petraterrium.simulation.global_demo_interactions import (
    attach_global_demo_cross_country_relationships,
    global_demo_interaction_program,
)
from petraterrium.simulation.global_demo_population import (
    GLOBAL_DEMO_VERSION,
    GlobalAgentProfile,
    GlobalFinanceAssignment,
    build_global_demo_population,
)
from petraterrium.simulation.global_finance import (
    GlobalFinanceProfile,
    load_global_finance_pack,
    sample_global_finances,
)
from petraterrium.simulation.population_generation import (
    AgentInitialStateProvenance,
    EvidenceReference,
    validate_initial_population,
)
from petraterrium.simulation.specialization import load_specialization_catalog

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "petraterrium" / "simulation" / "defaults" / "base-v1.json"
SOURCE_DIR = ROOT / "data" / "sources"
FINANCE_SOURCES = (
    {
        "id": "statscan_employment_income_2021",
        "original_title": (
            "Tranches de revenu d’emploi, selon le plus haut niveau de scolarité : "
            "Canada, provinces et territoires"
        ),
        "english_title": (
            "Employment income groups by highest certificate, diploma or degree: "
            "Canada, provinces and territories"
        ),
        "publisher": "Statistique Canada",
        "publication_date": "2023-10-04",
        "population": "Canada Census 2021 residents aged 15 years and older",
        "place": "Canada",
        "language": "fr",
        "discovery_source": (
            "Recherche Web en français puis téléchargement officiel de Statistique Canada"
        ),
        "url": "https://www150.statcan.gc.ca/t1/tbl1/fr/tv.action?pid=9810040701",
        "supports": [
            "Employment-income distributions by age, sex, and education for "
            "deterministic initial finance imputation"
        ],
    },
    {
        "id": "statscan_financial_security_2023",
        "original_title": (
            "Actifs et dettes détenus selon le type de famille économique, par groupe "
            "d’âge, Canada, provinces et certaines régions métropolitaines de "
            "recensement, enquête sur la sécurité financière"
        ),
        "english_title": (
            "Assets and debts held by economic family type and age group, Canada, "
            "provinces and selected census metropolitan areas, Survey of Financial Security"
        ),
        "publisher": "Statistique Canada",
        "publication_date": "2024-10-29",
        "population": "Canadian economic families and persons not in an economic family",
        "place": "Canada",
        "language": "fr",
        "discovery_source": (
            "Recherche Web en français puis téléchargement officiel de Statistique Canada"
        ),
        "url": "https://www150.statcan.gc.ca/t1/tbl1/fr/tv.action?pid=1110001601",
        "supports": [
            "Deposit, non-pension financial-asset, and debt holding rates and medians by age"
        ],
    },
    {
        "id": "statscan_household_spending_2023",
        "original_title": (
            "Dépenses des ménages selon le quintile de revenu du ménage, Canada, "
            "régions et provinces"
        ),
        "english_title": (
            "Household spending by household-income quintile, Canada, regions and provinces"
        ),
        "publisher": "Statistique Canada",
        "publication_date": "2026-09-18",
        "population": "Canadian households in the 2023 Survey of Household Spending",
        "place": "Canada",
        "language": "fr",
        "discovery_source": (
            "Recherche Web en français puis téléchargement officiel de Statistique Canada"
        ),
        "url": "https://www150.statcan.gc.ca/t1/tbl1/fr/tv.action?pid=1110022301",
        "supports": [
            "Average annual household spending by household-income quintile"
        ],
    },
    {
        "id": "world_bank_wdi_global_finance_2026",
        "original_title": "World Development Indicators",
        "english_title": "World Development Indicators",
        "publisher": "World Bank",
        "publication_date": "2026-10-08",
        "population": "216 countries and population-weighted canonical regions",
        "place": "Global",
        "language": "en",
        "discovery_source": "Official World Bank WDI bulk archive",
        "url": "https://databank.worldbank.org/source/world-development-indicators",
        "supports": [
            "Country-specific PPP income, consumption, savings, credit context, and income shares"
        ],
    },
)
GLOBAL_ACTION_REASONS = {
    "bad_work": (
        "Global structural demo default for a poor-work outcome; no place-specific fitted "
        "transition rate is attached."
    ),
    "eat_breakfast": (
        "Global structural demo default for breakfast duration and state effects; no "
        "place-specific fitted transition rate is attached."
    ),
    "eat_dinner": (
        "Global structural demo default for dinner duration and state effects; no "
        "place-specific fitted transition rate is attached."
    ),
    "eat_lunch": (
        "Global structural demo default for lunch duration, cost, and state effects; no "
        "place-specific fitted transition rate is attached."
    ),
    "exercise": (
        "Global structural demo default for exercise choice and state effects; no "
        "place-specific fitted transition rate is attached."
    ),
    "personal_care": (
        "Global structural demo default for personal-care duration and state effects; no "
        "place-specific fitted transition rate is attached."
    ),
    "skip_lunch": (
        "Global structural demo default for stress-stratified meal skipping; no "
        "place-specific fitted transition rate is attached."
    ),
    "sleep": (
        "Global structural demo default for sleep duration and state effects; no "
        "place-specific fitted transition rate is attached."
    ),
    "social_activity": (
        "Global structural demo default for social activity and state effects; no "
        "place-specific fitted transition rate is attached."
    ),
    "work_or_study": (
        "Global structural demo default for work or study outcomes and cash flow; no "
        "place-specific fitted transition rate is attached."
    ),
}


def canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _input_hash(value: object) -> str:
    return canonical_hash(value).removeprefix("sha256:")


def _role(profile: GlobalAgentProfile) -> str:
    if 6 <= profile.age <= 22:
        return "student"
    if 23 <= profile.age <= 64 and profile.occupation_isco != "unknown":
        return "worker"
    return "person"


def _enricher(
    templates: list[dict[str, Any]],
    finance_details: dict[str, dict[str, Any]],
):
    def enrich(agent: AgentRecord, profile: GlobalAgentProfile) -> AgentRecord:
        template = templates[profile.index]
        role = _role(profile)
        home_id = f"home:{agent.agent_id}"
        states = {
            key: value
            for key, value in template["states"].items()
            if not key.startswith("finance.") and key != "location"
        }
        for feature_id in (
            "conscientiousness",
            "extraversion",
            "generalized_trust",
            "risk_aversion",
        ):
            value = agent.traits.get(feature_id)
            if isinstance(value, (int, float)):
                states[feature_id] = str(value)
        states.update(agent.states)
        states.update(
            {
                "is_employed": "1" if role == "worker" else "0",
                "is_student": "1" if role == "student" else "0",
                "is_retired": "1" if profile.age >= 65 else "0",
                "location": home_id,
            }
        )
        traits = {
            **agent.traits,
            **finance_details[profile.agent_id],
            "agent_type": role,
            "agent_types": ["person"] if role == "person" else ["person", role],
            "occupation": role,
            "education_country_label": f"ISCED level {profile.education_isced}",
            "family_status": "estimated_single_household",
            "specific_place": home_id,
            "state_initialization_status": "default_estimated",
            "state_initialization_source": "Shipped global deterministic state vectors",
            "state_initialization_uncertainty": 1.0,
        }
        traits.pop("household_id", None)
        return agent.model_copy(update={"role": role, "states": states, "traits": traits})

    return enrich


def _finance_resolver(
    canada_dataset,
    global_pack,
    finance_details: dict[str, dict[str, Any]],
    canada_program: FinanceInitializationProgram,
    global_program: FinanceInitializationProgram,
):
    def resolve(profile: GlobalAgentProfile) -> GlobalFinanceAssignment:
        if profile.country_code == "CA":
            country_macro = sample_global_finances(
                GlobalFinanceProfile(
                    agent_id=profile.agent_id,
                    country_code=profile.country_code,
                    region=profile.region,
                ),
                global_pack,
                seed=1,
                program=global_program,
            )
            sampled = sample_canada_finances(
                CanadaFinanceProfile(
                    agent_id=profile.agent_id,
                    age=profile.age,
                    sex=profile.sex,
                    years_of_education={
                        "0": 0,
                        "1": 6,
                        "2": 9,
                        "3": 12,
                        "4": 13,
                        "5": 14,
                        "6": 16,
                        "7": 18,
                        "8": 21,
                    }.get(profile.education_isced, 0),
                    specialization=None,
                    occupation=_role(profile),
                ),
                canada_dataset,
                seed=1,
                program=canada_program,
            )
            finance_details[profile.agent_id] = {
                "finance_accounting_unit": "Canadian dollars",
                "finance_distribution_id": sampled.distribution_id,
                "finance_cell_id": sampled.cell_id,
                "finance_income_cell_id": sampled.income_cell_id,
                "finance_default_reason": (
                    "Deterministic imputation from official Canadian marginal income, "
                    "asset, debt, and spending cells; these are not linked person records."
                ),
                "finance_income_basis": "run_cumulative",
                "finance_expenses_basis": "run_cumulative",
                "finance_language": sampled.language,
                "finance_search_source": sampled.search_source,
                "finance_original_titles": list(sampled.original_titles),
                "finance_original_title": " | ".join(sampled.original_titles),
                "finance_english_title": (
                    "Employment income by education; assets and debts by age; household "
                    "spending by income quintile"
                ),
                "finance_source_url": FINANCE_SOURCES[0]["url"],
                "finance_component_evidence": {
                    "prices": asdict(country_macro.component_evidence["prices"]),
                },
            }
            return GlobalFinanceAssignment(
                evidence_scope="country_measured",
                source_place="Canada",
                source_id=sampled.distribution_id,
                source_status=sampled.status,
                source=sampled.source,
                source_version=sampled.source_version,
                source_date=sampled.source_date,
                source_population=sampled.source_population,
                uncertainty=sampled.uncertainty,
                currency="CAD",
                local_currency=country_macro.local_currency,
                price_level_ratio=country_macro.price_level_ratio,
                wage_per_workday=sampled.values["income"] / 260,
                money=sampled.values["money"],
                annual_income=sampled.values["income"],
                annual_expenses=sampled.values["expenses"],
                savings=sampled.values["savings"],
                debt=sampled.values["debt"],
            )
        sampled = sample_global_finances(
            GlobalFinanceProfile(
                agent_id=profile.agent_id,
                country_code=profile.country_code,
                region=profile.region,
            ),
            global_pack,
            seed=1,
            program=global_program,
        )
        scope = (
            "country_measured"
            if sampled.source_place == profile.country_code
            else "regional_imputed"
        )
        finance_details[profile.agent_id] = {
            "finance_accounting_unit": sampled.accounting_unit,
            "finance_distribution_id": sampled.distribution_id,
            "finance_cell_id": sampled.cell_id,
            "finance_default_reason": (
                "Person-level finance is imputed from this country's WDI PPP income "
                "shares and macro finance observations; linked household microdata is absent."
            ),
            "finance_income_basis": "run_cumulative",
            "finance_expenses_basis": "run_cumulative",
            "finance_source_url": global_pack.source["dataset_url"],
            "finance_component_evidence": {
                key: asdict(value)
                for key, value in sampled.component_evidence.items()
            },
        }
        return GlobalFinanceAssignment(
            evidence_scope=scope,
            source_place=sampled.source_place,
            source_id=f"{sampled.distribution_id}:{sampled.cell_id}",
            source_status=sampled.status,
            source=sampled.source,
            source_version=sampled.source_version,
            source_date=sampled.source_date,
            source_population=sampled.source_population,
            uncertainty=sampled.uncertainty,
            currency="PPP",
            local_currency=sampled.local_currency,
            price_level_ratio=sampled.price_level_ratio,
            wage_per_workday=sampled.values["income"] / 260,
            money=sampled.values["money"],
            annual_income=sampled.values["income"],
            annual_expenses=sampled.values["expenses"],
            savings=sampled.values["savings"],
            debt=sampled.values["debt"],
        )

    return resolve


def _population_provenance(agents: list[AgentRecord]) -> dict[str, dict[str, Any]]:
    result = {}
    for agent in agents:
        country = str(agent.traits["country_id"])
        age_sex = EvidenceReference(
            evidence_id=str(agent.traits["age_source_id"]),
            source=str(agent.traits["age_source"]),
            source_version=str(agent.traits["age_source_version"]),
            observed_at=str(agent.traits["age_source_date"]),
            licence="UN WPP terms of use",
            place=country,
            status="measured_marginal",
            fields=["age", "sex"],
            uncertainty="Synthetic individual sampled from the measured country marginal.",
            url="https://population.un.org/wpp/",
        )
        population = EvidenceReference(
            evidence_id=f"global-demo:{country}:{GLOBAL_DEMO_VERSION}",
            source="Global demo population evidence resolver",
            source_version=GLOBAL_DEMO_VERSION,
            observed_at="2026-10-27",
            licence="Source-specific licences recorded in feature provenance",
            place=country,
            status="imputed",
            fields=[
                "education",
                "occupation",
                "personality",
                "values",
                "finance",
            ],
            uncertainty=(
                "Every individual is a deterministic synthetic draw; country and regional "
                "source scopes remain attached to each field."
            ),
        )
        provenance = AgentInitialStateProvenance(
            source_template_id=f"global-demo-{country}",
            sampling_basis="imputed",
            household_evidence=population,
            field_evidence={"age": age_sex, "sex": age_sex},
            unknown_fields=[],
        )
        result[agent.agent_id] = provenance.model_dump(mode="json")
    return result


def update_skip_lunch(actions: list[dict[str, Any]]) -> None:
    action = next(item for item in actions if item["id"] == "skip_lunch")
    action["formula"] = "availability(midday) × f(stress) × f(financial_stress)"
    action["state_inputs"] = ["stress", "financial_stress", "hunger", "fatigue"]
    action["runtime_rules"] = [
        {
            "conditions": [
                {"input": "memory.stress", "operator": "lt", "value": 0.5},
                {"input": "memory.financial_stress", "operator": "lt", "value": 0.5},
                {"input": "context.hour", "operator": "eq", "value": 12.0},
            ],
            "probability": 0.05,
        },
        {
            "conditions": [
                {"input": "memory.stress", "operator": "lt", "value": 0.5},
                {"input": "memory.financial_stress", "operator": "gte", "value": 0.5},
                {"input": "context.hour", "operator": "eq", "value": 12.0},
            ],
            "probability": 0.2,
        },
        {
            "conditions": [
                {"input": "memory.stress", "operator": "gte", "value": 0.5},
                {"input": "memory.financial_stress", "operator": "lt", "value": 0.5},
                {"input": "context.hour", "operator": "eq", "value": 12.0},
            ],
            "probability": 0.35,
        },
        {
            "conditions": [
                {"input": "memory.stress", "operator": "gte", "value": 0.5},
                {"input": "memory.financial_stress", "operator": "gte", "value": 0.5},
                {"input": "context.hour", "operator": "eq", "value": 12.0},
            ],
            "probability": 0.55,
        },
    ]


def update_midday_meal_choice(actions: list[dict[str, Any]]) -> None:
    skip_lunch = next(item for item in actions if item["id"] == "skip_lunch")
    eat_lunch = next(item for item in actions if item["id"] == "eat_lunch")
    skip_lunch["exclusive_choice_group"] = "midday_meal"
    eat_lunch["exclusive_choice_group"] = "midday_meal"
    eat_lunch["runtime_rules"] = [
        {
            "conditions": [dict(condition) for condition in rule["conditions"]],
            "probability": round(1.0 - float(rule["probability"]), 12),
        }
        for rule in skip_lunch["runtime_rules"]
    ]


def _globalize_action_evidence(actions: list[dict[str, Any]]) -> None:
    for action in actions:
        action["evidence"] = {
            "status": "default_estimated",
            "explicit_default_reason": GLOBAL_ACTION_REASONS[action["id"]],
            "uncertainty_low": 0.0,
            "uncertainty_high": 1.0,
            "source_ids": [],
        }


def _globalize_cash_flows(actions: list[dict[str, Any]]) -> None:
    formulas = {
        "eat_breakfast": {
            "food": ("finance_annual_expenses", 0.00015),
        },
        "eat_dinner": {
            "food": ("finance_annual_expenses", 0.00045),
        },
        "eat_lunch": {
            "food": ("finance_annual_expenses", 0.00035),
        },
        "exercise": {
            "other_expenses": ("finance_annual_expenses", 0.0002),
        },
        "personal_care": {
            "other_expenses": ("finance_annual_expenses", 0.00005),
        },
        "social_activity": {
            "other_expenses": ("finance_annual_expenses", 0.0005),
        },
        "work_or_study": {
            "wages": ("finance_annual_income", 1 / 260),
            "transport": ("finance_annual_expenses", 0.00025),
            "taxes": ("finance_annual_income", 0.2 / 260),
        },
    }
    fields = {
        "wages",
        "business_income",
        "transfers",
        "housing",
        "food",
        "transport",
        "other_expenses",
        "taxes",
        "savings_contribution",
        "savings_withdrawal",
        "debt_draw",
        "debt_repayment",
    }
    for action in actions:
        selected = formulas.get(action["id"], {})
        action["cash_flow"] = {
            field: (
                {
                    "input": f"traits.{selected[field][0]}",
                    "multiplier": selected[field][1],
                    "minimum": 0.0,
                    "maximum": None,
                    "formula": (
                        f"{field} = traits.{selected[field][0]} "
                        f"× {selected[field][1]:.12g}"
                    ),
                }
                if field in selected
                else 0.0
            )
            for field in sorted(fields)
        }


def _globalize_coefficient_registry(registry: dict[str, Any]) -> None:
    registry["defaults"] = [
        {
            "id": "daily_activity_global_default",
            "action_id": "daily_activity_module",
            "place": {
                "level": "global",
                "place_id": "global",
                "region_id": None,
                "country_id": None,
                "city_id": None,
            },
            "coefficients": {
                "choose_exercise": 0.5,
                "choose_recovery": 0.5,
            },
            "intervals": {
                "choose_exercise": {"low": 0.0, "high": 1.0},
                "choose_recovery": {"low": 0.0, "high": 1.0},
            },
            "source": {
                "kind": "shipped_default_reason",
                "reason": (
                    "Equal branching is a global runnable demonstration prior with a "
                    "0–1 interval. It is not a measured or fitted place-specific rate."
                ),
                "default_dsl_version": "base-1.0.0",
                "default_dsl_hash": "$default_dsl_hash",
            },
        }
    ]
    registry["fitted"] = []
    registry["promotions"] = []


def _globalize_routine_evidence(routines: list[dict[str, Any]]) -> None:
    for routine in routines:
        routine["evidence"] = {
            "status": "default_estimated",
            "source_title": "Shipped global structural schedule default",
            "source_date": "2026-10-27",
            "source_uri": None,
            "note": (
                "This runnable schedule has wide uncertainty and is not a measured "
                "time-use pattern for any country or region."
            ),
        }


def _globalize_decision_trees(registry: dict[str, Any]) -> None:
    for tree in registry["trees"]:
        tree["place_ids"] = []


def _runtime_state_evidence(state_id: str) -> dict[str, Any]:
    return {
        "status": "default_estimated",
        "source": "Shipped Prompt 1 structural state update rule",
        "source_version": "base-1.0.0",
        "source_date": "2026-10-27",
        "url": None,
        "place": "Global structural default",
        "population": "All agents using the shipped default DSL",
        "language": "en",
        "original_title": "Petraterrium Prompt 1 state runtime rule",
        "english_title": "Petraterrium Prompt 1 state runtime rule",
        "search_source": "Shipped default DSL",
        "uncertainty": 1.0,
        "default_reason": (
            f"{state_id} retains its current value, receives declared state propagation, "
            "and applies DSL event deltas until fitted longitudinal evidence is promoted."
        ),
    }


def _globalize_state_runtime_rules(catalog: dict[str, Any]) -> None:
    definitions = {item["id"]: item for item in catalog["definitions"]}
    coefficients: dict[str, dict[str, float]] = {
        state_id: {} for state_id in definitions
    }
    propagation_formulas: dict[str, list[str]] = {
        state_id: [] for state_id in definitions
    }
    for source in catalog["definitions"]:
        for propagation in source["propagation"]:
            coefficient = propagation.get("coefficient")
            if coefficient is None:
                continue
            target = propagation["target_state_id"]
            coefficients[target][source["id"]] = (
                coefficients[target].get(source["id"], 0.0) + coefficient
            )
            propagation_formulas[target].append(propagation["formula"])
    rules = []
    for state_id, definition in sorted(definitions.items()):
        value_range = definition["value_range"]
        input_terms = coefficients[state_id]
        formula = " | ".join(propagation_formulas[state_id])
        if not formula:
            formula = (
                f"{state_id}[t+1] = clamp({state_id}[t] + event_delta, "
                f"{value_range['minimum']}, {value_range['maximum']})"
            )
        rules.append(
            {
                "target_state_id": state_id,
                "intercept": 0.0,
                "coefficients": input_terms,
                "minimum": value_range["minimum"],
                "maximum": value_range["maximum"],
                "formula": formula,
                "evidence": _runtime_state_evidence(state_id),
            }
        )
    catalog["runtime_rules"] = rules


def _finance_rule_evidence(target: str) -> dict[str, Any]:
    return {
        "status": "default_estimated",
        "explicit_default_reason": (
            f"The {target} accounting identity is a shipped structural ledger rule; "
            "action cash-flow amounts retain their own place-specific provenance."
        ),
        "uncertainty_low": 0.0,
        "uncertainty_high": 1.0,
        "source_ids": [],
    }


def _finance_rules() -> dict[str, Any]:
    rules = {
        "income": {
            "finance.income": 1.0,
            "cash_flow.wages": 1.0,
            "cash_flow.business_income": 1.0,
            "cash_flow.transfers": 1.0,
        },
        "expenses": {
            "finance.expenses": 1.0,
            "cash_flow.housing": 1.0,
            "cash_flow.food": 1.0,
            "cash_flow.transport": 1.0,
            "cash_flow.other_expenses": 1.0,
            "cash_flow.taxes": 1.0,
        },
        "money": {
            "finance.money": 1.0,
            "cash_flow.wages": 1.0,
            "cash_flow.business_income": 1.0,
            "cash_flow.transfers": 1.0,
            "cash_flow.debt_draw": 1.0,
            "cash_flow.savings_withdrawal": 1.0,
            "cash_flow.housing": -1.0,
            "cash_flow.food": -1.0,
            "cash_flow.transport": -1.0,
            "cash_flow.other_expenses": -1.0,
            "cash_flow.taxes": -1.0,
            "cash_flow.savings_contribution": -1.0,
            "cash_flow.debt_repayment": -1.0,
        },
        "savings": {
            "finance.savings": 1.0,
            "cash_flow.savings_contribution": 1.0,
            "cash_flow.savings_withdrawal": -1.0,
        },
        "debt": {
            "finance.debt": 1.0,
            "cash_flow.debt_draw": 1.0,
            "cash_flow.debt_repayment": -1.0,
        },
    }
    formulas = {
        "income": "income[t+1] = income[t] + wages + business_income + transfers",
        "expenses": (
            "expenses[t+1] = expenses[t] + housing + food + transport + "
            "other_expenses + taxes"
        ),
        "money": (
            "money[t+1] = max(0, money[t] + wages + business_income + transfers + "
            "debt_draw + savings_withdrawal - housing - food - transport - "
            "other_expenses - taxes - savings_contribution - debt_repayment)"
        ),
        "savings": (
            "savings[t+1] = max(0, savings[t] + savings_contribution - "
            "savings_withdrawal)"
        ),
        "debt": "debt[t+1] = max(0, debt[t] + debt_draw - debt_repayment)",
    }
    return {
        "version": "prompt1-finance-ledger-v1",
        "status": "confirmed",
        "rules": [
            {
                "id": f"update_{target}",
                "target": f"finance.{target}",
                "terms": rules[target],
                "minimum": 0.0,
                "maximum": None,
                "formula": formulas[target],
                "evidence": _finance_rule_evidence(target),
            }
            for target in ("income", "expenses", "money", "savings", "debt")
        ],
    }


def update_manifest() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if "interaction_program" not in manifest["managed_sections"]:
        manifest["managed_sections"].append("interaction_program")
    if "finance_rules" not in manifest["managed_sections"]:
        manifest["managed_sections"].append("finance_rules")
    if "finance_initialization" not in manifest["managed_sections"]:
        manifest["managed_sections"].append("finance_initialization")
    if "specialization_pipeline" not in manifest["managed_sections"]:
        manifest["managed_sections"].append("specialization_pipeline")
    content = manifest["content"]
    templates = content["initial_population"]["population"]["agents"]
    canada_dataset = load_canada_finance_dataset(SOURCE_DIR)
    global_pack = load_global_finance_pack()
    specialization_catalog = load_specialization_catalog()
    finance_initialization = default_finance_initialization_catalog()
    finance_details: dict[str, dict[str, Any]] = {}
    global_demo = build_global_demo_population(
        target_agents=1_000,
        seed=1,
        finance_resolver=_finance_resolver(
            canada_dataset,
            global_pack,
            finance_details,
            finance_initialization.programs[CANADA_FINANCE_PROGRAM_ID],
            finance_initialization.programs[GLOBAL_FINANCE_PROGRAM_ID],
        ),
        agent_enricher=_enricher(templates, finance_details),
        specialization_catalog=specialization_catalog,
    )
    population = attach_global_demo_cross_country_relationships(global_demo.population)
    validation = validate_initial_population(population)
    if not validation.valid:
        issues = "; ".join(item.message for item in validation.issues)
        raise ValueError(f"Global default population is invalid: {issues}")
    population_payload = population.model_dump(mode="json")
    content["initial_population"] = {
        "input_hash": _input_hash(
            {
                "population": population_payload,
                "feature_pack": GLOBAL_DEMO_VERSION,
                "finance_pack": global_pack.version,
                "specialization_pipeline": specialization_catalog.version,
                "finance_initialization": finance_initialization.model_dump(mode="json"),
            }
        ),
        "population": population_payload,
        "provenance": _population_provenance(population.agents),
        "validation": validation.model_dump(mode="json"),
    }
    content["initial_seeding_rules"] = [
        {
            "id": "global_demo",
            "seed": 1,
            "count": len(population.agents),
            "algorithm": "stable_sha256",
            "place": "Global",
            "agent_type_ids": sorted(
                {str(agent.traits["agent_type"]) for agent in population.agents}
            ),
            "expected_agent_ids": [agent.agent_id for agent in population.agents],
        }
    ]
    content["interaction_program"] = global_demo_interaction_program().model_dump(mode="json")
    content["finance_rules"] = _finance_rules()
    content["finance_initialization"] = finance_initialization.model_dump(mode="json")
    content["specialization_pipeline"] = specialization_catalog.model_dump(mode="json")
    source_by_id = {source["id"]: source for source in content["default_sources"]}
    source_by_id.update({source["id"]: source for source in FINANCE_SOURCES})
    content["default_sources"] = [source_by_id[key] for key in sorted(source_by_id)]
    _globalize_routine_evidence(content["routines"]["routines"])
    _globalize_state_runtime_rules(content["agent_states"])
    _globalize_decision_trees(content["decision_trees"])
    for routine in content["routines"]["routines"]:
        routine["steps"] = [
            step
            for step in routine["steps"]
            if not (routine["id"] == "daily_life" and step["id"] == "lunch")
        ]
    update_skip_lunch(content["default_actions"])
    update_midday_meal_choice(content["default_actions"])
    _globalize_cash_flows(content["default_actions"])
    _globalize_action_evidence(content["default_actions"])
    _globalize_coefficient_registry(content["coefficient_registry"])
    manifest["content_hash"] = canonical_hash(content)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    update_manifest()
