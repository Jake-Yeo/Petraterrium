import hashlib
import json
import re
from datetime import date
from typing import Literal, Protocol
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..atlas.auto_import_provider import (
    MAX_PAGE_TEXT,
    PublicResearchProvider,
    _result_links,
    _search_url,
    _visible_text,
)
from ..atlas.auto_import_research import (
    LANGUAGE_NAMES,
    LOCAL_ENGINES,
    SEARCH_SOURCE_ORDER,
    SOURCE_TERMS,
    PlaceFeatureTarget,
    SearchPlan,
    SearchStep,
    research_languages,
)
from ..llm_gateway import AIProviderError, SelectedAIProvider
from ..markov.pipeline_evidence import (
    PipelineEstimateSource,
    PipelineResearchLog,
    PipelineTransitionEstimate,
)

PROMPT_VERSION = "markov-transition-research-v1"
MAX_TRANSITION_EXCERPT = 6_000


class ProbabilityResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class TransitionOutcomeDefinition(ProbabilityResearchModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    description: str = Field(min_length=1)
    localized_descriptions: dict[str, str] = Field(default_factory=dict)


class TransitionResearchPlace(ProbabilityResearchModel):
    level: Literal["region", "country", "city"]
    place_id: str = Field(min_length=1)
    place_label: str = Field(min_length=1)
    population: int = Field(ge=0)
    country_code: str | None = None
    local_names: dict[str, str] = Field(default_factory=dict)
    dominant_languages: tuple[str, ...] = ()


class TransitionProbabilityResearchRequest(ProbabilityResearchModel):
    transition_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    outcome_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    outcome_description: str = Field(min_length=1)
    outcomes: tuple[TransitionOutcomeDefinition, ...] = Field(min_length=2)
    conditioning_id: str = Field(min_length=1)
    conditioning_description: str = Field(min_length=1)
    localized_conditioning_descriptions: dict[str, str] = Field(default_factory=dict)
    localized_search_terms: dict[str, str] = Field(default_factory=dict)
    place: TransitionResearchPlace
    time_unit: Literal["event", "hour", "day", "friday", "week", "year"]
    predictor_values: dict[str, str | float | int | bool] = Field(default_factory=dict)
    condition_values: dict[str, str | float | int | bool] = Field(default_factory=dict)
    population_basis: str | None = None
    as_of: date = Field(default_factory=date.today)

    @model_validator(mode="after")
    def valid_outcomes(self):
        identifiers = [outcome.id for outcome in self.outcomes]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Outgoing outcome ids must be unique")
        if self.outcome_id not in identifiers:
            raise ValueError("The researched outcome must appear in outgoing outcomes")
        return self


class TransitionResearchProvider(Protocol):
    def search_transition(
        self,
        step: SearchStep,
        request: TransitionProbabilityResearchRequest,
    ) -> list[PipelineEstimateSource]: ...


class _TransitionSynthesisDraft(ProbabilityResearchModel):
    probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    ci_low: float = Field(ge=0, le=1, allow_inf_nan=False)
    ci_high: float = Field(ge=0, le=1, allow_inf_nan=False)
    sample_size: int | None = Field(default=None, gt=0)
    reasoning: str = Field(min_length=1)
    assumptions: tuple[str, ...] = Field(min_length=1)
    selected_source_ids: tuple[str, ...] = Field(min_length=1)
    joint_outcome_source_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def valid_uncertainty(self):
        if not self.ci_low <= self.probability <= self.ci_high:
            raise ValueError("Probability must be inside its confidence interval")
        if self.ci_high - self.ci_low < 0.3 - 1e-12:
            raise ValueError("Estimated transition intervals must be at least 0.3 wide")
        text = " ".join((self.reasoning, *self.assumptions)).casefold()
        if re.search(r"independence product|marginal product|p\s*\(.+\)\s*[x×*]\s*p\s*\(", text):
            raise ValueError("Independence products cannot become transition evidence")
        return self


class PublicTransitionResearchProvider:
    def __init__(self, provider: PublicResearchProvider):
        self.provider = provider

    def search_transition(
        self,
        step: SearchStep,
        request: TransitionProbabilityResearchRequest,
    ) -> list[PipelineEstimateSource]:
        search_url = _search_url(step.engine, step.query)
        body, content_type = self.provider._download(search_url)
        links = _result_links(body, content_type, search_url)
        sources = []
        for link in links[:3]:
            try:
                content, page_type = self.provider._download(link)
            except (httpx.HTTPError, ValueError, OSError):
                continue
            excerpt = _visible_text(content, page_type)[
                : min(MAX_PAGE_TEXT, MAX_TRANSITION_EXCERPT)
            ].strip()
            if not excerpt:
                continue
            source_id = f"source-{hashlib.sha256(link.encode()).hexdigest()[:16]}"
            title = _source_title(excerpt, link)
            sources.append(
                PipelineEstimateSource(
                    id=source_id,
                    title=title,
                    url=link,
                    source_kind=step.source_kind,
                    retrieved_date=request.as_of.isoformat(),
                    language=step.language,
                    excerpt=excerpt,
                    source_version=f"retrieved-{request.as_of.isoformat()}",
                    license="Publisher terms apply",
                )
            )
        return sources


class MarkovProbabilityResearchService:
    def __init__(
        self,
        provider: TransitionResearchProvider,
        ai_provider: SelectedAIProvider,
    ):
        self.provider = provider
        self.ai_provider = ai_provider

    def research(
        self,
        request: TransitionProbabilityResearchRequest,
    ) -> PipelineTransitionEstimate:
        attempt_id = uuid4().hex
        plan = build_transition_search_plan(request)
        logs: list[PipelineResearchLog] = []
        sources_by_id: dict[str, PipelineEstimateSource] = {}
        for step in plan.steps:
            try:
                found = self.provider.search_transition(step, request)
                dated = [
                    source
                    if source.observation_date
                    or source.published_date
                    or source.retrieved_date
                    else source.model_copy(
                        update={"retrieved_date": request.as_of.isoformat()}
                    )
                    for source in found
                ]
                for source in dated:
                    sources_by_id.setdefault(source.id, source)
                outcome = "candidate" if found else "no_result"
                source_ids = tuple(source.id for source in dated)
            except (AIProviderError, httpx.HTTPError, ValueError, OSError):
                outcome = "error"
                source_ids = ()
            logs.append(
                PipelineResearchLog(
                    sequence=len(logs) + 1,
                    origin="automatic",
                    language=step.language,
                    engine=step.engine,
                    query_or_source=step.query,
                    source_kind=step.source_kind,
                    outcome=outcome,
                    source_ids=source_ids,
                )
            )
        sources = tuple(sources_by_id.values())
        synthesis, provenance = self._synthesize(request, logs, sources)
        if synthesis is None:
            synthesis, sources, logs = _maximum_uncertainty_fallback(
                request,
                attempt_id,
                sources,
                logs,
            )
        selected = set(synthesis.selected_source_ids)
        joint = set(synthesis.joint_outcome_source_ids)
        sources = tuple(
            source.model_copy(
                update={"supports_joint_outcome": source.id in joint}
            )
            for source in sources
        )
        predictor_values = request.predictor_values
        assumptions = synthesis.assumptions
        method = "source_synthesis"
        if predictor_values:
            qualifying_joint = selected & joint
            if qualifying_joint:
                method = "joint_outcome_synthesis"
            else:
                predictor_values = {}
                assumptions = (
                    *assumptions,
                    "Requested predictors were excluded because the retrieved sources did "
                    "not link them to the outcome on the same population.",
                )
        provider_name, model_name = _provider_identity(self.ai_provider)
        if provenance is not None:
            provider_name = provenance.source
            model_name = provenance.model
        estimate = PipelineTransitionEstimate(
            id=f"estimate-{request.transition_id}-{attempt_id[:12]}",
            pipeline_attempt_id=attempt_id,
            outcome_id=request.outcome_id,
            conditioning_id=request.conditioning_id,
            place=request.place.place_id,
            time_unit=request.time_unit,
            predictor_values=predictor_values,
            condition_values=request.condition_values,
            probability=synthesis.probability,
            ci_low=synthesis.ci_low,
            ci_high=synthesis.ci_high,
            population=request.population_basis or request.place.place_label,
            sample_size=synthesis.sample_size,
            reasoning=synthesis.reasoning,
            assumptions=assumptions,
            method=method,
            sources=sources,
            selected_source_ids=synthesis.selected_source_ids,
            search_log=tuple(logs),
            pipeline_provider=provider_name,
            pipeline_model=model_name,
            prompt_version=PROMPT_VERSION,
        )
        return estimate

    def _synthesize(self, request, logs, sources):
        if not sources:
            return None, None
        payload = json.dumps(
            {
                "request": request.model_dump(mode="json"),
                "search_log": [entry.model_dump(mode="json") for entry in logs],
                "sources": [source.model_dump(mode="json") for source in sources],
            },
            ensure_ascii=False,
        )
        try:
            generated = self.ai_provider.generate_structured(
                payload,
                _TransitionSynthesisDraft,
                system_prompt=(
                    "Synthesize a draft transition probability only from the supplied "
                    "research trace and source excerpts. Preserve wide uncertainty: the "
                    "confidence interval must span at least 0.3. News, public opinion, and "
                    "commentary may support an estimated rate when stronger sources are "
                    "absent, but the reasoning must identify that limitation. Never "
                    "multiply marginal rates, never use an independence estimate, and never "
                    "present the result as measured. A predictor-conditioned estimate "
                    "requires a selected source that links the predictor and outcome in the "
                    "same represented population; list those sources in "
                    "joint_outcome_source_ids. MBTI requires such joint outcome evidence. "
                    "Return the source ids actually used and state every assumption."
                ),
                prompt_version=PROMPT_VERSION,
            )
            draft = generated.output
        except (AIProviderError, ValidationError, ValueError):
            return None, None
        available = {source.id for source in sources}
        if not set(draft.selected_source_ids).issubset(available):
            return None, None
        if not set(draft.joint_outcome_source_ids).issubset(draft.selected_source_ids):
            return None, None
        if request.predictor_values and not draft.joint_outcome_source_ids:
            return None, None
        return draft, generated.provenance


def build_transition_search_plan(
    request: TransitionProbabilityResearchRequest,
) -> SearchPlan:
    target = PlaceFeatureTarget(
        level=request.place.level,
        place_id=request.place.place_id,
        place_label=request.place.place_label,
        feature_id="markov_transition_probability",
        population=request.place.population,
        current_status="estimated",
        as_of=request.as_of,
        country_code=request.place.country_code,
        local_names=request.place.local_names,
        dominant_languages=request.place.dominant_languages,
    )
    languages = research_languages(target)
    outcome = next(item for item in request.outcomes if item.id == request.outcome_id)
    steps = []
    for language in languages:
        place_name = request.place.local_names.get(language, request.place.place_label)
        outcome_term = request.localized_search_terms.get(
            language,
            outcome.localized_descriptions.get(language, request.outcome_description),
        )
        condition_term = request.localized_conditioning_descriptions.get(
            language,
            request.conditioning_description,
        )
        engines = LOCAL_ENGINES.get(language, {})
        for source_kind in SEARCH_SOURCE_ORDER:
            source_terms = SOURCE_TERMS[source_kind]
            source_term = source_terms.get(language, source_terms["en"])
            engine = engines.get(
                source_kind,
                f"{LANGUAGE_NAMES.get(language, language)} local web and statistics catalogs",
            )
            query = f"{place_name} {outcome_term} {condition_term} {source_term}"
            steps.append(
                SearchStep(
                    sequence=len(steps) + 1,
                    language=language,
                    language_name=LANGUAGE_NAMES.get(language, language),
                    query=query,
                    engine=engine,
                    source_kind=source_kind,
                )
            )
            if language != "en" and not engine.startswith("Bing"):
                steps.append(
                    SearchStep(
                        sequence=len(steps) + 1,
                        language=language,
                        language_name=LANGUAGE_NAMES.get(language, language),
                        query=query,
                        engine=f"Bing local-language fallback after {engine}",
                        source_kind=source_kind,
                    )
                )
    return SearchPlan(languages=languages, steps=tuple(steps))


def _maximum_uncertainty_fallback(request, attempt_id, sources, logs):
    selected_sources = list(sources)
    if selected_sources:
        source = selected_sources[0]
    else:
        source = PipelineEstimateSource(
            id=f"research-trace-{attempt_id[:12]}",
            title=f"Petraterrium research trace for {request.outcome_description}",
            source_kind="expert_commentary",
            retrieved_date=request.as_of.isoformat(),
            language=logs[0].language if logs else "en",
            excerpt=(
                f"The pipeline completed {len(logs)} ordered source searches for "
                f"{request.outcome_description} in {request.place.place_label}."
            ),
            source_version=PROMPT_VERSION,
            license="Project-generated research trace; publisher rights remain upstream",
        )
        selected_sources.append(source)
        logs.append(
            PipelineResearchLog(
                sequence=len(logs) + 1,
                origin="automatic",
                language=source.language,
                engine="Petraterrium research synthesis",
                query_or_source=source.excerpt,
                source_kind="expert_commentary",
                outcome="candidate",
                source_ids=(source.id,),
            )
        )
    probability = 1 / len(request.outcomes)
    reasoning = (
        "The ordered research trace did not yield a defensible numeric rate for "
        f"{request.outcome_description}. The executable draft therefore uses a symmetric "
        f"1/{len(request.outcomes)} prior across the named outgoing outcomes with maximum "
        "uncertainty. It is an estimated review draft, not a measured rate."
    )
    synthesis = _TransitionSynthesisDraft(
        probability=probability,
        ci_low=0,
        ci_high=1,
        reasoning=reasoning,
        assumptions=(
            "The named outgoing outcomes are treated symmetrically until source-backed "
            "transition evidence is promoted.",
            "The full zero-to-one interval preserves maximum uncertainty.",
        ),
        selected_source_ids=(source.id,),
    )
    return synthesis, tuple(selected_sources), logs


def _provider_identity(provider) -> tuple[str, str]:
    try:
        return provider.selected_identity()
    except (AIProviderError, AttributeError, ValueError):
        return "research_pipeline", "maximum_uncertainty_fallback"


def _source_title(excerpt: str, url: str) -> str:
    first_line = next((line.strip() for line in excerpt.splitlines() if line.strip()), "")
    if first_line:
        return first_line[:240]
    return urlparse(url).hostname or url
