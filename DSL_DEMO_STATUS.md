# Rust DSL demo status

## Implemented

- The only numeric tick entry point is `run_program` in `engine-rust/src/text_dsl/runtime.rs`.
  It parses no DSL during ticks and continues to use the compiled indexed execution plan.
- The only composition entry point is `run_composition` in
  `engine-rust/src/text_dsl/compositions.rs`. It accepts a composition or represented composition
  population ID and delegates every detailed tick to `run_program`.
- `CompositionDefinition` is the single recursive model for neighbourhoods, municipalities,
  divisions, and arbitrary user-defined levels. A level is a DSL string. Rust has no level enum,
  level match arm, or municipality/division runner.
- Legacy `neighbourhood` and `neighbourhood_population` syntax parses into the generic composition
  model. The compatibility adapter retains the previous report IDs, titles, state, and reports.
- Generic `composition` blocks define a level, weighted children, places or institutions,
  parameters, sparse adjacency, boundary flows, and outputs. Children may be agent archetypes or
  other compositions.
- Recursive composition keeps a fixed detailed sample budget. The represented weights never
  expand into represented object counts. A division containing two municipalities still simulates
  180 agents in the shipped example.
- Place scope follows the composition tree. Parent-declared places are shared by children; other
  places are namespaced at the closest declaring composition. This lets neighbourhoods meet at
  shared institutions without making every place global.
- Visit flows move selected households to a shared place. Transfer flows change composition
  membership while preserving agent IDs, traits, state, household links, and relationships.
  Sparse adjacency controls allowed direct flows and scales them by distance.
- Composition reports include the root aggregate, immediate-child rows, boundary-flow counts and
  rates, cross-child interaction counts and rates, base per-place reports, and base per-agent-type
  reports. Income, stress, and vote outputs retain standard deviation.
- The default DSL defines `Toronto` and `Vancouver` as municipalities and `Ontario` as a division.
  It also defines composition-scoped SchoolDistrict, Hospital, ShoppingCentre, and Transit places.
- Toronto and Vancouver define inter-neighbourhood visits, transfers, adjacency, concrete
  parameters, and output metrics. Ontario recursively composes both municipalities using the same
  runner and records their internal flows.
- Municipality and division aggregate functions reuse the Prompt 2 low/high-grid learner,
  interpolation, versioned artifacts, DSL/input hashes, time points, invalidation, and zero-tick
  cache-hit path.
- A generic program-level aggregate branch was added. `engine-rust/dsl/finance_demo.dsl` defines a
  market using only agents, a place with price state, decisions, actions, effects, reports, and an
  aggregate function. It runs through `run_program`; there is no finance or market runner.
- `place_state(place, field)`, `flow_count(flow)`, and `flow_rate(flow)` are generic report metrics.
  Composition-only place scope keeps new institutions out of unchanged Town and weighted reports.
- Rust validation returns every composition with its DSL level. Python forwards generic
  composition IDs, and the existing frontend selector renders neighbourhood, municipality,
  division, and represented composition choices through one control.
- Engine version is `0.7.0`. Nothing was pushed.

## Implemented but narrower

- Detailed boundary flows use concrete DSL rates and are applied at composition initialization.
  They are deterministic and auditable, but they do not yet recalculate each day from changing
  unemployment, jobs, rent, or stress.
- The synthetic tests prove that shared-place state can be updated by agents from multiple child
  compositions. The shipped daily-life program uses Work, School, Bar, and Cinema for its active
  shared interactions; the four newly named institutions are available as composition-scoped
  places, and Transit is used by visit flows, but the default does not define a separate action
  routine for every new institution.
- A division run executes the nested municipality flows, but it defines no inter-municipality flow.
  The final Ontario run therefore records six internal municipality flows and zero Toronto-to-
  Vancouver interactions.
- Composition parameters are parsed and preserved as DSL data. Aggregate-function inputs drive
  learned output changes; composition parameters are not yet expression variables inside flow
  rates.
- Aggregate learning still uses the two endpoints of each input range and multilinear
  interpolation. Fast-forward beyond day 30 repeats the learned endpoint.
- The finance example models price through generic place state and agent actions. It is an
  expressiveness proof, not an order-book or exchange calibration.

## Deferred and not part of this demo

- Country and world composition, country/world flows, and global represented-population weights.
- Multi-level top-down and bottom-up feedback, convergence, and time-varying cached composition
  functions.
- Atlas, GeoNames, WDI, external imports, research pipelines, evidence guards, and fitted models.
- Globe work, country polygons, graphs, inheritance views, decision-tree views, visual editors,
  and per-level management panels.
- Real-world calibration or prediction claims and interrupted-run pause/resume UI.

## Focused verification

- Generic composition parser, arbitrary level reuse, exact middle/upper weighting, shared-place
  interaction, transfer preservation, adjacency isolation, and zero-tick cache reuse: `4 passed`.
- Expanded 300-agent individual run versus a composition run over 30 days: `1 passed`; population,
  income, stress, health, vote, kids, action rate, commuting rate, and cross-group interaction rate
  stayed within the required 10 percent tolerance.
- Legacy neighbourhood parser, weighting, represented counts, place index, cache, determinism, and
  300-agent comparison: `7 passed` in `21.11s` debug time.
- DSL-only finance run, deterministic replay, place price, buy/sell reports, aggregate learning,
  and zero-tick cache hit: `1 passed`.
- Focused Python API routing and generic composition forwarding: passed.
- Focused browser municipality/division edit, detailed run, flow reports, relearn, and zero-tick
  cache test: `1 passed` in `8.4s`.
- Frontend production build: passed in `0.276s`.
- Targeted Ruff checks, generated-contract check, Rust format/check, and `git diff --check`: passed.
- The full backend test suite and full frontend end-to-end suite were not run, as required by this
  prompt.
- Source grep finds no `run_neighbourhood`, `run_municipality`, `run_division`, or named domain
  runner. Shipped municipality, division, neighbourhood, institution, and action names do not
  occur in Rust engine source.

## Performance

- Town, 30 days / 720 ticks / 130 agents: `0.428s`.
- Town, 365 days / 8,760 ticks / 130 agents: `4.377s`.
- Weighted household population, 30 days / 180 agents: `0.406s`.
- Detailed neighbourhood, 30 days / 180 agents: `0.488s`.
- Detailed municipality, 30 days / 180 agents: `0.732s`.
- Detailed division, 30 days / 180 agents: `0.606s`.
- Toronto aggregate learning: `2.257s` and `518,400` agent ticks.
- Toronto persisted-artifact cache hit: `0.0141s` and `0` agent ticks.
- DSL-only finance run, 30 days / 12 agents: `0.043s`.
- Default DSL hash: `sha256:19135dd666e5bda8edfa9df06b42eec199bba0fa1e13207dc28750980feb81d4`.

## Final demo run

- Legacy golden record: `87edc98083d542d2a63ca69a0917a69c`.
- Engine: `0.7.0`; seed: `1`; duration: `365` days / `8,760` ticks.
- Population: `100` sampled adults plus `30` generated children.
- Current state and every report are exactly equal to the persisted Prompt 3 golden after excluding
  only protocol and engine-version metadata.

## Final weighted archetype run

- Legacy golden record: `6fef20f60e3a4ae2a3035c1253f1281e`.
- Seed: `1`; duration: `30` days / `720` ticks; simulated agents: `180`.
- Current state and every report are exactly equal to the persisted Prompt 1 weighted golden.

## Final neighbourhood run

- Legacy golden record: `b1ac7e29863b4e8c8395e19bafd64c99`.
- Neighbourhood: `UrbanLiberal`; seed: `1`; duration: `30` days / `720` ticks.
- Simulated agents: `180`; reports: `5`; runtime: `0.488s`.
- Current state and every report are exactly equal to the persisted Prompt 3 neighbourhood golden.

## Final municipality run

- Composition: `Toronto`; seed: `1`; duration: `30` days / `720` ticks.
- Simulated agents: `180`; reports: `7`; runtime: `0.732s`.
- Cross-neighbourhood interactions: `3,084`; boundary-flow rows: `3`.
- Aggregate cache version: `1`; cache hit: `0.0141s`; cache agent ticks: `0`.

## Final division run

- Composition: `Ontario`; seed: `1`; duration: `30` days / `720` ticks.
- Simulated agents: `180`; reports: `7`; runtime: `0.606s`.
- Nested municipality flow rows: `6`; inter-municipality interactions: `0`.

## Final DSL-only finance run

- Program: `MarketLab`; seed: `1`; duration: `30` days / `720` ticks.
- Simulated agents: `12`; runtime: `0.043s`; reports: `1`.
- Final price: `51.54`; buys: `2,278`; sells: `1,902`; mean cash: `131.58`.
- Focused cache test confirmed a persisted-artifact hit with `0` agent ticks.
