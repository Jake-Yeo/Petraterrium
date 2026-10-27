import json

import httpx
import pytest

from petraterrium.atlas import auto_import_provider
from petraterrium.atlas.auto_import_provider import PublicResearchProvider, _result_links
from petraterrium.atlas.auto_import_requirements import canonical_requirement
from petraterrium.atlas.auto_import_research import PlaceFeatureTarget, UserSourceInput


def provider_with_transport(handler) -> PublicResearchProvider:
    provider = PublicResearchProvider()
    provider.client.close()
    provider.client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )
    return provider


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
    }
    target = PlaceFeatureTarget(
        level="city",
        place_id="1",
        place_label="Alpha",
        feature_id="income",
        population=10_000,
        current_status="missing",
    )
    provider = PublicResearchProvider()
    try:
        candidates = provider.inspect_user_source(
            UserSourceInput(kind="text", name="Pasted source", content=json.dumps(payload)),
            target,
            canonical_requirement("income"),
        )
    finally:
        provider.client.close()

    assert len(candidates) == 1
    assert candidates[0].source_kind == "user_text"
    assert candidates[0].url is None

