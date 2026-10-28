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
