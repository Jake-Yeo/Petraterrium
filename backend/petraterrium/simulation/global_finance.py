import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from petraterrium.atlas.regions import country_region
from petraterrium.simulation.finance_initialization import (
    FinanceInitializationProgram,
    default_global_finance_initialization_program,
    evaluate_finance_initialization,
)

PACK_FILENAME = "global-finance-wdi-v1.json"
PACK_VERSION = "wdi-global-finance-2026-10-08-v1"
INCOME_SHARE_KEYS = (
    "income_share_lowest_20",
    "income_share_second_20",
    "income_share_third_20",
    "income_share_fourth_20",
    "income_share_highest_20",
)
FinanceEvidenceScope = Literal["country_measured", "regional_imputed"]


@dataclass(frozen=True)
class GlobalFinanceProfile:
    agent_id: str
    country_code: str
    region: str | None = None


@dataclass(frozen=True)
class ResolvedMetric:
    value: float
    indicator_ids: tuple[str, ...]
    observation_years: tuple[int, ...]
    source_place: str
    population_coverage_percent: float


@dataclass(frozen=True)
class FinanceComponentEvidence:
    evidence_scope: FinanceEvidenceScope
    status: str
    source_place: str
    indicator_ids: tuple[str, ...]
    observation_years: tuple[int, ...]
    method: str
    uncertainty: float


@dataclass(frozen=True)
class SampledGlobalFinances:
    values: dict[str, float]
    status: str
    accounting_unit: str
    distribution_id: str
    cell_id: str
    source: str
    source_version: str
    source_date: str
    source_place: str
    source_population: str
    uncertainty: float
    evidence_scope: FinanceEvidenceScope
    local_currency: str
    local_currency_status: Literal["country_measured"]
    official_exchange_rate: float
    ppp_conversion_factor: float
    price_level_ratio: float
    cost_of_living_source_place: str
    cost_of_living_status: str
    component_evidence: dict[str, FinanceComponentEvidence]


@dataclass(frozen=True)
class GlobalFinanceEvidencePack:
    version: str
    accounting_unit: str
    source: dict[str, Any]
    methodology: dict[str, str]
    limitations: tuple[str, ...]
    priority_countries: tuple[str, ...]
    countries: dict[str, dict[str, Any]]
    regions: dict[str, dict[str, Any]]


def _default_pack_path() -> Path:
    return Path(__file__).resolve().parent / "defaults" / PACK_FILENAME


@lru_cache(maxsize=4)
def _load_global_finance_pack(path: str) -> GlobalFinanceEvidencePack:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise ValueError("Unsupported global finance evidence schema")
    if raw.get("version") != PACK_VERSION:
        raise ValueError(
            f"Expected global finance evidence {PACK_VERSION}, found {raw.get('version')}"
        )
    countries = {row["country_code"]: row for row in raw["countries"]}
    missing_priority = set(raw["priority_countries"]) - countries.keys()
    if missing_priority:
        raise ValueError(f"Global finance evidence lacks {sorted(missing_priority)}")
    return GlobalFinanceEvidencePack(
        version=raw["version"],
        accounting_unit=raw["accounting_unit"],
        source=raw["source"],
        methodology=raw["methodology"],
        limitations=tuple(raw["limitations"]),
        priority_countries=tuple(raw["priority_countries"]),
        countries=countries,
        regions=raw["regions"],
    )


def load_global_finance_pack(
    path: Path | None = None,
) -> GlobalFinanceEvidencePack:
    resolved = (path or _default_pack_path()).resolve()
    return _load_global_finance_pack(str(resolved))


def _country_region(
    pack: GlobalFinanceEvidencePack, country_code: str, region: str | None
) -> tuple[dict[str, Any] | None, str]:
    country = pack.countries.get(country_code)
    if country is not None:
        return country, str(country["region"])
    resolved_region = region or country_region(country_code)
    if resolved_region not in pack.regions:
        raise ValueError(f"No global finance evidence for {country_code} or {resolved_region}")
    return None, resolved_region


def _country_observation(metric: dict[str, Any], source_place: str) -> ResolvedMetric:
    years = metric.get("component_years", {metric["indicator_id"]: metric["year"]})
    return ResolvedMetric(
        value=float(metric["value"]),
        indicator_ids=tuple(sorted(years)),
        observation_years=tuple(sorted({int(year) for year in years.values()})),
        source_place=source_place,
        population_coverage_percent=100.0,
    )


def _region_observation(metric: dict[str, Any], source_place: str) -> ResolvedMetric:
    first_year = int(metric["observation_year_min"])
    last_year = int(metric["observation_year_max"])
    return ResolvedMetric(
        value=float(metric["value"]),
        indicator_ids=tuple(metric["indicator_ids"]),
        observation_years=(
            (first_year,) if first_year == last_year else (first_year, last_year)
        ),
        source_place=source_place,
        population_coverage_percent=float(metric["coverage_percent"]),
    )


def resolve_finance_metric(
    pack: GlobalFinanceEvidencePack,
    country_code: str,
    region: str | None,
    metric_name: str,
) -> ResolvedMetric:
    normalized_code = country_code.upper()
    country, resolved_region = _country_region(pack, normalized_code, region)
    if country is not None and metric_name in country["metrics"]:
        return _country_observation(country["metrics"][metric_name], normalized_code)
    region_metric = pack.regions[resolved_region]["metrics"].get(metric_name)
    if region_metric is None:
        raise ValueError(
            f"No {metric_name} evidence for {normalized_code} or {resolved_region}"
        )
    return _region_observation(region_metric, resolved_region)


def _component_evidence(
    status: str,
    observations: tuple[ResolvedMetric, ...],
    country_code: str,
    method: str,
    uncertainty: float,
) -> FinanceComponentEvidence:
    evidence_scope: FinanceEvidenceScope = (
        "country_measured"
        if all(observation.source_place == country_code for observation in observations)
        else "regional_imputed"
    )
    return FinanceComponentEvidence(
        evidence_scope=evidence_scope,
        status=status,
        source_place=" + ".join(
            dict.fromkeys(observation.source_place for observation in observations)
        ),
        indicator_ids=tuple(
            dict.fromkeys(
                indicator_id
                for observation in observations
                for indicator_id in observation.indicator_ids
            )
        ),
        observation_years=tuple(
            sorted(
                {
                    year
                    for observation in observations
                    for year in observation.observation_years
                }
            )
        ),
        method=method,
        uncertainty=uncertainty,
    )


def _rule_method(program: FinanceInitializationProgram, output_id: str) -> str:
    rule = program.outputs[output_id]
    descriptions = " ".join(
        program.assumptions[assumption_id].description
        for assumption_id in rule.assumption_ids
    )
    return f"{rule.formula}. {descriptions}"


def _rule_uncertainty(program: FinanceInitializationProgram, output_id: str) -> float:
    return max(
        program.assumptions[assumption_id].uncertainty
        for assumption_id in program.outputs[output_id].assumption_ids
    )


def sample_global_finances(
    profile: GlobalFinanceProfile,
    pack: GlobalFinanceEvidencePack,
    seed: int,
    program: FinanceInitializationProgram | None = None,
) -> SampledGlobalFinances:
    active_program = program or default_global_finance_initialization_program()
    normalized_profile = GlobalFinanceProfile(
        agent_id=profile.agent_id,
        country_code=profile.country_code.upper(),
        region=profile.region,
    )
    _, region = _country_region(
        pack, normalized_profile.country_code, normalized_profile.region
    )
    gni = resolve_finance_metric(
        pack,
        normalized_profile.country_code,
        normalized_profile.region,
        "gni_per_capita_ppp",
    )
    shares = tuple(
        resolve_finance_metric(
            pack, normalized_profile.country_code, normalized_profile.region, key
        )
        for key in INCOME_SHARE_KEYS
    )
    total_share = sum(share.value for share in shares)
    if not 98 <= total_share <= 102:
        raise ValueError(
            f"Income quintile shares for {normalized_profile.country_code} sum to "
            f"{total_share}"
        )
    savings_rate = resolve_finance_metric(
        pack,
        normalized_profile.country_code,
        normalized_profile.region,
        "adjusted_net_savings_pct_gni",
    )
    private_credit = resolve_finance_metric(
        pack,
        normalized_profile.country_code,
        normalized_profile.region,
        "private_credit_pct_gdp",
    )
    country = pack.countries.get(normalized_profile.country_code)
    official_exchange_rate = resolve_finance_metric(
        pack,
        normalized_profile.country_code,
        normalized_profile.region,
        "official_exchange_rate",
    )
    ppp_conversion_factor = resolve_finance_metric(
        pack,
        normalized_profile.country_code,
        normalized_profile.region,
        "ppp_conversion_factor",
    )
    price_level_ratio = resolve_finance_metric(
        pack,
        normalized_profile.country_code,
        normalized_profile.region,
        "price_level_ratio",
    )
    consumption = (
        resolve_finance_metric(
            pack,
            normalized_profile.country_code,
            normalized_profile.region,
            "household_consumption_per_capita_ppp",
        )
        if country is not None
        and "household_consumption_per_capita_ppp" in country["metrics"]
        else None
    )
    result = evaluate_finance_initialization(
        active_program,
        {
            "gni_per_capita_ppp": gni.value,
            "income_shares": [share.value for share in shares],
            "adjusted_net_savings_pct_gni": savings_rate.value,
            "private_credit_pct_gdp": private_credit.value,
            **(
                {"household_consumption_per_capita_ppp": consumption.value}
                if consumption is not None
                else {}
            ),
        },
        seed,
        normalized_profile.agent_id,
    )
    quintile_index = int(result.values["income_quintile_index"])
    income_evidence = _component_evidence(
        "imputed",
        (gni, shares[quintile_index]),
        normalized_profile.country_code,
        _rule_method(active_program, "income"),
        _rule_uncertainty(active_program, "income"),
    )
    expense_observations = (consumption,) if consumption is not None else (gni, savings_rate)
    expense_evidence = _component_evidence(
        "imputed" if consumption is not None else "default_estimated",
        expense_observations,
        normalized_profile.country_code,
        _rule_method(active_program, "expenses"),
        _rule_uncertainty(active_program, "expenses"),
    )
    stock_evidence = {
        "money": FinanceComponentEvidence(
            evidence_scope=expense_evidence.evidence_scope,
            status="default_estimated",
            source_place=expense_evidence.source_place,
            indicator_ids=expense_evidence.indicator_ids,
            observation_years=expense_evidence.observation_years,
            method=_rule_method(active_program, "money"),
            uncertainty=_rule_uncertainty(active_program, "money"),
        ),
        "savings": _component_evidence(
            "default_estimated",
            (savings_rate,),
            normalized_profile.country_code,
            _rule_method(active_program, "savings"),
            _rule_uncertainty(active_program, "savings"),
        ),
        "debt": _component_evidence(
            "default_estimated",
            (private_credit,),
            normalized_profile.country_code,
            _rule_method(active_program, "debt"),
            _rule_uncertainty(active_program, "debt"),
        ),
    }
    population = resolve_finance_metric(
        pack, normalized_profile.country_code, normalized_profile.region, "population"
    )
    component_evidence = {
        "income": income_evidence,
        "expenses": expense_evidence,
        "prices": _component_evidence(
            "estimated",
            (price_level_ratio,),
            normalized_profile.country_code,
            (
                "WDI PPP conversion factor divided by the official exchange rate; "
                "a relative national price-level estimate rather than a household basket."
            ),
            0.35,
        ),
        **stock_evidence,
    }
    evidence_scope: FinanceEvidenceScope = (
        "regional_imputed"
        if any(
            evidence.evidence_scope == "regional_imputed"
            for evidence in component_evidence.values()
        )
        else "country_measured"
    )
    source_place = (
        normalized_profile.country_code
        if evidence_scope == "country_measured"
        else region
    )
    return SampledGlobalFinances(
        values={
            component: float(result.values[component])
            for component in ("money", "income", "expenses", "savings", "debt")
        },
        status="imputed",
        accounting_unit=pack.accounting_unit,
        distribution_id=pack.version,
        cell_id=f"{source_place}|income-quintile-{quintile_index + 1}",
        source="World Bank World Development Indicators",
        source_version=pack.version,
        source_date=str(pack.source["archive_release_date"]),
        source_place=source_place,
        source_population=(
            f"{round(population.value):,} people; WDI observation "
            f"{max(population.observation_years)}"
        ),
        uncertainty=max(
            evidence.uncertainty for evidence in component_evidence.values()
        ),
        evidence_scope=evidence_scope,
        local_currency=(
            str(country["currency_name"])
            if country is not None
            else pack.accounting_unit
        ),
        local_currency_status="country_measured",
        official_exchange_rate=official_exchange_rate.value,
        ppp_conversion_factor=ppp_conversion_factor.value,
        price_level_ratio=price_level_ratio.value,
        cost_of_living_source_place=price_level_ratio.source_place,
        cost_of_living_status="estimated",
        component_evidence=component_evidence,
    )
