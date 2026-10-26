from urllib.parse import urlparse

import httpx

from .contracts import AtlasSource
from .formats import MAX_BYTES

SOURCES = [
    AtlasSource(
        source_id="ipums",
        name="IPUMS International",
        url="https://international.ipums.org/",
        access="registration",
        license="Individual research license; no microdata redistribution",
        fields=["age_sex", "income", "education", "household_size"],
        adapter="IPUMS microdata or canonical export",
        instructions=(
            "Use your licensed extract. Export AGE, SEX, PERWT and optional"
            " INCWAGE/EDATTAIN. Supply its country ISO code and codebook; special"
            " codes must be cleaned explicitly. No automatic login or shared"
            " redistribution."
        ),
        download_hosts=["international.ipums.org", "extracts.ipums.org"],
    ),
    AtlasSource(
        source_id="us_pums",
        name="US ACS PUMS",
        url="https://www.census.gov/programs-surveys/acs/microdata.html",
        access="public",
        license="US Census public-use data; cite release and dictionary",
        fields=["age_sex", "income", "education", "household_size"],
        adapter="Weighted person/household microdata",
        instructions=(
            "Load a Census PUMS CSV: AGEP, SEX, PWGTP, SCHL, PINCP for persons; NP"
            " and WGTP for households. Keep person and household files separate."
        ),
        download_hosts=["www2.census.gov", "api.census.gov"],
    ),
    AtlasSource(
        source_id="un_wpp",
        name="UN World Population Prospects",
        url="https://population.un.org/wpp/",
        access="public",
        license="UN data terms; preserve revision, observation year and attribution",
        fields=["age_sex"],
        adapter="Population by age and sex",
        instructions=(
            "Load an age/sex CSV with ISO3_code, Time, AgeGrp, PopMale, PopFemale."
            " Only the declared observation year is selected; country counts become"
            " inherited archetypes."
        ),
        download_hosts=["population.un.org"],
    ),
    AtlasSource(
        source_id="worldpop",
        name="WorldPop",
        url="https://www.worldpop.org/",
        access="public",
        license="CC BY 4.0; check individual release",
        fields=["density_per_km2"],
        adapter="GeoTIFF population grid",
        instructions=(
            "Load a released GeoTIFF tile. Declare persons_per_cell or"
            " persons_per_km2 units. City-centre grid samples are imputed density,"
            " not observed city marginals."
        ),
        download_hosts=["data.worldpop.org", "api.worldpop.org"],
    ),
    AtlasSource(
        source_id="gpw",
        name="Gridded Population of the World",
        url=(
            "https://www.earthdata.nasa.gov/data/catalog/sedac-ciesin-sedac-gpwv4-pop"
            "density-r11-4.11"
        ),
        access="registration",
        license="NASA/SEDAC release terms; Earthdata registration may be required",
        fields=["density_per_km2"],
        adapter="GeoTIFF population grid",
        instructions=(
            "Download an authorized GPW population or density GeoTIFF, select its"
            " actual units, then import. Nodata pixels remain missing."
        ),
        download_hosts=[
            "sedac.ciesin.columbia.edu",
            "sedac.ciesin.columbia.edu",
            "data.earthdata.nasa.gov",
        ],
    ),
    AtlasSource(
        source_id="dhs",
        name="Demographic and Health Surveys",
        url="https://dhsprogram.com/data/Access-Instructions.cfm",
        access="registration",
        license="Project-specific access; no dataset redistribution",
        fields=["age_sex", "education", "household_size"],
        adapter="Licensed extract and confirmed schema",
        instructions=(
            "Obtain project approval. Load a CSV/Parquet/JSON export with its"
            " codebook; map distributions or explicit respondent traits/outcomes. No"
            " automatic country or special-code guessing."
        ),
        download_hosts=["dhsprogram.com", "www.dhsprogram.com"],
    ),
    AtlasSource(
        source_id="wvs",
        name="World Values Survey",
        url="https://www.worldvaluessurvey.org/WVSContents.jsp",
        access="registration",
        license="Release-specific attribution and access terms",
        fields=["ideology", "income", "education", "behaviour"],
        adapter="Survey schema mapper",
        instructions=(
            "Load an authorized wave export with descriptive headers/codebook labels"
            " and weights. Map trait columns and a binary action outcome only when"
            " the survey measures that link; otherwise behaviour stays label-only."
        ),
        download_hosts=["www.worldvaluessurvey.org", "worldvaluessurvey.org"],
    ),
    AtlasSource(
        source_id="ess",
        name="European Social Survey",
        url="https://www.europeansocialsurvey.org/data-portal",
        access="registration",
        license="CC BY-NC-SA 4.0; confirm release terms",
        fields=["ideology", "income", "education", "behaviour"],
        adapter="Survey schema mapper",
        instructions=(
            "Load a licensed wave export and survey weights. Confirm field meanings"
            " and missing-value codes against its dictionary before committing."
            " Country archetypes remain inherited."
        ),
        download_hosts=["www.europeansocialsurvey.org", "ess.sikt.no"],
    ),
    AtlasSource(
        source_id="pew",
        name="Pew Global Attitudes",
        url="https://www.pewresearch.org/tools-and-datasets/",
        access="registration",
        license="Account and dataset agreement; no implied redistribution right",
        fields=["ideology", "behaviour"],
        adapter="Survey schema mapper",
        instructions=(
            "Download through your Pew account, export CSV/Parquet/JSON with"
            " codebook labels and weights, then confirm the mapping. Trait labels"
            " alone never create behaviour coefficients."
        ),
        download_hosts=["www.pewresearch.org", "pewresearch.org"],
    ),
    AtlasSource(
        source_id="gallup",
        name="Gallup World Poll",
        url="https://www.gallup.com/analytics/318923/world-poll-public-datasets.aspx",
        access="licensed",
        license="Subscription or partner public-release terms; no blanket redistribution",
        fields=["ideology", "behaviour"],
        adapter="Licensed survey schema mapper",
        instructions=(
            "Use your authorized subscriber export or a named public partner"
            " release. The loader requires license confirmation and preserves run"
            " scope. It never fabricates access or coefficients."
        ),
        download_hosts=["www.gallup.com", "analytics.gallup.com"],
    ),
    AtlasSource(
        source_id="anes",
        name="American National Election Studies",
        url="https://electionstudies.org/data-center/",
        access="public",
        license="Public-use research/statistical terms with attribution; restricted files excluded",
        fields=["ideology", "education", "income", "behaviour"],
        adapter="Survey schema mapper",
        instructions=(
            "Use a public-use study export, the release codebook and weights."
            " Convert outcome codes to documented binary actions before fitting;"
            " unsupported special codes fail validation."
        ),
        download_hosts=["electionstudies.org"],
    ),
]
SOURCE_BY_ID = {source.source_id: source for source in SOURCES}


def fetch_source(source_id: str, url: str, access_confirmed: bool) -> tuple[str, bytes]:
    source = SOURCE_BY_ID[source_id]
    if source.access != "public" and not access_confirmed:
        raise ValueError("Confirm your access rights or upload an authorized export")
    for _ in range(5):
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in source.download_hosts
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Download must use HTTPS on an approved source host")
        with httpx.stream("GET", url, timeout=120, follow_redirects=False) as response:
            if response.is_redirect:
                from urllib.parse import urljoin

                url = urljoin(url, response.headers["location"])
                continue
            response.raise_for_status()
            contents = bytearray()
            for chunk in response.iter_bytes():
                contents.extend(chunk)
                if len(contents) > MAX_BYTES:
                    raise ValueError(
                        "Source exceeds the configured import byte limit; choose a country/year"
                        " extract"
                    )
            return parsed.path.rsplit("/", 1)[-1], bytes(contents)
    raise ValueError("Too many source redirects")
