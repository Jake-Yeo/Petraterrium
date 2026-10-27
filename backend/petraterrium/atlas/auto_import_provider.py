import csv
import io
import ipaddress
import json
import os
import socket
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
from xml.etree import ElementTree

import httpx
from pydantic import BaseModel, ConfigDict

from ..llm_gateway import structured_call
from .auto_import_requirements import CanonicalFieldRequirement
from .auto_import_research import (
    PlaceFeatureTarget,
    SearchStep,
    SourceCandidate,
    UserSourceInput,
)

MAX_RESEARCH_BYTES = 2_000_000
MAX_PAGE_TEXT = 40_000
MAX_REDIRECTS = 5
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class _CandidateEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[SourceCandidate]


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._anchor_text = []

    def handle_endtag(self, tag: str):
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join(self._anchor_text).strip()))
            self._href = None
            self._anchor_text = []

    def handle_data(self, data: str):
        value = " ".join(data.split())
        if value:
            self.text.append(value)
            if self._href:
                self._anchor_text.append(value)


class PublicResearchProvider:
    def __init__(self, fixture_path: str | Path | None = None):
        self.fixture_path = Path(
            fixture_path or os.getenv("PETRATERRIUM_RESEARCH_FIXTURE", "")
        ) if fixture_path or os.getenv("PETRATERRIUM_RESEARCH_FIXTURE") else None
        self.client = httpx.Client(
            timeout=15,
            follow_redirects=False,
            headers={"User-Agent": "Petraterrium data atlas research/0.2"},
        )

    def inspect_user_source(
        self,
        source: UserSourceInput,
        target: PlaceFeatureTarget,
        requirement: CanonicalFieldRequirement,
    ) -> list[SourceCandidate]:
        if source.kind == "url":
            content, content_type = self._download(source.locator or "")
            return self._extract(
                content,
                source.locator,
                content_type,
                target,
                requirement,
                "user_url",
                source.language,
            )
        return self._extract(
            source.content or "",
            source.locator or source.name,
            "text/plain",
            target,
            requirement,
            "user_upload" if source.kind == "upload" else "user_text",
            source.language,
        )

    def search(
        self,
        step: SearchStep,
        target: PlaceFeatureTarget,
        requirement: CanonicalFieldRequirement,
    ) -> list[SourceCandidate]:
        fixture = self._fixture_candidates(step, target)
        if fixture is not None:
            return fixture
        search_url = _search_url(step.engine, step.query)
        body, content_type = self._download(search_url)
        links = _result_links(body, content_type, search_url)
        candidates = []
        for link in links[:3]:
            try:
                content, page_type = self._download(link)
                candidates.extend(
                    self._extract(
                        content,
                        link,
                        page_type,
                        target,
                        requirement,
                        step.source_kind,
                        step.language,
                    )
                )
            except (httpx.HTTPError, ValueError, OSError):
                continue
        return candidates

    def _fixture_candidates(
        self,
        step: SearchStep,
        target: PlaceFeatureTarget,
    ) -> list[SourceCandidate] | None:
        if self.fixture_path is None:
            return None
        records = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        candidates = []
        matched = False
        for record in records.get("searches", []):
            match = record.get("match", {})
            if any(
                match.get(key) not in (None, value)
                for key, value in (
                    ("place_id", target.place_id),
                    ("feature_id", target.feature_id),
                    ("language", step.language),
                    ("engine", step.engine),
                    ("source_kind", step.source_kind),
                )
            ):
                continue
            matched = True
            candidates.extend(
                SourceCandidate.model_validate(candidate)
                for candidate in record.get("candidates", [])
            )
        return candidates if matched else []

    def _download(self, url: str) -> tuple[str, str]:
        current_url = url
        for redirect_count in range(MAX_REDIRECTS + 1):
            parsed = urlparse(current_url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("Research URLs must use HTTP or HTTPS")
            _require_public_host(parsed.hostname)
            with self.client.stream("GET", current_url) as response:
                if response.status_code in REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Research redirect has no destination")
                    if redirect_count == MAX_REDIRECTS:
                        raise ValueError("Research source exceeds the redirect limit")
                    current_url = urljoin(current_url, location)
                    continue
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_RESEARCH_BYTES:
                        raise ValueError("Research source exceeds the configured size limit")
                content_type = response.headers.get("content-type", "text/plain")
                encoding = response.encoding or "utf-8"
            return content.decode(encoding, errors="replace"), content_type
        raise ValueError("Research source exceeds the redirect limit")

    def _extract(
        self,
        content: str,
        locator: str | None,
        content_type: str,
        target: PlaceFeatureTarget,
        requirement: CanonicalFieldRequirement,
        source_kind: str,
        language: str | None,
    ) -> list[SourceCandidate]:
        structured = _structured_candidates(content, content_type)
        if structured:
            return [
                _attribute_candidate(candidate, locator, source_kind, language)
                for candidate in structured
            ]
        if not os.getenv("OPENAI_API_KEY"):
            return []
        text = _visible_text(content, content_type)[:MAX_PAGE_TEXT]
        if not text:
            return []
        from openai import OpenAI

        payload = json.dumps(
            {
                "target": target.model_dump(mode="json"),
                "requirement": requirement.model_dump(mode="json"),
                "source_url": locator,
                "source_kind": source_kind,
                "expected_language": language,
                "source_text": text,
            },
            ensure_ascii=False,
        )
        result, _ = structured_call(
            OpenAI,
            "openai",
            os.getenv("PETRATERRIUM_RESEARCH_MODEL", "gpt-5-mini"),
            "atlas-source-extraction-v1",
            (
                "Extract only explicitly stated distributions and metadata from the supplied "
                "source. Return no candidate when feature, place, denominator, population or "
                "sample universe, observation date, publication date, time basis, units, and "
                "category values "
                "are not stated. Preserve a "
                "short original-language excerpt and translate it to English when needed. "
                "Classify news and indirect survey figures as hints. Never calculate, infer, "
                "complete, or guess a missing value."
            ),
            payload,
            _CandidateEnvelope,
        )
        return [
            _attribute_candidate(
                candidate.model_dump(mode="json"), locator, source_kind, language
            )
            for candidate in result.candidates
        ]


def _require_public_host(hostname: str) -> None:
    addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
    for address in addresses:
        value = ipaddress.ip_address(address)
        if not value.is_global:
            raise ValueError("Research URLs cannot target local or private network addresses")


def _attribute_candidate(
    value: dict,
    locator: str | None,
    source_kind: str,
    expected_language: str | None,
) -> SourceCandidate:
    candidate = SourceCandidate.model_validate(value)
    supplied_language = value.get("language")
    language = supplied_language or expected_language or candidate.language or "unknown"
    user_source = source_kind in {"user_url", "user_upload", "user_text"}
    if source_kind == "user_url":
        url = locator
    elif user_source:
        url = None
    else:
        url = locator
    return candidate.model_copy(
        update={
            "url": url,
            "source_kind": source_kind,
            "language": language,
        }
    )


def _search_url(engine: str, query: str) -> str:
    encoded = quote_plus(query)
    if engine == "National Bureau of Statistics of China":
        return f"https://www.stats.gov.cn/search/s?qt={encoded}"
    if engine == "CNKI":
        return f"https://kns.cnki.net/kns8s/defaultresult/index?kw={encoded}"
    if engine in {"Baidu", "Baidu News"}:
        return f"https://www.baidu.com/s?wd={encoded}"
    if engine == "e-Stat / Statistics Bureau of Japan":
        return f"https://www.e-stat.go.jp/stat-search?page=1&query={encoded}"
    if engine == "CiNii / J-STAGE":
        return f"https://cir.nii.ac.jp/all?q={encoded}"
    if engine in {"Yahoo Japan", "Yahoo Japan News"}:
        return f"https://search.yahoo.co.jp/search?p={encoded}"
    if engine == "Google Scholar":
        return f"https://scholar.google.com/scholar?q={encoded}"
    return f"https://www.bing.com/search?format=rss&q={encoded}"


def _result_links(content: str, content_type: str, base_url: str) -> list[str]:
    links = []
    if "xml" in content_type or content.lstrip().startswith("<?xml"):
        try:
            root = ElementTree.fromstring(content)
            links.extend(
                element.text.strip()
                for element in root.findall(".//item/link")
                if element.text
            )
        except ElementTree.ParseError:
            pass
    parser = _PageParser()
    parser.feed(content)
    for href, _ in parser.links:
        candidate = urljoin(base_url, href)
        parsed = urlparse(candidate)
        query = parse_qs(parsed.query)
        redirected = query.get("url", query.get("u", []))
        if redirected:
            candidate = unquote(redirected[0])
        if urlparse(candidate).scheme in {"http", "https"}:
            links.append(candidate)
    base_without_fragment = urlparse(base_url)._replace(fragment="").geturl()
    return list(
        dict.fromkeys(
            link
            for link in links
            if urlparse(link)._replace(fragment="").geturl() != base_without_fragment
        )
    )


def _visible_text(content: str, content_type: str) -> str:
    if "html" not in content_type and "<html" not in content[:500].casefold():
        return content
    parser = _PageParser()
    parser.feed(content)
    return "\n".join(parser.text)


def _structured_candidates(content: str, content_type: str) -> list[dict]:
    text = _visible_text(content, content_type).strip()
    for candidate_text in (content.strip(), text):
        if not candidate_text:
            continue
        try:
            parsed = json.loads(candidate_text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "candidates" in parsed:
            return list(parsed["candidates"])
        if isinstance(parsed, dict) and "distribution" in parsed:
            return [parsed]
        if isinstance(parsed, list) and all(isinstance(value, dict) for value in parsed):
            return parsed
    if "csv" in content_type or "," in text.partition("\n")[0]:
        rows = list(csv.DictReader(io.StringIO(text)))
        if rows and {"category", "value"}.issubset(rows[0]):
            metadata = {
                key: value
                for key, value in rows[0].items()
                if key not in {"category", "value"}
            }
            metadata["distribution"] = {
                row["category"]: float(row["value"]) for row in rows
            }
            return [metadata]
    return []
