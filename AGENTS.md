# Petraterrium agent guide

## Working agreement

- The numeric engine is the source of truth. The globe renders recorded snapshots and must never invent numbers, interpolate results the engine did not produce, or run its own copy of the simulation.
- Determinism is a feature: the same config + seed produces the same snapshots. The streamed run and the stored final run are the same data — streaming reads the recorder, never a parallel computation.
- Data contracts come first: run config, daily snapshot, and metrics schemas are defined in one place and versioned. Backend and frontend validate against them; never hand-roll ad-hoc shapes in a route or component.
- Add or update a focused regression test before fixing a reported defect. Test the committed state change (engine output), not only the rendered preview.
- Do not add comments to code. The code itself should be readable: descriptive names, small focused functions, and clear structure, so no comments are needed to describe what the code does. If code would need a comment to be understood, rename or refactor it instead. The only exception is TODO / FAKE markers marking unfinished work, which do not explain code.
- Run the backend tests, the frontend build, and `git diff --check` after implementation changes.
- Never push commits or code changes to a remote repository on the user's behalf. Leave repository changes local for the user to review and push.
- Finish every task with a concise summary of what changed, how it was verified, and any material limitation or follow-up. Never leave the user to reconstruct the result from progress messages.

## Amazon-style engineering leadership

Use Amazon's official [Leadership Principles](https://www.amazon.jobs/content/en/our-workplace/leadership-principles) as an engineering operating model:

- **Customer Obsession:** work backwards from the demo journey a judge actually experiences — pick a scenario, watch the globe, check the receipts — and from the validation story: does the replay match history?
- **Ownership and Deliver Results:** own the outcome across engine, API, streaming, persistence, empty/error states, tests, and documentation. Do not stop at an endpoint that merely exposes unfinished plumbing.
- **Invent and Simplify / Frugality:** one engine, one recorder, one snapshot format — never a per-scenario engine. Reuse NumPy vectorization before adding a framework. Treat LLM calls as a scarce resource: cache, batch, and never call per agent per step.
- **Are Right, A Lot / Learn and Be Curious:** inspect actual outputs, seek evidence that could disprove the first theory, and state uncertainty candidly — bands and probabilities, never point claims dressed as predictions.
- **Insist on the Highest Standards / Dive Deep:** find the root cause, add a regression test, audit adjacent paths, and fix defects so they stay fixed. Treat determinism, data honesty (imputed-data flags, coefficient provenance), and accessibility as product requirements.
- **Think Big / Bias for Action:** design changes so the next scenario type fits as config, while promptly implementing reversible decisions and measuring the result.
- **Earn Trust / Have Backbone; Disagree and Commit:** communicate directly and respectfully, surface weak assumptions (for example, "this coefficient is a literature default, not fitted"), recommend the stronger product choice, and fully execute the chosen direction.
- **Strive to be Earth's Best Employer / Success and Scale Bring Broad Responsibility:** leave code and workflows easier for the next contributor, avoid hidden compute costs, protect user data boundaries (uploads stay in their run), and consider accessibility and downstream effects.

## Product completeness and interaction design

- Implement the complete user workflow, not only the first control that makes the underlying data reachable. For runs, cover creation, launch, live streaming, results exploration, comparison, export (CSV/JSON), saved-run management, deletion, empty states, confirmation, persistence feedback, and recoverable errors when those actions apply.
- Put choices at the decision point. Pick scenario, geography, and dates before launching; once a run is open, keep the view focused on that run instead of embedding run management in the run toolbar.
- Reuse one shared component and interaction model across scenarios. The globe, timeline, metric charts, and snapshot table are scenario-agnostic — never build a pandemic globe and a separate controversy globe.
- Before declaring a UI task complete, exercise the main path and the management paths in the rendered app: first run, multiple saved runs, reopen, delete, cancel/back, and failure recovery (backend down mid-stream → resume by sequence ID).
- Keep expensive hidden views suspended or unmounted. A background globe renderer or open SSE stream must not consume frames or connections when its view is hidden.

## Module size and responsibility

- Most source files should land around 150–500 lines.
- When a file grows past roughly 800 lines, review whether it owns more than one responsibility and extract cohesive modules when it does.
- This is a design signal, not a hard line cap. A cohesive 700-line engine module is preferable to eight 90-line fragments that require reading all eight together.
- Split by domain behavior or lifecycle, not arbitrary line ranges. Each extracted module should have a clear name, a small public API, and tests that can exercise it directly.
- Prefer a stable facade when many callers use an existing module. Move implementation behind the facade instead of creating widespread import churn without architectural benefit.
- Keep config parsing/validation, engine step functions, population generation, calibration/fitting, LLM calls, recorder/streaming, API routes, globe rendering, and UI markup in separate modules.
- Do not create pass-through files whose only purpose is reducing a line count.

## Engine and data invariants

These are non-negotiable correctness rules. A change that breaks one is wrong even if the app still runs.

- The frontend never computes simulation state; it renders snapshots the backend recorded. No client-side sim, no interpolated values presented as results.
- Same config hash + seed + engine version → identical snapshots. Any change to config, engine code, or data version changes the hash and invalidates cached results.
- Masses and leaders have a hard boundary: statistical masses update by vectorized rules; LLM leaders decide weekly and act only through parameters, messages, or environment changes — never by editing individual agents or snapshot numbers directly.
- Every snapshot carries run_id, day index, seed, engine version, and data version. A snapshot without provenance is never displayed as a result.
- Ensemble outputs are always distributions (median, bands, P(threshold)). A single run is never presented as "the prediction."
- No hindsight: backtest runs only see data dated on or before the simulated date. Leader prompts must not contain post-date information.
- Missing data is never silently filled with plausible defaults. Unknown values are flagged as imputed or unknown with provenance, or the run refuses with a clear error.
- User uploads belong to their run. Never mix uploaded data into the shared atlas or another run without explicit promotion.
- Every LLM leader decision is logged with its prompt version and output, so a run is auditable and reproducible.

## LLM call discipline

- All LLM calls go through one module: provider, model, prompt version, and caching in one place. Prompts are versioned strings, not inline f-strings scattered across routes.
- Every call logs model, prompt version, and estimated cost. Leader decisions are cached by (config hash, week, leader) so ensembles never re-call the same decision.
- No LLM call inside a per-step or per-agent loop. LLM decisions are weekly (leaders), cached/scripted inside ensembles, or offline (design). A per-step LLM call is a defect, not a feature.

## Engine purity and testing

- Step functions are pure: (state, params, rng) → next state. No I/O, no network, no wall-clock inside the step loop. This is what makes ensembles, caching, and A-vs-B comparison possible.
- Testing pyramid for sims: unit tests for step functions with known-answer cases (zero transmission → zero new infections; population conserved); property tests (totals preserved; monotonicity where it must hold); golden-file tests (a frozen config produces a frozen snapshot file — the determinism guard); one end-to-end fake-data run test.
- Engine errors fail the run with a stored error record, never a hung stream. The API exposes a run status machine (queued/running/done/failed) and the frontend renders each state.

## Refactoring checks

- Preserve serialized run/config compatibility unless the user explicitly says migration compatibility is unnecessary. Old run configs still load; old snapshots remain readable.
- Keep public API routes and snapshot/config schemas stable where practical; move internals first.
- Avoid per-step allocations in engine hot paths. Vectorize; never loop over millions of agents in Python.
- When extracting a system, move its tests or add focused coverage so later changes do not force readers back into a monolith.

## Framework architecture

Petraterrium has three separate evidence layers:

1. A model or hypothesis lives in a validated DSL config. A new system or scenario is data, not an engine branch.
2. Each coefficient has evidence status, source version, and uncertainty. Unknown or label-only values must remain visible and cannot silently become fitted effects.
3. Each population distribution has evidence status, source version, and uncertainty. Population generation happens before tick zero.

The existing flat backend package remains as a stable facade instead of moving every import under `backend/app/`. This avoids cosmetic churn in the working scaffold. The module boundaries from the framework design map to the repository as follows:

| Responsibility | Module |
| --- | --- |
| HTTP, jobs, SSE | `backend/petraterrium/main.py`, `service.py`, `recorder.py` |
| Shared run and API contracts | `backend/petraterrium/contracts.py` |
| DSL schema, validation, loading, rendering | `backend/petraterrium/dsl/` |
| Generic numeric tick loop | `backend/petraterrium/runtime.py`, exposed by `engine.py` |
| Old request-shape adapter | `backend/petraterrium/compatibility.py` |
| Atlas, imports, source loaders | `backend/petraterrium/atlas/` |
| Universal feature schemas and place distributions | `backend/petraterrium/atlas/features.py`, `backend/petraterrium/dsl/models.py` |
| Canonical regions, hierarchy, weighted aggregation | `backend/petraterrium/atlas/regions.py`, `backend/petraterrium/atlas/hierarchy.py` |
| Conditional choice evidence and evidence tiers | `backend/petraterrium/atlas/choice_evidence.py` |
| Harmonization and compositional estimates | `backend/petraterrium/framework_data.py` |
| Population, defaults, IPF, bundles | `backend/petraterrium/population.py` |
| Actions, conflicts, chains, roles | `backend/petraterrium/actions.py` |
| Sparse social influence | `backend/petraterrium/network.py` |
| Media generation, ranking, response | `backend/petraterrium/media.py` |
| Leaders and evidence table | `backend/petraterrium/leaders.py` |
| Ensemble anchor replay | `backend/petraterrium/ensembles.py` |
| Events, exact stories, causal receipts | `backend/petraterrium/events.py` |
| Static and recorded action decision graphs | `backend/petraterrium/decision_graph.py`, `frontend/src/decision-graph/` |
| Backtests and counterfactual differences | `backend/petraterrium/backtesting.py` |
| Central LLM provider boundary | `backend/petraterrium/llm_gateway.py` |
| Globe and WebGL picking | `frontend/src/globe.ts` |
| Stories and agent drill-down | `frontend/src/stories/`, `frontend/src/main.ts` |
| Manual DSL Builder | `frontend/src/dsl-builder/` |
| Data Organizer | `frontend/src/atlas/` |
| Shared generated schema and types | `shared/dsl-schema/`, `shared/types/` |

`engine.py` is intentionally a small stable facade. Scenario-specific compatibility construction lives outside the numeric engine. The frontend retains its existing flat Vite entry and globe modules while cohesive new views use the framework directories above.

## Framework rules

- The numeric runtime may interpret only validated DSL primitives. Never add a scenario name or scenario branch to `engine.py` or `runtime.py`.
- Bounded graph traversal uses schema-approved primitives and a maximum depth of five. No arbitrary loops, I/O, external calls, or LLM calls belong in DSL execution.
- A run identity includes normalized config, engine/data versions, evidence-table version, and population version.
- Mass snapshots are recorded at the configured interval. SSE reads those records and includes ordered `ensemble_update` events.
- Synthetic agent point views are backend projections from a recorded snapshot. The browser may aggregate or format recorded values but may not advance state.
- User imports begin in a run scope. Shared-atlas promotion remains a separate confirmed write.
- A single sample is labelled as one sample. Only actual multi-seed results may be framed as an ensemble distribution.
- Feature schemas are global; feature distributions are place-specific. Resolution uses city, country, subregion, region, then an explicitly approved global fallback. Unknown remains unknown.
- Resolved feature distributions are sampled during population generation before tick zero; unknown features remain absent from agent traits.
- MBTI remains label-only unless population-specific joint trait-and-outcome evidence is attached. An MBTI label cannot silently become a predictor.
- Canonical regions split China and India from the rest of Asia, place Mexico in Latin America and the Caribbean, and place Russia in Europe. Dataset region labels require a versioned mapping.
- Choice evidence keeps source tier, denominator, time unit, confidence interval, and date. Tier-five hints never become measured coefficients.
- Decision graphs are derived deterministically from validated DSL actions and recorded action logs. The browser may lay out and filter a graph but never infer transitions or frequencies.

## Run and verify

Backend setup and development:

```sh
cd backend
uv sync --locked
uv run python scripts/load_cities.py
uv run uvicorn petraterrium.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend development:

```sh
cd frontend
npm ci
npm run dev
```

Required verification after implementation changes:

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

The shared DSL schema and mirrored TypeScript contracts are generated by `backend/scripts/export_contracts.py`. Do not edit generated schema or type files by hand.
