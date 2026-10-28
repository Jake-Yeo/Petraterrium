# Rust DSL demo status

## Implemented

- The numeric engine still has one tick entry point, `run_program`, and one recursive composition
  entry point, `run_composition`. No media, community, platform, influencer, recommendation, coupling,
  country, world, trade, or migration runner was added.
- `CompositionDefinition` remains the shared recursive type for physical, media, coupled, and synthetic
  levels. The shipped DSL defines two communities, one platform, a physical peer module, and a coupled
  physical/media composition without requiring a neighbourhood, municipality, division, or country
  inside the media hierarchy.
- The generic DSL now supports entity schemas. `Post` declares topic, source, sentiment, engagement,
  and age fields. Mass posts remain statistical action/entity records rather than full text objects.
- Actions can declare recorded fields. When `record_actions = false`, the engine retains only actions
  that explicitly request fields. The media demo therefore retains spotlight post events while mass
  post/comment/like/share receipts remain aggregate counts and rates.
- A `spotlight agent` is a validated one-agent archetype. `InfluencerX` has one sampled identity,
  individual traits, a deterministic ID, recorded post history, and larger DSL-defined community
  effects than a mass post.
- Scalar `action_rate` and `sd` report metrics are generic DSL metrics. Rates divide by agents whose
  active decision can perform the requested aggregate, so heterogeneous peer modules use the correct
  denominator.
- Recommendation is the branch expression in DSL: popularity, interest match, agreement, outrage,
  trust, friend sharing, and age decay determine share probability. Rust has no recommender branch.
- Viral spread uses the same DSL expression at every engagement value. The platform flow compares the
  community's measured viral-post output with a DSL threshold; raising that input threshold to 1,000
  produces zero spread without a special case.
- `ModerationPolicy` is a reusable probability policy. It multiplies post/share weights by nominal
  effect × compliance. Strict moderation and topic closure lower rates while leaving them non-zero.
  Decisions remain in their trees.
- Composition policies apply to detailed decisions and cached scalar action outputs through the same
  generic effect definitions.
- Explicit composition couplings read declared source outputs and write declared target aggregate
  inputs. Validation rejects unknown endpoints, outputs, inputs, fields, and incompatible clocks.
- Detailed coupled compositions advance in DSL-defined sync chunks through `run_program`, compute
  child outputs, and apply target aggregate effects for the next chunk. Compositions without
  couplings use the unchanged Prompt 6 path.
- Field effects apply when a coupled input crosses its DSL invalidation threshold. Decision modifiers
  refresh from the policy-adjusted baseline at each sync instead of compounding accidentally.
- `boundaries` provide the individual hinge between peer modules. The demo pairs 100 physical agents
  with 100 media-user states deterministically and shares political lean, trust, and stress while
  retaining separate physical and media decisions.
- Cached coupling stores target inputs for the next sync, records coupling/boundary receipts, carries
  state for 90-day fast-forward, and preserves branch-scoped invalidation.
- Media cache artifacts retain the same hashes, validity, dependencies, versions, ticks, and
  invalidation reasons as physical artifacts. Warm API requests send only the selected root's
  persisted dependency closure, so adding a second vertical does not slow World cache evaluation.
- Composition-only agent definitions are omitted from unrelated physical reports and appear when
  their composition instantiates them. Town through World reports remain exact versus Prompt 6.
- The DSL editor shows entity, spotlight, community, platform, coupling, and boundary code directly.
  The browser demo edits the recommendation coefficient, saves it, runs Reddit and coupled modules,
  and displays cached coupling receipts with no JSON or per-domain UI.
- Engine version is `0.10.0`. Prompt 7 changes were not committed or pushed.

## Implemented but narrower

- The shipped program keeps the existing one-hour base tick. Media action durations are measured in
  minutes and the synthetic test proves 1,440 media ticks per day, but the shipped physical/media
  demo does not run two different base tick sizes inside one process. Peer modules synchronize daily.
- Spotlight actions affect their community immediately. Cross-module effects, including spotlight
  consequences outside that community, cross at the next daily sync rather than per post.
- Mass posts use the declared `Post` schema and aggregate statistics; the runtime does not persist one
  Post object per mass action. This avoids per-post memory growth.
- Detailed platform flow expressions are evaluated before the detailed run and therefore do not use
  end-of-run child action counts. The cached platform response uses learned community outputs and is
  the proof for the viral-threshold spread behavior.
- Boundary pairing is deterministic by sorted sampled IDs. The demo does not import an external
  cross-service identity key.
- No LLM text generation was implemented. Spotlight and mass behavior work entirely from numeric DSL
  state; no LLM is called per user, post, or tick.
- Media values are concrete demo estimates, not fitted or calibrated real-world claims.
- Cold media learning uses the existing low/high multilinear learner and costs 864,000 detailed agent
  ticks. Warm media/platform/coupled evaluation is the scaled path.
- Appending media DSL increases per-process parse/compile overhead. All required thresholds still
  pass, but Town and World wall times are higher than Prompt 6's smaller source file.

## Deferred and not part of this demo

- Corporate hierarchy and corporate ↔ financial coupling.
- A new finance or stock-market system beyond the unchanged `finance_demo.dsl`.
- Atlas/research imports, evidence pipelines, fitted real-world behavior models, and calibration.
- Globe/polygon work, graphs, inheritance views, decision-tree views, visual editors, and per-level
  management panels.
- Persistent full-text mass posts and optional LLM-generated spotlight text.
- Interrupted-run pause/resume UI.

## Focused verification

- Generic media parser, hierarchy reuse, recommendation/viral threshold, moderation/topic closure,
  spotlight event weighting, action event fields, bidirectional coupling, coupling isolation, minute
  tick execution, DSL sync cadence, branch cache isolation, 90-day evolution, boundary identity, and
  monolith comparison: `6 passed` in `11.02s`.
- Prompt 6 cached composition tests: `9 passed`; country/world tests: `8 passed`.
- Existing generic composition tests: `5 passed`; archetype tests: `5 passed`; neighbourhood tests:
  `7 passed`.
- Targeted Python API routing/artifact persistence tests passed; dependency-closure artifact filtering
  has focused coverage through the persisted hierarchy test.
- Focused rendered media workflow passed in `10.3s` after the final boundary/source changes.
- Frontend production build, targeted Ruff, generated-contract check, Rust format/check, and
  `git diff --check` passed.
- Full backend and frontend suites were not run, as Prompt 7 explicitly forbids them during this work.
- Town, weighted household, neighbourhood, municipality, division, country, world, and finance state
  and report payloads are exact against Prompt 6 commit `d730638`.
- Source grep finds no hierarchy/domain runner and no shipped media/community/platform/influencer IDs
  in Rust engine source.

## Performance

- Town, 30 days / 720 ticks / 130 agents: `0.5440s`.
- Town, 365 days / 8,760 ticks / 130 agents: `4.4816s`.
- Weighted household population, 30 days / 180 agents: `0.4160s`.
- Detailed neighbourhood, 30 days / 180 agents: `0.4974s`.
- Detailed municipality, 30 days / 180 agents: `0.5964s`.
- Detailed division, 30 days / 180 agents: `0.6466s`.
- Detailed country, 30 days / 180 agents: `0.7782s`.
- Detailed world, 30 days / 180 agents: `1.2377s`.
- DSL-only finance, 30 days / 12 agents: `0.0436s`.
- Detailed media platform, 30 days / 100 users: `0.7146s`.
- Detailed coupled modules, 30 days / 200 module states: `1.0979s`.
- Cold World hierarchy bootstrap: `25.0194s`, `6,220,800` detailed ticks.
- Cold media/coupled bootstrap: `4.3750s`, `864,000` detailed ticks.
- Warm Toronto: `0.0179s`; Ontario: `0.0419s`; Canada: `0.0613s`; World: `0.0707s`.
- Warm PersonalFinance: `0.0188s`; Reddit: `0.0374s`; CoupledTownMedia: `0.0446s`.
- Every warm evaluation above used `0` agent ticks and returned `cache_hit=true`.
- Coupled 90-day fast-forward: `0.1022s`, `0` agent ticks, `90` daily flow snapshots.
- Default DSL hash: `sha256:08888ac64894912fbb36ebc5a53ac0f725d8f921ad4c29acd1606c5dbaa84802`.

## Final demo run

- Engine `0.10.0`; seed `1`; 365 days / 8,760 ticks; 130 agents.
- State and reports exactly match Prompt 6 commit `d730638`.

## Final weighted archetype run

- Seed `1`; 30 days; 180 agents; `0.4160s`.
- State and reports exactly match Prompt 6.

## Final neighbourhood run

- `UrbanLiberal`; seed `1`; 30 days; 180 agents; `0.4974s`.
- State and reports exactly match Prompt 6.

## Final municipality run

- `Toronto`; seed `1`; 30 days; 180 agents; `0.5964s`.
- State and reports exactly match Prompt 6.

## Final division run

- `Ontario`; seed `1`; 30 days; 180 agents; `0.6466s`.
- State and reports exactly match Prompt 6.

## Final country run

- `Canada`; seed `1`; 30 days; 180 agents; 40,000,000 represented; `0.7782s`.
- State and reports exactly match Prompt 6.

## Final world run

- `World`; seed `1`; 30 days; 180 agents; 6,999,999,999 represented; `1.2377s`.
- State and reports exactly match Prompt 6, including sparse adjacency and flow receipts.

## Final DSL-only finance run

- `MarketLab`; seed `1`; 30 days; 12 agents; `0.0436s`.
- State and reports exactly match Prompt 6.

## Final media run

- `Reddit`; seed `1`; 30 days; 100 simulated users; 8,000,000 represented; `0.7146s`.
- Final daily rates: posts `1.28`, comments `2.71`, likes `3.41`, shares `4.54` per eligible
  user. Mean sentiment is `0.3211`, mean outrage `0.5180`, and polarization `0.2823`.
- The platform records `474` viral actions on the final day and `12` spotlight actions.
- The one spotlight individual produced `425` retained events over the run. Each receipt includes its
  agent/source ID, topic, sentiment, engagement, age, outcome, place, and tick; mass receipts are not
  retained.
- PersonalFinance posts at `1.381` and shares at `4.651`; stricter CivicForum posts at `1.108` and
  shares at `4.351`. Both remain non-zero.

## Final cached media run

- Cold media/coupled learning: `864,000` detailed ticks in `4.3750s`.
- Warm PersonalFinance: `0.0188s`; warm Reddit: `0.0374s`; both `0` ticks and cache hits.
- Reddit reuses the two community caches; each community reuses the three mass-user archetypes and
  one spotlight artifact where applicable.
- Raising the DSL viral threshold to `1,000` yields zero cross-community viral spread; the baseline
  threshold yields positive spread.
- Changing PersonalFinance's signal invalidates PersonalFinance, Reddit, and the coupled root while
  CivicForum remains cached and no leaf agents rerun.

## Final coupled physical+media run

- `CoupledTownMedia`; seed `1`; 30 days; 100 physical states + 100 paired media states; `1.0979s`.
- Daily aggregate channels are explicit DSL: physical events → media signal, media outrage → physical
  protest/stress, and media sentiment → vote share. No per-post physical sync occurs.
- The boundary channel shares political lean, trust, and stress between each deterministic pair while
  physical and media decisions stay separate.
- Final detailed outputs: protest rate `9.12`, sentiment `0.3500`, outrage `0.5500`, vote share
  `0.5526`, physical→media coupling `1.0`, media→physical coupling `0.2683`.
- Against the cached split-module run, differences are: protest `2.72%`, sentiment `0%`, outrage
  `0.10%`, and vote share `0%`, all below the required 10%.
- Warm coupled evaluation is `0.0446s` with zero ticks. At 90 days, posting changes from `1.1384` on
  day 30 to `1.1088` on day 90, sharing from `5.8387` to `5.7519`, and polarization from `0.31415`
  to `0.31501`; the endpoint is not a repeated day-30 state.

## Prompt 8 corporate vertical

### Implemented

- `CompositionDefinition` remains the only recursive hierarchy type. Corporate levels are ordinary
  DSL strings, and the engine still exposes only `run_program` and `run_composition`. No corporate,
  store, franchise, brand, conglomerate, or company runner was added.
- The shipped DSL contains a corporate forest with one parent, two labels, two branches under one
  label, four managed stores, and a separate family-owned store root. Store leaves contain the
  physical `Store` place and the agents who buy, work, manage, quit, search, fire, close, reopen, set
  terms, and receive owner payouts.
- `random at current place where ...` and `current place` effects are generic target/effect
  primitives. Customer and worker actions use the same action definitions at every store. Target
  role filters resolve against agents at the source agent's exact current place and tick.
- Purchases debit customer money once and credit store cash/revenue once. Work debits store cash and
  credits worker money. Serve/work does not repeat the purchase transfer. A focused one-tick case
  conserves exactly `200` money units across customer, worker, and store.
- Employment is mutable DSL state. Quit and fire clear employer/employed, job search can restore the
  link, and store worker count changes with those transitions. Store status and price/wage decisions
  are also DSL actions rather than engine branches.
- Composition formulas are generic report/output primitives. They can use parameters, prior outputs,
  direct child outputs, `sum.output`, and `weighted.output`. Formula validation is line-numbered and
  formula outputs are available to detailed and cached coupling evaluation.
- Store, branch, label, and parent ledgers expose revenue, wages, costs, profit, payout, and cash.
  Lower levels report zero post-payout cash and one payout, so the same money is not counted as cash
  at every level. The parent retains received cash; debt and market capitalization remain separate.
- The independent store reports its payout to the owner path and never contributes to parent cash.
  Moving that store into a branch requires only a DSL membership edit; the parent profit recipient
  changes without Rust changes.
- Fractional composition weights and authoritative allocations are generic. A distribution declares
  `authoritative_total`, `sample_budget`, and allocation leaves. Every allocation level must sum to
  `1.0 ± 0.001`; largest-remainder allocation produces exact represented and simulated totals.
  Optional declared leaf counts must cover every leaf, match the derived counts, and sum exactly.
- The shipped Texas distribution declares `500` represented stores and a `30`-store sample. Weights
  allocate `200` to Dallas, `150` to Austin, and `150` to Houston; Dallas splits into `100` and `100`.
  Editing only the total to `550` reallocates the leaves and still sums exactly to `550`.
- Scoped place construction keeps each nested store's place separate. No global store list or
  cross-composition jump was added; movement still requires an explicit composition flow.
- Corporate price and wage policies propagate down through existing aggregate inputs. Revenue,
  wages, profit, and payouts aggregate up. Store operations sync daily, branches every 30 days, and
  labels/parent every 90 days; the existing divide-cleanly validator checks those clocks.
- Physical/corporate aggregate couplings are explicit DSL declarations. Removing the coupling block
  removes both coupling receipts and cross-module effects. Changing the root sync from 90 to 180
  days halves the coupling exchanges over 180 days without a Rust change.
- Corporate functions use the existing artifact learner/cache. A brand-only price edit invalidates
  that brand, its branches, and ancestors while the unrelated brand and family store remain cached.
  Ancestor branch inputs are tracked separately from feedback/coupling inputs, preserving both branch
  invalidation and standalone reuse of media artifacts.
- The editor lists the new site/branch/label/parent/forest/allocation/coupled compositions and their
  aggregate functions automatically. The focused browser demo edits revenue, wages, and franchise
  fee, runs detailed output, obtains a zero-tick warm cache hit, and opens physical/corporate flows.
- Engine version is `0.11.0`. Nothing was committed or pushed for Prompt 8.

### Implemented but narrower

- Corporate unit economics are concrete demo estimates authored in DSL. They are not researched,
  fitted, calibrated, or claims about real companies.
- Corporate sync ledgers are formula-derived state snapshots. Detailed Store place cash changes per
  transaction, while branch/label/parent cash and payout are evaluated at composition sync rather
  than stored in a persistent double-entry journal.
- The corporate detailed run samples the declared store-team archetypes and represents the remaining
  members through formulas/weights. The explicit Texas allocation is the scale proof: 30 simulated
  store units represent 500. It does not instantiate 500 store objects.
- The corporate forest itself contains the shared physical Store leaves and agents. The separate
  physical/corporate coupling demo uses deterministic boundary pairing between module states rather
  than aliasing one mutable agent object across both child modules.
- The owner payout executes at the DSL's daily closing hour. Label/parent earnings synchronize at 90
  days; no calendar-quarter accounting or tax calendar was added.

### Deferred and not part of Prompt 8

- Corporate-to-financial coupling, stock price, dividends, and capital allocation from market price.
- New finance behavior beyond the unchanged `finance_demo.dsl` / `MarketLab`.
- LLM text or decisions for CEOs, presidents, or other leaders.
- Media UI top-post views, generic disease/ideology spread, research/data imports, fitted real-world
  models, calibration, globe work, graphs, and visual editors.
- Pause/resume and persistent full-text mass posts.

### Prompt 8 focused verification

- Corporate parser/runtime suite: `12 passed` in `1.21s`. Coverage includes non-corporate proof of
  the generic primitives, same-place role targeting, conserved purchase/wage money, exact hierarchy
  sums, family payout conservation, DSL-only acquisition, authoritative allocation and validation,
  total expansion, branch cache isolation, explicit coupling, sync cadence, and 30-day composed
  comparison.
- Prompt 7 media tests: `6 passed`; cached composition tests: `9 passed`; country/world tests:
  `8 passed`; generic composition tests: `5 passed`; archetype tests: `5 passed`; neighbourhood
  tests: `7 passed`.
- Targeted Python source/run and persisted hierarchy tests: `2 passed` in `0.02s`.
- Focused rendered corporate workflow: `1 passed` in `4.3s` (`6.6s` including server setup).
- Rust format/check, Ruff, generated-contract check, frontend production build, and
  `git diff --check` passed. Full backend/frontend suites were not run because Prompt 8 explicitly
  requires focused tests only.
- Source grep finds no corporate/domain runner and none of the shipped corporate identifiers in
  Rust engine source.
- The first final-gate attempt stopped on an incorrect finance request shape. The second exposed a
  detailed coupling formula-output gap. A focused regression fixed it, and the completed next gate
  passed. The cached-media warm timing was repeated with compact persisted artifacts after an
  initial non-comparable request included embedded learning reports.

### Prompt 8 performance and compatibility

- Every final Town, weighted, neighbourhood, municipality, division, country, world, finance,
  Reddit, and coupled physical/media state/report payload exactly matches Prompt 7 commit `9e29a7c`.
- Town, 30 days / 720 ticks / 130 agents: `0.5031s`; Town, 365 days / 8,760 ticks:
  `3.9497s`.
- Weighted households: `0.4255s`; neighbourhood: `0.5017s`; municipality: `0.6211s`;
  division: `0.6832s`; country: `0.8357s`; world: `1.4312s`.
- Finance: `0.0531s`; Reddit: `0.5444s`; coupled physical/media: `1.1170s`. Their final payloads
  are exact against Prompt 7.
- Cold media/coupled learning: `4.3397s` and `864,000` agent ticks. Compact warm Reddit is
  `0.0458s`; compact warm coupled physical/media is `0.0543s`; both are cache hits with zero ticks.
- Default DSL hash: `sha256:c9f3474d4d2123c3039552184acf75c0aba1941f7f19012c39c7d9ed6b03d994`.

## Final corporate run

- `CorporateForest`; seed `1`; 30 days / 720 ticks; 6 sampled agent states; `0.0430s`.
- Synthetic exact ledger: Store A `65`, Store B `50`, Store C `58`, Store D `44`; branches `108`
  and `52`; labels `151` and `41`; parent profit/cash `181`; independent profit/payout `40`; forest
  total `221`. Lower-level post-payout cash is zero.
- The detailed 30-day and composed cached outputs differ by `0%` for revenue, profit, and wages.
- Before acquisition, parent profit is `181`, independent profit is `40`, and total is `221`. After
  the DSL-only membership move, parent profit is `221`, independent output is absent, and total stays
  `221`.

## Final cached corporate run

- Cold bootstrap: `0.1021s`, `8,640` detailed agent ticks. Compact warm evaluation: `0.0546s`, zero
  ticks, `cache_hit=true`.
- Store/branch artifacts are reused. Editing Brand One's price input invalidates Brand One, both of
  its branches, the parent, and forest; Brand Two, Store D, and FamilyStore remain cached.
- A scheduled price change makes day 90 differ from day 30, so fast-forward does not repeat a frozen
  endpoint.

## Final coupled physical+corporate run

- `CoupledPhysicalCorporate`; seed `1`; 30 days / 720 ticks; 7 sampled module states; `0.0496s`.
- The two directions are explicit: physical purchase output supplies corporate price policy, and
  corporate total profit supplies physical demand. Identity boundary fields are money and stress.
- Removing couplings yields zero coupling rows and removes the demand effect. Over 180 days, a
  90-day sync records four directional exchanges and a 180-day sync records two.
- Cold cached bootstrap: `0.1294s`, `11,520` detailed ticks. Compact warm evaluation: `0.0672s`, zero
  ticks, `cache_hit=true`.
