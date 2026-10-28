import json
from pathlib import Path

from petraterrium.simulation.prompt1_source_audit import (
    MAJOR_FIELDS,
    audit_prompt1_sources,
)


def finding(report, finding_id):
    return next(item for item in report.findings if item.finding_id == finding_id)


def country(report, country_code):
    return next(item for item in report.countries if item.country_code == country_code)


def test_audit_records_the_exact_global_demo_mix_and_artifact_receipts():
    report = audit_prompt1_sources()

    assert report.schema_version == "prompt1-source-audit-v3"
    assert report.result == "incomplete"
    assert report.dsl_content_hash == (
        "sha256:cca92c543f6835211ef7ae99065cc3b67eef18453adc6a8b27d29e434ff40a5f"
    )
    assert report.total_agents == 1_000
    assert report.country_agent_counts == {
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
    assert report.region_agent_counts == {
        "Northern America": 81,
        "Latin America & Caribbean": 73,
        "Europe": 31,
        "Africa": 49,
        "Asia excluding China and India": 149,
        "China": 304,
        "India": 307,
        "Oceania": 6,
        "Rest / unassigned": 0,
    }
    assert finding(report, "global_population").status == "pass"
    assert all(len(receipt.sha256) == 64 for receipt in report.artifacts.values())
    assert "finance_initialization_interpreter" in report.artifacts
    assert "rust_agent_runtime" in report.artifacts
    assert json.loads(report.model_dump_json())["total_agents"] == 1_000


def test_audit_proves_country_source_integrity_without_overstating_measurement():
    report = audit_prompt1_sources()

    assert finding(report, "canadian_source_leakage").status == "pass"
    assert finding(report, "foreign_country_source_place").status == "pass"
    assert finding(report, "country_measured_label_semantics").status == "risk"
    for audited_country in report.countries:
        for field in audited_country.fields.values():
            assert field.canadian_source_leakage is False
            assert field.foreign_country_source is False
            assert field.individual_values_measured is False
        finance = audited_country.fields["finance"]
        assert finance.geographic_scope == "own_country_source"
        assert finance.source_statuses == ("imputed",)
        assert finance.source_places == (
            ("Canada",) if audited_country.country_code == "CA" else (audited_country.country_code,)
        )


def test_audit_lists_regional_imputation_and_unknown_evidence_exactly():
    report = audit_prompt1_sources()

    assert country(report, "BR").fields["education"].geographic_scope == "regional_imputed"
    assert country(report, "BD").fields["values"].geographic_scope == "mixed"
    for field in ("education", "occupation", "personality", "values"):
        assert country(report, "CA").fields[field].geographic_scope == "regional_imputed"
        assert country(report, "AU").fields[field].geographic_scope == "regional_imputed"
    assert finding(report, "regional_imputations").affected_countries == (
        "AU",
        "BD",
        "BR",
        "CA",
    )
    assert report.evidence_inventory.state_initialization_statuses == {"unknown": 31}
    assert report.evidence_inventory.state_evidence_statuses == {
        "literature_support": 8,
        "unknown": 120,
    }
    assert report.evidence_inventory.relationship_evidence_statuses == {"unknown": 4}
    assert report.evidence_inventory.action_evidence_statuses == {"default_estimated": 10}
    assert report.evidence_inventory.numeric_coefficients_with_unknown_evidence == (
        "stress:propagation:beta_health_stress",
    )
    assert len(report.evidence_inventory.default_actions_without_source_ids) == 10


def test_audit_exposes_threshold_aware_specialization_pipeline_evidence():
    report = audit_prompt1_sources()
    specialization = report.specialization_evidence

    assert specialization.total_agents == 1_000
    assert specialization.missing_value_count == 690
    assert specialization.threshold_years == (12,)
    assert specialization.status_counts == {
        "not_applicable": 690,
        "present": 310,
    }
    assert specialization.evidence_scope_counts == {
        "country_measured": 647,
        "estimated": 353,
    }
    assert specialization.source_status_counts == {
        "estimated": 353,
        "measured": 647,
    }
    assert specialization.unknown_country_codes == ()
    assert specialization.threshold_status_mismatch_count == 0
    assert specialization.country_status_counts["CA"] == {
        "not_applicable": 3,
        "present": 5,
    }
    assert specialization.country_status_counts["IN"] == {
        "not_applicable": 216,
        "present": 91,
    }
    assert "age/sex/education" in specialization.required_data
    assert "ISCED-F-compatible" in specialization.required_data
    assert all(
        audited_country.fields["specialization"].geographic_scope == "own_country_source"
        for audited_country in report.countries
    )
    assert all(
        audited_country.fields["specialization"].source_places
        == (audited_country.country_code,)
        and set(audited_country.fields["specialization"].source_statuses)
        <= {"measured", "estimated"}
        and audited_country.fields["specialization"].missing_item_provenance == ()
        for audited_country in report.countries
    )
    assert finding(report, "specialization_evidence").status == "pass"
    assert finding(report, "specialization_evidence").logged_in_missing is True
    assert "310 qualified agents have a specialization" in finding(
        report, "specialization_evidence"
    ).summary
    assert "690 agents are structurally not applicable" in finding(
        report, "specialization_evidence"
    ).summary
    assert finding(report, "specialization_threshold_status").status == "pass"
    assert report.dsl_source_of_truth.result == "complete"
    assert all(
        finding(report, finding_id).status == "pass"
        for finding_id in (
            "dsl_single_source_state_formulas",
            "dsl_single_source_finance_initialization",
            "dsl_single_source_finance_tick_accounting",
            "dsl_single_source_action_formulas",
            "dsl_single_source_decision_programs",
            "dsl_single_source_interactions",
        )
    )


def test_audit_keeps_finance_source_scope_separate_from_person_level_quality():
    report = audit_prompt1_sources()

    canada = country(report, "CA")
    assert canada.finance_currency == "CAD"
    assert canada.finance_accounting_unit == "Canadian dollars"
    assert canada.fields["finance"].sources == (
        "Statistique Canada tables 98-10-0407-01, 11-10-0016-01, and 11-10-0223-01",
    )
    for audited_country in report.countries:
        if audited_country.country_code == "CA":
            continue
        assert audited_country.finance_currency == "PPP"
        assert audited_country.finance_accounting_unit == "current international dollars (PPP)"
        assert audited_country.fields["finance"].sources == (
            "World Bank World Development Indicators",
        )
    finance_finding = finding(report, "individual_finance_imputation")
    assert finance_finding.status == "gap"
    assert finance_finding.affected_countries == tuple(report.country_agent_counts)
    currency_finding = finding(report, "local_currency_and_cost_of_living")
    assert currency_finding.status == "gap"
    assert currency_finding.affected_countries == tuple(
        code for code in report.country_agent_counts if code != "CA"
    )


def test_audit_exposes_incomplete_search_traces_and_gap_register_entries():
    report = audit_prompt1_sources()

    assert all(item.status == "incomplete" for item in report.local_language_search)
    assert all(
        set(item.fields_missing_item_level_search_trace).issubset(MAJOR_FIELDS)
        for item in report.local_language_search
    )
    canada = next(item for item in report.local_language_search if item.country_code == "CA")
    assert canada.fields_with_item_level_search_trace == ("specialization", "finance")
    assert "specialization" not in canada.fields_missing_item_level_search_trace
    assert canada.recorded_languages == ("en", "fr", "iu")
    assert canada.has_non_english_local_trace is True
    china = next(item for item in report.local_language_search if item.country_code == "CN")
    assert "zh" in china.registry_languages
    assert "specialization" in china.fields_with_item_level_search_trace
    assert china.recorded_languages == ("en", "zh")
    assert china.has_non_english_local_trace is True
    assert report.missing_register.entries_found == (
        "country_feature_imputations",
        "fitted_action_coefficients",
        "individual_finance_microdata",
        "specialization_joint_data",
    )
    assert report.missing_register.entries_absent == (
        "cross_country_interaction_proof",
        "dsl_single_source",
        "global_and_place_distribution_comparison",
        "local_currency_and_cost_of_living",
        "local_language_search_logs",
    )
    assert finding(report, "missing_register_completeness").status == "gap"


def test_source_inventory_preserves_exact_recorded_metadata_without_network_claims():
    report = audit_prompt1_sources()
    sources = {source.source_id: source for source in report.source_inventory}

    wdi = sources["world_bank_wdi_global_finance_2026"]
    assert wdi.source == "World Bank"
    assert wdi.date == "2026-10-08"
    assert wdi.place == "Global"
    assert wdi.population == "216 countries and population-weighted canonical regions"
    assert wdi.language == "en"
    assert wdi.discovery_source == "Official World Bank WDI bulk archive"
    assert wdi.missing_required_metadata == ()
    statcan = sources["statscan_employment_income_2021"]
    assert statcan.language == "fr"
    assert statcan.place == "Canada"
    assert statcan.title.startswith("Tranches de revenu")
    assert statcan.english_title.startswith("Employment income groups")
    assert statcan.missing_required_metadata == ()
    assert "not independently re-researched" in report.verification_boundary


def test_audit_identifies_complete_dsl_definitions_and_generic_runtimes():
    report = audit_prompt1_sources()
    audit = report.dsl_source_of_truth
    items = {item.domain: item for item in audit.items}

    assert audit.result == "complete"
    assert audit.decision_tree_country_codes == (
        "AU",
        "BD",
        "BR",
        "CA",
        "CN",
        "ID",
        "IN",
        "MX",
        "NG",
        "PK",
        "RU",
        "US",
    )
    assert audit.decision_tree_uncovered_country_codes == ()
    assert items["state_formulas"].status == "dsl_defined"
    assert items["state_formulas"].dsl_formula_count == 163
    assert items["state_formulas"].executable_parameter_count == 31
    assert items["state_formulas"].unresolved_items == ()
    assert items["finance_initialization"].status == "dsl_defined"
    assert items["finance_initialization"].dsl_formula_count == 12
    assert items["finance_initialization"].executable_parameter_count == 270
    assert items["finance_initialization"].unresolved_items == ()
    assert set(items["finance_initialization"].dsl_definition_ids) == {
        "finance-initialization:canada-statscan-finance-initialization:debt",
        "finance-initialization:canada-statscan-finance-initialization:expenses",
        "finance-initialization:canada-statscan-finance-initialization:financial_assets",
        "finance-initialization:canada-statscan-finance-initialization:income",
        "finance-initialization:canada-statscan-finance-initialization:money",
        "finance-initialization:canada-statscan-finance-initialization:savings",
        "finance-initialization:global-wdi-finance-initialization:debt",
        "finance-initialization:global-wdi-finance-initialization:expenses",
        "finance-initialization:global-wdi-finance-initialization:income",
        "finance-initialization:global-wdi-finance-initialization:income_quintile_index",
        "finance-initialization:global-wdi-finance-initialization:money",
        "finance-initialization:global-wdi-finance-initialization:savings",
    }
    assert items["finance_initialization"].runtime_symbols == (
        "FinanceInitializationCatalog",
        "evaluate_finance_initialization",
    )
    assert items["finance_tick_accounting"].status == "dsl_defined"
    assert items["finance_tick_accounting"].dsl_formula_count == 14
    assert items["finance_tick_accounting"].executable_parameter_count == 38
    assert {
        "ledger:update_income",
        "ledger:update_expenses",
        "ledger:update_money",
        "ledger:update_savings",
        "ledger:update_debt",
    } <= set(items["finance_tick_accounting"].dsl_definition_ids)
    assert items["action_formulas"].status == "dsl_defined"
    assert items["action_formulas"].executable_parameter_count == 18
    assert items["action_formulas"].unresolved_items == ()
    assert {
        "eat_lunch",
        "skip_lunch",
        "exclusive-choice:midday_meal:eat_lunch",
        "exclusive-choice:midday_meal:skip_lunch",
    } <= set(items["action_formulas"].dsl_definition_ids)
    assert "evaluate_exclusive_action_group" in items["action_formulas"].runtime_symbols
    assert items["decision_programs"].status == "dsl_defined"
    assert items["decision_programs"].runtime_symbols == ("compile_runtime_decisions",)
    assert items["decision_programs"].outside_dsl_behaviors == ()
    assert items["interactions"].status == "dsl_defined"
    assert items["interactions"].dsl_definition_ids == (
        "basic_social_contact",
        "relationship:friend",
        "rule:global-demo-cross-country-contact",
    )
    assert items["interactions"].outside_dsl_behaviors == ()
    assert finding(report, "dsl_single_source_finance_initialization").status == "pass"
    assert finding(report, "dsl_single_source_action_formulas").status == "pass"
    assert finding(report, "dsl_single_source_state_formulas").status == "pass"
    assert finding(report, "dsl_single_source_finance_tick_accounting").status == "pass"
    assert finding(report, "dsl_single_source_decision_programs").status == "pass"
    assert finding(report, "dsl_single_source_interactions").status == "pass"


def test_human_gap_register_keeps_material_audit_limits_upfront():
    text = (Path(__file__).resolve().parents[2] / "PROMPT1_DATA_GAPS.md").read_text()
    normalized = " ".join(text.split())

    assert "no Canadian source attached to a non-Canadian agent" in normalized
    assert "1,000 synthetic agents across 12 countries" in normalized
    assert (
        "All person-level money, income, expenses, savings, and debt values are imputed"
        in normalized
    )
    assert "No search attempts were invented" in normalized
    assert "does not contain a run receipt proving that a cross-country interaction" in normalized
    assert "validated finance initialization programs" in normalized
    assert "one seeded categorical draw" in normalized
    assert "690 agents are below the 12-year education threshold" in normalized
    assert "310 qualified agents receive a specialization" in normalized
    assert "China and Nigeria use country-specific estimates" in normalized
    assert "ISCED-F-compatible" in normalized
