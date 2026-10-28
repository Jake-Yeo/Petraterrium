import json

import httpx
import pytest

from petraterrium.ai_provider import AIGeneration, AIProviderError, _strict_output_schema
from petraterrium.ai_settings import AISourceProvenance
from petraterrium.atlas import auto_import_provider
from petraterrium.atlas.auto_import_provider import (
    PublicResearchProvider,
    _result_links,
    _search_url,
)
from petraterrium.atlas.auto_import_requirements import canonical_requirement
from petraterrium.atlas.auto_import_research import (
    PlaceFeatureTarget,
    SourceCandidate,
    UserSourceInput,
)


def provider_with_transport(handler) -> PublicResearchProvider:
    provider = PublicResearchProvider()
    provider.client.close()
    provider.client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )
    return provider


def income_target() -> PlaceFeatureTarget:
    return PlaceFeatureTarget(
        level="city",
        place_id="1",
        place_label="Alpha",
        feature_id="income",
        population=10_000,
        current_status="missing",
    )


def specialization_target(label="India", code="IN") -> PlaceFeatureTarget:
    return PlaceFeatureTarget(
        level="country",
        place_id=code,
        place_label=label,
        feature_id="specialization",
        population=1_000_000,
        current_status="missing",
        country_code=code,
    )


@pytest.mark.parametrize(
    ("engine", "expected"),
    (
        ("KOSIS", "https://kosis.kr/search/search.do?query=field+of+study"),
        ("Naver", "https://search.naver.com/search.naver?query=field+of+study"),
        (
            "Naver News",
            "https://search.naver.com/search.naver?where=news&query=field+of+study",
        ),
    ),
)
def test_korean_search_engines_route_to_local_services(engine, expected):
    assert _search_url(engine, "field of study") == expected


def extracted_candidate() -> dict:
    return {
        "title": "Alpha household income study",
        "url": "https://research.example/income",
        "source_kind": "research_article",
        "feature": "income",
        "place": "Alpha",
        "place_level": "city",
        "denominator": "households",
        "population": 1_000,
        "observation_date": "2024-01-01",
        "published_date": "2024-06-01",
        "time_unit": "annual",
        "unit": "percent",
        "distribution": {"lower": 60, "upper": 40},
        "evidence_kind": "measured",
        "credible": True,
        "credibility_reason": "Peer reviewed household study",
        "language": "en",
        "original_excerpt": "Sixty percent lower and forty percent upper",
        "sample_size": 1_000,
        "source_version": "2024",
        "license": "CC BY 4.0",
    }


def test_download_validates_every_redirect_destination_before_request(monkeypatch):
    validated_hosts = []
    requested_urls = []

    def validate(hostname):
        validated_hosts.append(hostname)
        if hostname == "127.0.0.1":
            raise ValueError("Research URLs cannot target local or private network addresses")

    def handler(request):
        requested_urls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    monkeypatch.setattr(auto_import_provider, "_require_public_host", validate)
    provider = provider_with_transport(handler)
    try:
        with pytest.raises(ValueError, match="local or private"):
            provider._download("https://public.example/source")
    finally:
        provider.client.close()

    assert validated_hosts == ["public.example", "127.0.0.1"]
    assert requested_urls == ["https://public.example/source"]


def test_download_follows_bounded_public_redirects_and_validates_each_request(monkeypatch):
    validated_hosts = []

    def handler(request):
        if request.url.host == "first.example":
            return httpx.Response(301, headers={"location": "https://second.example/next"})
        if request.url.path == "/next":
            return httpx.Response(307, headers={"location": "/final"})
        return httpx.Response(200, text="distribution", headers={"content-type": "text/plain"})

    monkeypatch.setattr(
        auto_import_provider,
        "_require_public_host",
        lambda hostname: validated_hosts.append(hostname),
    )
    provider = provider_with_transport(handler)
    try:
        content, content_type = provider._download("https://first.example/start")
    finally:
        provider.client.close()

    assert content == "distribution"
    assert content_type == "text/plain"
    assert validated_hosts == ["first.example", "second.example", "second.example"]


def test_download_extracts_pdf_text_inside_the_research_provider(monkeypatch):
    class Page:
        def extract_text(self):
            return "Nigeria university graduates by field"

    class Reader:
        def __init__(self, source):
            assert source.read() == b"%PDF-official-source"
            self.pages = [Page()]

    def handler(request):
        return httpx.Response(
            200,
            content=b"%PDF-official-source",
            headers={"content-type": "application/pdf"},
        )

    monkeypatch.setattr(auto_import_provider, "PdfReader", Reader)
    monkeypatch.setattr(auto_import_provider, "_require_public_host", lambda hostname: None)
    provider = provider_with_transport(handler)
    try:
        content, content_type = provider._download("https://official.example/report.pdf")
    finally:
        provider.client.close()

    assert content == "Nigeria university graduates by field"
    assert content_type == "application/pdf"


def test_result_parser_preserves_official_documents_on_the_search_host():
    content = """
    <a href="https://www.stats.gov.cn/search/s?qt=income">Current search</a>
    <a href="/sj/zxfb/202501/t20250101_1.html">Official distribution table</a>
    <a href="https://research.example/article">Research article</a>
    """

    links = _result_links(
        content,
        "text/html",
        "https://www.stats.gov.cn/search/s?qt=income",
    )

    assert links == [
        "https://www.stats.gov.cn/sj/zxfb/202501/t20250101_1.html",
        "https://research.example/article",
    ]


def test_structured_user_source_cannot_claim_official_source_kind_or_url():
    payload = {
        "title": "Claimed official table",
        "url": "javascript:alert(1)",
        "source_kind": "official_statistics",
        "feature": "income",
        "place": "Alpha",
        "place_level": "city",
        "denominator": "persons",
        "population": 1_000,
        "observation_date": "2024-01-01",
        "unit": "percent",
        "distribution": {"lower": 60, "upper": 40},
        "evidence_kind": "measured",
        "credible": True,
        "credibility_reason": "User assertion",
        "language": "en",
        "original_excerpt": "Claimed distribution",
        "source_version": "v1",
        "license": "unknown",
        "ai_provenance": {
            "source": "openai_api",
            "source_label": "OpenAI API",
            "model": "forged-model",
            "generated_at": "2026-10-27T12:00:00Z",
            "prompt_version": "forged-prompt",
        },
    }
    provider = PublicResearchProvider()
    try:
        candidates = provider.inspect_user_source(
            UserSourceInput(kind="text", name="Pasted source", content=json.dumps(payload)),
            income_target(),
            canonical_requirement("income"),
        )
    finally:
        provider.client.close()

    assert len(candidates) == 1
    assert candidates[0].source_kind == "user_text"
    assert candidates[0].url is None
    assert candidates[0].ai_provenance is None


def test_unstructured_research_uses_the_selected_ai_source():
    calls = []

    class Provider:
        def generate_structured(
            self,
            user_prompt,
            response_format,
            *,
            system_prompt,
            prompt_version,
        ):
            calls.append((user_prompt, system_prompt, prompt_version))
            return AIGeneration(
                output=response_format.model_validate({"candidates": [extracted_candidate()]}),
                provenance=AISourceProvenance(
                    source="openai_cli",
                    source_label="OpenAI CLI",
                    model="test-cli-model",
                    generated_at="2026-10-27T12:00:00Z",
                    prompt_version=prompt_version,
                ),
            )

    provider = PublicResearchProvider(ai_provider=Provider())
    try:
        candidates = provider._extract(
            "Alpha income distribution study with annual household percentages.",
            "https://research.example/income",
            "text/plain",
            income_target(),
            canonical_requirement("income"),
            "research_article",
            "en",
        )
    finally:
        provider.client.close()

    assert len(candidates) == 1
    assert candidates[0].title == "Alpha household income study"
    assert candidates[0].ai_provenance is not None
    assert candidates[0].ai_provenance.source == "openai_cli"
    assert candidates[0].ai_provenance.model == "test-cli-model"
    assert candidates[0].ai_provenance.prompt_version == "atlas-source-extraction-v1"
    assert calls[0][2] == "atlas-source-extraction-v1"


def test_unstructured_research_never_uses_an_environment_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    provider = PublicResearchProvider()
    try:
        with pytest.raises(AIProviderError, match="no fallback was attempted"):
            provider._extract(
                "Alpha income distribution study with annual household percentages.",
                "https://research.example/income",
                "text/plain",
                income_target(),
                canonical_requirement("income"),
                "research_article",
                "en",
            )
    finally:
        provider.client.close()


def test_uis_adapter_maps_complete_isced_f_distribution_without_ai():
    records = [
        {
            "indicatorId": indicator,
            "geoUnit": "IND",
            "year": 2023,
            "value": 100 / 11,
            "footnotes": [{"value": "Country submission to UNESCO UIS"}],
        }
        for indicator in auto_import_provider.UIS_FIELD_CODES
    ]
    payload = json.dumps(
        {
            "records": records,
            "indicatorMetadata": [
                {
                    "lastDataUpdate": "02/09/2026",
                    "lastDataUpdateDescription": "February 2026 Data Release",
                }
            ],
        }
    )
    provider = PublicResearchProvider()
    try:
        candidates = provider._extract(
            payload,
            "https://api.uis.unesco.org/api/public/data/indicators",
            "application/json",
            specialization_target(),
            canonical_requirement("specialization"),
            "user_url",
            "en",
        )
    finally:
        provider.client.close()

    assert len(candidates) == 1
    assert set(candidates[0].distribution) == {f"{code:02d}" for code in range(11)}
    assert sum(candidates[0].distribution.values()) == 100
    assert candidates[0].population is None
    assert candidates[0].source_kind == "official_statistics"
    assert candidates[0].license == "CC BY-SA 4.0"


def test_oecd_adapter_normalizes_official_count_rows_and_preserves_population():
    header = "EDUCATION_FIELD,TIME_PERIOD,UNIT_MEASURE,OBS_VALUE\n"
    rows = "".join(
        f"F{code:02d},2023,PS,{code + 1}\n" for code in range(11)
    )
    provider = PublicResearchProvider()
    try:
        candidates = provider._extract(
            header + rows,
            "https://sdmx.oecd.org/public/rest/data/example",
            "text/csv",
            specialization_target("Brazil", "BR"),
            canonical_requirement("specialization"),
            "user_url",
            "en",
        )
    finally:
        provider.client.close()

    assert len(candidates) == 1
    assert sum(candidates[0].distribution.values()) == 100
    assert candidates[0].population == 66
    assert candidates[0].sample_size == 66
    assert candidates[0].source_kind == "official_statistics"
    assert candidates[0].license == "OECD Terms and Conditions"


def test_china_moe_adapter_extracts_graduate_counts_as_crosswalk_input():
    disciplines = [
        ("哲学 Philosophy", 1),
        ("经济学 Economics", 2),
        ("法学 Law", 3),
        ("教育学 Education", 4),
        ("文学 Literature", 5),
        ("历史学 History", 6),
        ("理学 Science", 7),
        ("工学 Engineering", 8),
        ("农学 Agriculture", 9),
        ("医学 Medicine", 10),
        ("管理学 Management", 11),
        ("艺术学 Art", 12),
    ]
    rows = "".join(
        f"<tr><td>{label}</td><td>{graduates}</td><td>0</td><td>0</td><td>0</td></tr>"
        for label, graduates in disciplines
    )
    content = (
        "<table><tr><td>单位：人</td></tr>"
        "<tr><td>毕业生数 Graduates</td><td>招生数 Entrants</td>"
        "<td>在校生数 Enrolment</td><td>预计毕业生数</td></tr>"
        "<tr><td>总计 Total</td><td>78</td><td>0</td><td>0</td><td>0</td></tr>"
        f"{rows}</table>"
    )
    provider = PublicResearchProvider()
    try:
        candidates = provider._extract(
            content,
            "https://hudong.moe.gov.cn/jyb_sjzl/moe_560/2022/quanguo/"
            "202401/t20240110_1099511.html",
            "text/html",
            specialization_target("China", "CN"),
            canonical_requirement("specialization"),
            "user_url",
            "zh",
        )
    finally:
        provider.client.close()

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source_kind == "official_statistics"
    assert candidate.evidence_kind == "hint"
    assert candidate.observation_date.isoformat() == "2022-12-31"
    assert candidate.published_date.isoformat() == "2024-01-10"
    assert candidate.denominator == "tertiary graduates"
    assert candidate.language == "zh"
    assert len(candidate.distribution) == 12
    assert sum(candidate.distribution.values()) == 100


def test_nigeria_nuc_pdf_table_is_extracted_before_generic_text_truncation():
    rows = [
        ("Administration and Management", 14),
        ("Sciences", 13),
        ("Social Sciences", 12),
        ("Education", 11),
        ("Engineering and Technology", 10),
        ("Arts", 9),
        ("Agriculture", 8),
        ("Basic Medical and Health Sciences", 7),
        ("Computing", 6),
        ("Law", 5),
        ("Environmental Sciences", 4),
        ("Medicine", 3),
        ("Pharmacy", 2),
        ("Veterinary Medicine", 1),
    ]
    table = "\n".join(f"{label} 0 0 {count}" for label, count in rows)
    content = (
        "Earlier pages\n"
        "Table 3.5.5: Total Enrolment by Discipline by Gender and Ownership "
        "Ordered by Grand Total\n"
        f"{table}\nGrand Total 0 0 105\n3.6 Undergraduate New Entrants"
    )
    provider = PublicResearchProvider()
    try:
        candidates = provider._extract(
            content,
            "https://nuc.edu.ng/wp-content/uploads/2021/07/"
            "2019-NIGERIAN-UNIVERSITY-SYSTEM-STATISTICAL-DIGEST.pdf",
            "application/pdf",
            specialization_target("Nigeria", "NG"),
            canonical_requirement("specialization"),
            "user_url",
            "en",
        )
    finally:
        provider.client.close()

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source_kind == "official_statistics"
    assert candidate.evidence_kind == "hint"
    assert candidate.denominator == "tertiary students"
    assert candidate.sample_size == 105
    assert len(candidate.distribution) == 14
    assert sum(candidate.distribution.values()) == 100


def test_pakistan_hec_pdf_chart_is_extracted_as_canonical_isced_distribution():
    content = """
    The graph represents the distribution of male and female students across different
    disciplines. It provides a visual depiction of how males and females are enrolled in
    various academic fields.
    202,030 96,623 9,156 31,741 74,701 222,159 129,842 131,332 375,078
    121,807 11,116 362
    97,773 82,236 38,556 134,716 201,958 192,829 274,603 117,138 325,318
    149,891 14,233 711
    0 50,000 100,000 150,000 200,000 250,000 300,000 350,000 400,000
    Gender-wise Enrollment in Major Disciplines (2020-21)
    Female Male
    """
    provider = PublicResearchProvider()
    try:
        candidates = provider._extract(
            content,
            "https://www.hec.gov.pk/english/services/universities/HEDP/"
            "PublishingImages/Pages/Component-4/Annual-Report.pdf",
            "application/pdf",
            specialization_target("Pakistan", "PK"),
            canonical_requirement("specialization"),
            "user_url",
            "en",
        )
    finally:
        provider.client.close()

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source_kind == "official_statistics"
    assert candidate.evidence_kind == "measured"
    assert candidate.denominator == "tertiary students"
    assert candidate.sample_size == 3_034_836
    assert set(candidate.distribution) == {f"{code:02d}" for code in range(11)}
    assert sum(candidate.distribution.values()) == 100


def test_specialization_synthesis_schema_and_source_backed_fallback_are_canonical():
    class FailingProvider:
        def generate_structured(self, *args, **kwargs):
            raise AIProviderError("cli_failed", "Configured AI synthesis failed")

    raw = SourceCandidate(
        candidate_id="moe-source",
        title="China graduates by discipline",
        url="https://hudong.moe.gov.cn/table",
        source_kind="official_statistics",
        feature="specialization",
        place="China",
        place_level="country",
        denominator="tertiary graduates",
        population=100,
        observation_date="2022-12-31",
        published_date="2024-01-10",
        time_unit="graduation year",
        unit="percent",
        distribution={
            "Philosophy": 5,
            "Economics": 10,
            "Law": 10,
            "Education": 10,
            "Literature": 5,
            "History": 5,
            "Science": 10,
            "Engineering": 20,
            "Agriculture": 5,
            "Medicine": 10,
            "Management": 5,
            "Art": 5,
        },
        evidence_kind="hint",
        credible=True,
        credibility_reason="Official table needing an ISCED-F crosswalk",
        language="zh",
        original_excerpt="教育部学科毕业生",
        translated_excerpt="Ministry discipline graduates",
        source_version="2022",
        license="not stated",
    )
    provider = PublicResearchProvider(ai_provider=FailingProvider())
    try:
        result = provider.synthesize_estimate(
            specialization_target("China", "CN"),
            canonical_requirement("specialization"),
            (),
            (raw,),
        )
    finally:
        provider.client.close()

    assert "source_ids_used" in auto_import_provider._EstimateDraft.model_json_schema()[
        "required"
    ]
    assert set(result.distribution) == {f"{code:02d}" for code in range(11)}
    assert sum(result.distribution.values()) == 100
    assert result.estimate_source_ids == ("moe-source",)
    assert "Configured AI synthesis failed" in result.estimate_reasoning
    assert result.translated_excerpt == result.estimate_reasoning
    assert all(
        upper - lower >= 30
        for lower, upper in result.estimate_confidence_intervals.values()
    )


def test_estimate_synthesis_schema_uses_strict_category_records():
    schema = _strict_output_schema(
        auto_import_provider._EstimateDraft.model_json_schema()
    )

    assert schema["properties"]["categories"]["type"] == "array"
    pending = [schema]
    while pending:
        node = pending.pop()
        if isinstance(node, list):
            pending.extend(node)
            continue
        if not isinstance(node, dict):
            continue
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
        pending.extend(node.values())


def test_estimate_synthesis_converts_category_records_to_candidate_maps():
    class Provider:
        def generate_structured(
            self,
            user_prompt,
            response_format,
            *,
            system_prompt,
            prompt_version,
        ):
            assert response_format is auto_import_provider._EstimateDraft
            assert prompt_version == "atlas-research-synthesis-v1"
            return AIGeneration(
                output=response_format.model_validate(
                    {
                        "categories": [
                            {
                                "category_id": "lower",
                                "percentage": 60,
                                "confidence_lower": 30,
                                "confidence_upper": 90,
                            },
                            {
                                "category_id": "upper",
                                "percentage": 40,
                                "confidence_lower": 10,
                                "confidence_upper": 70,
                            },
                        ],
                        "reasoning": "The source supports a wide-uncertainty estimate.",
                        "assumptions": ["The source population represents Alpha."],
                        "source_ids_used": ["source-1", "unrecognized-source"],
                    }
                ),
                provenance=AISourceProvenance(
                    source="openai_cli",
                    source_label="OpenAI CLI",
                    model="test-cli-model",
                    generated_at="2026-10-27T12:00:00Z",
                    prompt_version=prompt_version,
                ),
            )

    source = SourceCandidate.model_validate(
        {**extracted_candidate(), "candidate_id": "source-1"}
    )
    provider = PublicResearchProvider(ai_provider=Provider())
    try:
        result = provider.synthesize_estimate(
            income_target(),
            canonical_requirement("income"),
            (),
            (source,),
        )
    finally:
        provider.client.close()

    assert result.distribution == {"lower": 60, "upper": 40}
    assert result.estimate_confidence_intervals == {
        "lower": (30, 90),
        "upper": (10, 70),
    }
    assert result.estimate_source_ids == ("source-1",)
    assert result.ai_provenance is not None
    assert result.ai_provenance.prompt_version == "atlas-research-synthesis-v1"
