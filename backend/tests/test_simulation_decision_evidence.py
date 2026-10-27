from datetime import date

import pytest
from pydantic import ValidationError

from petraterrium.simulation.decision_evidence import (
    AgentDecisionContext,
    AgentPlace,
    DecisionEdgeTemplate,
    DecisionFactorEvidence,
    DecisionProbabilityFormula,
    EvidencePlace,
    EvidencePredicate,
    NoSourceAttachment,
    ProbabilityFactor,
    ResearchCitation,
    decision_domain_templates,
    evaluate_decision_edge,
)


def source(
    source_id: str,
    title: str,
    population: str,
    decision_id: str,
    factor_ids: tuple[str, ...],
) -> ResearchCitation:
    return ResearchCitation(
        kind="research_paper",
        imported_source_id=source_id,
        title=title,
        source="FAKE fixture journal",
        publication_date=date(2024, 1, 1),
        population_studied=population,
        link_or_reference=f"fixture://{source_id}",
        supports_decision_ids=(decision_id,),
        supports_factor_ids=factor_ids,
    )


def place(country_id: str, region_id: str, city_id: str | None = None) -> AgentPlace:
    return AgentPlace(region_id=region_id, country_id=country_id, city_id=city_id)


def context(
    agent_id: str,
    country_id: str,
    region_id: str,
    extraversion: str = "high",
) -> AgentDecisionContext:
    return AgentDecisionContext(
        agent_id=agent_id,
        place=place(country_id, region_id),
        traits={"big_five_extraversion": extraversion},
        place_attributes={"evening_venues_available": True},
        time={"weekday": "friday"},
        context={"free_evening": True},
    )


def go_out_edge(source_receipt: ResearchCitation | None = None) -> DecisionEdgeTemplate:
    decision_id = "go_out_friday"
    factor_ids = (
        "extraversion_factor",
        "venue_factor",
        "weekday_factor",
        "availability_factor",
    )
    return DecisionEdgeTemplate(
        id="leave_home",
        decision_id=decision_id,
        domain="social",
        from_state="decide",
        to_state="go_out",
        label="Go out on Friday night",
        formula=DecisionProbabilityFormula(
            id="go_out_formula",
            name="Friday social outing probability",
            combination="product",
            factors=(
                ProbabilityFactor(
                    id=factor_ids[0],
                    name="Extraversion fit",
                    input_kind="trait",
                    input_key="big_five_extraversion",
                    feature_id="big_five_extraversion",
                ),
                ProbabilityFactor(
                    id=factor_ids[1],
                    name="Venue availability",
                    input_kind="place",
                    input_key="evening_venues_available",
                ),
                ProbabilityFactor(
                    id=factor_ids[2],
                    name="Friday timing",
                    input_kind="time",
                    input_key="weekday",
                ),
                ProbabilityFactor(
                    id=factor_ids[3],
                    name="Free evening",
                    input_kind="context",
                    input_key="free_evening",
                ),
            ),
        ),
        source=source_receipt
        or NoSourceAttachment(reason="No imported study supports this decision yet"),
    )


def evidence_for_country(
    country_id: str,
    region_id: str,
    values: tuple[float, float, float, float],
) -> list[DecisionFactorEvidence]:
    decision_id = "go_out_friday"
    factor_ids = (
        "extraversion_factor",
        "venue_factor",
        "weekday_factor",
        "availability_factor",
    )
    source_receipt = source(
        f"{country_id.lower()}-fixture-study",
        f"FAKE {country_id} Friday activity study",
        f"Adults in {country_id}",
        decision_id,
        factor_ids,
    )
    input_values = ("high", True, "friday", True)
    return [
        DecisionFactorEvidence(
            id=f"{country_id.lower()}-{factor_id}",
            decision_id=decision_id,
            edge_id="leave_home",
            factor_id=factor_id,
            place=EvidencePlace(
                level="country",
                place_id=country_id,
                region_id=region_id,
                country_id=country_id,
            ),
            predicate=EvidencePredicate(operator="exact", value=input_value),
            basis="measured_joint",
            estimate=value,
            ci_low=max(0.0, value - 0.05),
            ci_high=min(1.0, value + 0.05),
            sample_size=500,
            fittable=True,
            source=source_receipt,
        )
        for factor_id, input_value, value in zip(
            factor_ids, input_values, values, strict=True
        )
    ]


def test_country_resolution_uses_each_countrys_evidence_and_never_copies() -> None:
    factor_ids = (
        "extraversion_factor",
        "venue_factor",
        "weekday_factor",
        "availability_factor",
    )
    japan_source = source(
        "japan-fixture-study",
        "FAKE Japan Friday activity study",
        "Adults in Japan",
        "go_out_friday",
        factor_ids,
    )
    edge = go_out_edge(japan_source)
    rows = evidence_for_country("JP", "eastern-asia", (0.5, 0.8, 0.75, 0.9))
    rows += evidence_for_country("CA", "northern-america", (0.25, 0.8, 0.5, 0.9))

    japan = evaluate_decision_edge(edge, context("jp-1", "JP", "eastern-asia"), rows)
    canada_edge = edge.model_copy(
        update={
            "source": source(
                "canada-fixture-study",
                "FAKE Canada Friday activity study",
                "Adults in Canada",
                "go_out_friday",
                factor_ids,
            )
        }
    )
    canada = evaluate_decision_edge(
        canada_edge,
        context("ca-1", "CA", "northern-america"),
        rows,
    )
    absent = evaluate_decision_edge(
        edge,
        context("br-1", "BR", "latin-america-caribbean"),
        rows,
    )

    assert japan.status == "measured"
    assert japan.probability == pytest.approx(0.27)
    assert {receipt.evidence_place.place_id for receipt in japan.factors} == {"JP"}
    assert canada.status == "measured"
    assert canada.probability == pytest.approx(0.09)
    assert {receipt.evidence_place.place_id for receipt in canada.factors} == {"CA"}
    assert absent.status == "unknown"
    assert absent.probability is None
    assert absent.ci_low == 0
    assert absent.ci_high == 1
    assert all(receipt.evidence_id is None for receipt in absent.factors)
    assert all(receipt.source.kind == "none" for receipt in absent.factors)


def test_city_evidence_beats_country_evidence_for_that_city_only() -> None:
    factor_ids = (
        "extraversion_factor",
        "venue_factor",
        "weekday_factor",
        "availability_factor",
    )
    edge = go_out_edge(
        source(
            "canada-fixture-study",
            "FAKE Canada Friday activity study",
            "Adults in Canada",
            "go_out_friday",
            factor_ids,
        )
    )
    rows = evidence_for_country("CA", "northern-america", (0.5, 0.5, 0.5, 0.5))
    city_source = source(
        "toronto-fixture-study",
        "FAKE Toronto Friday activity study",
        "Adults in Toronto",
        "go_out_friday",
        factor_ids,
    )
    rows += [
        row.model_copy(
            update={
                "id": f"toronto-{row.factor_id}",
                "place": EvidencePlace(
                    level="city",
                    place_id="toronto",
                    region_id="northern-america",
                    country_id="CA",
                    city_id="toronto",
                ),
                "estimate": 0.8,
                "ci_low": 0.7,
                "ci_high": 0.9,
                "source": city_source,
            }
        )
        for row in rows
    ]
    toronto_context = context("toronto-1", "CA", "northern-america").model_copy(
        update={"place": place("CA", "northern-america", "toronto")}
    )

    toronto = evaluate_decision_edge(edge, toronto_context, rows)
    elsewhere = evaluate_decision_edge(
        edge,
        context("ca-2", "CA", "northern-america"),
        rows,
    )

    assert toronto.probability == pytest.approx(0.4096)
    assert {receipt.resolved_level for receipt in toronto.factors} == {"city"}
    assert elsewhere.probability == pytest.approx(0.0625)
    assert {receipt.resolved_level for receipt in elsewhere.factors} == {"country"}


def test_less_specific_place_evidence_is_visible_but_blocked_as_a_predictor() -> None:
    factor_ids = (
        "extraversion_factor",
        "venue_factor",
        "weekday_factor",
        "availability_factor",
    )
    source_receipt = source(
        "regional-fixture-study",
        "FAKE regional Friday activity study",
        "Adults in Northern America",
        "go_out_friday",
        factor_ids,
    )
    edge = go_out_edge(source_receipt)
    country_rows = evidence_for_country(
        "CA", "northern-america", (0.5, 0.5, 0.5, 0.5)
    )
    regional_rows = [
        row.model_copy(
            update={
                "id": f"regional-{row.factor_id}",
                "place": EvidencePlace(
                    level="region",
                    place_id="northern-america",
                    region_id="northern-america",
                ),
                "source": source_receipt,
            }
        )
        for row in country_rows
    ]
    global_rows = [
        row.model_copy(
            update={
                "id": f"global-{row.factor_id}",
                "place": EvidencePlace(level="global", place_id="global"),
                "source": source_receipt,
            }
        )
        for row in country_rows
    ]

    regional = evaluate_decision_edge(
        edge,
        context("ca-1", "CA", "northern-america"),
        regional_rows,
    )
    global_fallback = evaluate_decision_edge(
        edge,
        context("ca-2", "CA", "northern-america"),
        global_rows,
    )

    assert regional.status == "unknown"
    assert regional.probability is None
    assert regional.fittable is False
    assert {receipt.status for receipt in regional.factors} == {"inherited"}
    assert {receipt.evidence_place.place_id for receipt in regional.factors} == {
        "northern-america"
    }
    assert all("inherited" in receipt.message for receipt in regional.factors)
    assert global_fallback.status == "unknown"
    assert global_fallback.probability is None
    assert global_fallback.fittable is False
    assert {receipt.status for receipt in global_fallback.factors} == {"imputed"}
    assert {receipt.evidence_place.place_id for receipt in global_fallback.factors} == {
        "global"
    }


def test_region_evidence_is_direct_for_a_region_level_agent() -> None:
    factor_ids = (
        "extraversion_factor",
        "venue_factor",
        "weekday_factor",
        "availability_factor",
    )
    source_receipt = source(
        "regional-fixture-study",
        "FAKE regional Friday activity study",
        "Adults in Northern America",
        "go_out_friday",
        factor_ids,
    )
    edge = go_out_edge(source_receipt)
    country_rows = evidence_for_country(
        "CA", "northern-america", (0.5, 0.5, 0.5, 0.5)
    )
    rows = [
        row.model_copy(
            update={
                "id": f"regional-{row.factor_id}",
                "place": EvidencePlace(
                    level="region",
                    place_id="northern-america",
                    region_id="northern-america",
                ),
                "source": source_receipt,
            }
        )
        for row in country_rows
    ]
    region_context = context("region-1", "CA", "northern-america").model_copy(
        update={
            "place": AgentPlace(
                region_id="northern-america",
                country_id=None,
            )
        }
    )

    result = evaluate_decision_edge(edge, region_context, rows)

    assert result.status == "measured"
    assert result.probability == pytest.approx(0.0625)
    assert {receipt.resolution_status for receipt in result.factors} == {"direct"}
    assert {receipt.resolved_level for receipt in result.factors} == {"region"}


def test_country_evidence_inherited_by_a_city_is_not_city_measured() -> None:
    factor_ids = (
        "extraversion_factor",
        "venue_factor",
        "weekday_factor",
        "availability_factor",
    )
    source_receipt = source(
        "canada-fixture-study",
        "FAKE Canada Friday activity study",
        "Adults in Canada",
        "go_out_friday",
        factor_ids,
    )
    edge = go_out_edge(source_receipt)
    rows = evidence_for_country("CA", "northern-america", (0.5, 0.5, 0.5, 0.5))
    city_context = context("toronto-1", "CA", "northern-america").model_copy(
        update={"place": place("CA", "northern-america", "toronto")}
    )

    result = evaluate_decision_edge(edge, city_context, rows)

    assert result.status == "measured"
    assert result.status_label == "measured at source place — inherited by agent place"
    assert result.probability == pytest.approx(0.0625)
    assert {receipt.status for receipt in result.factors} == {"measured"}
    assert {receipt.resolution_status for receipt in result.factors} == {"inherited"}
    assert {receipt.resolved_level for receipt in result.factors} == {"country"}
    assert all(receipt.fittable is True for receipt in result.factors)


def test_marginals_are_independence_estimates_and_cannot_fit() -> None:
    factor_ids = (
        "extraversion_factor",
        "venue_factor",
        "weekday_factor",
        "availability_factor",
    )
    source_receipt = source(
        "japan-marginal-fixture",
        "FAKE Japan marginal study",
        "Adults in Japan",
        "go_out_friday",
        factor_ids,
    )
    edge = go_out_edge(source_receipt)
    rows = evidence_for_country("JP", "eastern-asia", (0.5, 0.8, 0.75, 0.9))
    rows[0] = rows[0].model_copy(
        update={
            "basis": "marginal",
            "fittable": False,
            "source": source_receipt,
        }
    )

    result = evaluate_decision_edge(edge, context("jp-1", "JP", "eastern-asia"), rows)

    assert result.status == "independence_estimate"
    assert result.status_label == "independence estimate — not measured"
    assert result.probability == pytest.approx(0.27)
    assert result.ci_low == 0
    assert result.ci_high == 1
    assert result.fittable is False
    assert result.factors[0].status == "independence_estimate"
    assert result.factors[0].fittable is False


def test_mbti_is_label_only_without_population_specific_joint_evidence() -> None:
    citation = source(
        "canada-mbti-fixture",
        "FAKE Canada MBTI outcome study",
        "Adults in Canada",
        "social_invitation",
        ("mbti_factor", "free_time_factor"),
    )
    edge = DecisionEdgeTemplate(
        id="accept_invitation",
        decision_id="social_invitation",
        domain="social",
        from_state="invited",
        to_state="accept",
        label="Accept a social invitation",
        formula=DecisionProbabilityFormula(
            id="invitation_formula",
            name="Invitation acceptance probability",
            combination="product",
            factors=(
                ProbabilityFactor(
                    id="mbti_factor",
                    name="MBTI label association",
                    input_kind="trait",
                    input_key="mbti",
                    feature_id="mbti",
                ),
                ProbabilityFactor(
                    id="free_time_factor",
                    name="Free time",
                    input_kind="context",
                    input_key="free_evening",
                ),
            ),
        ),
        source=citation,
    )
    agent = AgentDecisionContext(
        agent_id="ca-mbti",
        place=place("CA", "northern-america"),
        traits={"mbti": "ENFP"},
        place_attributes={},
        time={},
        context={"free_evening": True},
    )
    base_rows = [
        DecisionFactorEvidence(
            id="canada-mbti-marginal",
            decision_id="social_invitation",
            edge_id="accept_invitation",
            factor_id="mbti_factor",
            place=EvidencePlace(
                level="country",
                place_id="CA",
                region_id="northern-america",
                country_id="CA",
            ),
            predicate=EvidencePredicate(operator="exact", value="ENFP"),
            basis="marginal",
            estimate=0.6,
            ci_low=0.5,
            ci_high=0.7,
            sample_size=300,
            fittable=False,
            source=citation,
        ),
        DecisionFactorEvidence(
            id="canada-free-time-joint",
            decision_id="social_invitation",
            edge_id="accept_invitation",
            factor_id="free_time_factor",
            place=EvidencePlace(
                level="country",
                place_id="CA",
                region_id="northern-america",
                country_id="CA",
            ),
            predicate=EvidencePredicate(operator="exact", value=True),
            basis="measured_joint",
            estimate=0.8,
            ci_low=0.7,
            ci_high=0.9,
            sample_size=300,
            fittable=True,
            source=citation,
        ),
    ]

    label_only = evaluate_decision_edge(edge, agent, base_rows)
    joint_rows = [
        base_rows[0].model_copy(
            update={"basis": "measured_joint", "fittable": True}
        ),
        base_rows[1],
    ]
    measured = evaluate_decision_edge(edge, agent, joint_rows)

    assert label_only.status == "unknown"
    assert label_only.factors[0].status == "label_only"
    assert label_only.factors[0].fittable is False
    assert measured.status == "measured"
    assert measured.probability == pytest.approx(0.48)


def test_citation_must_link_to_imported_source_and_supported_decision() -> None:
    with pytest.raises(ValidationError):
        ResearchCitation(
            kind="article",
            imported_source_id="",
            title="FAKE unsupported article",
            source="FAKE fixture publisher",
            publication_date=date(2024, 1, 1),
            population_studied="Fixture population",
            link_or_reference="fixture://unsupported",
            supports_decision_ids=("other_decision",),
            supports_factor_ids=("extraversion_factor",),
        )

    receipt = source(
        "unsupported-fixture",
        "FAKE unsupported study",
        "Fixture population",
        "other_decision",
        ("extraversion_factor",),
    )
    with pytest.raises(ValidationError):
        go_out_edge(receipt)


def test_templates_cover_domains_without_invented_rates_or_citations() -> None:
    templates = decision_domain_templates()

    assert {template.domain for template in templates} == {
        "work",
        "social",
        "family",
        "health",
        "consumption",
        "political",
        "other",
    }
    assert all(template.status == "awaiting_evidence" for template in templates)
    assert all(edge.source.kind == "none" for template in templates for edge in template.edges)
    assert all(
        edge.source.label == "no source attached — estimated / unknown"
        for template in templates
        for edge in template.edges
    )
    assert all(len(edge.formula.factors) >= 2 for template in templates for edge in template.edges)
    assert all(
        not hasattr(edge, "probability") for template in templates for edge in template.edges
    )
