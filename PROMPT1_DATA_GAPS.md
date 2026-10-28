# Prompt 1 source and provenance audit

This register is the human-readable companion to the deterministic audit in
[`prompt1_source_audit.py`](backend/petraterrium/simulation/prompt1_source_audit.py).
Run the following command to produce the full machine-readable JSON report:

```sh
cd backend
uv run python -m petraterrium.simulation.prompt1_source_audit
```

The audit checks the checked-in default manifest, the global finance pack, and
[`MISSING.md`](MISSING.md). It checks recorded metadata and internal consistency. It does
not independently re-research publications, visit source URLs, or certify empirical
claims.

## Current global population

The checked-in default contains 1,000 synthetic agents across 12 countries and eight
populated canonical regions. `Rest / unassigned` has zero agents.

| Country | Agents | Canonical region |
| --- | ---: | --- |
| Australia | 6 | Oceania |
| Bangladesh | 36 | Asia excluding China and India |
| Brazil | 45 | Latin America & Caribbean |
| Canada | 8 | Northern America |
| China | 304 | China |
| Indonesia | 60 | Asia excluding China and India |
| India | 307 | India |
| Mexico | 28 | Latin America & Caribbean |
| Nigeria | 49 | Africa |
| Pakistan | 53 | Asia excluding China and India |
| Russian Federation | 31 | Europe |
| United States of America | 73 | Northern America |

| Canonical region | Agents |
| --- | ---: |
| India | 307 |
| China | 304 |
| Asia excluding China and India | 149 |
| Northern America | 81 |
| Latin America & Caribbean | 73 |
| Africa | 49 |
| Europe | 31 |
| Oceania | 6 |
| Rest / unassigned | 0 |

The static audit finds no Canadian source attached to a non-Canadian agent and no source
place outside the agent's own country or its labelled canonical region.

## Major-field evidence

`Own-country source` describes geography. It does not mean that an individual synthetic
agent was measured. Every field value in the generated population is a synthetic draw.

| Country | Age and sex | Education | Specialization | Occupation | Personality | Values and ideology | Finance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AU | Own-country marginal | Regional imputation | Own-country measured distribution | Regional imputation | Regional imputation | Regional imputation | Own-country macro inputs; person values imputed |
| BD | Own-country marginal | Own-country marginal | Own-country measured distribution | Own-country marginal | Own-country literature estimate | Mixed country and regional imputation | Own-country macro inputs; person values imputed |
| BR | Own-country marginal | Regional imputation | Own-country measured distribution | Own-country marginal | Own-country literature estimate | Own-country measured and literature inputs | Own-country macro inputs; person values imputed |
| CA | Own-country marginal | Regional imputation | Own-country measured distribution | Regional imputation | Regional imputation | Regional imputation | Own-country Statistics Canada marginals; person values imputed |
| CN | Own-country marginal | Own-country marginal | Own-country estimated distribution | Own-country source marked imputed | Own-country literature estimate | Own-country measured and literature inputs | Own-country macro inputs; person values imputed |
| ID | Own-country marginal | Own-country marginal | Own-country measured distribution | Own-country marginal | Own-country literature estimate | Own-country measured and literature inputs | Own-country macro inputs; person values imputed |
| IN | Own-country marginal | Own-country marginal | Own-country measured distribution | Own-country marginal | Own-country literature estimate | Own-country measured and literature inputs | Own-country macro inputs; person values imputed |
| MX | Own-country marginal | Own-country marginal | Own-country measured distribution | Own-country marginal | Own-country literature estimate | Own-country measured and literature inputs | Own-country macro inputs; person values imputed |
| NG | Own-country marginal | Own-country marginal | Own-country estimated distribution | Own-country marginal | Own-country literature estimate | Own-country measured and literature inputs | Own-country macro inputs; person values imputed |
| PK | Own-country marginal | Own-country marginal | Own-country measured distribution | Own-country marginal | Own-country literature estimate | Own-country measured and literature inputs | Own-country macro inputs; person values imputed |
| RU | Own-country marginal | Own-country marginal | Own-country measured distribution | Own-country marginal | Own-country literature estimate | Own-country measured and literature inputs | Own-country macro inputs; person values imputed |
| US | Own-country marginal | Own-country marginal | Own-country measured distribution | Own-country marginal | Own-country literature estimate | Own-country measured and literature inputs | Own-country macro inputs; person values imputed |

The exact regional gaps are Brazil education; Canada and Australia education,
occupation, personality, values, and ideology; and part of Bangladesh values. These use
their named canonical-region distributions and retain the `regional_imputed` scope.

Age and sex use UN World Population Prospects 2024 Revision country marginals for the
2023 de facto population, recorded as published on 2024-07-11. Education uses World Bank
World Development Indicators transforms. Occupation uses ILOSTAT ISCO-08 transforms.
Personality uses OpenPsychometrics Big Five response aggregates with high uncertainty.
Values use a mixture of World Values Survey Wave 7, Global Preferences Survey, and
Schwartz culture-level inputs. These source names and versions are recorded, but most
use-level records lack the original title, English translation, language, discovery
source, and exact represented population required by the revised prompt.

## Education specialization

The in-app research pipeline now supplies an ISCED-F-compatible own-country distribution
for every represented country. In the deterministic 1,000-agent population, 690 agents are
below the 12-year education threshold and remain structurally `not_applicable`. The other
310 qualified agents receive a specialization before tick zero. Their values are synthetic
draws from their country's distribution; they are not individual observations.

Australia, Bangladesh, Brazil, Canada, Indonesia, India, Mexico, Pakistan, Russia, and the
United States use confirmed official UNESCO UIS, OECD, or Pakistan HEC field distributions
and are labelled measured at the source-distribution level. China and Nigeria use
country-specific estimates with their reasoning, assumptions, source trail, and wider
uncertainty retained. Those estimates do not copy another country's distribution. No
country is filled with Canadian data or presented as measured from a foreign-country table.

Each country receipt records the pipeline attempt, local-first language sequence, search
engine or source, every source tried, selected sources, mapping version, represented
population, date, licence, reasoning, uncertainty, and draft or promotion status. The
distribution uses all 11 ISCED-F 2013 broad fields. The remaining empirical limitation is
the lack of joint age/sex/education and field-of-study microdata for most countries. Such
joint data would refine conditional assignment and uncertainty; its absence does not leave
a qualified agent without an executable measured or estimated specialization distribution.

| Country | Pipeline result | Distribution basis | Reference year | Uncertainty | Review state |
| --- | --- | --- | ---: | ---: | --- |
| Australia | Measured | UNESCO UIS tertiary graduates by field | 2023 | 0.05 | Confirmed |
| Bangladesh | Measured | UNESCO UIS tertiary graduates by field | 2020 | 0.05 | Confirmed |
| Brazil | Measured | OECD UOE tertiary graduates by field | 2023 | 0.05 | Confirmed |
| Canada | Measured | OECD UOE tertiary graduates by field | 2023 | 0.05 | Promoted |
| China | Estimated | China Ministry of Education graduate disciplines crosswalked to ISCED-F | 2022 | 0.35 | Confirmed |
| Indonesia | Measured | UNESCO UIS tertiary graduates by field | 2018 | 0.05 | Confirmed |
| India | Measured | UNESCO UIS tertiary graduates by field | 2023 | 0.05 | Confirmed |
| Mexico | Measured | OECD UOE tertiary graduates by field | 2023 | 0.05 | Confirmed |
| Nigeria | Estimated | National Universities Commission enrolment disciplines crosswalked to ISCED-F | 2019 | 0.35 | Confirmed |
| Pakistan | Measured | Higher Education Commission tertiary enrolment by ISCED-F field | 2021 | 0.05 | Confirmed |
| Russian Federation | Measured | UNESCO UIS tertiary graduates by field | 2019 | 0.05 | Confirmed |
| United States | Measured | OECD UOE tertiary graduates by field | 2023 | 0.05 | Confirmed |

## Finance

Canada uses Statistics Canada tables 98-10-0407-01, 11-10-0016-01, and 11-10-0223-01.
Its accounting unit is CAD. The source record retains French original titles, English
translations, dates, represented populations, and the French discovery path. The agent
values are deterministic imputations from separate marginals, not linked person records.

The other 11 countries use their own country rows from the World Bank World Development
Indicators archive recorded as released on 2026-10-08. Income uses GNI per capita PPP and
income-quintile shares. Expenses use own-country household-consumption PPP where present.
Nigeria lacks that row, so its expenses use Nigeria's GNI and adjusted net savings as an
explicit `default_estimated` fallback. Money, savings, and debt are high-uncertainty model
stocks for every non-Canadian country.

The following finance gaps remain:

- All person-level money, income, expenses, savings, and debt values are imputed.
- `PPP` is an accounting unit for the 11 non-Canadian countries, not each country's local
  currency. Explicit local-currency conversion, country price levels, wages, and
  cost-of-living evidence are not attached.
- WDI marginals do not supply linked income, spending, liquid balance, savings, debt, age,
  education, occupation, or behavior records.
- Non-Canadian finance records preserve the WDI archive source, version, date, country
  place, and represented population, but do not preserve a country-local-language search
  trace.

| Country | Current accounting unit | Own-country input | Currency and cost-of-living gap |
| --- | --- | --- | --- |
| Australia | PPP | WDI country row | AUD conversion, country price/cost series, and linked household finance are absent |
| Bangladesh | PPP | WDI country row | BDT conversion, country price/cost series, and linked household finance are absent |
| Brazil | PPP | WDI country row | BRL conversion, country price/cost series, and linked household finance are absent |
| Canada | CAD | Statistics Canada marginals | Linked person/household finance and an explicit cost-of-living series are absent |
| China | PPP | WDI country row | CNY conversion, country price/cost series, and linked household finance are absent |
| India | PPP | WDI country row | INR conversion, country price/cost series, and linked household finance are absent |
| Indonesia | PPP | WDI country row | IDR conversion, country price/cost series, and linked household finance are absent |
| Mexico | PPP | WDI country row | MXN conversion, country price/cost series, and linked household finance are absent |
| Nigeria | PPP | WDI country GNI and savings fallback for expenses | NGN conversion, direct consumption row, country price/cost series, and linked household finance are absent |
| Pakistan | PPP | WDI country row | PKR conversion, country price/cost series, and linked household finance are absent |
| Russian Federation | PPP | WDI country row | RUB conversion, country price/cost series, and linked household finance are absent |
| United States of America | PPP | WDI country row | USD conversion policy, country price/cost series, and linked household finance are absent |

Closing these gaps requires weighted country microdata for income and household finances,
dated price and cost-of-living series, currency conversion policy, and joint mappings to
agent traits. Each input must retain the original-language title and text, English
translation, source date, represented population, place, language, and discovery source.

## Local-language search provenance

The embedded specialization pipeline receipts now retain item-level search metadata for
all 12 countries. They include the original and English titles, query or direct discovery
path, engine or source used, language, place, represented population, and result of every
attempt. Canadian finance also retains its French item-level discovery trace. The older
age/sex, education, occupation, personality, values, and most finance records still lack
that complete search trail.

The audit therefore still marks every country incomplete across the full set of eight
major fields, while marking specialization search provenance complete. An English-only
trace for a place requiring a non-English local-language search remains incomplete; the
specialization receipts record the local-language attempt before the English fallback.

| Country | Own-language discovery required by the prompt | Recorded item-level languages | Exact gap |
| --- | --- | --- | --- |
| Bangladesh | Bengali (`bn`) before English | Bengali and English specialization searches | The other seven major fields lack complete item-level language, title/translation, and discovery metadata |
| Brazil | Portuguese (`pt`); Spanish (`es`) or French (`fr`) when applicable to the source population | Portuguese, English, Spanish, and French specialization searches | The other seven major fields lack complete item-level language, title/translation, and discovery metadata |
| China | Chinese (`zh`), Cantonese (`yue`), Wu (`wuu`), Uyghur (`ug`), or the applicable source-population language | Chinese and English specialization searches, including Baidu, CNKI, and Chinese official-source attempts | The other seven major fields lack complete item-level language, title/translation, and discovery metadata |
| India | Hindi (`hi`), Bengali (`bn`), Telugu (`te`), Marathi (`mr`), Tamil (`ta`), Urdu (`ur`), Gujarati (`gu`), Kannada (`kn`), Malayalam (`ml`), Odia (`or`), Punjabi (`pa`), Assamese (`as`), or the applicable source-population language | Hindi, Bengali, Telugu, and English specialization searches | The other seven major fields lack complete item-level language, title/translation, and discovery metadata |
| Indonesia | Indonesian (`id`) or Javanese (`jv`) when applicable | Indonesian, Javanese, Dutch, and English specialization searches | The other seven major fields lack complete item-level language, title/translation, and discovery metadata |
| Mexico | Spanish (`es`) | Spanish and English specialization searches | The other seven major fields lack complete item-level language, title/translation, and discovery metadata |
| Nigeria | Hausa (`ha`), Yoruba (`yo`), Igbo (`ig`), Fulfulde (`ff`), or the applicable source-population language | Hausa, Yoruba, Igbo, and English specialization searches | The other seven major fields lack complete item-level language, title/translation, and discovery metadata |
| Pakistan | Urdu (`ur`), Punjabi (`pa`), Sindhi (`sd`), Pashto (`ps`), Brahui (`brh`), or the applicable source-population language | Urdu, Punjabi, Sindhi, and English specialization searches | The other seven major fields lack complete item-level language, title/translation, and discovery metadata |
| Russian Federation | Russian (`ru`), Tatar (`tt`), or the applicable source-population language | Russian, Tatar, Kalmyk, and English specialization searches | The other seven major fields lack complete item-level language, title/translation, and discovery metadata |

Australia and the United States record their English-first specialization searches and
local-language fallbacks. Canada's registry languages are English (`en`), French (`fr`),
and Inuktitut (`iu`); its specialization receipt includes all three and its finance records
include French. Six other Canadian major fields still lack complete item-level search
metadata.

No search attempts were invented to close this gap. The audit reports only attempts stored
in the embedded pipeline receipts and continues to report absent searches as absent.

## DSL single-source audit

The revised hard DSL requirement is met by the checked-in default manifest. The audit
validates every managed DSL section before reporting it as executable.

| Domain | Shipped DSL coverage | Runtime behavior outside or unresolved in the DSL |
| --- | --- | --- |
| State formulas | The DSL contains 132 hypothesis formulas plus one executable runtime rule for each of 31 agent states | The generic compiler verifies that runtime targets and declared propagation coefficients agree, then the Rust weighted-state interpreter applies them |
| Finance initialization | The managed `finance_initialization` section contains validated Canada Statistics Canada and global WDI programs with 12 output formulas for income, expenses, money, savings, debt, and supporting outputs | Country loaders resolve measured or imputed inputs, then the shared expression interpreter evaluates the manifest program before tick zero |
| Finance tick accounting | The DSL contains nine action cash-flow formulas and confirmed rules for all five ledgers: income, expenses, money, savings, and debt | The Python compiler translates the rules and the Rust weighted-input interpreter applies them without named ledger equations in runtime code |
| Action formulas | All ten default actions have DSL formulas and 18 runtime probability rules | `eat_lunch` and `skip_lunch` are complementary branches of the exclusive `midday_meal` group; matching condition partitions sum to 1 and the Rust runtime makes one seeded categorical draw per eligible agent and tick |
| Decision programs | One two-edge decision module and its coefficients are in the DSL with global place scope | The generic runtime compiles the confirmed DSL program for all 12 represented countries |
| Interactions | The `basic_social_contact` tree, confirmed cross-country rule, numeric factors, relationship evidence, and 1,000 seeded relationship edges are in the shipped DSL | The generic runtime serializes and executes the shipped definitions; the values remain default estimates rather than measured behavior |

Finance initialization is serialized in the managed manifest as two validated finance
initialization programs. The country-specific loaders prepare source inputs, while the
shared interpreter evaluates the program expressions and deterministic draws. The
resulting synthetic person values remain imputations; DSL ownership closes the execution
ownership gap, not the empirical data gap.

The midday execution gap is also closed. `eat_lunch` and `skip_lunch` use the same four
stress and financial-stress condition partitions. Their probabilities are complementary
within each partition, and the exclusive group uses one seeded categorical draw. Only the
selected branch applies its state effects and cash flow.

## Requirements that remain estimated

- All ten default action definitions carry `default_estimated` evidence with 0–1
  uncertainty and no fitted place model. The ten actions contain 18 structural probability
  rules. The executable lunch choice is still a broad default rather than a measured or
  fitted country rate.
- All 31 executable state runtime rules are global `default_estimated` structural rules.
  The DSL owns their formulas and bounds, but that ownership does not turn them into fitted
  population evidence.
- All generated initial state vectors are `default_estimated` with uncertainty 1.0; all 31
  state initialization definitions remain `unknown`.
- Person-level finance is imputed in all 12 countries. Money, savings, and debt stocks are
  model estimates; Nigeria expenses also use an own-country estimated fallback.
- Personality is a high-uncertainty literature estimate for the ten priority countries and
  a regional imputation for Canada and Australia.
- Parts of values and ideology use literature estimates; Bangladesh is mixed with a
  regional imputation, while Canada and Australia are regional imputations.
- Brazil education and Canada/Australia education and occupation remain regional
  imputations. China occupation uses a country source whose provenance status is imputed.
- Specialization uses own-country measured distributions for ten countries and
  country-specific estimates for China and Nigeria. Qualified agents receive
  an ISCED-F value; joint age/sex/education and field-of-study evidence remains a refinement
  gap, especially for the two estimated distributions.
- The shipped cross-country relationship and interaction factors are structural DSL
  estimates with uncertainty 1.0, not measured social behavior.
- `beta_health_stress` is numeric while its evidence is marked `unknown`.

## States, actions, and relationships

The shipped manifest explicitly records these evidence conditions:

- All 31 state initialization definitions are `unknown`. Generated state vectors are
  separately labelled `default_estimated` with uncertainty 1.0.
- Across state decision modifiers, propagation, event effects, and recovery links, 120 are
  `unknown` and eight have literature support for direction only. These unresolved
  hypotheses are evidence gaps; the separate 31 executable runtime update rules are
  present in the DSL.
- Four relationship-state evidence links are `unknown`.
- All ten default action definitions are `default_estimated`. They contain stated default
  reasons and 0–1 uncertainty, but no source IDs or per-place search logs. All ten are
  executable; lunch and meal-skipping are mutually exclusive default estimates rather
  than fitted rates.
- `beta_health_stress` has a numeric value while its attached evidence is `unknown`. It
  must be treated as a structural demo value, never a measured or fitted effect.

The defaults remain executable under the evidence guard, but their rates and effects are
not population predictions. The full version requires local-first source searches and
linked longitudinal state, context, action, outcome, and finance data followed by held-out
fitting for each action and place.

## Acceptance evidence not stored in the default manifest

The checked-in manifest contains cross-country relationship edges and a confirmed
interaction rule, but it does not contain a run receipt proving that a cross-country
interaction occurred during the 1,000-agent run. It also does not contain the required
global, country, and region distribution-comparison receipt. This audit does not claim
those UI acceptance paths fail; it records that the static artifacts cannot prove they
passed.

[`MISSING.md`](MISSING.md) already records the country-feature imputations, missing linked
finance microdata, and missing fitted action coefficients. The specialization pipeline
closes the executable-distribution gap while retaining the stronger joint-data requirement
as a refinement. The full local-language search-log gap for the other fields, local-currency
and cost-of-living gap, cross-country interaction receipt, and global and per-place
distribution-comparison receipt remain open here so they are visible before the demo is
described as complete.
