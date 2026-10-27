import json
from copy import deepcopy
from pathlib import Path

import pytest

from petraterrium.atlas.choice_evidence import (
    choice_from_counts,
    resolve_choice_evidence,
    unknown_choice,
)
from petraterrium.dsl import ChoiceEvidence, validate_dsl

SMOKE_PATH = Path(__file__).resolve().parents[2] / "shared" / "dsl-schema" / "smoke-spread.json"


def smoke_config():
    return json.loads(SMOKE_PATH.read_text())


def choice(action: str, value: float, identity: str | None = None):
    return {
        "id": identity or f"test-{action}",
        "action_id": action,
        "conditioning_id": "after-scroll",
        "conditioning": {"state": {"signal": "aware"}},
        "definition": f"Choose {action} after consuming a post",
        "value": value,
        "ci_low": max(0, value - 0.05),
        "ci_high": min(1, value + 0.05),
        "source_type": "representative_survey",
        "tier": 3,
        "sample_size": 1000,
        "source_date": "2026-01-15",
        "population": "Adults in Northport",
        "denominator": "Adults who consumed the post",
        "time_unit": "event",
        "source_time_unit": "event",
        "tier_flag": "measured",
        "provenance": {
            "source": "FAKE representative choice fixture",
            "version": "test-v1",
            "status": "present",
            "uncertainty": 0.1,
        },
    }


def messages(payload):
    return " ".join(issue.message for issue in validate_dsl(payload).errors).lower()


def test_news_choice_is_hint_only_and_cannot_be_promoted_to_measured():
    hint = choice("talk", 0.25)
    hint.update(
        {
            "value": None,
            "ci_low": 0,
            "ci_high": 1,
            "source_type": "news",
            "tier": 5,
            "sample_size": None,
            "tier_flag": "hint_only",
            "provenance": {
                **hint["provenance"],
                "source": "Local newspaper account",
                "status": "hint_only",
                "uncertainty": 1,
            },
        }
    )
    parsed = ChoiceEvidence.model_validate(hint)
    assert parsed.tier_flag == "hint_only"
    promoted = {**hint, "tier_flag": "measured", "value": 0.25}
    with pytest.raises(ValueError, match="hint-only"):
        ChoiceEvidence.model_validate(promoted)


def test_time_use_counts_produce_per_friday_probability_with_the_exact_denominator():
    row = choice_from_counts(
        identity="friday-socializing",
        action_id="talk",
        conditioning_id="friday-students",
        numerator=42,
        sample_size=120,
        population="Northport students aged 20",
        denominator="Friday diary days for Northport students aged 20",
        source="FAKE time-use fixture",
        source_date="2026-02-01",
        time_unit="friday",
    )
    assert row.value == pytest.approx(0.35)
    assert row.sample_size == 120
    assert row.denominator == "Friday diary days for Northport students aged 20"
    assert row.source_type == "time_use_diary"
    assert row.tier == 2


def test_average_day_rate_is_rejected_as_friday_without_explicit_adjustment():
    row = choice("talk", 1)
    row.update(
        {
            "conditioning_id": "friday-rate",
            "time_unit": "friday",
            "source_time_unit": "day",
        }
    )
    with pytest.raises(ValueError, match="Friday"):
        ChoiceEvidence.model_validate(row)
    row["explicit_time_adjustment"] = True
    adjusted = ChoiceEvidence.model_validate(row)
    assert adjusted.explicit_time_adjustment is True


def test_choice_probabilities_for_a_conditioning_sum_to_one():
    valid = smoke_config()
    valid["choice_evidence"] = [choice("repost", 0.2), choice("ignore", 0.8)]
    assert validate_dsl(valid).valid
    invalid = deepcopy(valid)
    invalid["choice_evidence"][1]["value"] = 0.7
    invalid["choice_evidence"][1]["ci_low"] = 0.65
    invalid["choice_evidence"][1]["ci_high"] = 0.75
    assert "sum to 1" in messages(invalid)


def test_missing_choice_resolves_to_unknown_with_wide_interval_and_requirement():
    row = unknown_choice("talk", "friday-students", "CAN", "friday")
    assert row.tier_flag == "unknown"
    assert row.value is None
    assert (row.ci_low, row.ci_high) == (0, 1)
    assert row.provenance.status == "missing"
    assert "time-use" in row.missing_requirement.lower()
    with pytest.raises(ValueError, match="remain unknown"):
        ChoiceEvidence.model_validate(
            {
                **row.model_dump(),
                "tier_flag": "measured",
                "value": 0.5,
                "sample_size": 100,
            }
        )


def test_choice_resolution_prefers_country_then_region_without_cross_country_copy():
    country = ChoiceEvidence.model_validate(
        {
            **choice("talk", 1, "country-choice"),
            "conditioning_id": "friday-students",
            "conditioning": {"place": "CAN"},
            "time_unit": "friday",
            "source_time_unit": "friday",
        }
    )
    region = ChoiceEvidence.model_validate(
        {
            **choice("talk", 1, "region-choice"),
            "conditioning_id": "friday-students",
            "conditioning": {"place": "Northern America"},
            "time_unit": "friday",
            "source_time_unit": "friday",
            "tier_flag": "imputed",
            "provenance": {
                **choice("talk", 1)["provenance"],
                "status": "imputed",
                "uncertainty": 0.4,
            },
        }
    )
    resolved = resolve_choice_evidence(
        [region, country],
        "talk",
        "friday-students",
        city="Vancouver",
        country="CAN",
        region="Northern America",
        time_unit="friday",
    )
    assert resolved.evidence.id == "country-choice"
    assert resolved.status == "inherited"
    missing = resolve_choice_evidence(
        [country],
        "talk",
        "friday-students",
        city="Shanghai",
        country="CHN",
        region="China",
        time_unit="friday",
    )
    assert missing.status == "unknown"
    assert missing.evidence.value is None
    assert (missing.evidence.ci_low, missing.evidence.ci_high) == (0, 1)
