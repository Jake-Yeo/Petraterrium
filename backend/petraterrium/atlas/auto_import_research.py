import hashlib
import math
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..ai_settings import AISourceProvenance
from .auto_import_requirements import CanonicalFieldRequirement, canonical_requirement

PlaceLevel = Literal["region", "country", "city"]
CurrentFieldStatus = Literal["missing", "inherited", "imputed", "estimated"]
AttemptStatus = Literal[
    "draft",
    "researching",
    "awaiting_mapping_confirmation",
    "ready",
    "not_found",
    "rejected",
    "promoted",
]
EvidenceKind = Literal["measured", "estimated"]
SourceKind = Literal[
    "official_statistics",
    "census",
    "representative_survey",
    "research_article",
    "government_report",
    "university_report",
    "news",
    "online_opinion",
    "expert_commentary",
    "user_url",
    "user_upload",
    "user_text",
]
SearchOutcome = Literal["no_result", "candidate", "rejected", "error"]
MappingConfidence = Literal["exact", "alias", "unknown"]


class ResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ContextPlace(ResearchModel):
    level: Literal["region", "country"]
    place_id: str = Field(min_length=1)
    place_label: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()


class PlaceFeatureTarget(ResearchModel):
    level: PlaceLevel
    place_id: str = Field(min_length=1)
    place_label: str = Field(min_length=1)
    feature_id: str = Field(min_length=1)
    population: int = Field(ge=0)
    current_status: CurrentFieldStatus
    scope: str = Field(default="shared", min_length=1)
    as_of: date = Field(default_factory=date.today)
    country_code: str | None = None
    local_names: dict[str, str] = Field(default_factory=dict)
    dominant_languages: tuple[str, ...] = ()
    place_aliases: tuple[str, ...] = ()
    context_places: tuple[ContextPlace, ...] = ()


class UserSourceInput(ResearchModel):
    kind: Literal["url", "upload", "text"]
    name: str = Field(min_length=1)
    locator: str | None = None
    content: str | None = None
    language: str | None = None

    @model_validator(mode="after")
    def has_source(self):
        if self.kind == "url" and not self.locator:
            raise ValueError("A URL source needs a locator")
        if self.kind in {"upload", "text"} and not self.content:
            raise ValueError(f"A {self.kind} source needs content")
        return self


class SearchStep(ResearchModel):
    sequence: int = Field(ge=1)
    language: str = Field(min_length=2)
    language_name: str = Field(min_length=1)
    query: str = Field(min_length=1)
    engine: str = Field(min_length=1)
    source_kind: SourceKind


class SearchPlan(ResearchModel):
    languages: tuple[str, ...]
    steps: tuple[SearchStep, ...]


class SourceCandidate(ResearchModel):
    candidate_id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = Field(min_length=1)
    url: str | None = None
    source_kind: SourceKind
    feature: str = Field(min_length=1)
    place: str = Field(min_length=1)
    place_level: PlaceLevel
    denominator: str | None = None
    population: int | None = Field(default=None, ge=0)
    observation_date: date | None = None
    published_date: date | None = None
    time_unit: str | None = None
    unit: str | None = None
    distribution: dict[str, float] = Field(default_factory=dict)
    evidence_kind: Literal["measured", "hint"]
    credible: bool
    credibility_reason: str
    language: str = "en"
    original_excerpt: str = Field(min_length=1)
    translated_excerpt: str | None = None
    sample_size: int | None = Field(default=None, ge=1)
    source_version: str = "unknown"
    license: str = "unknown"
    estimate_reasoning: str | None = None
    estimate_assumptions: tuple[str, ...] = ()
    estimate_confidence_intervals: dict[str, tuple[float, float]] = Field(default_factory=dict)
    estimate_source_ids: tuple[str, ...] = ()
    ai_provenance: AISourceProvenance | None = None

    @model_validator(mode="after")
    def validates_estimate_intervals(self):
        for label, (lower, upper) in self.estimate_confidence_intervals.items():
            if label not in self.distribution:
                raise ValueError(f"Estimate interval has no distribution value: {label}")
            if lower < 0 or upper > 100 or upper < lower:
                raise ValueError(f"Estimate interval is outside 0–100: {label}")
            if self.evidence_kind == "hint" and upper - lower < 30:
                raise ValueError(f"Estimated interval must span at least 30 points: {label}")
        return self


class VerificationCheck(ResearchModel):
    name: Literal[
        "credibility",
        "feature",
        "place",
        "denominator",
        "population",
        "date",
        "time_basis",
        "unit",
        "distribution",
        "translation",
        "evidence_kind",
    ]
    passed: bool
    expected: str
    actual: str
    reason: str


class SourceVerification(ResearchModel):
    candidate_id: str
    accepted: bool
    direct_measurement: bool
    checks: tuple[VerificationCheck, ...]
    reasons: tuple[str, ...]


class RejectedSource(ResearchModel):
    candidate: SourceCandidate
    verification: SourceVerification


class ResearchLogEntry(ResearchModel):
    sequence: int = Field(ge=1)
    origin: Literal["user", "automatic"]
    language: str
    engine: str
    query_or_source: str
    source_kind: SourceKind
    outcome: SearchOutcome
    candidate_ids: tuple[str, ...] = ()
    rejection_reasons: tuple[str, ...] = ()
    searched_at: datetime | None = None


class LabelMapping(ResearchModel):
    source_label: str
    proposed_label: str | None = None
    confidence: MappingConfidence
    reason: str


class MappingPreview(ResearchModel):
    version: str
    rows: tuple[LabelMapping, ...]
    needs_confirmation: Literal[True] = True


class ConfirmedLabelMapping(ResearchModel):
    source_label: str
    target_label: str | None


class MappingConfirmation(ResearchModel):
    confirmed: bool
    mappings: tuple[ConfirmedLabelMapping, ...]
    distribution: dict[str, float] | None = None


class SourceExtraction(ResearchModel):
    candidate_id: str
    title: str
    extracted_distribution: dict[str, float]
    weight: float = Field(gt=0)
    weight_basis: str


class PercentageInterval(ResearchModel):
    lower: float = Field(ge=0, le=100)
    upper: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def ordered(self):
        if self.upper < self.lower:
            raise ValueError("Uncertainty interval upper bound must be at least its lower bound")
        return self


class EstimateTrace(ResearchModel):
    method: Literal[
        "weighted_compositional_estimate",
        "research_synthesis_estimate",
        "maximum_uncertainty_prior",
    ] = "weighted_compositional_estimate"
    extractions: tuple[SourceExtraction, ...]
    calculation: tuple[str, ...]
    assumptions: tuple[str, ...]
    confidence_intervals: dict[str, PercentageInterval]
    source_ids_used: tuple[str, ...] = ()
    better_data_needed: str


class AutoImportAttempt(ResearchModel):
    attempt_id: str
    target: PlaceFeatureTarget
    requirement: CanonicalFieldRequirement
    status: AttemptStatus
    result_kind: EvidenceKind | None = None
    user_sources: tuple[UserSourceInput, ...] = ()
    search_plan: SearchPlan
    search_log: tuple[ResearchLogEntry, ...] = ()
    sources: tuple[SourceCandidate, ...] = ()
    rejected_sources: tuple[RejectedSource, ...] = ()
    selected_source_ids: tuple[str, ...] = ()
    verifications: tuple[SourceVerification, ...] = ()
    mapping_preview: MappingPreview | None = None
    mapping_confirmed: bool = False
    proposed_distribution: dict[str, float] | None = None
    mapped_distribution: dict[str, float] | None = None
    estimate_trace: EstimateTrace | None = None
    languages_searched: tuple[str, ...] = ()
    failure_reason: str | None = None
    promotion_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ResearchProvider(Protocol):
    def inspect_user_source(
        self,
        source: UserSourceInput,
        target: PlaceFeatureTarget,
        requirement: CanonicalFieldRequirement,
    ) -> list[SourceCandidate]: ...

    def search(
        self,
        step: SearchStep,
        target: PlaceFeatureTarget,
        requirement: CanonicalFieldRequirement,
    ) -> list[SourceCandidate]: ...

    def synthesize_estimate(
        self,
        target: PlaceFeatureTarget,
        requirement: CanonicalFieldRequirement,
        search_log: tuple[ResearchLogEntry, ...],
        candidates: tuple[SourceCandidate, ...],
    ) -> SourceCandidate: ...


LANGUAGE_NAMES = {
    "bn": "Bengali",
    "ar": "Arabic",
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "hi": "Hindi",
    "id": "Indonesian",
    "ig": "Igbo",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "ru": "Russian",
    "ur": "Urdu",
    "yo": "Yoruba",
    "ha": "Hausa",
    "zh": "Chinese",
}
FALLBACK_COUNTRY_LANGUAGES = {
    "CN": ("zh",),
    "JP": ("ja",),
    "IN": ("hi",),
    "KR": ("ko",),
    "MX": ("es",),
    "BR": ("pt",),
    "DE": ("de",),
    "FR": ("fr",),
    "IT": ("it",),
    "RU": ("ru",),
    "ID": ("id",),
    "BD": ("bn",),
    "PK": ("ur",),
    "NG": ("ha", "yo", "ig"),
    "US": ("en",),
    "CA": ("en", "fr"),
    "AU": ("en",),
}
FEATURE_TERMS = {
    "age_sex": {
        "en": "age and sex population distribution",
        "zh": "年龄 性别 人口 分布",
        "ja": "年齢 性別 人口 分布",
        "es": "distribución de población por edad y sexo",
        "fr": "répartition de la population par âge et sexe",
        "de": "Bevölkerung nach Alter und Geschlecht",
        "pt": "distribuição da população por idade e sexo",
    },
    "income": {
        "en": "income distribution",
        "zh": "收入 分布",
        "ja": "所得 分布",
        "es": "distribución de ingresos",
        "fr": "distribution des revenus",
        "de": "Einkommensverteilung",
        "pt": "distribuição de renda",
    },
    "education": {
        "en": "educational attainment distribution",
        "zh": "教育程度 分布",
        "ja": "教育水準 分布",
        "es": "distribución del nivel educativo",
        "fr": "répartition du niveau d'études",
        "de": "Bildungsabschluss Verteilung",
        "pt": "distribuição de escolaridade",
    },
    "specialization": {
        "en": "field of study ISCED-F distribution graduates students",
        "zh": "学科 专业 毕业生 分布 ISCED-F",
        "ja": "専攻 分野 卒業生 分布 ISCED-F",
        "ko": "전공 분야 졸업생 분포 ISCED-F",
        "hi": "अध्ययन क्षेत्र स्नातक वितरण ISCED-F",
        "id": "distribusi bidang studi lulusan ISCED-F",
        "ur": "تعلیم کے شعبے فارغ التحصیل تقسیم ISCED-F",
        "bn": "অধ্যয়নের ক্ষেত্র স্নাতক বণ্টন ISCED-F",
        "de": "Verteilung der Absolventen nach Studienfach ISCED-F",
        "it": "distribuzione dei laureati per campo di studio ISCED-F",
        "ru": "распределение выпускников по областям образования МСКО-О",
        "pt": "distribuição de concluintes por área de estudo CINE-F",
        "es": "distribución de graduados por campo de estudio CINE-F",
        "fr": "répartition des diplômés par domaine d'études CITE-F",
        "ha": "rabon ɗaliban da suka kammala karatu bisa fannin karatu ISCED-F",
        "yo": "ipin àwọn akẹ́kọ̀ọ́ tó jáde nípa ẹ̀ka ẹ̀kọ́ ISCED-F",
        "ig": "nkesa ndị gụsịrị akwụkwọ dịka ngalaba ọmụmụ ISCED-F",
    },
    "ideology_economic": {
        "en": "economic ideology survey distribution",
        "zh": "经济 意识形态 调查 分布",
        "ja": "経済 イデオロギー 調査 分布",
    },
    "ideology_state": {
        "en": "authoritarian democratic values survey distribution",
        "zh": "威权 民主 价值观 调查 分布",
        "ja": "権威主義 民主主義 価値観 調査 分布",
    },
    "ideology_cultural": {
        "en": "traditional progressive values survey distribution",
        "zh": "传统 进步 价值观 调查 分布",
        "ja": "伝統 進歩 価値観 調査 分布",
    },
    "household_size": {
        "en": "household size distribution",
        "zh": "家庭 户规模 分布",
        "ja": "世帯 人員 分布",
        "es": "distribución del tamaño del hogar",
        "fr": "répartition de la taille des ménages",
        "de": "Haushaltsgröße Verteilung",
        "pt": "distribuição do tamanho do domicílio",
    },
}
SOURCE_TERMS = {
    "official_statistics": {
        "en": "official statistics",
        "zh": "官方 统计",
        "ja": "公的統計",
    },
    "census": {"en": "census", "zh": "人口普查", "ja": "国勢調査"},
    "representative_survey": {
        "en": "representative survey",
        "zh": "代表性 调查",
        "ja": "代表 調査",
    },
    "research_article": {"en": "research article", "zh": "研究 论文", "ja": "研究 論文"},
    "government_report": {"en": "government report", "zh": "政府 报告", "ja": "政府 報告"},
    "university_report": {"en": "university report", "zh": "大学 报告", "ja": "大学 報告"},
    "news": {"en": "local news", "zh": "当地 新闻", "ja": "地域 ニュース"},
    "online_opinion": {
        "en": "public opinion forum",
        "zh": "公众 意见 论坛",
        "ja": "世論 フォーラム",
    },
    "expert_commentary": {"en": "expert commentary", "zh": "专家 评论", "ja": "専門家 解説"},
}
LOCALIZED_SOURCE_TERMS = {
    "bn": {
        "official_statistics": "সরকারি পরিসংখ্যান",
        "census": "আদমশুমারি",
        "representative_survey": "প্রতিনিধিত্বমূলক জরিপ",
        "research_article": "গবেষণা প্রবন্ধ",
        "government_report": "সরকারি প্রতিবেদন",
        "university_report": "বিশ্ববিদ্যালয় প্রতিবেদন",
        "news": "স্থানীয় সংবাদ",
        "online_opinion": "জনমত ফোরাম",
        "expert_commentary": "বিশেষজ্ঞ মন্তব্য",
    },
    "de": {
        "official_statistics": "amtliche Statistik",
        "census": "Volkszählung",
        "representative_survey": "repräsentative Umfrage",
        "research_article": "Forschungsartikel",
        "government_report": "Regierungsbericht",
        "university_report": "Universitätsbericht",
        "news": "lokale Nachrichten",
        "online_opinion": "öffentliches Meinungsforum",
        "expert_commentary": "Expertenkommentar",
    },
    "es": {
        "official_statistics": "estadísticas oficiales",
        "census": "censo",
        "representative_survey": "encuesta representativa",
        "research_article": "artículo de investigación",
        "government_report": "informe gubernamental",
        "university_report": "informe universitario",
        "news": "noticias locales",
        "online_opinion": "foro de opinión pública",
        "expert_commentary": "comentario de expertos",
    },
    "fr": {
        "official_statistics": "statistiques officielles",
        "census": "recensement",
        "representative_survey": "enquête représentative",
        "research_article": "article de recherche",
        "government_report": "rapport gouvernemental",
        "university_report": "rapport universitaire",
        "news": "actualités locales",
        "online_opinion": "forum d'opinion publique",
        "expert_commentary": "commentaire d'expert",
    },
    "ha": {
        "official_statistics": "alkaluman hukuma",
        "census": "ƙidayar jama'a",
        "representative_survey": "binciken wakilci",
        "research_article": "maƙalar bincike",
        "government_report": "rahoton gwamnati",
        "university_report": "rahoton jami'a",
        "news": "labaran gida",
        "online_opinion": "dandalin ra'ayin jama'a",
        "expert_commentary": "sharhin ƙwararre",
    },
    "hi": {
        "official_statistics": "आधिकारिक आँकड़े",
        "census": "जनगणना",
        "representative_survey": "प्रतिनिधि सर्वेक्षण",
        "research_article": "शोध लेख",
        "government_report": "सरकारी रिपोर्ट",
        "university_report": "विश्वविद्यालय रिपोर्ट",
        "news": "स्थानीय समाचार",
        "online_opinion": "जनमत मंच",
        "expert_commentary": "विशेषज्ञ टिप्पणी",
    },
    "id": {
        "official_statistics": "statistik resmi",
        "census": "sensus",
        "representative_survey": "survei representatif",
        "research_article": "artikel penelitian",
        "government_report": "laporan pemerintah",
        "university_report": "laporan universitas",
        "news": "berita lokal",
        "online_opinion": "forum opini publik",
        "expert_commentary": "komentar ahli",
    },
    "ig": {
        "official_statistics": "ọnụ ọgụgụ gọọmentị",
        "census": "ọnụ ọgụgụ mmadụ",
        "representative_survey": "nyocha nnọchiteanya",
        "research_article": "edemede nyocha",
        "government_report": "akụkọ gọọmentị",
        "university_report": "akụkọ mahadum",
        "news": "akụkọ mpaghara",
        "online_opinion": "ọgbakọ echiche ọha",
        "expert_commentary": "nkọwa ọkachamara",
    },
    "it": {
        "official_statistics": "statistiche ufficiali",
        "census": "censimento",
        "representative_survey": "sondaggio rappresentativo",
        "research_article": "articolo di ricerca",
        "government_report": "rapporto governativo",
        "university_report": "rapporto universitario",
        "news": "notizie locali",
        "online_opinion": "forum di opinione pubblica",
        "expert_commentary": "commento di esperti",
    },
    "ko": {
        "official_statistics": "공식 통계",
        "census": "인구주택총조사",
        "representative_survey": "대표성 조사",
        "research_article": "연구 논문",
        "government_report": "정부 보고서",
        "university_report": "대학 보고서",
        "news": "지역 뉴스",
        "online_opinion": "여론 포럼",
        "expert_commentary": "전문가 논평",
    },
    "pt": {
        "official_statistics": "estatísticas oficiais",
        "census": "censo",
        "representative_survey": "pesquisa representativa",
        "research_article": "artigo científico",
        "government_report": "relatório governamental",
        "university_report": "relatório universitário",
        "news": "notícias locais",
        "online_opinion": "fórum de opinião pública",
        "expert_commentary": "comentário de especialista",
    },
    "ru": {
        "official_statistics": "официальная статистика",
        "census": "перепись населения",
        "representative_survey": "репрезентативный опрос",
        "research_article": "научная статья",
        "government_report": "государственный доклад",
        "university_report": "университетский отчёт",
        "news": "местные новости",
        "online_opinion": "форум общественного мнения",
        "expert_commentary": "экспертный комментарий",
    },
    "ur": {
        "official_statistics": "سرکاری اعداد و شمار",
        "census": "مردم شماری",
        "representative_survey": "نمائندہ سروے",
        "research_article": "تحقیقی مقالہ",
        "government_report": "سرکاری رپورٹ",
        "university_report": "یونیورسٹی رپورٹ",
        "news": "مقامی خبریں",
        "online_opinion": "عوامی رائے فورم",
        "expert_commentary": "ماہرانہ تبصرہ",
    },
    "yo": {
        "official_statistics": "ìṣirò ìjọba",
        "census": "ìkànìyàn",
        "representative_survey": "ìwádìí aṣojú",
        "research_article": "àpilẹ̀kọ ìwádìí",
        "government_report": "ìròyìn ìjọba",
        "university_report": "ìròyìn yunifásítì",
        "news": "ìròyìn agbègbè",
        "online_opinion": "àpérò èrò gbogbo ènìyàn",
        "expert_commentary": "àsọyé amòye",
    },
}
for source_language, translations in LOCALIZED_SOURCE_TERMS.items():
    for source_kind, localized_term in translations.items():
        SOURCE_TERMS[source_kind][source_language] = localized_term
LOCAL_ENGINES = {
    "zh": {
        "official_statistics": "National Bureau of Statistics of China",
        "census": "National Bureau of Statistics of China",
        "research_article": "CNKI",
        "representative_survey": "Baidu",
        "government_report": "Baidu",
        "university_report": "CNKI",
        "news": "Baidu News",
        "online_opinion": "Baidu",
        "expert_commentary": "Baidu",
    },
    "ja": {
        "official_statistics": "e-Stat / Statistics Bureau of Japan",
        "census": "e-Stat / Statistics Bureau of Japan",
        "research_article": "CiNii / J-STAGE",
        "representative_survey": "Yahoo Japan",
        "news": "Yahoo Japan News",
        "government_report": "Yahoo Japan",
        "university_report": "CiNii / J-STAGE",
        "online_opinion": "Yahoo Japan",
        "expert_commentary": "Yahoo Japan",
    },
    "ko": {
        "official_statistics": "KOSIS",
        "census": "KOSIS",
        "representative_survey": "Naver",
        "research_article": "Naver",
        "government_report": "Naver",
        "university_report": "Naver",
        "news": "Naver News",
        "online_opinion": "Naver",
        "expert_commentary": "Naver",
    },
    "ru": {
        "official_statistics": "Rosstat",
        "census": "Rosstat",
        "representative_survey": "Yandex",
        "research_article": "eLIBRARY.RU",
        "government_report": "Yandex",
        "university_report": "eLIBRARY.RU",
        "news": "Yandex News",
        "online_opinion": "Yandex",
        "expert_commentary": "Yandex",
    },
    "pt": {
        "official_statistics": "IBGE",
        "census": "IBGE",
        "representative_survey": "Google Brasil",
        "research_article": "SciELO Brasil",
        "government_report": "Google Brasil",
        "university_report": "SciELO Brasil",
        "news": "Google Notícias Brasil",
        "online_opinion": "Google Brasil",
        "expert_commentary": "Google Brasil",
    },
    "es": {
        "official_statistics": "INEGI and local official catalogs",
        "census": "INEGI and local official catalogs",
        "representative_survey": "Google México",
        "research_article": "Redalyc / SciELO",
        "government_report": "Google México",
        "university_report": "Redalyc / SciELO",
        "news": "Google Noticias México",
        "online_opinion": "Google México",
        "expert_commentary": "Google México",
    },
    "hi": {
        "official_statistics": "MoSPI India",
        "census": "Census of India",
        "representative_survey": "Google India",
        "research_article": "Google Scholar India",
        "government_report": "Google India",
        "university_report": "Google Scholar India",
        "news": "Google News India",
        "online_opinion": "Google India",
        "expert_commentary": "Google India",
    },
    "id": {
        "official_statistics": "BPS Statistics Indonesia",
        "census": "BPS Statistics Indonesia",
        "representative_survey": "Google Indonesia",
        "research_article": "GARUDA Indonesia",
        "government_report": "Google Indonesia",
        "university_report": "GARUDA Indonesia",
        "news": "Google Berita Indonesia",
        "online_opinion": "Google Indonesia",
        "expert_commentary": "Google Indonesia",
    },
    "bn": {
        "official_statistics": "Bangladesh Bureau of Statistics",
        "census": "Bangladesh Bureau of Statistics",
        "representative_survey": "Google Bangladesh",
        "research_article": "BanglaJOL",
        "government_report": "Google Bangladesh",
        "university_report": "BanglaJOL",
        "news": "Google News Bangladesh",
        "online_opinion": "Google Bangladesh",
        "expert_commentary": "Google Bangladesh",
    },
    "ur": {
        "official_statistics": "Pakistan Bureau of Statistics",
        "census": "Pakistan Bureau of Statistics",
        "representative_survey": "Google Pakistan",
        "research_article": "HEC Pakistan Research Repository",
        "government_report": "Google Pakistan",
        "university_report": "HEC Pakistan Research Repository",
        "news": "Google News Pakistan",
        "online_opinion": "Google Pakistan",
        "expert_commentary": "Google Pakistan",
    },
    "ha": {
        "official_statistics": "Bing Nigeria local-language search",
        "census": "Bing Nigeria local-language search",
        "representative_survey": "Bing Nigeria local-language search",
        "research_article": "Bing Nigeria local-language search",
        "government_report": "Bing Nigeria local-language search",
        "university_report": "Bing Nigeria local-language search",
        "news": "Bing Nigeria local-language search",
        "online_opinion": "Bing Nigeria local-language search",
        "expert_commentary": "Bing Nigeria local-language search",
    },
    "yo": {
        "official_statistics": "Bing Nigeria local-language search",
        "census": "Bing Nigeria local-language search",
        "representative_survey": "Bing Nigeria local-language search",
        "research_article": "Bing Nigeria local-language search",
        "government_report": "Bing Nigeria local-language search",
        "university_report": "Bing Nigeria local-language search",
        "news": "Bing Nigeria local-language search",
        "online_opinion": "Bing Nigeria local-language search",
        "expert_commentary": "Bing Nigeria local-language search",
    },
    "ig": {
        "official_statistics": "Bing Nigeria local-language search",
        "census": "Bing Nigeria local-language search",
        "representative_survey": "Bing Nigeria local-language search",
        "research_article": "Bing Nigeria local-language search",
        "government_report": "Bing Nigeria local-language search",
        "university_report": "Bing Nigeria local-language search",
        "news": "Bing Nigeria local-language search",
        "online_opinion": "Bing Nigeria local-language search",
        "expert_commentary": "Bing Nigeria local-language search",
    },
    "fr": {
        "official_statistics": "Bing local-language search",
        "census": "Bing local-language search",
        "representative_survey": "Bing local-language search",
        "research_article": "Bing local-language search",
        "government_report": "Bing local-language search",
        "university_report": "Bing local-language search",
        "news": "Bing local-language search",
        "online_opinion": "Bing local-language search",
        "expert_commentary": "Bing local-language search",
    },
    "en": {
        "official_statistics": "Official statistics and census catalogs",
        "census": "Official statistics and census catalogs",
        "research_article": "Google Scholar",
        "representative_survey": "Bing",
        "government_report": "Bing",
        "university_report": "Google Scholar",
        "news": "Bing News",
        "online_opinion": "Bing",
        "expert_commentary": "Bing",
    },
}
SEARCH_SOURCE_ORDER: tuple[SourceKind, ...] = (
    "official_statistics",
    "census",
    "representative_survey",
    "research_article",
    "government_report",
    "university_report",
    "news",
    "online_opinion",
    "expert_commentary",
)
MAPPING_VERSION = "atlas-auto-import-labels-v1"


def _base_language(language: str) -> str:
    return language.strip().replace("_", "-").split("-", 1)[0].lower()


@lru_cache(maxsize=1)
def _country_info_languages() -> dict[str, tuple[str, ...]]:
    path = Path(__file__).resolve().parents[2] / "data" / "countryInfo.txt"
    if not path.exists():
        return FALLBACK_COUNTRY_LANGUAGES
    result: dict[str, tuple[str, ...]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        columns = line.split("\t")
        if len(columns) <= 15:
            continue
        languages = tuple(
            dict.fromkeys(
                _base_language(value)
                for value in columns[15].split(",")
                if value.strip()
            )
        )
        if languages:
            result[columns[0].upper()] = languages
    return {
        code: tuple(
            dict.fromkeys(
                (*FALLBACK_COUNTRY_LANGUAGES.get(code, ()), *result.get(code, ()))
            )
        )
        for code in FALLBACK_COUNTRY_LANGUAGES.keys() | result.keys()
    }


def research_languages(target: PlaceFeatureTarget) -> tuple[str, ...]:
    supplied = tuple(_base_language(value) for value in target.dominant_languages if value)
    country_code = (target.country_code or "").upper()
    detected = _country_info_languages().get(country_code, ())
    preferred = FALLBACK_COUNTRY_LANGUAGES.get(country_code, ())
    candidates = list(dict.fromkeys((*supplied, *preferred, *detected)))
    local_languages = [language for language in candidates if language != "en"]
    if local_languages:
        ordered = [local_languages[0], "en", *local_languages[1:]][:4]
    else:
        ordered = ["en"]
    if not ordered:
        ordered.append("en")
    elif "en" not in ordered:
        ordered.append("en")
    return tuple(ordered)


def _localized_term(terms: dict[str, str], language: str) -> str:
    return terms.get(language, terms["en"])


def build_search_plan(target: PlaceFeatureTarget) -> SearchPlan:
    requirement = canonical_requirement(target.feature_id)
    languages = tuple(
        language
        for language in research_languages(target)
        if language == "en"
        or (
            language in FEATURE_TERMS[requirement.feature_id]
            and all(language in SOURCE_TERMS[source_kind] for source_kind in SEARCH_SOURCE_ORDER)
        )
    )
    steps = []
    for language in languages:
        place_name = target.local_names.get(language, target.place_label)
        feature_term = _localized_term(FEATURE_TERMS[requirement.feature_id], language)
        engines = LOCAL_ENGINES.get(language, {})
        for source_kind in SEARCH_SOURCE_ORDER:
            source_term = _localized_term(SOURCE_TERMS[source_kind], language)
            engine = engines.get(
                source_kind,
                f"{LANGUAGE_NAMES.get(language, language)} local web and statistics catalogs",
            )
            steps.append(
                SearchStep(
                    sequence=len(steps) + 1,
                    language=language,
                    language_name=LANGUAGE_NAMES.get(language, language),
                    query=f"{place_name} {feature_term} {source_term}",
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
                        query=f"{place_name} {feature_term} {source_term}",
                        engine=f"Bing local-language fallback after {engine}",
                        source_kind=source_kind,
                    )
                )
    return SearchPlan(languages=languages, steps=tuple(steps))


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold().strip()
    return " ".join(re.sub(r"[^\w\u3400-\u9fff]+", " ", decomposed).split())


def _age_sex_label(label: str) -> str | None:
    normalized = _normalized(label).replace("歳", "").replace("岁", "")
    female = any(token in normalized for token in ("female", "women", "woman", "女性", "女子"))
    male = not female and any(
        token in normalized for token in ("male", "men", "man", "男性", "男子")
    )
    if not female and not male:
        return None
    sex = "female" if female else "male"
    numbers = re.findall(r"\d+", normalized)
    if len(numbers) == 1 and (
        any(token in normalized for token in ("plus", "over", "以上")) or "+" in label
    ):
        age = f"{numbers[0]}_plus"
    elif len(numbers) == 1:
        age = numbers[0]
    else:
        return None
    proposed = f"{sex}_{age}"
    return proposed if proposed in canonical_requirement("age_sex").canonical_values else None


def propose_label_mapping(
    distribution: dict[str, float], requirement: CanonicalFieldRequirement
) -> MappingPreview:
    rows = []
    canonical_by_normalized = {
        _normalized(value): value for value in requirement.canonical_values
    }
    aliases = {_normalized(source): target for source, target in requirement.label_aliases.items()}
    for source_label in distribution:
        normalized = _normalized(source_label)
        proposed = canonical_by_normalized.get(normalized)
        confidence: MappingConfidence = "exact"
        reason = "Exact canonical label"
        if proposed is None and requirement.feature_id == "age_sex":
            proposed = _age_sex_label(source_label)
            confidence = "alias" if proposed else "unknown"
            reason = "Age and sex label normalized" if proposed else "No canonical age-sex match"
        if proposed is None and normalized in aliases:
            proposed = aliases[normalized]
            confidence = "alias"
            reason = "Versioned canonical alias"
        if proposed is None and requirement.allows_source_categories and source_label.strip():
            proposed = source_label.strip()
            confidence = "alias"
            reason = "Source-defined band retained for explicit confirmation"
        if proposed is None:
            confidence = "unknown"
            reason = "Human mapping required; no label was guessed"
        rows.append(
            LabelMapping(
                source_label=source_label,
                proposed_label=proposed,
                confidence=confidence,
                reason=reason,
            )
        )
    return MappingPreview(version=MAPPING_VERSION, rows=tuple(rows))


def _matches(actual: str | None, expected: tuple[str, ...]) -> bool:
    if not actual:
        return False
    normalized = _normalized(actual)
    return any(normalized == _normalized(value) for value in expected)


def _matches_time_basis(
    actual: str | None,
    requirement: CanonicalFieldRequirement,
) -> bool:
    if _matches(actual, (requirement.time_unit,)):
        return True
    if not actual:
        return False
    accepted = {
        "specialization": (
            "academic year",
            "graduation year",
            "calendar year",
            "reference year",
            "census date",
            "survey wave",
        )
    }.get(requirement.feature_id, ())
    return _matches(actual, accepted)


def _distribution_reason(
    candidate: SourceCandidate,
    requirement: CanonicalFieldRequirement,
) -> tuple[bool, str]:
    if not candidate.distribution:
        return False, "No distribution was extracted"
    values = tuple(candidate.distribution.values())
    if any(not math.isfinite(value) for value in values):
        return False, "Distribution contains a non-finite value"
    if any(value < 0 or value > 100 for value in values):
        return False, "Distribution values must be between 0 and 100"
    total = sum(values)
    if not math.isclose(total, requirement.distribution_total, abs_tol=0.5):
        return False, (
            f"Distribution totals {total:g}; expected {requirement.distribution_total:g}"
        )
    if requirement.feature_id.startswith("ideology_"):
        bounds = [
            float(value)
            for label in candidate.distribution
            for value in re.findall(r"-?\d+(?:\.\d+)?", label)
        ]
        if not bounds or any(value < -1 or value > 1 for value in bounds):
            return False, "Ideology axis categories need numeric bounds from -1 to +1"
    return True, f"Distribution totals {total:g}"


def verify_candidate(
    candidate: SourceCandidate,
    target: PlaceFeatureTarget,
    requirement: CanonicalFieldRequirement,
) -> SourceVerification:
    feature_expected = (requirement.feature_id, requirement.name, *requirement.feature_aliases)
    place_expected = (
        target.place_id,
        target.place_label,
        *target.local_names.values(),
        *target.place_aliases,
    )
    feature_match = _matches(candidate.feature, feature_expected)
    exact_place_match = candidate.place_level == target.level and _matches(
        candidate.place, place_expected
    )
    contextual_place_match = candidate.evidence_kind == "hint" and any(
        candidate.place_level == context.level
        and _matches(
            candidate.place,
            (context.place_id, context.place_label, *context.aliases),
        )
        for context in target.context_places
    )
    place_match = exact_place_match or contextual_place_match
    denominator_match = _matches(candidate.denominator, requirement.accepted_denominators)
    official_national_percentage = (
        candidate.population is None
        and exact_place_match
        and candidate.source_kind
        in {
            "official_statistics",
            "census",
            "government_report",
            "user_url",
        }
        and candidate.unit is not None
        and _matches(candidate.unit, requirement.accepted_units)
    )
    population_match = (
        candidate.population is not None and candidate.population > 0
    ) or official_national_percentage
    date_match = bool(
        candidate.observation_date
        and candidate.published_date
        and candidate.observation_date <= target.as_of
        and candidate.published_date <= target.as_of
    )
    time_basis_match = _matches_time_basis(candidate.time_unit, requirement)
    unit_match = _matches(candidate.unit, requirement.accepted_units)
    distribution_match, distribution_reason = _distribution_reason(candidate, requirement)
    translation_match = candidate.language == "en" or bool(candidate.translated_excerpt)
    direct_measurement = (
        candidate.evidence_kind == "measured"
        and candidate.source_kind != "news"
        and exact_place_match
    )
    evidence_match = candidate.evidence_kind == "hint" or direct_measurement
    checks = (
        VerificationCheck(
            name="credibility",
            passed=candidate.credible,
            expected="Credible source with a stated basis",
            actual=candidate.credibility_reason,
            reason=candidate.credibility_reason,
        ),
        VerificationCheck(
            name="feature",
            passed=feature_match,
            expected=requirement.name,
            actual=candidate.feature,
            reason="Feature matches" if feature_match else "Source measures a different feature",
        ),
        VerificationCheck(
            name="place",
            passed=place_match,
            expected=f"{target.level}: {target.place_label}",
            actual=f"{candidate.place_level}: {candidate.place}",
            reason=(
                "Place matches"
                if exact_place_match
                else (
                    "Broader contextual place is usable only as an estimate hint"
                    if contextual_place_match
                    else "Source is for a different place or level"
                )
            ),
        ),
        VerificationCheck(
            name="denominator",
            passed=denominator_match,
            expected=requirement.denominator,
            actual=candidate.denominator or "not stated",
            reason="Denominator matches"
            if denominator_match
            else "Denominator is missing or does not match",
        ),
        VerificationCheck(
            name="population",
            passed=population_match,
            expected=(
                "A stated positive population/sample universe, or a national official "
                "percentage table with a declared denominator"
            ),
            actual=str(candidate.population) if candidate.population is not None else "not stated",
            reason=(
                "Population is stated"
                if candidate.population is not None and candidate.population > 0
                else (
                    "National official percentage table defines its denominator"
                    if official_national_percentage
                    else "Population is missing"
                )
            ),
        ),
        VerificationCheck(
            name="date",
            passed=date_match,
            expected=f"Stated observation and publication dates on or before {target.as_of}",
            actual=(
                f"observed {candidate.observation_date or 'not stated'}; "
                f"published {candidate.published_date or 'not stated'}"
            ),
            reason=(
                "Observation and publication dates pass the availability cutoff"
                if date_match
                else "Observation or publication date is missing or after the availability cutoff"
            ),
        ),
        VerificationCheck(
            name="time_basis",
            passed=time_basis_match,
            expected=requirement.time_unit,
            actual=candidate.time_unit or "not stated",
            reason="Time basis matches"
            if time_basis_match
            else "Time basis is missing or incompatible",
        ),
        VerificationCheck(
            name="unit",
            passed=unit_match,
            expected=", ".join(requirement.accepted_units),
            actual=candidate.unit or "not stated",
            reason="Unit matches" if unit_match else "Unit is missing or incompatible",
        ),
        VerificationCheck(
            name="distribution",
            passed=distribution_match,
            expected=f"Values in range totaling {requirement.distribution_total:g}",
            actual=distribution_reason,
            reason=distribution_reason,
        ),
        VerificationCheck(
            name="translation",
            passed=translation_match,
            expected="Original text and an English translation for non-English evidence",
            actual="translation present" if candidate.translated_excerpt else "original text only",
            reason="Provenance is displayable in English"
            if translation_match
            else "Non-English evidence needs a translation",
        ),
        VerificationCheck(
            name="evidence_kind",
            passed=evidence_match,
            expected="Measured evidence or an explicitly labelled estimate hint",
            actual=candidate.evidence_kind,
            reason="Evidence classification accepted"
            if evidence_match
            else "News cannot establish a direct measured distribution",
        ),
    )
    reasons = tuple(check.reason for check in checks if not check.passed)
    return SourceVerification(
        candidate_id=candidate.candidate_id,
        accepted=not reasons,
        direct_measurement=not reasons and direct_measurement,
        checks=checks,
        reasons=reasons,
    )


def _wide_interval(value: float) -> PercentageInterval:
    width = 30.0
    lower = max(0.0, value - width / 2)
    upper = min(100.0, value + width / 2)
    if upper - lower < width and lower == 0:
        upper = min(100.0, width)
    if upper - lower < width and upper == 100:
        lower = max(0.0, 100 - width)
    return PercentageInterval(lower=round(lower, 6), upper=round(upper, 6))


def pipeline_fallback_candidate(
    target: PlaceFeatureTarget,
    requirement: CanonicalFieldRequirement,
    search_log: tuple[ResearchLogEntry, ...] | list[ResearchLogEntry],
    provider_errors: tuple[str, ...] | list[str] = (),
) -> SourceCandidate:
    fallback_labels = {
        "income": ("lowest", "lower_middle", "upper_middle", "highest"),
        "ideology_economic": (
            "-1.0 to -0.5",
            "-0.5 to 0.0",
            "0.0 to 0.5",
            "0.5 to 1.0",
        ),
        "ideology_state": (
            "-1.0 to -0.5",
            "-0.5 to 0.0",
            "0.0 to 0.5",
            "0.5 to 1.0",
        ),
        "ideology_cultural": (
            "-1.0 to -0.5",
            "-0.5 to 0.0",
            "0.0 to 0.5",
            "0.5 to 1.0",
        ),
    }
    labels = tuple(
        label
        for label in (
            requirement.canonical_values
            or fallback_labels.get(requirement.feature_id, ("estimated",))
        )
        if label != "unknown"
    )
    share = round(100 / len(labels), 6)
    distribution = {label: share for label in labels}
    first_label = labels[0]
    distribution[first_label] = round(
        distribution[first_label] + 100 - sum(distribution.values()),
        6,
    )
    attempted = len(search_log)
    errors = len(provider_errors)
    reasoning = (
        f"The in-app pipeline completed {attempted} logged source and engine attempts for "
        f"{target.place_label}. No extracted distribution passed every validation check, so "
        "it produced a maximum-uncertainty equal-share prior over the canonical values. "
        "The prior asserts no unsupported place difference and must be replaced when a "
        "stronger source passes validation."
    )
    assumptions = (
        "Canonical categories are possible for the qualified target population.",
        "No category receives a place-specific advantage without accepted evidence.",
        "The estimate is descriptive and cannot fit a behavior coefficient.",
        f"{errors} provider errors were retained in the visible search log.",
    )
    candidate_id = "estimate-" + hashlib.sha256(
        (
            f"{target.scope}|{target.level}|{target.place_id}|"
            f"{requirement.feature_id}|{target.as_of.isoformat()}"
        ).encode()
    ).hexdigest()[:24]
    return SourceCandidate(
        candidate_id=candidate_id,
        title=f"Petraterrium research synthesis for {target.place_label}",
        source_kind="expert_commentary",
        feature=requirement.feature_id,
        place=target.place_label,
        place_level=target.level,
        denominator=requirement.denominator,
        population=max(1, target.population),
        observation_date=target.as_of,
        published_date=target.as_of,
        time_unit=requirement.time_unit,
        unit=requirement.accepted_units[0],
        distribution=distribution,
        evidence_kind="hint",
        credible=True,
        credibility_reason=(
            "Pipeline-generated conservative estimate after the complete ordered search plan"
        ),
        language="en",
        original_excerpt=reasoning,
        source_version="atlas-research-synthesis-v1",
        license="Project-generated estimate; upstream source rights remain with publishers",
        estimate_reasoning=reasoning,
        estimate_assumptions=assumptions,
        estimate_confidence_intervals={label: (0.0, 100.0) for label in labels},
    )


def derive_estimate(
    candidates: list[SourceCandidate], requirement: CanonicalFieldRequirement
) -> tuple[dict[str, float], EstimateTrace, tuple[str, ...]]:
    if not candidates:
        raise ValueError("An estimate needs at least one credible hint")
    grouped: dict[tuple[str, ...], list[SourceCandidate]] = defaultdict(list)
    for candidate in candidates:
        label_key = tuple(sorted(_normalized(label) for label in candidate.distribution))
        grouped[label_key].append(candidate)
    synthesized = [
        candidate for candidate in candidates if candidate.source_kind == "expert_commentary"
    ]
    compatible = synthesized or max(
        grouped.values(), key=lambda values: (len(values), -candidates.index(values[0]))
    )
    excluded = tuple(
        candidate.candidate_id for candidate in candidates if candidate not in compatible
    )
    source_labels = list(compatible[0].distribution)
    normalized_labels = {_normalized(label): label for label in source_labels}
    totals: dict[str, float] = defaultdict(float)
    total_weight = 0.0
    extractions = []
    for candidate in compatible:
        raw_total = sum(candidate.distribution.values())
        normalized_distribution = {
            normalized_labels[_normalized(label)]: value * 100 / raw_total
            for label, value in candidate.distribution.items()
        }
        weight = float(candidate.sample_size or 1)
        weight_basis = (
            f"reported sample size {candidate.sample_size}"
            if candidate.sample_size
            else "equal source weight because no sample size was reported"
        )
        for label, value in normalized_distribution.items():
            totals[label] += value * weight
        total_weight += weight
        extractions.append(
            SourceExtraction(
                candidate_id=candidate.candidate_id,
                title=candidate.title,
                extracted_distribution={
                    label: round(value, 6) for label, value in normalized_distribution.items()
                },
                weight=weight,
                weight_basis=weight_basis,
            )
        )
    distribution = {label: round(value / total_weight, 6) for label, value in totals.items()}
    rounding_delta = 100 - sum(distribution.values())
    first_label = next(iter(distribution))
    distribution[first_label] = round(distribution[first_label] + rounding_delta, 6)
    supplied_intervals = {
        label: bounds
        for candidate in compatible
        for label, bounds in candidate.estimate_confidence_intervals.items()
    }
    intervals = {
        label: (
            PercentageInterval(
                lower=supplied_intervals[label][0],
                upper=supplied_intervals[label][1],
            )
            if label in supplied_intervals
            else _wide_interval(value)
        )
        for label, value in distribution.items()
    }
    calculation = (
        "Normalize each extracted source distribution to 100 percent.",
        "Weight each source by its reported sample size; use equal source weight when absent.",
        "Average matching categories and preserve the source categories for human mapping.",
        "Assign a 30 percentage-point uncertainty interval to every estimated share.",
    )
    assumptions = tuple(
        dict.fromkeys(
            assumption
            for candidate in compatible
            for assumption in candidate.estimate_assumptions
        )
    ) or (
        "The selected surveys or reports are informative for the target place.",
        "Differences in sampling frame and field date are not corrected without microdata.",
        "This estimate is descriptive only and is ineligible for coefficient fitting.",
    )
    method: Literal[
        "weighted_compositional_estimate",
        "research_synthesis_estimate",
        "maximum_uncertainty_prior",
    ] = "weighted_compositional_estimate"
    if all(candidate.source_kind == "expert_commentary" for candidate in compatible):
        method = (
            "research_synthesis_estimate"
            if any(
                candidate.ai_provenance is not None or candidate.estimate_source_ids
                for candidate in compatible
            )
            else "maximum_uncertainty_prior"
        )
        calculation = tuple(
            dict.fromkeys(
                candidate.estimate_reasoning or candidate.credibility_reason
                for candidate in compatible
            )
        )
    trace = EstimateTrace(
        method=method,
        extractions=tuple(extractions),
        calculation=calculation,
        assumptions=assumptions,
        confidence_intervals=intervals,
        source_ids_used=tuple(
            dict.fromkeys(
                source_id
                for candidate in compatible
                for source_id in (
                    candidate.estimate_source_ids or (candidate.candidate_id,)
                )
            )
        ),
        better_data_needed=requirement.better_data_needed,
    )
    return distribution, trace, excluded


def apply_confirmed_mapping(
    distribution: dict[str, float],
    preview: MappingPreview,
    confirmation: MappingConfirmation,
    requirement: CanonicalFieldRequirement,
) -> dict[str, float]:
    if not confirmation.confirmed:
        raise ValueError("Mapping must be explicitly confirmed")
    source_distribution = confirmation.distribution or distribution
    if set(source_distribution) != set(distribution):
        raise ValueError("Edited distribution must cover every source category exactly once")
    if any(
        not math.isfinite(value) or value < 0 or value > 100
        for value in source_distribution.values()
    ):
        raise ValueError("Edited distribution values must be finite percentages from 0 to 100")
    source_total = sum(source_distribution.values())
    if not math.isclose(source_total, requirement.distribution_total, abs_tol=0.5):
        raise ValueError(
            f"Edited distribution totals {source_total:g}; expected "
            f"{requirement.distribution_total:g}"
        )
    expected_labels = {row.source_label for row in preview.rows}
    supplied = {row.source_label for row in confirmation.mappings}
    if supplied != expected_labels or len(supplied) != len(confirmation.mappings):
        raise ValueError("Confirmed mappings must cover every source label exactly once")
    mapped: dict[str, float] = defaultdict(float)
    canonical = set(requirement.canonical_values)
    target_labels = [
        (row.target_label or "").strip()
        for row in confirmation.mappings
        if (row.target_label or "").strip()
    ]
    if len(target_labels) != len(set(target_labels)):
        raise ValueError("Each source category must map to a distinct canonical category")
    for row in confirmation.mappings:
        target_label = (row.target_label or "").strip()
        if not target_label:
            raise ValueError(f"Choose a canonical label for {row.source_label}")
        if canonical and target_label not in canonical:
            raise ValueError(f"{target_label} is not a canonical label for {requirement.name}")
        mapped[target_label] += source_distribution[row.source_label]
    total = sum(mapped.values())
    if not math.isclose(total, requirement.distribution_total, abs_tol=0.5):
        raise ValueError(
            f"Mapped distribution totals {total:g}; expected {requirement.distribution_total:g}"
        )
    result = {label: round(value, 6) for label, value in mapped.items()}
    first_label = next(iter(result))
    result[first_label] = round(
        result[first_label] + requirement.distribution_total - sum(result.values()),
        6,
    )
    return result

