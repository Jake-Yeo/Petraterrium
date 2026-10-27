from datetime import UTC, date, datetime

import pytest

from petraterrium.ai_provider import AIProviderError
from petraterrium.atlas.auto_import_requirements import canonical_requirement
from petraterrium.atlas.auto_import_research import (
    ConfirmedLabelMapping,
    MappingConfirmation,
    PlaceFeatureTarget,
    SourceCandidate,
    UserSourceInput,
    apply_confirmed_mapping,
    propose_label_mapping,
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


def service(provider, repository=None, writer=None, identities=None):
    identity_values = iter(identities or ["a" * 32])
    return AutoImportResearchService(
        repository or MemoryAttemptRepository(),
        provider,
        writer,
        clock=lambda: datetime(2026, 10, 26, tzinfo=UTC),
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

    assert researched.status == "not_found"
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

    assert researched.status == "not_found"
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


def test_no_credible_result_stays_missing_and_persists_search_log_without_repeating(tmp_path):
    provider = ScriptedProvider()
    repository = JsonAttemptRepository(tmp_path / "attempts")
    first_service = service(provider, repository=repository, identities=["a" * 32])
    attempt = first_service.create_attempt(
        target(local_names={"zh": "上海市"}),
    )
    researched = first_service.research(attempt.attempt_id)

    assert researched.status == "not_found"
    assert researched.mapped_distribution is None
    assert researched.failure_reason.startswith("No credible source")
    assert researched.search_log
    assert {entry.language for entry in researched.search_log} >= {"zh", "en"}
    assert any(entry.engine == "CNKI" for entry in researched.search_log)
    assert any(entry.engine == "Baidu" for entry in researched.search_log)

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
    assert repeated.status == "not_found"
    assert second_provider.searches == []
    assert repeated.search_log == researched.search_log


def test_selected_ai_source_failure_is_the_visible_attempt_error():
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

    assert researched.status == "not_found"
    assert researched.failure_reason == (
        "OpenAI CLI failed with exit code 17: selected source unavailable; "
        "no fallback was attempted."
    )
    assert all(entry.outcome == "error" for entry in researched.search_log)

