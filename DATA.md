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
