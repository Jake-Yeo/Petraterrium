# Rust DSL demo status

## Implemented

- The only numeric tick entry point remains `run_program` in
  `engine-rust/src/text_dsl/runtime.rs`. The only composition entry point remains
  `run_composition` in `engine-rust/src/text_dsl/compositions.rs`. No country, world, trade,
  migration, feedback, or other level-specific runner was added.
- `CompositionDefinition` remains the recursive type for neighbourhood, municipality, division,
  country, world, and synthetic levels. Levels remain DSL strings rather than Rust enums or match
  branches.
- The DSL now supports reusable composition archetypes with a level, child level, parameters, and
  outputs. `CountryFederalDemocracy` is a reusable country contract; Canada, USA, and Mexico are
  separate instances with their own division weights and parameters.
- The shipped DSL defines British Columbia, California, Texas, Central Mexico, and Northern Mexico
  through the same composition syntax as Ontario. It defines Canada, USA, Mexico, and a world through
  that same syntax.
- The world uses a sparse DSL adjacency graph with Canada–USA and USA–Mexico edges. It has no direct
  Canada–Mexico edge.
- Exchange, transfer, visit, infection, and diffusion are generic flow effect labels. Their rates are
  parsed expressions that can read parameters, aggregate inputs, child parameters, child outputs,
  sparse distances, and earlier flow rates.
- Country and world reports expose population, represented population, pooled income/stress/vote
  statistics, GDP proxy, trade, migration, and infection outputs. Flow reports retain one snapshot
  per requested day and show the root plus its immediate children.
- Detailed transfer moves whole households while retaining agent IDs, traits, household IDs, and
  relationships. Cached transfer changes child weights at the next sync.
- The DSL defines division syncs at one or five days, country syncs at 30 days, and world syncs at 90
  days. Validation rejects parent/child clocks that do not divide cleanly with a named line error.
- Cached evaluation reports convergence separately for every composition node. Cache metadata still
  includes version, DSL/input hashes, validity, seed, original/evaluation ticks, detailed/cached
  state, dependencies, and invalidation reason.
- Request-local node memoization evaluates a reusable composition definition once per day and
  resolved input context. A warm world evaluation remains recursive but does not repeatedly evaluate
  the same municipality/neighbourhood definition under several divisions.
- Extensive cached metrics now scale child sums and action counts to the child's allocated share of
  the fixed parent cohort. This fixes the country/world double-counting found by the 300-agent
  physical comparison.
- Artifact versions advance at most once per function per request. A cold traversal that reuses a
  child no longer makes the first warm traversal perform a hierarchy-only stabilization pass.
- Branch-specific invalidation propagates from the changed division to its country and world while
  leaving the unrelated country branch cached. Global pandemic events invalidate every participating
  country through ordinary DSL cache rules.
- `World`, `WorldHouseholds`, and `SevenBillionWorld` represent `6,999,999,999` people with a fixed
  180-agent detailed cohort. Reports always separate simulated and represented counts.
- The DSL editor lists country/world compositions and aggregate functions, displays the exact source,
  and uses the same generic run/cache controls. The browser demo edits a world country weight, saves
  it, runs it, and displays changed aggregates without Rust, JSON, or per-domain UI changes.
- Engine version is `0.9.0`. Nothing was pushed.

## Implemented but narrower

- The first evaluation for a new DSL hash still learns the reusable leaf response surfaces. The final
  world cold bootstrap costs `6,220,800` agent ticks and `24.3295s`; country/world parent levels add
  no agent ticks. Warm hierarchy evaluation is the scaled execution path.
- The detailed world run takes `1.1035s`. The required detailed country run remains below one second,
  and the warm cached world run is `0.0641s` with zero agent ticks.
- Cached flow tables show the selected root and immediate children. Deeper flow detail is available by
  evaluating that child level, while the recursive cache table still shows every level.
- If a detailed composition records no cross-child action, its root visit flow becomes an explicit
  `boundary_flow` interaction receipt. Recorded agent-to-agent actions continue to take precedence.
- Visit and transfer mutate detailed agent state. Exchange, infection, and diffusion produce
  provenance-bearing flow receipts and cached outputs; they do not yet mutate arbitrary detailed
  agent fields because the DSL has no generic flow-to-field-effect block.
- Country/world values are concrete demo estimates. They are not calibrated real-world claims, and
  the three shipped countries are a composition proof rather than a complete world country catalog.
- The country archetype supplies a reusable parameter/output/child-level contract. Country instances
  continue to declare their concrete divisions and weights, as required for instance identity.
- Aggregate response surfaces still use the existing low/high multilinear learner. This prompt did
  not introduce a new fit method.

## Deferred and not part of this demo

- Media, corporate, and finance cross-vertical composition and coupling.
- Atlas, GeoNames, WDI, external imports, research pipelines, evidence guards, provenance imports,
  and fitted real-world behavior models.
- Globe or polygon work, graphs, inheritance views, decision-tree views, visual drag-and-drop
  editors, and per-level management panels.
- Real-world calibration/prediction claims and interrupted-run pause/resume UI.

## Focused verification

- Synthetic country/world parser, generic recursion, exact 60/40 country and world weighting,
  archetype/instance differentiation, all five flow effects, sparse adjacency, transfer identity
  preservation, branch invalidation, event broadcast, per-level convergence, 90-day evolution,
  represented counts, determinism, and country/world 300-agent physical comparisons: `8 passed`.
- Existing recursive cached composition regression file: `9 passed`.
- Existing generic composition tests: `5 passed`; archetype tests: `5 passed`; neighbourhood tests:
  `7 passed`.
- Targeted Python text-DSL API routing and recursive artifact persistence: `2 passed`.
- Focused browser country/world workflow, including a DSL weight edit, detailed runs, warm cache,
  branch override, recursive cache table, and 90-day evolution: passed in `6.7s`.
- Frontend production build, targeted Ruff checks, generated-contract check, Rust format/check, and
  `git diff --check`: passed.
- `cargo clippy` was unavailable because the installed Rust toolchain lacks the clippy component;
  `cargo check --release --locked` passed.
- The full backend and frontend suites were not run, as explicitly required by Prompt 6.
- A detached build of Prompt 5 commit `1e6233a` was compared directly with the current engine. Town,
  weighted household, neighbourhood, municipality, and division state and report payloads are exact.
- Source grep finds no `run_neighbourhood`, `run_municipality`, `run_division`, `run_country`,
  `run_world`, `run_feedback`, `run_trade`, or `run_migration`. The only shipped action-name grep hit
  is inside the existing `runtime.rs` test module.

## Performance

- Town, 30 days / 720 ticks / 130 agents: `0.3424s`.
- Town, 365 days / 8,760 ticks / 130 agents: `3.8222s`.
- Weighted household population, 30 days / 180 agents: `0.4110s`.
- Detailed neighbourhood, 30 days / 180 agents: `0.4984s`.
- Detailed municipality, 30 days / 180 agents: `0.5796s`.
- Detailed division, 30 days / 180 agents: `0.6309s`.
- DSL-only finance, 30 days / 12 agents: `0.0488s`.
- Detailed country, 30 days / 180 agents: `0.7608s`.
- Detailed world, 30 days / 180 agents: `1.1035s`.
- Cold world hierarchy bootstrap: `24.3295s`, `6,220,800` leaf agent ticks.
- Warm Toronto cached evaluation: `0.0220s`, `0` agent ticks.
- Warm Ontario cached evaluation: `0.0537s`, `0` agent ticks.
- Warm Canada cached evaluation: `0.0550s`, `0` agent ticks.
- Warm World cached evaluation: `0.0641s`, `0` agent ticks.
- Warm World 90-day evolving evaluation: `0.2052s`, `0` agent ticks.
- Default DSL hash: `sha256:9c9a03bf8077101753bb18979991039b83568c8afcaea5ea8429b931c7be708c`.

## Final demo run

- Engine: `0.9.0`; seed: `1`; duration: `365` days / `8,760` ticks.
- Population: `100` adults plus `30` generated children.
- Current state and every report exactly match Prompt 5 commit `1e6233a`.

## Final weighted archetype run

- Seed: `1`; duration: `30` days; simulated agents: `180`; runtime: `0.4110s`.
- Current state and every report exactly match Prompt 5 commit `1e6233a`.

## Final neighbourhood run

- `UrbanLiberal`; seed: `1`; duration: `30` days; agents: `180`; runtime: `0.4984s`.
- Current state and every report exactly match Prompt 5 commit `1e6233a`.

## Final municipality run

- `Toronto`; seed: `1`; duration: `30` days; agents: `180`; runtime: `0.5796s`.
- Current state and every report exactly match Prompt 5 commit `1e6233a`.

## Final division run

- `Ontario`; seed: `1`; duration: `30` days; agents: `180`; runtime: `0.6309s`.
- Current state and every report exactly match Prompt 5 commit `1e6233a`.

## Final DSL-only finance run

- `MarketLab`; seed: `1`; duration: `30` days; agents: `12`; runtime: `0.0488s`.
- Final price remains `51.54`; buys `2,278`; sells `1,902`; mean cash `131.58`.

## Final country run

- `Canada`; seed: `1`; duration: `30` days; simulated agents: `180`; represented population:
  `40,000,000`; runtime: `0.7608s`.
- It records `19` hierarchy flow rows and `117` cross-division agent interactions.

## Final world run

- `World`; seed: `1`; duration: `30` days; simulated agents: `180`; represented population:
  `6,999,999,999`; runtime: `1.1035s`.
- The boundary interaction receipt records `6` USA-to-Canada visiting agents.
- Root flow rates are non-zero in the expected declared directions: Canada→USA trade `0.05667`,
  USA→Mexico trade `0.04167`, Mexico→USA migration `0.03326`, USA→Canada travel `0.04400`,
  infection `0.05440`, and policy diffusion `0.07000`.
- No Canada→Mexico direct row exists, confirming sparse adjacency isolation.

## Final cached country run

- `Canada`; seed: `1`; duration: `30` days; runtime: `0.0550s`; agent ticks: `0`;
  `cache_hit=true`.
- The country reuses division, municipality, neighbourhood, and leaf artifacts from the world cold
  bootstrap.

## Final cached world run

- `World`; seed: `1`; duration: `30` days; runtime: `0.0641s`; agent ticks: `0`;
  `cache_hit=true`.
- The cache tree reports every country, division, municipality, neighbourhood, and leaf as cached.
- World feedback converges in `3` iterations with `0.0524%` change. Canada converges in `2` with
  `0.2682%`; USA in `2` with `0.4268%`; Mexico in `2` with `0.4267%`.

## Final cached 90-day world run

- `World`; seed: `1`; duration: `90` days; runtime: `0.2052s`; agent ticks: `0`.
- Scheduled day-30 economic shock: `0.10`.
- Mean income changes from `2,853.4923` on day 30 to `2,818.6522` on day 90. Mean stress changes
  from `0.393918` to `0.379023`; the endpoint is not a repeated day-30 value.
- The result contains `90` daily flow snapshots.
