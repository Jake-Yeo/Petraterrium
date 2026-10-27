# Petraterrium

Petraterrium is a DSL plus a generic deterministic engine, a versioned data atlas, and a globe-and-stories interface. A scenario is a validated config. The engine has no scenario-name branches, and the frontend displays state recorded by the backend rather than running its own simulation.

The framework keeps three things separate:

1. **How people act:** systems, states, transitions, actions, role gates, bounded network rules, media, events, leader actions, and couplings live in DSL.
2. **How strong each effect is:** every parameter carries a source, version, evidence status, and uncertainty. Joint trait-and-outcome data is required before a feature becomes a predictor.
3. **Who the population is:** distributions, defaults, behavior bundles, and IPF weights carry their own provenance. A marginal proves prevalence; it does not prove an outcome coefficient.

The bundled [smoke DSL](shared/dsl-schema/smoke-spread.json) uses explicit **FAKE** data to prove the contracts. It is a small signal-spread model across two invented places, not a forecast or a finished product scenario. Known evidence and depth gaps are listed in [MISSING.md](MISSING.md).

## What works

- Strict JSON/YAML DSL loading with a generated [shared schema](shared/dsl-schema/petraterrium-dsl.schema.json), semantic validation, plain-language rendering, and parameter sliders.
- Vectorized, double-buffered NumPy transitions with explicit tick/time scaling and daily snapshot aggregation.
- Stable run contracts, `202` job launch, ordered resumable SSE, cache identity across config, seed, source, evidence, and population versions, stored errors, exact metrics, and `ensemble_update` messages.
- Deterministic population generation, conditional defaults, behavior inheritance, IPF, typed relationships, homophilic sampled friends, role-gated actions, conflict receipts, bounded chains, sparse influence, media response, leaders, anchor replay, events, stories, and no-hindsight backtest units.
- Three.js globe clusters and dynamic place markers, viewport-limited WebGL agent points, picking, synthetic-agent receipts, a story newsroom, and a manual DSL Builder.
- The Data tab with the complete GeoNames cities500 backbone when loaded, server-side search/paging, direct/inherited/imputed/missing coverage, versioned run-scoped imports, validation, explicit promotion, source loaders, and behavior fitting.

The flat backend package is retained as a stable facade around cohesive modules. The map from the framework design to actual files is in [AGENTS.md](AGENTS.md).

## Run locally

Requirements are Python 3.13, [uv](https://docs.astral.sh/uv/), and Node.js 22.12 or newer. Simulation and exact schema mapping need no API key. Optional LLM-assisted import mapping uses `OPENAI_API_KEY` through the central provider boundary.

Start the backend:

```sh
cd backend
uv sync --locked
uv run python scripts/load_cities.py
uv run uvicorn petraterrium.main:app --host 127.0.0.1 --port 8000 --reload
```

Start the frontend in another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open <http://127.0.0.1:5173>. Vite proxies `/api` to FastAPI. API documentation is at <http://127.0.0.1:8000/docs>.

The **Simulation** tab still accepts the original request shape and resolves it through a compatibility DSL. The **DSL** tab loads the smoke config, validates edits live, exposes evidence status, and launches the full DSL request. The **Stories** tab opens exact snapshot-backed headlines and synthetic agents. The **Data** tab manages atlas coverage and imports.

## Run the smoke DSL through the API

```sh
cd backend
uv run python - <<'PY'
import json
from pathlib import Path
import httpx

dsl = json.loads(Path('../shared/dsl-schema/smoke-spread.json').read_text())
response = httpx.post(
    'http://127.0.0.1:8000/runs',
    json={'scenario': dsl['id'], 'seed': 42, 'dsl': dsl},
)
print(response.status_code, response.json()['run_id'])
PY
```

`POST /runs` returns the queued record with `202`; execution continues in the in-process background worker. Use the returned ID with `GET /runs/{id}` and `GET /runs/{id}/stream`. SSE sequence IDs cover every snapshot, the ensemble update, and the terminal event. Resume after an acknowledged sequence with `Last-Event-ID` or `?after=`.

## Add a new system

1. Copy the smoke JSON and change its `id` and `version`.
2. Declare state dimensions and initial distributions with evidence.
3. Declare parameters with units, provenance, evidence status, and uncertainty.
4. Add transitions, rules, bounded network traversal, actions, roles, events, media rules, leader actions, and explicit couplings as needed.
5. Set the population reference, tick config, and output spec before launch.
6. Submit the config to `POST /dsl/validate`; review missing references, distribution sums, role gates, chain termination, and implied aggregate checks.
7. Run it without changing Python engine code.
8. Add dated observed outcomes and backtest. Correct the rule, coefficient, or population input when validation fails; do not tune an unexplained number until a curve looks right.

The manual Builder is the first editing surface. An LLM designer can later propose the same JSON, but human confirmation and the same validator remain mandatory.

## API

| Route | Behavior |
| --- | --- |
| `GET /dsl/schema` | Canonical DSL JSON schema |
| `GET /dsl/smoke` | Thin FAKE smoke config |
| `POST /dsl/validate` | Semantic errors, warnings, and implied aggregates |
| `POST /dsl/render` | Plain-language summary and evidence-labelled sliders |
| `POST /runs` | `202`; queued new run or cached record |
| `GET /runs`, `GET /runs/{id}` | Status, output spec, snapshots, metrics, stories, versions, and missing fallbacks |
| `GET /runs/{id}/stream` | Ordered resumable `snapshot`, `ensemble_update`, and terminal SSE events |
| `GET /runs/{id}/agents` | Selected-place synthetic point payload, capped and filterable |
| `GET /agents/{id}` | Traits, state, log tier, relationships, timeline, and log scope |
| `GET /places/{id}` | Recorded place metrics, event IDs, and story arc |
| `GET /stories/{id}` | Exact story, place receipt, synthetic agents, and arc |
| `GET /data/coverage` | Field coverage from the live organizer |
| `POST /data/import` | Upload preview and human-confirmed mapping entry point |
| `/atlas/*` | Full organizer, import confirmation, commit, promotion, and source-loader API |

## Data atlas and feature dump

See [DATA.md](DATA.md) for cities500 loading, CSV/Parquet/JSON imports, direct versus inherited coverage, behavior fits, licensing, and source-specific limitations.

The reproducible extended feature dump combines GeoNames with the European Commission Urban Centre Database, redistributable World Bank indicators, UN household-size tables, and BLUE_DB local election results. Municipality-derived electoral alignment remains imputed and distinct from surveyed ideology.

```sh
cd backend
uv run python scripts/build_city_feature_dump.py --install-shared
```

Generated data stays under ignored `backend/data/`. The manifest records URLs, dates, hashes, licenses, row counts, and match semantics. The last published artifact is the [City feature dump 2026-10-26 release](https://github.com/Jake-Yeo/Petraterrium/releases/tag/data-atlas-2026-10-26). Builds are never pushed or published automatically.

## Contracts and reproducibility

[Backend contracts](backend/petraterrium/contracts.py) and [DSL models](backend/petraterrium/dsl/models.py) generate the frontend runtime schema, frontend types, shared DSL schema, and [mirrored shared types](shared/types/contracts.generated.ts):

```sh
cd backend
uv run python scripts/export_contracts.py
```

A run ID hashes normalized config, engine code/dependency version, data version, evidence-table version, and population version. The same complete input and seed yields byte-identical snapshots. An evidence or population version change invalidates the cache. The recorder supplies HTTP, SSE, metrics, stories, and agent projections from one result chain.

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

The tests cover DSL failures, deterministic state transitions, golden output, cache invalidation, stream resume, failures and deletion, population homophily, actions/conflicts/chains/roles, mapping persistence, safe composition, media/network effects, leader replay, exact stories, no hindsight, data imports and coverage, and the browser workflows.

## Intentionally not built

This framework task does not ship full pandemic, controversy, election, advertising, sports, environment, or zombie products. It does not claim to predict an outcome from one sample. Provider-backed leaders, full vector coupling of every thin module, durable workers, production spatial indexing, complete causal agent histories, and the saved backtest UI remain follow-up work recorded in [MISSING.md](MISSING.md).
