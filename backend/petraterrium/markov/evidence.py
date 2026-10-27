import re

from ..dsl import Evidence
from .models import (
    CompilationContext,
    EvidenceCatalog,
    MarkovModule,
    MissingEvidenceRequirement,
    ModuleTransition,
    ResolvedProbability,
)


def normalized_predictors(
    module: MarkovModule,
    transition: ModuleTransition,
    context: CompilationContext,
) -> tuple[dict[str, object], list[str]]:
    inputs = {item.id: item for item in module.inputs}
    values: dict[str, object] = {}
    missing: list[str] = []
    for input_id in transition.probability.predictor_inputs:
        input_value = inputs[input_id]
        feature_id = input_value.feature_id or input_id
        if feature_id in context.strata:
            values[feature_id] = context.strata[feature_id]
        elif input_id in context.strata:
            values[feature_id] = context.strata[input_id]
        else:
            missing.append(feature_id)
    return values, sorted(missing)


def choice_matches(
    row,
    transition: ModuleTransition,
    context: CompilationContext,
    predictors: dict[str, object],
) -> bool:
    query = transition.probability
    if row.action_id != query.outcome_id or row.conditioning_id != query.conditioning_id:
        return False
    if row.conditioning.place != context.place or row.time_unit != context.time_unit:
        return False
    if row.tier_flag != "measured" or row.provenance.status != "present":
        return False
    if row.source_date is None or row.value is None or row.sample_size is None:
        return False
    expected_traits = {key: str(value) for key, value in predictors.items()}
    if row.conditioning.traits != expected_traits:
        return False
    stated_conditions = {**row.conditioning.state, **row.conditioning.context}
    expected_conditions = {key: str(value) for key, value in context.conditions.items()}
    return stated_conditions == expected_conditions


def transition_evidence_matches(
    row,
    transition: ModuleTransition,
    context: CompilationContext,
    predictors: dict[str, object],
) -> bool:
    query = transition.probability
    evidence_kind = row.kind
    if evidence_kind not in query.allowed_evidence:
        return False
    return (
        row.outcome_id == query.outcome_id
        and row.conditioning_id == query.conditioning_id
        and row.place == context.place
        and row.time_unit == context.time_unit
        and row.predictor_values == predictors
        and row.condition_values == context.conditions
    )


def requirement_key(
    module: MarkovModule,
    transition: ModuleTransition,
    context: CompilationContext,
    features: list[str],
) -> str:
    raw = "/".join(
        [
            "markov",
            module.id,
            transition.id,
            context.place,
            context.time_unit,
            "+".join(features) or "unconditioned",
        ]
    )
    return re.sub(r"[^a-z0-9_+/-]+", "-", raw.lower()).strip("-")


def missing_requirement(
    module: MarkovModule,
    transition: ModuleTransition,
    context: CompilationContext,
    features: list[str],
) -> MissingEvidenceRequirement:
    condition = ", ".join(features) if features else "the declared population"
    if "mbti" in features:
        prefix = "population-specific measured joint MBTI-to-outcome evidence"
    else:
        prefix = "Measured joint or held-out fitted trait-to-outcome evidence"
    requirement = (
        f"{prefix} for transition `{transition.id}` to `{transition.probability.outcome_id}` "
        f"in `{context.place}` at `{context.time_unit}`, conditioned on {condition}, measured "
        "on the same weighted respondents with the outcome denominator, source version, date, "
        "sample size, survey weights, confidence interval, and held-out validation for fitted "
        "models"
    )
    return MissingEvidenceRequirement(
        key=requirement_key(module, transition, context, features),
        module_id=module.id,
        transition_id=transition.id,
        requirement=requirement,
    )


def unknown_probability(
    module: MarkovModule,
    transition: ModuleTransition,
) -> ResolvedProbability:
    return ResolvedProbability(
        module_id=module.id,
        transition_id=transition.id,
        from_state=transition.from_state,
        to_state=transition.to_state,
        status="unknown",
        probability=None,
        ci_low=0,
        ci_high=1,
        evidence_kind="unknown",
        evidence_id=None,
        provenance=Evidence(
            source="No qualifying measured or held-out fitted transition evidence",
            version="missing",
            status="unknown",
            uncertainty=1,
        ),
    )


def resolve_probability(
    module: MarkovModule,
    transition: ModuleTransition,
    catalog: EvidenceCatalog,
    context: CompilationContext,
) -> tuple[ResolvedProbability, MissingEvidenceRequirement | None]:
    predictors, missing_predictors = normalized_predictors(module, transition, context)
    features = sorted(
        (item.feature_id or item.id)
        for item in module.inputs
        if item.id in transition.probability.predictor_inputs
    )
    if missing_predictors:
        return (
            unknown_probability(module, transition),
            missing_requirement(module, transition, context, features),
        )
    custom_matches = [
        row
        for row in catalog.transition
        if transition_evidence_matches(row, transition, context, predictors)
    ]
    custom_matches.sort(key=lambda row: (row.kind != "measured_joint", row.id))
    if custom_matches:
        row = custom_matches[0]
        return (
            ResolvedProbability(
                module_id=module.id,
                transition_id=transition.id,
                from_state=transition.from_state,
                to_state=transition.to_state,
                status="resolved",
                probability=row.probability,
                ci_low=row.ci_low,
                ci_high=row.ci_high,
                evidence_kind=row.kind,
                evidence_id=row.id,
                provenance=row.provenance,
            ),
            None,
        )
    if "mbti" not in features and "measured_choice" in transition.probability.allowed_evidence:
        choice_matches_found = [
            row
            for row in catalog.choice
            if choice_matches(row, transition, context, predictors)
        ]
        choice_matches_found.sort(key=lambda row: row.id)
        if choice_matches_found:
            row = choice_matches_found[0]
            return (
                ResolvedProbability(
                    module_id=module.id,
                    transition_id=transition.id,
                    from_state=transition.from_state,
                    to_state=transition.to_state,
                    status="resolved",
                    probability=row.value,
                    ci_low=row.ci_low,
                    ci_high=row.ci_high,
                    evidence_kind="measured_choice",
                    evidence_id=row.id,
                    provenance=row.provenance,
                ),
                None,
            )
    return (
        unknown_probability(module, transition),
        missing_requirement(module, transition, context, features),
    )
