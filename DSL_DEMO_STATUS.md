# Rust DSL demo status

## Implemented

- The only numeric tick entry point remains `run_program` in
  `engine-rust/src/text_dsl/runtime.rs`. The only composition entry point remains
  `run_composition` in `engine-rust/src/text_dsl/compositions.rs`.
- `CompositionDefinition` remains the single recursive type for every composition level. No
  neighbourhood, municipality, division, cache, feedback, finance, or scenario runner was added.
- Composition flows now store parsed expressions rather than fixed Rust numbers. Expressions can
  read composition parameters, aggregate inputs, current parent outputs, child outputs, and sparse
  adjacency distances.
- A DSL `cached` block defines sync days, a maximum of one to five feedback iterations, convergence
  tolerance, and output-to-input feedback couplings.
- The generic cached-composition evaluator recursively resolves child aggregate artifacts, combines
  means by weights, pools standard deviations, sums action counts, preserves the detailed sample
  population, applies parent effects, and recalculates flows at every sync.
- A parent cache never runs parent agents. A valid Ontario evaluation recursively reads Toronto and
  Vancouver, which read the three neighbourhood functions, and completes with zero agent ticks.
- Missing or invalid leaf artifacts relearn only those leaves. Parent artifacts are regenerated from
  child outputs and record dependency versions; unchanged sibling branches remain cached.
- Cache metadata is returned for every root, child, and grandchild: version, DSL hash, input hash,
  validity dates, seed, original learning ticks, evaluation ticks, cached/detailed state, and the
  invalidation reason.
- The service persists every changed artifact version independently. It sends a compact hierarchy
  catalog to Rust with learned reports removed from transport while retaining the full persisted
  artifact on disk.
- Top-down inputs propagate by matching DSL input IDs. Branch-specific overrides support changes
  such as `NorthOne.unemployment=0.8`. Composition parameters take part in input resolution and
  threshold invalidation.
- Bottom-up child outputs feed parent aggregation. DSL feedback couplings feed parent outputs into
  the next child evaluation at a sync point and iterate until tolerance or the configured cap.
- Fast-forwarding uses piecewise 30-day learned functions with daily composition syncs. Weights,
  flows, feedback inputs, and scheduled input changes carry into the next piece instead of repeating
  the day-30 endpoint.
- Cached flow reports contain a snapshot for every sync day. Visit and transfer rates recalculate
  from the current inputs and aggregates, and transfers update the next sync's child weights.
- Ontario now declares Toronto-to-Vancouver visit and transfer flows. Its detailed run records
  non-zero inter-municipality interactions through the same generic place and flow machinery used
  inside municipalities.
- The aggregate UI now accepts branch overrides and scheduled changes, renders the recursive cache
  table and convergence report, and distinguishes cache hits, hierarchy-only updates, and detailed
  branch relearns.
- Engine version is `0.8.0`. Nothing was pushed.

## Implemented but narrower

- The first evaluation after a new DSL hash must bootstrap missing leaf artifacts. For the shipped
  hierarchy this costs `6,220,800` agent ticks and `25.741s`. It relearns the three neighbourhood
  branches only; Toronto, Vancouver, and Ontario are composed without parent agent ticks.
- With valid child artifacts, historical Toronto parent learning drops from `518,400` ticks to `0`.
  The cold bootstrap is more expensive than the old isolated parent learn because all three reusable
  neighbourhood response surfaces must exist first.
- Cached cross-child interactions are derived from DSL visit flows. Detailed runs continue to report
  actual recorded target interactions.
- Top-down propagation automatically maps equal input IDs. Renaming an input between levels still
  requires matching DSL IDs or an explicit feedback coupling.
- The shipped municipalities use one local feedback pass per parent preview; Ontario performs the
  convergent loop. The generic synthetic test exercises the full five-iteration capability at
  multiple levels.
- Aggregate response surfaces still use the existing low/high multilinear grid. Cached hierarchy
  composition improves reuse and time evolution; it does not replace those surfaces with fitted
  real-world models.

## Deferred and not part of this demo

- Country and world composition, country/world flows, and global represented-population weights.
- Atlas, GeoNames, WDI, external imports, research pipelines, evidence guards, and fitted models.
- Globe work, polygons, graphs, inheritance views, decision-tree views, visual drag-and-drop
  editors, and per-level management panels.
- Real-world calibration or prediction claims and interrupted-run pause/resume UI.

## Focused verification

- Cached composition parser, exact weighted reuse, missing-child-only relearn, parent learning tick
  reduction, daily flow recalculation, parameter-driven outputs, branch invalidation propagation,
  feedback convergence, evolving 90-day evaluation, generic division flows, determinism, and the
  300-agent detailed comparison: `9 passed`.
- Existing aggregate-function parser, interpolation, cache accuracy, threshold/time/event/DSL
  invalidation, determinism, and 90-day legacy behavior: `5 passed`.
- Generic composition parser, weighting, transfer, adjacency, cache, and 300-agent comparison:
  `5 passed`.
- Legacy neighbourhood parsing, targeting, exact weighting, represented counts, place indexing,
  cache invalidation, and determinism: `7 passed`.
- DSL-only finance run and cache: `1 passed`.
- Targeted Python API routing, ordinary artifact persistence, and recursive hierarchy artifact
  persistence: `3 passed`.
- Focused synthetic browser hierarchy test: passed in `7.0s`.
- Focused shipped Ontario detailed/cache/90-day browser test: passed in `4.6s` with warm artifacts.
- Frontend production build, targeted Ruff checks, generated-contract check, Rust format/check, and
  `git diff --check`: passed.
- The full backend suite and full frontend suite were not run, as required by this prompt.
- Source grep finds no `run_neighbourhood`, `run_municipality`, `run_division`, `run_country`,
  `run_world`, `run_feedback`, or other named hierarchy/domain runner. Shipped place, composition,
  action, and flow names do not occur in Rust engine source.

## Performance

- Town, 30 days / 720 ticks / 130 agents: `0.323s`.
- Town, 365 days / 8,760 ticks / 130 agents: `4.026s`.
- Weighted household population, 30 days / 180 agents: `0.409s`.
- Detailed neighbourhood, 30 days / 180 agents: `0.486s`.
- Detailed municipality, 30 days / 180 agents: `0.573s`.
- Detailed division, 30 days / 180 agents: `0.618s`.
- DSL-only finance, 30 days / 12 agents: `0.044s`.
- Cold Ontario hierarchy bootstrap: `25.741s`, `6,220,800` leaf agent ticks.
- Warm Toronto cached evaluation: `0.021s`, `0` agent ticks.
- Warm Ontario cached evaluation: `0.037s`, `0` agent ticks.
- Warm Ontario 90-day evolving evaluation: `0.097s`, `0` agent ticks.
- Synthetic parent learning: `1,200` detailed ticks before child-cache reuse, `0` after reuse.
- Default DSL hash: `sha256:a353610fdbcf8846b2f7586efd88a5b747a3df3fb1dd6ac1c2f9b3aa72289e06`.

## Final demo run

- Legacy golden record: `87edc98083d542d2a63ca69a0917a69c`.
- Engine: `0.8.0`; seed: `1`; duration: `365` days / `8,760` ticks.
- Population: `100` adults plus `30` generated children.
- Current state and every report exactly equal the persisted golden after excluding only protocol and
  engine-version metadata.

## Final weighted archetype run

- Legacy golden record: `6fef20f60e3a4ae2a3035c1253f1281e`.
- Seed: `1`; duration: `30` days; simulated agents: `180`; runtime: `0.409s`.
- Current state and every report exactly equal the persisted weighted golden.

## Final neighbourhood run

- Legacy golden record: `b1ac7e29863b4e8c8395e19bafd64c99`.
- `UrbanLiberal`; seed: `1`; duration: `30` days; agents: `180`; runtime: `0.486s`.
- Current state and every report exactly equal the persisted neighbourhood golden.

## Final municipality run

- `Toronto`; seed: `1`; duration: `30` days; agents: `180`; runtime: `0.573s`.
- Cross-neighbourhood interactions remain `3,084`, matching Prompt 4.
- With its child neighbourhood artifacts valid, cached Toronto runs in `0.021s` and `0` ticks.
- Historical direct parent learning was `518,400` ticks; recursive child-cache reuse is `0` parent
  ticks.

## Final division run

- `Ontario`; seed: `1`; duration: `30` days; agents: `180`; runtime: `0.618s`.
- It records `2,097` inter-municipality interactions and `8` flow rows, including the two new
  Ontario-level visit/transfer rows. Prompt 4 recorded zero inter-municipality interactions.

## Final cached division run

- `Ontario`; seed: `1`; duration: `30` days; runtime: `0.037s`; agent ticks: `0`.
- Root, municipality, and neighbourhood artifacts all report `cached=true` with their complete
  provenance metadata.
- Feedback converges in `3` iterations with `0.0283%` final aggregate change.

## Final cached 90-day run

- `Ontario`; seed: `1`; duration: `90` days; runtime: `0.097s`; agent ticks: `0`.
- Scheduled day-30 unemployment input: `0.075`.
- Mean income at day 30: `2,835.9917`; mean income at day 90: `2,841.6931`.
- Day 90 is higher by `5.7014`; it does not repeat the day-30 endpoint.
- The result contains `90` daily flow snapshots and converges in `3` iterations with `0.1042%`
  final change.

## Final DSL-only finance run

- `MarketLab`; seed: `1`; duration: `30` days; agents: `12`; runtime: `0.044s`.
- Final price: `51.54`; buys: `2,278`; sells: `1,902`; mean cash: `131.58`.
- No finance-specific runner or Rust branch was added.
