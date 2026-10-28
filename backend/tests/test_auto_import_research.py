from datetime import UTC, date, datetime, timedelta

import pytest

from petraterrium.ai_provider import AIProviderError
from petraterrium.atlas.auto_import_requirements import canonical_requirement
from petraterrium.atlas.auto_import_research import (
    FALLBACK_COUNTRY_LANGUAGES,
    FEATURE_TERMS,
    LOCAL_ENGINES,
    SEARCH_SOURCE_ORDER,
    SOURCE_TERMS,
    ConfirmedLabelMapping,
    MappingConfirmation,
    PlaceFeatureTarget,
    SourceCandidate,
    UserSourceInput,
    apply_confirmed_mapping,
    build_search_plan,
    derive_estimate,
    pipeline_fallback_candidate,
    propose_label_mapping,
    verify_candidate,
)
from petraterrium.atlas.auto_import_service import (
    AutoImportResearchService,
    JsonAttemptRepository,
    MemoryAttemptRepository,
    PromotionCommand,
)


class ScriptedProvider:
    def __init__(self, search=None, user=None):
        self.search_script = search or (lambda step, target, requirement: [])
        self.user_script = user or (lambda source, target, requirement: [])
        self.searches = []
        self.user_inspections = []

    def search(self, step, target, requirement):
        self.searches.append(step)
        return self.search_script(step, target, requirement)

    def inspect_user_source(self, source, target, requirement):
        self.user_inspections.append(source)
        return self.user_script(source, target, requirement)


class SynthesizingProvider(ScriptedProvider):
    def __init__(self, synthesis):
        super().__init__()
        self.synthesis = synthesis

    def synthesize_estimate(self, target, requirement, search_log, candidates):
        return self.synthesis


class RecordingPromotionWriter:
    def __init__(self):
        self.payloads = []

    def promote(self, payload):
        self.payloads.append(payload)
        return f"promotion-{len(self.payloads)}"


def target(
    feature_id="education",
    label="Shanghai",
    country_code="CN",
    local_names=None,
    scope="shared",
    as_of=date(2026, 10, 26),
):
    return PlaceFeatureTarget(
        level="city",
        place_id=label.casefold(),
        place_label=label,
        feature_id=feature_id,
        population=24_870_895,
        current_status="missing",
        scope=scope,
        as_of=as_of,
        country_code=country_code,
        local_names=local_names or {},
    )


def test_specialization_requirement_is_isced_f_compatible():
    requirement = canonical_requirement("specialization")

    assert requirement.canonical_values == tuple(f"{value:02d}" for value in range(11))
    assert requirement.denominator == "people with a post-secondary field of study"


def test_specialization_and_source_tiers_cover_every_configured_local_language():
    configured_languages = {
        language
        for languages in FALLBACK_COUNTRY_LANGUAGES.values()
        for language in languages
        if language != "en"
    }

    for language in configured_languages:
        assert language in FEATURE_TERMS["specialization"]
        assert FEATURE_TERMS["specialization"][language] != FEATURE_TERMS["specialization"]["en"]
        for source_kind in SEARCH_SOURCE_ORDER:
            assert language in SOURCE_TERMS[source_kind]
            assert SOURCE_TERMS[source_kind][language] != SOURCE_TERMS[source_kind]["en"]


def test_korean_specialization_plan_uses_kosis_and_naver_with_korean_terms():
    korea = PlaceFeatureTarget(
        level="country",
        place_id="KR",
        place_label="South Korea",
        feature_id="specialization",
        population=51_751_065,
        current_status="missing",
        country_code="KR",
        dominant_languages=("ko",),
        local_names={"ko": "대한민국"},
        as_of=date(2026, 10, 26),
    )

    plan = build_search_plan(korea)
    korean_steps = [step for step in plan.steps if step.language == "ko"]

    assert plan.languages[:2] == ("ko", "en")
    assert korean_steps[0].engine == "KOSIS"
    assert korean_steps[0].query.startswith("대한민국 전공 분야 졸업생 분포 ISCED-F")
    assert next(step for step in korean_steps if step.source_kind == "news").engine == "Naver News"
    assert LOCAL_ENGINES["ko"]["representative_survey"] == "Naver"


def test_search_plan_does_not_label_english_fallback_terms_as_local_language():
    unsupported = PlaceFeatureTarget(
        level="country",
        place_id="XX",
        place_label="Example",
        feature_id="specialization",
        population=1_000,
        current_status="missing",
        country_code="XX",
        dominant_languages=("wuu",),
        as_of=date(2026, 10, 26),
    )

    plan = build_search_plan(unsupported)

    assert plan.languages == ("en",)
    assert {step.language for step in plan.steps} == {"en"}


def test_source_backed_deterministic_crosswalk_is_research_synthesis():
    requirement = canonical_requirement("specialization")
    distribution = {f"{code:02d}": 100 / 11 for code in range(11)}
    distribution["00"] += 100 - sum(distribution.values())
    crosswalk = SourceCandidate(
        candidate_id="crosswalk-estimate",
        title="Versioned ISCED-F crosswalk estimate",
        source_kind="expert_commentary",
        feature="specialization",
        place="China",
        place_level="country",
        denominator=requirement.denominator,
        population=4_715_658,
        observation_date=date(2022, 12, 31),
        published_date=date(2024, 1, 10),
        time_unit=requirement.time_unit,
        unit="percent",
        distribution=distribution,
        evidence_kind="hint",
        credible=True,
        credibility_reason="Versioned crosswalk of an official graduate table",
        original_excerpt="Versioned crosswalk of an official graduate table",
        source_version="atlas-specialization-crosswalk-v1",
        license="Project-generated estimate",
        estimate_reasoning="Official source categories were crosswalked to ISCED-F.",
        estimate_assumptions=("The source disciplines map to the broad fields.",),
        estimate_confidence_intervals={label: (0.0, 100.0) for label in distribution},
        estimate_source_ids=("official-moe-source",),
    )

    _, trace, excluded = derive_estimate([crosswalk], requirement)

    assert not excluded
    assert trace.method == "research_synthesis_estimate"
    assert trace.source_ids_used == ("official-moe-source",)


def test_equal_share_pipeline_fallback_remains_maximum_uncertainty_prior():
    requirement = canonical_requirement("specialization")
    country_target = PlaceFeatureTarget(
        level="country",
        place_id="CN",
        place_label="China",
        feature_id="specialization",
        population=1_422_584_933,
        current_status="missing",
        country_code="CN",
        as_of=date(2026, 10, 26),
    )
    fallback = pipeline_fallback_candidate(country_target, requirement, ())

    _, trace, excluded = derive_estimate([fallback], requirement)

    assert not excluded
    assert trace.method == "maximum_uncertainty_prior"


def test_research_log_records_pipeline_synthesis_and_its_candidate():
    distribution = {f"{code:02d}": 100 / 11 for code in range(11)}
    distribution["00"] += 100 - sum(distribution.values())
    synthesis = SourceCandidate(
        candidate_id="pipeline-synthesis",
        title="Pipeline ISCED-F estimate",
        source_kind="expert_commentary",
        feature="specialization",
        place="India",
        place_level="country",
        denominator="people with a post-secondary field of study",
        population=1_000_000,
        observation_date=date(2026, 10, 26),
        published_date=date(2026, 10, 26),
        time_unit="academic year, graduation year, census date, or survey wave",
        unit="percent",
        distribution=distribution,
        evidence_kind="hint",
        credible=True,
        credibility_reason="Pipeline synthesis from logged research",
        original_excerpt="Pipeline synthesis from logged research",
        source_version="atlas-research-synthesis-v1",
        license="Project-generated estimate",
        estimate_reasoning="Pipeline synthesis from logged research",
        estimate_assumptions=("Wide uncertainty applies.",),
        estimate_confidence_intervals={
            label: (0.0, 100.0) for label in distribution
        },
    )
    country_target = PlaceFeatureTarget(
        level="country",
        place_id="IN",
        place_label="India",
        feature_id="specialization",
        population=1_000_000,
        current_status="missing",
        country_code="IN",
        as_of=date(2026, 10, 26),
    )
    auto_import = service(SynthesizingProvider(synthesis))

    researched = auto_import.research(
        auto_import.create_attempt(country_target).attempt_id
    )

    synthesis_log = researched.search_log[-1]
    assert synthesis_log.engine == "Configured AI synthesis"
    assert synthesis_log.outcome == "candidate"
    assert synthesis_log.candidate_ids == ("pipeline-synthesis",)


def test_official_national_percentage_table_does_not_require_redundant_headcount():
    country_target = PlaceFeatureTarget(
        level="country",
        place_id="IN",
        place_label="India",
        feature_id="specialization",
        population=1_428_627_663,
        current_status="missing",
        country_code="IN",
        as_of=date(2026, 10, 26),
    )
    distribution = {f"{code:02d}": 100 / 11 for code in range(11)}
    distribution["00"] += 100 - sum(distribution.values())
    official = SourceCandidate(
        title="Official national distribution",
        source_kind="official_statistics",
        feature="specialization",
        place="India",
        place_level="country",
        denominator="tertiary graduates",
        population=None,
        observation_date=date(2023, 12, 31),
        published_date=date(2026, 2, 9),
        time_unit="graduation year",
        unit="percent",
        distribution=distribution,
        evidence_kind="measured",
        credible=True,
        credibility_reason="Complete national administrative percentage table",
        original_excerpt="National tertiary graduate distribution",
        source_version="2023",
        license="CC BY-SA 4.0",
    )

    verification = verify_candidate(
        official,
        country_target,
        canonical_requirement("specialization"),
    )

    assert verification.accepted
    population = next(check for check in verification.checks if check.name == "population")
    assert population.passed
    assert "defines its denominator" in population.reason


def candidate(
    *,
    title="Official table",
    source_kind="official_statistics",
    feature="education",
    place="Shanghai",
    denominator="adults",
    population=10_000,
    language="en",
    original_excerpt="Distribution table",
    translated_excerpt=None,
    distribution=None,
    evidence_kind="measured",
    credible=True,
    sample_size=None,
):
    canonical_ids = {
        "age_sex",
        "income",
        "education",
        "ideology_economic",
        "ideology_state",
        "ideology_cultural",
        "household_size",
    }
    requirement_id = feature if feature in canonical_ids else "education"
    return SourceCandidate(
        title=title,
        url="https://example.test/table",
        source_kind=source_kind,
        feature=feature,
        place=place,
        place_level="city",
        denominator=denominator,
        population=population,
        observation_date=date(2024, 1, 1),
        published_date=date(2024, 2, 1),
        time_unit=canonical_requirement(requirement_id).time_unit,
        unit="percent",
        distribution=distribution or {"0": 20, "1": 30, "2": 50},
        evidence_kind=evidence_kind,
        credible=credible,
        credibility_reason="Published methodology and sampling frame",
        language=language,
        original_excerpt=original_excerpt,
        translated_excerpt=translated_excerpt,
        sample_size=sample_size,
        source_version="2024",
        license="Open government licence",
    )


def service(provider, repository=None, writer=None, identities=None, clock=None):
    identity_values = iter(identities or ["a" * 32])
    return AutoImportResearchService(
        repository or MemoryAttemptRepository(),
        provider,
        writer,
        clock=clock or (lambda: datetime(2026, 10, 26, tzinfo=UTC)),
        identity=lambda: next(identity_values),
    )


def test_chinese_city_searches_local_sources_first_and_preserves_translation():
    chinese_source = candidate(
        title="上海市统计年鉴教育程度表",
        language="zh",
        original_excerpt="上海市常住人口教育程度构成",
        translated_excerpt="Educational attainment composition of Shanghai residents",
    )

    def results(step, _target, _requirement):
        if step.language == "zh" and step.engine == "National Bureau of Statistics of China":
            return [chinese_source]
        return []

    provider = ScriptedProvider(search=results)
    auto_import = service(provider)
    attempt = auto_import.create_attempt(
        target(local_names={"zh": "上海市"}),
    )
    researched = auto_import.research(attempt.attempt_id)

    assert researched.status == "awaiting_mapping_confirmation"
    assert researched.result_kind == "measured"
    assert researched.languages_searched[0] == "zh"
    assert researched.languages_searched.index("zh") < researched.languages_searched.index("en")
    assert provider.searches[0].query.startswith("上海市")
    assert provider.searches[0].engine == "National Bureau of Statistics of China"
    source = next(
        item
        for item in researched.sources
        if item.candidate_id == chinese_source.candidate_id
    )
    assert source.original_excerpt == "上海市常住人口教育程度构成"
    assert source.translated_excerpt == "Educational attainment composition of Shanghai residents"
    assert [row.proposed_label for row in researched.mapping_preview.rows] == ["0", "1", "2"]


def test_japanese_city_searches_japanese_before_english_and_keeps_bilingual_provenance():
    japanese_source = candidate(
        title="東京都教育統計",
        place="Tokyo",
        language="ja",
        original_excerpt="東京都の教育水準別人口構成",
        translated_excerpt="Tokyo population composition by educational attainment",
    )

    def results(step, _target, _requirement):
        if step.language == "ja" and step.engine.startswith("e-Stat"):
            return [japanese_source]
        return []

    provider = ScriptedProvider(search=results)
    auto_import = service(provider)
    attempt = auto_import.create_attempt(
        target(label="Tokyo", country_code="JP", local_names={"ja": "東京都"})
    )
    researched = auto_import.research(attempt.attempt_id)

    assert researched.status == "awaiting_mapping_confirmation"
    assert researched.languages_searched == ("ja", "en")
    assert provider.searches[0].language == "ja"
    assert provider.searches[0].query.startswith("東京都")
    assert any(step.language == "en" for step in provider.searches)
    assert researched.sources[0].original_excerpt == "東京都の教育水準別人口構成"
    assert researched.sources[0].translated_excerpt.startswith("Tokyo population")


def test_wrong_user_source_is_rejected_for_feature_and_place_and_cannot_promote():
    wrong_source = candidate(
        feature="age and sex",
        place="Suzhou",
        language="zh",
        original_excerpt="苏州市人口年龄结构",
        translated_excerpt="Age structure of the population of Suzhou",
    )
    provider = ScriptedProvider(user=lambda _source, _target, _requirement: [wrong_source])
    writer = RecordingPromotionWriter()
    auto_import = service(provider, writer=writer)
    attempt = auto_import.create_attempt(
        target(),
        [UserSourceInput(kind="url", name="Wrong table", locator="https://example.test")],
    )
    researched = auto_import.research(attempt.attempt_id)

    assert researched.status == "awaiting_mapping_confirmation"
    assert researched.result_kind == "estimated"
    assert len(researched.rejected_sources) == 1
    reasons = researched.rejected_sources[0].verification.reasons
    assert "Source measures a different feature" in reasons
    assert "Source is for a different place or level" in reasons
    assert writer.payloads == []
    with pytest.raises(ValueError, match="verified mapping"):
        auto_import.promotion_payload(attempt.attempt_id)


def test_right_user_source_requires_mapping_confirmation_and_explicit_promotion():
    right_source = candidate(
        distribution={"primary": 25, "lower secondary": 35, "upper secondary": 40}
    )
    provider = ScriptedProvider(user=lambda _source, _target, _requirement: [right_source])
    writer = RecordingPromotionWriter()
    auto_import = service(provider, writer=writer)
    attempt = auto_import.create_attempt(
        target(),
        [UserSourceInput(kind="text", name="Official extract", content="table")],
    )

    researched = auto_import.research(attempt.attempt_id)
    assert researched.status == "awaiting_mapping_confirmation"
    assert writer.payloads == []
    assert [row.proposed_label for row in researched.mapping_preview.rows] == ["1", "2", "3"]

    ready = auto_import.confirm_proposed_mapping(attempt.attempt_id)
    assert ready.status == "ready"
    assert ready.mapped_distribution == {"1": 25.0, "2": 35.0, "3": 40.0}
    assert writer.payloads == []
    with pytest.raises(ValueError, match="explicit confirmation"):
        auto_import.promote(attempt.attempt_id, PromotionCommand(confirmed=False))

    promoted = auto_import.promote(attempt.attempt_id, PromotionCommand(confirmed=True))
    assert promoted.status == "promoted"
    assert promoted.promotion_id == "promotion-1"
    assert writer.payloads[0].evidence_status == "measured"
    assert writer.payloads[0].predictive_evidence_eligible
    assert writer.payloads[0].coverage_percent < 1
    repeated = auto_import.promote(attempt.attempt_id, PromotionCommand(confirmed=True))
    assert repeated == promoted
    assert len(writer.payloads) == 1


def test_source_published_after_availability_cutoff_is_rejected():
    future_source = candidate().model_copy(
        update={"published_date": date(2027, 1, 1)}
    )
    provider = ScriptedProvider(search=lambda *_: [future_source])
    auto_import = service(provider)
    attempt = auto_import.create_attempt(target(as_of=date(2026, 12, 31)))

    researched = auto_import.research(attempt.attempt_id)

    assert researched.status == "awaiting_mapping_confirmation"
    assert researched.result_kind == "estimated"
    verification = researched.rejected_sources[0].verification
    date_check = next(check for check in verification.checks if check.name == "date")
    assert not date_check.passed
    assert "after the availability cutoff" in date_check.reason


def test_missing_time_basis_and_out_of_range_ideology_bins_are_rejected():
    missing_time = candidate().model_copy(update={"time_unit": None})
    ideology = candidate(
        feature="ideology_economic",
        denominator="adults",
        distribution={"-2 to 0": 50, "0 to 1": 50},
    )
    provider = ScriptedProvider(search=lambda *_: [missing_time])
    auto_import = service(provider)
    attempt = auto_import.create_attempt(target())
    researched = auto_import.research(attempt.attempt_id)
    time_check = next(
        check
        for check in researched.rejected_sources[0].verification.checks
        if check.name == "time_basis"
    )
    assert not time_check.passed

    ideology_provider = ScriptedProvider(search=lambda *_: [ideology])
    ideology_import = service(ideology_provider)
    ideology_attempt = ideology_import.create_attempt(target(feature_id="ideology_economic"))
    ideology_result = ideology_import.research(ideology_attempt.attempt_id)
    distribution_check = next(
        check
        for check in ideology_result.rejected_sources[0].verification.checks
        if check.name == "distribution"
    )
    assert not distribution_check.passed
    assert "-1 to +1" in distribution_check.reason


def test_mapping_rejects_two_source_categories_collapsing_into_one_category():
    requirement = canonical_requirement("education")
    distribution = {"primary": 40, "elementary": 60}
    preview = propose_label_mapping(distribution, requirement)
    confirmation = MappingConfirmation(
        confirmed=True,
        mappings=(
            ConfirmedLabelMapping(source_label="primary", target_label="1"),
            ConfirmedLabelMapping(source_label="elementary", target_label="1"),
        ),
    )

    with pytest.raises(ValueError, match="distinct canonical category"):
        apply_confirmed_mapping(distribution, preview, confirmation, requirement)


def test_confirmed_mapping_reconciles_rounding_to_exactly_one_hundred_percent():
    requirement = canonical_requirement("specialization")
    distribution = {f"{code:02d}": 100 / 11 for code in range(11)}
    preview = propose_label_mapping(distribution, requirement)
    confirmation = MappingConfirmation(
        confirmed=True,
        mappings=tuple(
            ConfirmedLabelMapping(
                source_label=row.source_label,
                target_label=row.proposed_label,
            )
            for row in preview.rows
        ),
    )

    mapped = apply_confirmed_mapping(
        distribution,
        preview,
        confirmation,
        requirement,
    )

    assert sum(mapped.values()) == 100


def test_search_history_isolated_by_scope_and_valid_result_cannot_be_destroyed():
    provider = ScriptedProvider(search=lambda _step, _target, _requirement: [candidate()])
    repository = MemoryAttemptRepository()
    auto_import = service(
        provider,
        repository=repository,
        identities=["a" * 32, "b" * 32],
    )
    first = auto_import.create_attempt(target(scope="run-a"))
    researched = auto_import.research(first.attempt_id)
    assert researched.status == "awaiting_mapping_confirmation"
    with pytest.raises(ValueError, match="Review or promote"):
        auto_import.research(first.attempt_id)

    provider.searches.clear()
    second = auto_import.create_attempt(target(scope="run-b"))
    assert second.search_log == ()
    auto_import.research(second.attempt_id)
    assert provider.searches


def test_survey_and_news_hints_produce_only_a_traceable_wide_interval_estimate():
    survey = candidate(
        title="Metro household survey",
        feature="income",
        place="Vancouver",
        denominator="adults",
        distribution={"under 50k": 60, "50k or more": 40},
        source_kind="representative_survey",
        evidence_kind="hint",
        sample_size=800,
    )
    news = candidate(
        title="Local reporting of a second survey",
        feature="income",
        place="Vancouver",
        denominator="adults",
        distribution={"under 50k": 50, "50k or more": 50},
        source_kind="news",
        evidence_kind="hint",
        sample_size=200,
    )

    def results(step, _target, _requirement):
        if step.language == "en" and step.source_kind == "representative_survey":
            return [survey]
        if step.language == "en" and step.source_kind == "news":
            return [news]
        return []

    writer = RecordingPromotionWriter()
    auto_import = service(ScriptedProvider(search=results), writer=writer)
    attempt = auto_import.create_attempt(
        target(feature_id="income", label="Vancouver", country_code="CA")
    )
    researched = auto_import.research(attempt.attempt_id)

    assert researched.result_kind == "estimated"
    assert researched.status == "awaiting_mapping_confirmation"
    assert researched.proposed_distribution == {"under 50k": 58.0, "50k or more": 42.0}
    trace = researched.estimate_trace
    assert trace is not None
    assert len(trace.extractions) == 2
    assert any("sample size" in extraction.weight_basis for extraction in trace.extractions)
    assert any("coefficient fitting" in assumption for assumption in trace.assumptions)
    assert all(
        interval.upper - interval.lower >= 30
        for interval in trace.confidence_intervals.values()
    )
    assert trace.better_data_needed

    auto_import.confirm_proposed_mapping(attempt.attempt_id)
    promoted = auto_import.promote(attempt.attempt_id, PromotionCommand(confirmed=True))
    assert promoted.status == "promoted"
    payload = writer.payloads[0]
    assert payload.evidence_status == "estimated"
    assert not payload.predictive_evidence_eligible
    assert payload.estimate_trace is not None


def test_no_credible_result_becomes_estimated_and_each_attempt_runs_full_research(tmp_path):
    provider = ScriptedProvider()
    repository = JsonAttemptRepository(tmp_path / "attempts")
    first_service = service(provider, repository=repository, identities=["a" * 32])
    attempt = first_service.create_attempt(
        target(local_names={"zh": "上海市"}),
    )
    researched = first_service.research(attempt.attempt_id)

    assert researched.status == "awaiting_mapping_confirmation"
    assert researched.result_kind == "estimated"
    assert researched.proposed_distribution is not None
    assert researched.failure_reason is None
    assert researched.search_log
    assert {entry.language for entry in researched.search_log} >= {"zh", "en"}
    assert any(entry.engine == "CNKI" for entry in researched.search_log)
    assert any(entry.engine == "Baidu" for entry in researched.search_log)
    assert all(entry.searched_at is not None for entry in researched.search_log)

    reloaded_repository = JsonAttemptRepository(tmp_path / "attempts")
    reloaded = reloaded_repository.get(attempt.attempt_id)
    assert reloaded.search_log == researched.search_log
    assert reloaded.languages_searched == researched.languages_searched

    second_provider = ScriptedProvider()
    second_service = service(
        second_provider,
        repository=reloaded_repository,
        identities=["b" * 32],
    )
    follow_up = second_service.create_attempt(target(local_names={"zh": "上海市"}))
    repeated = second_service.research(follow_up.attempt_id)
    assert repeated.status == "awaiting_mapping_confirmation"
    assert repeated.result_kind == "estimated"
    assert second_provider.searches
    assert repeated.search_log == researched.search_log


def test_provider_and_synthesis_exhaustion_produces_timestamped_estimated_draft():
    current = datetime(2026, 10, 26, tzinfo=UTC)

    def advancing_clock():
        nonlocal current
        result = current
        current += timedelta(seconds=1)
        return result

    class ExhaustedProvider(ScriptedProvider):
        def search(self, step, target, requirement):
            self.searches.append(step)
            raise RuntimeError(f"{step.engine} unavailable")

        def synthesize_estimate(self, target, requirement, search_log, candidates):
            raise TimeoutError("Configured synthesis timed out")

    auto_import = service(ExhaustedProvider(), clock=advancing_clock)
    attempt = auto_import.create_attempt(
        target(
            feature_id="specialization",
            label="China",
            country_code="CN",
            local_names={"zh": "中国"},
        )
    )

    researched = auto_import.research(attempt.attempt_id)

    assert researched.status == "awaiting_mapping_confirmation"
    assert researched.result_kind == "estimated"
    assert researched.failure_reason is None
    assert researched.estimate_trace is not None
    assert researched.estimate_trace.method == "maximum_uncertainty_prior"
    assert all(
        interval.lower == 0 and interval.upper == 100
        for interval in researched.estimate_trace.confidence_intervals.values()
    )
    assert researched.sources[-1].place == "China"
    assert researched.sources[-1].estimate_reasoning
    assert researched.search_log[-1].engine == "Petraterrium deterministic estimator"
    assert researched.search_log[-1].outcome == "candidate"
    timestamps = [entry.searched_at for entry in researched.search_log]
    assert all(timestamp is not None for timestamp in timestamps)
    assert timestamps == sorted(timestamps)


def test_country_language_plan_puts_configured_local_languages_before_english():
    for country_code, expected_language in (("IN", "hi"), ("RU", "ru"), ("NG", "ha")):
        target = PlaceFeatureTarget(
            level="country",
            place_id=country_code,
            place_label=country_code,
            feature_id="specialization",
            population=1_000,
            current_status="missing",
            scope="shared",
            as_of=date(2026, 10, 27),
            country_code=country_code,
            dominant_languages=("en", expected_language),
        )

        plan = build_search_plan(target)

        assert plan.languages[0] == expected_language
        assert plan.languages[1] == "en"

def test_selected_ai_source_failure_is_visible_before_estimated_fallback():
    class FailingProvider(ScriptedProvider):
        def search(self, step, target, requirement):
            self.searches.append(step)
            raise AIProviderError(
                "openai_cli_failed",
                "OpenAI CLI failed with exit code 17: selected source unavailable; "
                "no fallback was attempted.",
            )

    auto_import = service(FailingProvider())
    attempt = auto_import.create_attempt(target())

    researched = auto_import.research(attempt.attempt_id)

    assert researched.status == "awaiting_mapping_confirmation"
    assert researched.result_kind == "estimated"
    assert researched.failure_reason is None
    assert researched.proposed_distribution is not None
    assert sum(researched.proposed_distribution.values()) == pytest.approx(100)
    assert all(entry.outcome == "error" for entry in researched.search_log[:-1])
    assert researched.search_log[-1].outcome == "candidate"
    assert researched.search_log[-1].engine == "Petraterrium deterministic estimator"
    assert any(
        "OpenAI CLI failed with exit code 17" in reason
        for entry in researched.search_log
        for reason in entry.rejection_reasons
    )


def test_specialization_pipeline_returns_a_draft_after_full_local_first_research():
    provider = ScriptedProvider()
    auto_import = service(provider)
    attempt = auto_import.create_attempt(
        target(
            feature_id="specialization",
            label="China",
            country_code="CN",
            local_names={"zh": "中国"},
        )
    )

    researched = auto_import.research(attempt.attempt_id)

    assert researched.status == "awaiting_mapping_confirmation"
    assert researched.result_kind == "estimated"
    assert researched.proposed_distribution is not None
    assert set(researched.proposed_distribution) == {
        "00",
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
        "08",
        "09",
        "10",
    }
    assert sum(researched.proposed_distribution.values()) == pytest.approx(100)
    assert researched.estimate_trace is not None
    assert researched.estimate_trace.assumptions
    assert researched.languages_searched[0] == "zh"
    assert provider.searches[0].language == "zh"
    assert provider.searches[0].engine == "National Bureau of Statistics of China"
    assert any(step.engine == "Baidu" for step in provider.searches)
    assert any(step.engine == "CNKI" for step in provider.searches)
    assert any(step.language == "en" for step in provider.searches)

