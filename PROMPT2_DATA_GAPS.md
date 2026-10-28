# Prompt 2 time, DSL, and recorded-output audit

This register describes the shipped Prompt 2 default and the evidence boundary of the saved
global demo. It complements `PROMPT1_DATA_GAPS.md` and `MISSING.md`.

## Executable default

The installed default is `base-1.0.0+pipeline-7`. Its cached duration run is
`e4f1220c21c34ddd949448633b331803`, with run hash
`sha256:0bbd73e2de4e778ff185a449cebc36f74a2c4339c18b411558e27f77ac1aa9ac`.
The run preserves 120 source-tier search records, 200 country/region/action candidates, ten
chosen global estimates, the default-state snapshot, and all preceding cache versions.

The active research catalog covers 12 countries, eight canonical regions, and all ten shipped
actions. Its 200 place/action profiles are executable duration overrides: eight are measured and
192 are estimated. Resolution uses the agent's country, then region, then the labelled global
fallback. The global fallback remains a WPP-population-weighted estimate across the 12 represented
countries because instruments, survey years, populations, mappings, and denominators differ.

| Action | Minimum hours | Median hours | Maximum hours | Runtime status |
| --- | ---: | ---: | ---: | --- |
| Bad work outcome | 0.86 | 6.86 | 10.33 | Estimated global default |
| Eat breakfast | 0.11 | 0.42 | 1.26 | Estimated global default |
| Eat dinner | 0.17 | 0.52 | 1.55 | Estimated global default |
| Eat lunch | 0.17 | 0.52 | 1.04 | Estimated global default |
| Exercise | 0.21 | 1.04 | 3.75 | Estimated global default |
| Personal care | 0.14 | 0.55 | 1.65 | Estimated global default |
| Skip lunch | 0.17 | 0.52 | 1.04 | Estimated proxy |
| Sleep | 6.18 | 9.18 | 13.39 | Estimated global default |
| Social activity | 0.24 | 1.45 | 6.51 | Estimated global default |
| Work or study | 0.87 | 6.84 | 10.50 | Estimated global default |

Probability evidence and duration evidence are separate. Time-use sources support the duration
range only. They are never presented as fitted evidence for whether an agent performs the action.
Action probabilities remain explicit structural defaults with 0–1 uncertainty until promoted
held-out behavior models replace them.

## Saved global demo

Run `aecbf9a40489412793ddecc5e52ddc0c` is the final checked demo:

- Rust engine `0.2.1`
- 1,000 agents, 30 days, 720 one-hour ticks, seed 1
- 12 countries, eight regions, and 12 represented cities
- 990 aggregate rows: 360 country, 240 region, 360 city, and 30 global
- Country finance, employment, agent-type mix, and action rates for every day
- One compressed spatial series per day with every recorded tick and bounding-box/city filtering
- 12 spotlight agents with full timelines; routine agents have no persisted action feed
- Every spotlight day accounts for exactly 24 hours

The visual DSL editor changes actions, formulas, typed place/time conditions, separate probability
and duration evidence, shape parameters, priorities, aggregate declarations, states, thresholds,
coefficients, and decision graphs through preview and explicit confirmation. Accepted
revisions get an immutable hash, apply to the next run through a registry overlay, and do not
change prior runs. The cached pipeline inspector exposes its search trail, candidates, selected
data, snapshot, version history, diff, activation, and one-action restore.

## Material evidence limitations

- Place-specific duration profiles cover the 12 demo countries and eight canonical regions.
  Places outside that set use the visible global estimate; weekday, age, sex, and finer subgroup
  duration strata still need compatible time-use microdata.
- Non-US duration candidates transfer occurrence-shape ratios from the cached ATUS fit after
  applying locally sourced activity totals. They remain estimates, including where the local
  input is official.
- Indonesia uses a labelled UN ESCAP regional estimate after the recorded BPS source was
  unavailable. Nigeria's retained survey covers four states rather than the whole country.
- The checked search catalog and receipt make restoration reproducible. Existing catalog results
  remain cached; a newly confirmed action uses the app's official-source duration researcher and
  records any estimated fallback. A full refresh of every local search engine remains separate.
- Routine actions resolve to canonical timed actions where possible. A custom routine without
  matching duration research receives a visible broad `default_estimated` triangular range from
  its confirmed schedule window until stronger research replaces it.
- Globe points are deterministic, privacy-preserving backend projections around recorded city
  coordinates resolved from the Rust location column at every tick. They are not addresses; exact
  within-city paths still require privacy-preserving coordinates for each runtime location.
- Default probabilities remain structural estimates. The shared Atlas still has no promoted
  place-specific fitted behavior models.
