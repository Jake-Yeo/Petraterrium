import asyncio
from collections import Counter

from petraterrium.atlas.bulk_auto_import import (
    BulkAutoImportOrchestrator,
    BulkImportOutcome,
    BulkImportSelection,
    BulkImportTarget,
    BulkItemExecutionError,
    BulkPromotionSelection,
    InMemoryBulkImportRepository,
    select_bulk_targets,
)


def target(
    item_id: str,
    level: str,
    impact: float,
    population: int,
    *,
    feature: str = "education",
    country: str = "US",
) -> BulkImportTarget:
    return BulkImportTarget(
        item_id=item_id,
        place_id=item_id.split("/")[0],
        place_name=item_id.split("/")[0].replace(":", " "),
        level=level,
        feature_id=feature,
        population=population,
        missing_impact=impact,
        attributes={"country": country},
    )


def measured(attempt_id: str) -> BulkImportOutcome:
    return BulkImportOutcome(
        attempt_id=attempt_id,
        evidence_status="measured",
        summary="Verified measured distribution",
        source_labels=("National statistics office",),
        promotion_eligible=True,
        predictor_eligible=True,
    )


def estimated(attempt_id: str) -> BulkImportOutcome:
    return BulkImportOutcome(
        attempt_id=attempt_id,
        evidence_status="estimated",
        summary="Transparent estimate from adjacent official tables",
        source_labels=("National statistics office",),
        confidence_interval=(0.1, 0.7),
        estimate_reason="Combined two compatible official marginal tables",
        promotion_eligible=True,
        predictor_eligible=False,
    )


def unresolved(attempt_id: str) -> BulkImportOutcome:
    return BulkImportOutcome(
        attempt_id=attempt_id,
        evidence_status="unresolved",
        summary="No credible distribution found",
        promotion_eligible=False,
        predictor_eligible=False,
    )


def test_selection_orders_hierarchy_and_splits_low_population_cities():
    candidates = [
        target("city:small/education", "city", 900, 999_999),
        target("country:MX/education", "country", 10, 120_000_000, country="MX"),
        target("region:asia/education", "region", 20, 4_000_000_000),
        target("city:large/income", "city", 100, 2_000_000, feature="income"),
        target("region:latam/education", "region", 500, 650_000_000),
        target("country:US/education", "country", 900, 330_000_000),
    ]

    selected = select_bulk_targets(candidates, BulkImportSelection())

    assert [item.item_id for item in selected] == [
        "region:latam/education",
        "region:asia/education",
        "country:US/education",
        "country:MX/education",
        "city:large/income",
    ]
    low_priority = select_bulk_targets(
        candidates,
        BulkImportSelection.below_threshold_cities(),
    )
    assert [item.item_id for item in low_priority] == ["city:small/education"]


def test_filter_and_individual_selectors_compose_and_explicit_city_bypasses_threshold():
    candidates = [
        target("city:a/education", "city", 20, 100_000, country="JP"),
        target("city:b/education", "city", 10, 200_000, country="JP"),
        target("city:c/education", "city", 30, 300_000, country="CN"),
    ]
    selection = BulkImportSelection(
        levels=("city",),
        item_ids=("city:b/education",),
        filters={"country": ("JP",)},
    )

    selected = select_bulk_targets(candidates, selection)

    assert [item.item_id for item in selected] == ["city:b/education"]


def test_bounded_concurrency_continues_after_independent_failure():
    async def scenario():
        repository = InMemoryBulkImportRepository()
        active = 0
        maximum_active = 0
        completed: list[str] = []

        async def executor(request):
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            if request.target.item_id == "country:2/education":
                raise RuntimeError("source unavailable")
            completed.append(request.target.item_id)
            return measured(f"attempt-{request.target.item_id}")

        orchestrator = BulkAutoImportOrchestrator(repository, executor)
        candidates = [
            target(f"country:{index}/education", "country", 100 - index, 1_000_000)
            for index in range(6)
        ]
        draft = await orchestrator.create_batch(candidates, max_concurrency=2)

        review = await orchestrator.run(draft.batch.batch_id)

        assert maximum_active == 2
        assert review.progress.review == 5
        assert review.progress.failed == 1
        assert len(completed) == 5
        assert review.batch.state == "review_ready"
        assert review.progress.promoted == 0

    asyncio.run(scenario())


def test_review_separates_measured_and_estimated_without_automatic_promotion():
    async def scenario():
        repository = InMemoryBulkImportRepository()
        promoted: list[str] = []

        async def executor(request):
            if request.target.feature_id == "income":
                return estimated(f"estimate-{request.target.item_id}")
            return measured(f"measure-{request.target.item_id}")

        async def promoter(request):
            promoted.append(request.target.item_id)
            return f"promotion-{request.target.item_id}"

        orchestrator = BulkAutoImportOrchestrator(repository, executor, promoter)
        candidates = [
            target("region:asia/education", "region", 200, 2_000_000_000),
            target(
                "region:asia/income",
                "region",
                100,
                2_000_000_000,
                feature="income",
            ),
        ]
        draft = await orchestrator.create_batch(candidates)
        review = await orchestrator.run(draft.batch.batch_id)

        assert review.progress.measured == 1
        assert review.progress.estimated == 1
        assert review.progress.promotion_eligible == 2
        assert review.progress.promoted == 0
        assert promoted == []
        statuses = {item.target.feature_id: item.outcome.evidence_status for item in review.items}
        assert statuses == {"education": "measured", "income": "estimated"}

        promoted_review = await orchestrator.promote(
            draft.batch.batch_id,
            BulkPromotionSelection(item_ids=("region:asia/income",)),
        )

        assert promoted == ["region:asia/income"]
        assert promoted_review.progress.promoted == 1
        assert promoted_review.batch.state == "partially_promoted"
        education = next(
            item for item in promoted_review.items if item.target.feature_id == "education"
        )
        assert education.promotion_state == "not_requested"

    asyncio.run(scenario())


def test_resume_retries_only_failures_and_preserves_unpromoted_review_items():
    async def scenario():
        repository = InMemoryBulkImportRepository()
        calls: Counter[str] = Counter()
        previous_attempts: dict[str, list[str | None]] = {}

        async def executor(request):
            item_id = request.target.item_id
            calls[item_id] += 1
            previous_attempts.setdefault(item_id, []).append(request.previous_attempt_id)
            if item_id == "country:retry/education" and calls[item_id] == 1:
                raise BulkItemExecutionError("temporary search failure", "attempt-failed")
            return measured(f"attempt-{item_id}-{calls[item_id]}")

        initial = BulkAutoImportOrchestrator(repository, executor)
        draft = await initial.create_batch(
            [
                target("country:retry/education", "country", 200, 10_000_000),
                target("country:done/education", "country", 100, 9_000_000),
            ]
        )
        first_review = await initial.run(draft.batch.batch_id)
        assert first_review.progress.failed == 1
        assert first_review.progress.review == 1

        resumed = BulkAutoImportOrchestrator(repository, executor)
        final_review = await resumed.resume(draft.batch.batch_id)

        assert final_review.progress.failed == 0
        assert final_review.progress.review == 2
        assert calls == {
            "country:retry/education": 2,
            "country:done/education": 1,
        }
        assert previous_attempts["country:retry/education"] == [None, "attempt-failed"]
        done = next(
            item for item in final_review.items if item.target.item_id == "country:done/education"
        )
        assert done.attempt_count == 1
        assert done.promotion_state == "not_requested"

    asyncio.run(scenario())


def test_unresolved_item_prevents_promotion_complete_state():
    async def scenario():
        repository = InMemoryBulkImportRepository()

        async def executor(request):
            if request.target.item_id.startswith("country:missing"):
                return unresolved(f"attempt-{request.target.item_id}")
            return measured(f"attempt-{request.target.item_id}")

        async def promoter(request):
            return f"promotion-{request.target.item_id}"

        orchestrator = BulkAutoImportOrchestrator(repository, executor, promoter)
        draft = await orchestrator.create_batch(
            [
                target("country:found/education", "country", 200, 10_000_000),
                target("country:missing/education", "country", 100, 9_000_000),
            ]
        )
        review = await orchestrator.run(draft.batch.batch_id)
        promoted = await orchestrator.promote(
            draft.batch.batch_id,
            BulkPromotionSelection(item_ids=("country:found/education",)),
        )

        assert review.progress.unresolved == 1
        assert promoted.progress.promoted == 1
        assert promoted.batch.state == "partially_promoted"

    asyncio.run(scenario())
