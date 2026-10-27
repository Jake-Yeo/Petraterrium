# Data atlas

The Data tab extends the existing Petraterrium app. It uses a durable SQLite atlas and leaves the simulation's `RunConfig`, `DailySnapshot`, and `Metrics` formats intact. The simulation remains the original FAKE country-only SEIR demonstration; atlas records do not silently change its population or parameters.

## Load the complete backbone

```sh
cd backend
uv sync --locked
uv run python scripts/load_cities.py
```

The Data tab's **Load full GeoNames backbone** button does the same job. A successful load is retained across restarts and subsequent loads return its recorded metadata. To import an already downloaded release, use `--archive path/to/cities500.zip`. `--database path/to/atlas.sqlite3` selects a separate atlas; `PETRATERRIUM_ATLAS_PATH` configures the API's store.

The 2026-10-26 [GeoNames dump](https://download.geonames.org/export/dump/readme.txt) had 236,731 records. The loader retained **225,931**, excluded 10,800, and found zero duplicate GeoNames IDs. It excludes sections/neighborhoods (`PPLX`), abandoned (`PPLQ`), destroyed (`PPLW`), and historical (`PPLH`) places. It retains the dump's administrative-seat exceptions below 500 inhabitants so the official backbone is preserved. These are observed load results, not constants used by the app. Subsequent releases can have different totals.

GeoNames data is [CC BY 4.0](https://www.geonames.org/export/). The downloaded archive, its SHA-256 version, exclusion counts, date, and complete retained rows are stored locally. Runtime databases, archives, uploaded data, drafts, and mapping caches are ignored by Git and never pushed to the public source repository.

Each city has a stable `geonameid`, name and ASCII name, coordinates, country, admin1/admin2, population, and timezone. Source population zero is flagged missing. Weighted coverage uses the sum of positive city populations and reports the number of cities excluded from that denominator. GeoNames urban populations can overlap; these weights are not national population estimates.

The assigned metro policy is the top three places per country with at least one million inhabitants; other cities are assigned to the disaggregation tier. These assignments are visible, with `simulation_ready=false`. The existing repo did not contain a real country/top-metro engine or density-adjusted city projection. Those numbers are not manufactured here: the current simulator stays country-only until a real-data simulation implementation can use the atlas correctly. Imported WorldPop/GPW densities are stored separately for that future step.

## Coverage semantics

The canonical marginal fields are `age_sex`, `income`, `education`, `ideology`, and `household_size`.

| Status | Meaning |
| --- | --- |
| Present | City-specific observed data matched by stable ID or an unambiguous name/country match |
| Inherited | A country archetype applies to this city |
| Imputed | A regional/admin1 archetype applies to this city |
| Missing | No applicable value exists in the selected scope and date |

Resolution prefers city observations over regional archetypes over country archetypes. Within the same geography, the run's version takes precedence over the shared version, then the latest committed version wins. Older versions remain readable. A city status is missing if any field is unresolved; otherwise it is imputed if any field is imputed, inherited if any is inherited, and present only when every field is observed locally. Per-field statuses retain their individual distinctions.

The summary reports full/partial/none twice: for direct data, and for direct plus inherited data. Imputations never increase either total. Coverage for each field is reported unweighted and weighted by city population. The main city coverage percentage is direct; the adjacent percentage includes inheritance. `resolved_coverage_percent` additionally includes imputations and is kept separate.

The gather list shows the 20 largest gaps in city-specific observations, including inherited/imputed fields that still need local observations. The city table remains complete and paged; country, tier, status, search, and missing-field filters operate on the server. Each overview returns city rows, all-city totals, and ranked gaps from one SQLite read transaction and one revision. A committed import changes the underlying records, so the next overview updates all three together.

## Extended city-feature dump

Build the redistributable dump from the official bulk releases:

The current generated artifact is published in the [City feature dump 2026-10-26 release](https://github.com/Jake-Yeo/Petraterrium/releases/tag/data-atlas-2026-10-26).

```sh
cd backend
uv run python scripts/build_city_feature_dump.py --install-shared
```

The explicit `--install-shared` option publishes derived canonical country marginals and the latest BLUE_DB electoral alignment to the shared atlas. Electoral alignment resolves through a city-to-LAU spatial crosswalk and is always `imputed`; it never counts as direct or inherited ideology. Omit the option to build the files without changing atlas coverage. `--refresh` downloads current source releases again. `--data-directory`, `--output`, and `--database` select alternate locations.

The 2026-10-26 build produced 225,931 city rows and these feature collections:

| Collection | Geography | Status when resolved to a city | Contents |
| --- | --- | --- | --- |
| GeoNames cities500 | City point | Present | All 19 source columns, including alternate names, feature codes, admin levels, elevation, DEM, timezone, and modification date |
| GHS-UCDB R2024A v1.2 | Urban-centre polygon | Imputed | 2,805 attributes in 15 themes for 11,422 urban centres; 24,673 GeoNames city points fall inside 9,411 centres |
| World Development Indicators | Country | Inherited | 1,492 redistributable series, 7,457,950 historical values, and 249,804 latest values for 216 economies |
| UN Household Size and Composition 2026 | Country | Inherited | 39 features, 33,114 historical values from 1,129 source records, and 5,853 latest per-feature values for 200 countries or areas |
| BLUE_DB v2025.1 | Local administrative unit | Imputed | 356 national or European Parliament elections, 1,369,765 local result rows, and 3,899 party/candidate records across 31 European countries |

The dump is written to `backend/data/city_feature_dump/`:

| File | Purpose |
| --- | --- |
| `manifest.json` | Source URLs, releases, SHA-256 hashes, counts, output checksums, transform version, and data semantics |
| `cities.parquet` | Complete filtered GeoNames backbone and simulation tier |
| `city_feature_availability.parquet` | Per-city spatial, inherited, and total available feature counts |
| `blue_electoral_results.parquet` | LAU-election turnout, valid ballots, party vote JSON, party-family counts and shares, and validation flags |
| `blue_elections.parquet` | Election dates, chambers, rounds, ballot types, source files, and party columns |
| `blue_parties.parquet` | National party/candidate identity, Party Facts links, ideology class, and source metadata |
| `blue_eu_parties.parquet`, `blue_ep_groups.parquet` | European party federation and Parliament group metadata |
| `blue_geographies.parquet` | BLUE_DB LAU, NUTS, historical-name, and special electoral-unit catalog |
| `blue_city_matches.parquet` | GeoNames-to-2024-GISCO-LAU point-in-polygon matches, always flagged `imputed` |
| `blue_city_electoral_availability.parquet` | Election count and latest election date for every spatially matched city |
| `electoral_source_catalog.parquet` | Loaded and planned official election/survey sources for Europe, Asia and the Americas |
| `ucdb_urban_centres.parquet` | UCDB identity, names, country, population, centroid, area, and WKB boundary |
| `ucdb_city_matches.parquet` | GeoNames-to-UCDB point-in-polygon matches, always flagged `imputed` |
| `ucdb/*.parquet` | One wide table per UCDB theme, joined by `ID_UC_G0` |
| `ucdb_feature_catalog.parquet` | Attribute label, theme, group, unit, upstream source, method, year, and licence |
| `wdi_country_history.parquet` | Redistributable country-indicator-year values |
| `wdi_country_latest.parquet` | Latest country value for each WDI indicator |
| `wdi_feature_catalog.parquet` | WDI definitions, units, topics, methods, limitations, source, and per-series licence |
| `un_household_country_history.parquet` | All UN source-year household features |
| `un_household_country_latest.parquet` | Latest value per country and household feature |
| `un_household_feature_catalog.parquet` | Household feature definitions, units, source, and licence |
| `canonical_country_marginals.parquet` | Validated age/sex, income-quintile, education, and household-size values used by the organizer |

Resolve WDI and UN household values with `cities.country_code = *_country_latest.country_code`; those values remain inherited. Resolve UCDB values with `cities.geonameid = ucdb_city_matches.geonameid`, then join `ucdb_city_matches.ucdb_id = ucdb/*.ID_UC_G0`; those values remain spatially imputed because an urban-centre polygon is not the same thing as a city-specific survey. Resolve electoral data with `cities.geonameid = blue_city_matches.geonameid`, then `blue_city_matches.gisco_id = blue_electoral_results.gisco_id`.

The current canonical build contains 216 age/sex, 162 income, 148 education, and 189 household-size country observations. This yields inherited city coverage of 99.83%, 97.88%, 90.63%, and 98.53%, respectively. Direct coverage remains zero because none of these country or urban-centre sources is a city-specific observed marginal.

BLUE_DB maps 78,969 GeoNames cities into 2024 local administrative units; 68,667 have a result in the archive. Party-family alignment is available for those cities as an imputed percentage of valid ballots. Direct and inherited ideology coverage remain zero, and 157,264 cities have no electoral alignment. The archive classifies 99.24% of its 2,861,474,118 valid votes; unclassified parties remain an explicit `unknown` category. The loader flags 106 rows with negative upstream registered/invalid counts and preserves those source values instead of silently repairing them.

This electoral measure answers “how did valid ballots in the containing municipality split across BLUE_DB party families?” It does not answer “what percentage of all city residents personally identify as left or right?” Turnout, invalid/blank ballots, unknown party classifications, election date, ballot type, source file, release, and version remain separate so the distinction can be audited.

Six WDI series under SIPRI-specific terms are excluded from the redistributable output. UCDB contains 233 real data columns whose native IDs do not match its accompanying index workbook; the dump retains their values and native IDs with dataset-level UCDB provenance instead of inventing labels. Three `Unnamed` spreadsheet merge artifacts are excluded. Missing and nodata values remain null. Eurostat GISCO boundaries are used only to derive the city-to-LAU crosswalk and are not republished in the dump.

## Electoral alignment outside Europe

Government and election-agency sites do provide detailed results, but the scalable source is usually the national or state election authority rather than a city website. City sites often publish PDFs, dashboards, or local contests with unstable schemas. National portals provide consistent identifiers and bulk files, although city aggregation still needs boundary crosswalks and party-family classification.

| Region | Canonical source | Available grain | Loader state |
| --- | --- | --- | --- |
| India | [Election Commission of India statistical reports](https://www.eci.gov.in/statistical-reports) | Constituency; polling-station turnout for supported releases | Planned; boundaries and party-family history required |
| China | [Chinese General Social Survey](https://cgss.ruc.edu.cn/) | Authorized survey sample geography | Planned authorized extract; no comparable competitive municipal party-vote proxy |
| Canada | [Elections Canada official voting results](https://www.elections.ca/content.aspx?section=res&dir=rep/off) | Poll-by-poll CSV | Planned; poll boundaries must be aggregated to cities |
| Mexico | [INE election results](https://ine.mx/voto-y-elecciones/resultados-electorales/) | Casilla, section, district, municipality and state | Planned; municipality data is the preferred city crosswalk |
| Brazil | [TSE election results and open data](https://www.tse.jus.br/eleicoes/resultados-eleicoes) | Municipality, zone and section | Planned |
| Argentina | [DINE results system](https://www.argentina.gob.ar/dine/resultados-electorales) | Published electoral geographies; CSV and API | Planned |
| Chile | [SERVEL historical results](https://www.servel.cl/) | Table, district and commune depending on election | Planned |
| Colombia | [Registraduría historical results](https://registraduria.gov.co/-Historico-de-resultados-electorales-.html) | Municipality through polling table for supported elections | Planned |
| Peru | [ONPE](https://www.onpe.gob.pe/) | Department, province, district and polling act | Planned; bulk stability varies by election |
| Taiwan | [Central Election Commission open data](https://data.cec.gov.tw/) | Polling place through city/county | Planned |
| South Korea | [National Election Commission](https://info.nec.go.kr/) | Administrative and electoral districts | Planned |
| Indonesia | [KPU open data](https://opendata.kpu.go.id/) | Province through regency/city and lower units by file | Planned |
| Philippines | [COMELEC](https://www.comelec.gov.ph/) | Province through city/municipality, barangay and precinct by release | Planned; machine-readable results vary |
| Japan | [Ministry of Internal Affairs election data](https://www.soumu.go.jp/senkyo/senkyo_s/data/index.html) | National and prefectural; municipal files are decentralized | Planned and fragmented |

The generated `electoral_source_catalog.parquet` records these sources, their measurement, grain, access, reuse caveat, and loader state. Planned means the source has been identified and verified, not that its records are already present in the dump.

## Import workflow

1. Create or select an existing simulation run, then open **Data → Import data**.
2. Select CSV, Parquet, or JSON. A canonical source loader also accepts a single-file ZIP, gzipped CSV, or a WorldPop/GPW GeoTIFF. Enter source, data date, publication date, release version, uploader, and scope. The scope is always a run.
3. Preview headers and five sample rows. Review the proposed mapping. An ambiguous `?` must be replaced with an explicit target or cleared to explicitly ignore it.
4. Confirm and validate. No atlas observations are written at preview or validation time. Failed validation identifies exact row numbers and fields and blocks the commit. Missing values are counted by field.
5. Commit the validated mapping. This creates a new immutable version. The previous version remains in the version history.
6. Optionally use **Promote…** on a committed run version. Confirm the effect and redistribution rights. Promotion creates a new shared version and preserves the private original. Licensed IPUMS/DHS/Gallup/Pew source imports are kept private by policy.

Use a city `geonameid` for direct observations; a country ISO code without a city for inheritance; or country plus admin1 for regional imputation. A city ID already supplies its country; an additionally supplied country must match. Fractional IDs and ambiguous city names fail validation.

Distributions are JSON objects mapping source category labels to percentages, or dotted columns such as `age_sex.female_0_14`. Values must be finite, within 0–100, and sum to 100 within 0.01 percentage points. A distribution needs at least two labeled categories. Whole-field and component mappings cannot be mixed. Raw uploaded distributions are never renormalized or rewritten by the LLM. Household means must be greater than zero and at most 30. Mean income requires explicit currency/time units; negative source incomes are permitted within the declared validation bounds.

The default upload limits are 256 MiB and two million rows. `ATLAS_MAX_IMPORT_BYTES` and `ATLAS_MAX_IMPORT_ROWS` configure them. Larger sources should use an authorized country/year extract rather than silently truncating rows. Draft files and their mapping/validation reports are durable in the local atlas database.

Run scopes with imported data remain selectable as archived scopes after the simulation server restarts. Drafts can be reopened with **Resume review**; confirmation and validation are required again before committing. Creating a new upload still requires a current run.

## LLM mapping

The centralized mapper uses the [OpenAI Responses structured-output interface](https://developers.openai.com/api/docs/guides/structured-outputs). Set `OPENAI_API_KEY` on the API process. `ATLAS_MAPPING_MODEL` defaults to `gpt-4.1-mini`; model, prompt version, usage, and an estimated cost are recorded. Estimates for that default use its [published token rates](https://developers.openai.com/api/docs/models/gpt-4.1-mini); estimates for other models are unavailable rather than invented.

Only headers and five sample rows are submitted, with `store=false`. Mapping proposals are cached within their run, model, prompt version, and sample/header identity. Provider failures are disclosed and not permanently cached. Exact canonical-header suggestions remain available without an LLM; ambiguous columns still require human resolution. The model never commits, rewrites data, infers coefficients, or fills missing observations.

## Behaviour fitting

Behaviour surveys are tracked separately from marginals. Map respondent traits as `trait.<name>`, a measured binary action as `outcome`, an optional `behaviour` name, and source weights as `survey_weight`. Without a trait-to-action link, the version is label-only and has no coefficients.

Linked observations feed a deterministic, weighted classical logistic regression. At least 30 linked rows and both outcomes in both partitions are required. The split is 80/20 by a stable row hash; feature encodings are learned on training rows only. A candidate becomes available only if its held-out weighted log loss beats the existing comparable model on that same holdout, or an intercept-only baseline when no model exists. Incomparable incumbent features block replacement. Rejected candidates remain versioned, with metrics, and cannot displace a better model. Missing survey weights use uniform weights; this is a fitting convention, not an invented behaviour coefficient.

Shared promotion repeats the held-out comparison in the destination scope. Country behaviour availability and provenance appear in city rows and details. No fitted atlas model is silently connected to the FAKE simulator.

Historical views filter both declared observation/source date and publication date. Future-dated imports are rejected. `GET /atlas/overview?scope=…&as_of=YYYY-MM-DD` resolves eligible historical versions; `GET /atlas/cities/{id}` applies the same rule. An imported `observation_date` later than its declared data date is rejected. Dates are provenance supplied by the source/uploader and still need to be checked against the actual release.

## Canonical source loaders

| Source | Loader and access |
| --- | --- |
| [IPUMS International](https://international.ipums.org/international/conditions.shtml) | Licensed extract; weighted `AGE`, `SEX`, `PERWT`, optional `INCWAGE`/`EDATTAIN`, or confirmed canonical export. Country codes and special codes require the release dictionary. Registration does not imply redistribution rights. |
| [US PUMS](https://www.census.gov/programs-surveys/acs/microdata.html) | Weighted person CSV (`AGEP`, `SEX`, `PWGTP`, `SCHL`, `PINCP`) or separate household CSV (`NP`, `WGTP`). Country-level archetypes are explicitly inherited. Source income values are not silently inflation-adjusted. |
| [UN WPP](https://population.un.org/wpp/) | Native `ISO3_code`, `Time`, `AgeGrp`, `PopMale`, `PopFemale` exports; selects the declared year and medium/historical variant, excludes aggregates, derives country age/sex percentages, and records processing notes. |
| [WorldPop](https://www.worldpop.org/) | Public GeoTIFF counts or density, with explicit units. City-centre grid samples are imputed density; nodata/zero samples remain missing. |
| [GPW](https://www.earthdata.nasa.gov/) | Authorized NASA/SEDAC GeoTIFF export through the same grid loader. Release access and units must be supplied. |
| [DHS](https://dhsprogram.com/data/Access-Instructions.cfm) | Approved project export through the confirmed marginal/survey schema mapper; no automatic account access or dataset redistribution. |
| [WVS](https://www.worldvaluessurvey.org/) | Authorized wave export with release-specific codebook labels and weights, through the confirmed survey mapper. |
| [ESS](https://www.europeansocialsurvey.org/data-portal) | Authorized wave export, with its codebook and CC BY-NC-SA/release terms preserved. |
| [Pew](https://www.pewresearch.org/short-reads/2021/10/22/how-to-access-pew-research-center-survey-data/) | Account-authorized CSV/Parquet/JSON export through the survey mapper. Native SPSS archives must first be exported to a supported table format. |
| [Gallup World Poll](https://www.gallup.com/analytics/318923/world-poll-public-datasets.aspx) | Authorized subscription or named public-partner export through the survey mapper; the application does not invent access. |
| [ANES](https://electionstudies.org/data-center/) | Public-use study export with release codebook and weights, through the survey mapper. Restricted-use files are excluded. |

Each loader uses the same source/date/version/scope records, staging, validation, and commit operations as uploads. Approved-host HTTPS download URLs can be loaded from the import dialog; registered/licensed sources require explicit access confirmation. Redirects must remain on approved hosts. Loaders do not bypass accounts or license gates and do not guess opaque survey codebooks.

## Verify

```sh
cd backend
uv run pytest
uv run ruff check .
uv run python scripts/export_contracts.py --check
cd ../frontend
npm run build
npm run test:e2e
cd ..
git diff --check
```

Browser tests use their own `.playwright/atlas.sqlite3`, API port 8011, and frontend port 5181. Their small FAKE GeoNames fixture never changes the live atlas or imports. Simulation golden/API/SSE tests remain in place alongside coverage, import, source, scope, mapping, and fitting checks.
