# Weighted neighbourhood exemplar status

Date: 2026-10-28

Nothing was committed or pushed.

## Source identity

- The requested starting `engine-rust/dsl/default.dsl` SHA-256 was verified against `HEAD`: `c40ef01144ca2aaf83ea87354fbe6e1471836533befdfc16c655b92a50f12220`.
- The implemented DSL SHA-256 is `20821ac82a6462324a53df40c52db3914414411c9d5c7e2c7d8940d06d785db2`.
- Rust engine version is `0.13.0`. Exemplar caches also carry this engine version and cache schema version.

## Implemented

- The default run is one logical represented population partitioned into city-specific neighbourhood exemplars. It no longer runs an implicit global sample when `composition_id` is omitted.
- Every detailed exemplar contains 75 complete households and 225 people. Household archetype counts use largest remainder and sum exactly to 75. Simulated agents have no weights inside an exemplar.
- Each city has its own deterministic exemplar IDs. Counts start from city strata, population share, and heterogeneity, then add stable seeded exemplars until measured mean, distribution, and tail thresholds converge or the 50-exemplar city cap is reached.
- Exemplar weights sum exactly to city represented people. City totals sum through division and country counts to the requested world total. Changing the total rescales real-neighbourhood instances and represented households without changing exemplar IDs, counts, or sizes.
- City aggregation is a mixture distribution. It records pooled standard deviation, 21-point mixture quantiles, p10/p50/p90, and event-tail rates for state fields and every DSL action aggregate.
- Measured, inherited, and fallback status travels from city and stratum provenance into every exemplar. Inherited cities cannot expose a measured exemplar label. Lytton is the named fallback city.
- Each cache entry stores the DSL hash, engine version, schema version, exemplar ID, stratum, seed, observed input grid, requested input, time window, learning ticks, validity window, dependencies, metrics, agents, household links, and residence path.
- Initial learning runs three observed input points: low, requested, and high for tax, unemployment, media trend, price, and policy. Cache evaluation uses inverse-distance interpolation between observed points. An input outside the observed bounds learns only that exemplar and extends its grid.
- Cache validity checks schema, engine version, DSL hash, seed, time window, validity window, events, and input bounds. City-scoped events relearn only that city. Parent cache metadata records exact child versions from city through division, country, and world.
- Parent/child feedback is evaluated at the smallest DSL-declared city `sync_up`. Spotlight and boundary agents change DSL input states; affected exemplar functions re-evaluate for up to five iterations and stop below one percent change.
- Migrants, commuters, traders, influencers, owners, and visiting leaders are selected from cached logical agents. Migration changes household and residence roles, commuters meet at TransitHub, traders exchange money and shares, influencers post, and national leaders negotiate. Aggregate flow/coupling causality has been removed.
- All four sectors remain overlays on the same people: Physical, Media, Conglomerate, and Financial. Leaders are selected from eligible logical agents with unique assignments. The default full run assigns 521 spotlight offices, including 500 store managers, and reports zero unassigned required roles.
- `record_actions` remains false by default. The composed result records action statistics while omitting raw action receipts unless the DSL explicitly requests them.
- The run panel contains Total represented pool, Days, Seed, and Run full system in that order. Advanced contains city debug selection only. Detail, Sample budget, Planned draws, and the hidden legacy fast-forward controls are removed.
- The DSL validator requires every `graph_group = main` slice to form one connected level chain. Disconnected roots, forks, merges, repeated levels, level cycles, and composition links outside the slice are rejected with `INVALID_VERTICAL_SLICE` and a source line. `IndependentBusinesses` is restored as its own main vertical slice and is a direct child of the executable `Petraterrium` root.
- React Flow renders each validated slice as one vertical level line without manufacturing a slice-root card. Tab labels derive from the same root-level label as the first card, producing World, Platforms, Conglomerates, Independent businesses, and Economies. World is exactly World → Countries → Divisions → Cities → Neighbourhoods; Conglomerates is Conglomerates → Brands → Franchises → Stores. Named declarations such as Canada, USA, and Toronto appear in the selected level's detail pane. Renaming a root level or adding a valid main slice changes its tab and line without a frontend edit. Mouse-wheel input over the graph pane and cards is contained as graph zoom, while the DSL toolbar stays sticky and the editor gutter stays synchronized.

## DSL fields

Added to composition syntax:

- `households_per_exemplar`
- `stratum`
- `stratifiers`
- `heterogeneity`
- `distribution_status`
- `provenance`
- `clock`
- `sync_up`

Removed from the executable population path:

- `sample_budget` and global multinomial hierarchy allocation
- Detail Low/Medium/High and Planned draws
- composition `flows`, `couplings`, `boundaries`, and the old `cached` composition block
- flow-count and flow-rate output metrics
- separate per-sector people

The existing `population.size` remains only as a generic agent/archetype primitive. It is not a world-sample control.

## Previous default 30-day golden

This record predates the vertical-slice validation change and the restoration of Independent Businesses to the executable root. The DSL source hash and default program changed, so the 30-day golden was not claimed again without rerunning the expensive gate.

- Total represented pool: `6,999,999,999`; seed: `1`; days: `30`; total exemplars: `92`.
- Cold learning: `228.747s`; `44,712,000` mass agent-ticks; `92` learned exemplars.
- Real neighbourhood instances represented: `31,111,111.107`; represented households: `2,333,333,333`.
- Leader assignments: `521`; unassigned required roles: `0`.
- Canonical cached per-exemplar metric digest: `18cfce39794bc2409c06184f9f5e6ac703e039d79408a296a62eae4b985a5f09`.

### City convergence

| City | People | Households | Exemplars | Evidence | Mean Δ | Distribution Δ | Tail Δ | Result |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- |
| Houston | 1,944,444,444 | 648,148,148 | 18 | inherited | 1.130% | 1.065% | 0.166 pp | converged |
| LosAngeles | 2,430,555,555 | 810,185,185 | 17 | inherited | 0.535% | 0.586% | 0.071 pp | converged |
| Lytton | 4,861,111 | 1,620,370 | 1 | fallback | 0.000% | 0.000% | 0.000 pp | converged |
| MexicoCity | 686,274,510 | 228,758,170 | 14 | measured | 0.553% | 1.812% | 0.161 pp | converged |
| Monterrey | 480,392,157 | 160,130,719 | 14 | inherited | 0.517% | 2.700% | 0.132 pp | converged |
| Toronto | 972,222,222 | 324,074,074 | 14 | measured | 1.608% | 1.855% | 0.449 pp | converged |
| Vancouver | 481,250,000 | 160,416,667 | 14 | measured | 1.831% | 2.665% | 0.238 pp | converged |

### Exemplar inventory by city and stratum

| City | Stratum | Exemplar IDs | Count | Households each | Real instances | City weight | Evidence |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| Houston | dense_urban_high_education | Houston__dense_urban_high_education__01, Houston__dense_urban_high_education__02, Houston__dense_urban_high_education__03, Houston__dense_urban_high_education__04, Houston__dense_urban_high_education__05, Houston__dense_urban_high_education__06, Houston__dense_urban_high_education__07, Houston__dense_urban_high_education__08 | 8 | 75 | 3,024,691.356 | 35.000% | inherited |
| Houston | suburban_mixed_households | Houston__suburban_mixed_households__01, Houston__suburban_mixed_households__02, Houston__suburban_mixed_households__03, Houston__suburban_mixed_households__04, Houston__suburban_mixed_households__05, Houston__suburban_mixed_households__06, Houston__suburban_mixed_households__07 | 7 | 75 | 4,320,987.653 | 50.000% | inherited |
| Houston | rural_mixed_households | Houston__rural_mixed_households__01, Houston__rural_mixed_households__02, Houston__rural_mixed_households__03 | 3 | 75 | 1,296,296.298 | 15.000% | inherited |
| LosAngeles | dense_urban_high_education | LosAngeles__dense_urban_high_education__01, LosAngeles__dense_urban_high_education__02, LosAngeles__dense_urban_high_education__03, LosAngeles__dense_urban_high_education__04, LosAngeles__dense_urban_high_education__05, LosAngeles__dense_urban_high_education__06, LosAngeles__dense_urban_high_education__07, LosAngeles__dense_urban_high_education__08 | 8 | 75 | 6,481,481.480 | 60.000% | inherited |
| LosAngeles | suburban_mixed_households | LosAngeles__suburban_mixed_households__01, LosAngeles__suburban_mixed_households__02, LosAngeles__suburban_mixed_households__03, LosAngeles__suburban_mixed_households__04, LosAngeles__suburban_mixed_households__05, LosAngeles__suburban_mixed_households__06 | 6 | 75 | 3,240,740.742 | 30.000% | inherited |
| LosAngeles | rural_mixed_households | LosAngeles__rural_mixed_households__01, LosAngeles__rural_mixed_households__02, LosAngeles__rural_mixed_households__03 | 3 | 75 | 1,080,246.911 | 10.000% | inherited |
| Lytton | homogeneous_rural_households | Lytton__homogeneous_rural_households__01 | 1 | 75 | 21,604.938 | 100.000% | fallback |
| MexicoCity | dense_urban_high_education | MexicoCity__dense_urban_high_education__01, MexicoCity__dense_urban_high_education__02, MexicoCity__dense_urban_high_education__03, MexicoCity__dense_urban_high_education__04, MexicoCity__dense_urban_high_education__05, MexicoCity__dense_urban_high_education__06 | 6 | 75 | 1,982,570.809 | 65.000% | measured |
| MexicoCity | suburban_mixed_households | MexicoCity__suburban_mixed_households__01, MexicoCity__suburban_mixed_households__02, MexicoCity__suburban_mixed_households__03, MexicoCity__suburban_mixed_households__04, MexicoCity__suburban_mixed_households__05 | 5 | 75 | 915,032.680 | 30.000% | inherited |
| MexicoCity | rural_mixed_households | MexicoCity__rural_mixed_households__01, MexicoCity__rural_mixed_households__02, MexicoCity__rural_mixed_households__03 | 3 | 75 | 152,505.444 | 5.000% | inherited |
| Monterrey | dense_urban_high_education | Monterrey__dense_urban_high_education__01, Monterrey__dense_urban_high_education__02, Monterrey__dense_urban_high_education__03, Monterrey__dense_urban_high_education__04, Monterrey__dense_urban_high_education__05, Monterrey__dense_urban_high_education__06 | 6 | 75 | 960,784.316 | 45.000% | inherited |
| Monterrey | suburban_mixed_households | Monterrey__suburban_mixed_households__01, Monterrey__suburban_mixed_households__02, Monterrey__suburban_mixed_households__03, Monterrey__suburban_mixed_households__04, Monterrey__suburban_mixed_households__05 | 5 | 75 | 960,784.311 | 45.000% | inherited |
| Monterrey | rural_mixed_households | Monterrey__rural_mixed_households__01, Monterrey__rural_mixed_households__02, Monterrey__rural_mixed_households__03 | 3 | 75 | 213,507.627 | 10.000% | inherited |
| Toronto | dense_urban_high_education | Toronto__dense_urban_high_education__01, Toronto__dense_urban_high_education__02, Toronto__dense_urban_high_education__03, Toronto__dense_urban_high_education__04, Toronto__dense_urban_high_education__05, Toronto__dense_urban_high_education__06 | 6 | 75 | 2,160,493.827 | 50.000% | measured |
| Toronto | suburban_mixed_households | Toronto__suburban_mixed_households__01, Toronto__suburban_mixed_households__02, Toronto__suburban_mixed_households__03, Toronto__suburban_mixed_households__04, Toronto__suburban_mixed_households__05 | 5 | 75 | 1,440,329.218 | 33.333% | inherited |
| Toronto | rural_mixed_households | Toronto__rural_mixed_households__01, Toronto__rural_mixed_households__02, Toronto__rural_mixed_households__03 | 3 | 75 | 720,164.609 | 16.667% | inherited |
| Vancouver | dense_urban_high_education | Vancouver__dense_urban_high_education__01, Vancouver__dense_urban_high_education__02, Vancouver__dense_urban_high_education__03, Vancouver__dense_urban_high_education__04, Vancouver__dense_urban_high_education__05, Vancouver__dense_urban_high_education__06 | 6 | 75 | 962,500.000 | 45.000% | measured |
| Vancouver | suburban_mixed_households | Vancouver__suburban_mixed_households__01, Vancouver__suburban_mixed_households__02, Vancouver__suburban_mixed_households__03, Vancouver__suburban_mixed_households__04, Vancouver__suburban_mixed_households__05 | 5 | 75 | 748,611.111 | 35.000% | inherited |
| Vancouver | rural_mixed_households | Vancouver__rural_mixed_households__01, Vancouver__rural_mixed_households__02, Vancouver__rural_mixed_households__03 | 3 | 75 | 427,777.778 | 20.000% | inherited |

### Learning cost by stratum

| Stratum | Exemplars | Households | People | Observed points | Agent-ticks | Total time | Mean time/exemplar |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| dense_urban_high_education | 40 | 75 | 225 | 3 | 19,440,000 | 88.227s | 2.206s |
| homogeneous_rural_households | 1 | 75 | 225 | 3 | 486,000 | 2.173s | 2.173s |
| rural_mixed_households | 18 | 75 | 225 | 3 | 8,748,000 | 40.162s | 2.231s |
| suburban_mixed_households | 33 | 75 | 225 | 3 | 16,038,000 | 74.317s | 2.252s |

### Cached total rescaling

| Total | Time | Mass ticks | Exemplars | Real instances | Households | Metric digest |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6,999,999,999 | 2.351s | 0 | 92 | 31,111,111.107 | 2,333,333,333 | `18cfce39794bc2409c06184f9f5e6ac703e039d79408a296a62eae4b985a5f09` |
| 8,000,000,000 | 2.138s | 0 | 92 | 35,555,555.556 | 2,666,666,666 | `18cfce39794bc2409c06184f9f5e6ac703e039d79408a296a62eae4b985a5f09` |
| 2,000,000,000 | 2.152s | 0 | 92 | 8,888,888.889 | 666,666,666 | `18cfce39794bc2409c06184f9f5e6ac703e039d79408a296a62eae4b985a5f09` |

The exemplar count and per-exemplar metric digest are identical at 7B, 8B, and 2B. Only represented instance and household weights change.

## Cache invalidation and relearning

- Cache miss: learn low/requested/high points for that exemplar.
- Input inside observed bounds: interpolate with zero mass-agent ticks.
- New input or input outside observed bounds: learn only that exemplar and append the point.
- City event such as `Toronto:policy_change`: relearn Toronto exemplars only.
- DSL hash, engine version, schema, seed, or time-window change: invalidate the affected exemplar function.
- Child version changes rebuild only ancestor metadata along that city → division → country → world branch.

## Removed causal flow and global-sample code

Deleted Rust modules:

- `engine-rust/src/text_dsl/composition_cache.rs`
- `engine-rust/src/text_dsl/composition_cache_artifacts.rs`
- `engine-rust/src/text_dsl/composition_cache_reports.rs`
- `engine-rust/src/text_dsl/composition_couplings.rs`

Rewritten population source:

- `engine-rust/src/text_dsl/population_distribution.rs` now retains only the generic seeded multinomial primitive; the global pool planner and hierarchy allocator are gone.

Deleted obsolete DSL fixtures and suites:

- `engine-rust/dsl/cached_composition_test.dsl`
- the obsolete pre-rename Conglomerate DSL fixture
- `engine-rust/dsl/country_world_test.dsl`
- `engine-rust/dsl/financial_coupling_test.dsl`
- `engine-rust/dsl/media_test.dsl`
- `engine-rust/tests/cached_compositions.rs`
- `engine-rust/tests/compositions.rs`
- the obsolete pre-rename Conglomerate/Financial coupling suite
- the obsolete pre-rename Conglomerate hierarchy suite
- `engine-rust/tests/country_world.rs`
- `engine-rust/tests/financial_transactions.rs`
- `engine-rust/tests/leader_roles.rs`
- `engine-rust/tests/media_vertical.rs`
- `frontend/tests/text-dsl-demo.spec.ts`

Named old couplings are deleted rather than aliased:

- `world_to_media`, `media_outrage_to_world`, and `media_sentiment_to_world`: same-person media actions now change stress, outrage, and `media_trend`.
- The former world-to-store and store-to-world channels: customer, cashier, store-manager, and owner actions move money and expose post-action statistics.
- `store_profit_to_firms` and `firm_allocation_to_stores`: franchise-manager, brand-manager, and CEO actions perform the transfers.
- Alpha/Beta profit, price, market-cap, and trader-signal couplings: deleted with the synthetic entities; trader and firm-agent actions own price, issuance, and borrowing.

Finance `flows` that remain elsewhere in the repository are per-agent cash-flow receipts, not composition-to-composition causal flows.

## Golden disposition

- Deleted: global 291-agent / 97-household sample, Detail-level, per-slice population, cached-composition, and aggregate-flow goldens and fixtures.
- Changed: default DSL cleanup, hierarchy graph, full-system, population-distribution, text-DSL API, and rendered DSL workflow expectations now assert exemplar architecture.
- Kept: generic parser, expression, duration, role-decision, action exclusivity, state-finance, location, and interaction-tree tests that do not depend on the removed architecture.
- New: default 30-day measured record above, focused exemplar parser/size/weight/stratification/convergence/cache/feedback/boundary/determinism tests, and rendered exemplar hierarchy acceptance.

## Verification

- Focused Rust vertical-slice graph acceptance: 5 passed, including disconnected-root and branching-level rejection with DSL source lines.
- Focused backend text-DSL API: 4 passed.
- Rendered DSL acceptance: 6 passed, including exact level lines and matching root/tab labels for every slice, validation rejection for disconnected main-slice levels, a custom additional slice, executable Independent Businesses participation, wheel zoom while hovering a graph card with unchanged page scroll, sticky editor controls, and synchronized gutter scrolling; measured graph render 30.1 ms, versus the stated 1,310.4 ms regression and 108.9 ms earlier baseline.
- Frontend TypeScript and production build passed.
- Ruff passed for changed backend modules.
- Full Rust suite: 140 passed.
- Backend Ruff and generated-contract checks passed.
- Rust formatting, frontend Prettier, frontend production build, VS Code diagnostics, and `git diff --check` passed.
- The broad backend suite was stopped after roughly four minutes in `tests/test_api.py`; no failure had been emitted, but the serial real-simulation API cases were still running. The focused changed backend suite passed 4 tests.
- The broad frontend E2E gate encountered two pre-existing `atlas.spec.ts` timeouts because the rendered app had no Data tab, then was stopped; 69 unrelated tests did not run. The focused changed DSL workflow passed all 5 browser tests.

## Implemented more narrowly

- The learned input grid is a deterministic three-point sparse grid across all declared inputs, not a full Cartesian grid. Out-of-grid requests add observed points selectively, so coverage grows where the composed run needs it without multiplying cold learning by 243 combinations.
- Advanced exposes single-city debug runs. A separate single-exemplar debug selector is not implemented.
- Cold learning is intentionally expensive: 228.747 seconds for the measured 30-day gate. Cache-only composed runs are 2.14–2.35 seconds and run zero mass-agent ticks.
- `engine-rust/src/text_dsl/exemplars.rs` and the TSX graph remain larger than the repository’s preferred module-size range and should be split by planning, cache learning, boundary composition, and presentation if this surface grows further.

## Legacy-term search disposition

- `sample_budget`, `detail =`, and old demo identifiers remain only as string literals in negative cleanup tests that assert they are absent from the shipped DSL.
- `lab` remains a generic graph-group value for optional test or auxiliary compositions. The rendered tab set comes from every DSL slice whose graph group is `main`; auxiliary groups remain outside that tab set.
- Frontend uses `detail` only for HTTP error payloads and the node-inspection pane. There is no run Detail input or API field.
- No pre-rename sector term remains in the shipped DSL, Rust text-DSL engine, frontend implementation, tests, or this report.
