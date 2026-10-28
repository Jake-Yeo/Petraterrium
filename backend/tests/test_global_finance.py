import json
import math
from pathlib import Path

from petraterrium.simulation.global_finance import (
    GlobalFinanceProfile,
    load_global_finance_pack,
    sample_global_finances,
)
from scripts.build_global_finance_pack import (
    MEANINGFUL_REGIONS,
    PRIORITY_COUNTRIES,
    build_pack,
)

ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = (
    ROOT
    / "petraterrium"
    / "simulation"
    / "defaults"
    / "global-finance-wdi-v1.json"
)
SOURCE_PATH = ROOT / "data" / "sources" / "WDI_CSV.zip"


def test_checked_in_pack_covers_priority_countries_and_all_meaningful_regions():
    pack = load_global_finance_pack(PACK_PATH)

    assert set(PRIORITY_COUNTRIES) <= pack.countries.keys()
    assert set(pack.regions) == set(MEANINGFUL_REGIONS)
    assert len(pack.countries) >= 200
    assert pack.accounting_unit == "current international dollars (PPP)"
    assert pack.source["archive_sha256"] == (
        "1cbb81b7e8e656e05fe9236f201d6d59a82d62a77f96c147c1bc63940a7b0c0c"
    )

    for country_code in PRIORITY_COUNTRIES:
        metrics = pack.countries[country_code]["metrics"]
        assert {
            "population",
            "gni_per_capita_ppp",
            "gdp_per_capita_ppp",
            "gini",
            "income_share_lowest_20",
            "income_share_second_20",
            "income_share_third_20",
            "income_share_fourth_20",
            "income_share_highest_20",
            "adjusted_net_savings_pct_gni",
            "private_credit_pct_gdp",
        } <= metrics.keys()
        share_total = sum(
            metrics[key]["value"]
            for key in (
                "income_share_lowest_20",
                "income_share_second_20",
                "income_share_third_20",
                "income_share_fourth_20",
                "income_share_highest_20",
            )
        )
        assert math.isclose(share_total, 100, abs_tol=0.2)
        sampled = sample_global_finances(
            GlobalFinanceProfile(
                agent_id=f"coverage-{country_code}", country_code=country_code
            ),
            pack,
            seed=1,
        )
        assert sampled.source_place == country_code
        assert sampled.evidence_scope == "country_measured"
        assert sampled.accounting_unit == "current international dollars (PPP)"
        assert sampled.local_currency
        assert sampled.local_currency_status == "country_measured"
        assert sampled.official_exchange_rate > 0
        assert sampled.ppp_conversion_factor > 0
        assert sampled.price_level_ratio > 0
        assert sampled.cost_of_living_source_place == country_code
        assert all(value >= 0 for value in sampled.values.values())

    for region in pack.regions.values():
        assert region["population"] > 0
        assert {
            "gni_per_capita_ppp",
            "gdp_per_capita_ppp",
            "gini",
            "income_share_lowest_20",
            "adjusted_net_savings_pct_gni",
            "private_credit_pct_gdp",
        } <= region["metrics"].keys()
        for metric in region["metrics"].values():
            assert 0 < metric["coverage_percent"] <= 100
            assert metric["covered_population"] <= metric["total_population"]


def test_pack_is_reproducible_from_the_pinned_official_wdi_archive():
    checked_in = json.loads(PACK_PATH.read_text(encoding="utf-8"))

    assert build_pack(SOURCE_PATH) == checked_in


def test_sampler_is_deterministic_and_uses_country_specific_values():
    pack = load_global_finance_pack(PACK_PATH)
    india_profile = GlobalFinanceProfile(agent_id="global-demo-agent", country_code="IN")
    china_profile = GlobalFinanceProfile(agent_id="global-demo-agent", country_code="CN")

    india_first = sample_global_finances(india_profile, pack, seed=1)
    india_second = sample_global_finances(india_profile, pack, seed=1)
    china = sample_global_finances(china_profile, pack, seed=1)

    assert india_first == india_second
    assert india_first.values != china.values
    assert india_first.source_place == "IN"
    assert china.source_place == "CN"
    assert india_first.component_evidence["income"].source_place == "IN"
    assert china.component_evidence["income"].source_place == "CN"
    assert india_first.component_evidence["income"].evidence_scope == (
        "country_measured"
    )
    assert china.component_evidence["expenses"].evidence_scope == "country_measured"
    assert india_first.component_evidence["income"].indicator_ids == (
        "NY.GNP.PCAP.PP.CD",
        "SI.DST.05TH.20",
    )
    assert china.component_evidence["income"].indicator_ids == (
        "NY.GNP.PCAP.PP.CD",
        "SI.DST.05TH.20",
    )
    assert all(value >= 0 for value in india_first.values.values())
    assert all(value >= 0 for value in china.values.values())


def test_nigeria_uses_its_own_macro_fallback_without_borrowing_canadian_values():
    pack = load_global_finance_pack(PACK_PATH)
    sampled = sample_global_finances(
        GlobalFinanceProfile(agent_id="nigeria-demo-agent", country_code="NG"),
        pack,
        seed=1,
    )

    expenses = sampled.component_evidence["expenses"]
    assert sampled.source_place == "NG"
    assert expenses.status == "default_estimated"
    assert expenses.evidence_scope == "country_measured"
    assert expenses.source_place == "NG"
    assert expenses.indicator_ids == (
        "NY.GNP.PCAP.PP.CD",
        "NY.ADJ.SVNG.GN.ZS",
    )
    assert expenses.uncertainty >= 0.95
    assert "unavailable" in expenses.method
    assert "CA" not in expenses.source_place
    assert "Statistique Canada" not in sampled.source


def test_missing_country_metric_uses_only_its_region_and_marks_the_component_imputed():
    pack = load_global_finance_pack(PACK_PATH)
    country = dict(pack.countries["IN"])
    country["metrics"] = dict(country["metrics"])
    country["metrics"].pop("private_credit_pct_gdp")
    countries = {**pack.countries, "IN": country}
    modified = type(pack)(
        version=pack.version,
        accounting_unit=pack.accounting_unit,
        source=pack.source,
        methodology=pack.methodology,
        limitations=pack.limitations,
        priority_countries=pack.priority_countries,
        countries=countries,
        regions=pack.regions,
    )

    sampled = sample_global_finances(
        GlobalFinanceProfile(
            agent_id="india-regional-credit-fallback",
            country_code="IN",
            region="India",
        ),
        modified,
        seed=1,
    )

    assert sampled.evidence_scope == "regional_imputed"
    assert sampled.source_place == "India"
    assert sampled.component_evidence["debt"].evidence_scope == "regional_imputed"
    assert sampled.component_evidence["debt"].source_place == "India"
    assert all(
        "CA" not in evidence.source_place
        for evidence in sampled.component_evidence.values()
    )


def test_region_values_are_population_weighted_and_report_coverage():
    pack = load_global_finance_pack(PACK_PATH)
    countries = [
        country
        for country in pack.countries.values()
        if country["region"] == "Northern America"
        and "gni_per_capita_ppp" in country["metrics"]
    ]
    covered_population = sum(
        country["metrics"]["population"]["value"] for country in countries
    )
    expected = sum(
        country["metrics"]["gni_per_capita_ppp"]["value"]
        * country["metrics"]["population"]["value"]
        for country in countries
    ) / covered_population
    aggregate = pack.regions["Northern America"]["metrics"]["gni_per_capita_ppp"]

    assert aggregate["aggregation"] == "population_weighted_mean"
    assert math.isclose(aggregate["value"], expected)
    assert aggregate["covered_population"] == round(covered_population)
    assert aggregate["coverage_percent"] > 99
