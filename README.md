# Petraterrium

A small, checkable world: a FastAPI + NumPy engine records a seeded pandemic run, streams the recorded days over SSE, and displays them on a Three.js globe.

The **Data** tab organizes the complete GeoNames cities500 backbone, field coverage, source versions, and run-scoped imports. See the [data atlas guide](DATA.md) for loading the full city list, importing CSV/Parquet/JSON, source loaders, behaviour fitting, licensing, and coverage definitions.

The atlas also has a reproducible extended city-feature dump. It combines the full GeoNames backbone with the European Commission Urban Centre Database, redistributable World Bank Development Indicators, and the UN household-size database without relabeling country data as city observations. Build it and explicitly publish its canonical country marginals into the shared atlas with:

```sh
cd backend
uv run python scripts/build_city_feature_dump.py --install-shared
```

The generated Parquet dataset and source downloads stay under ignored `backend/data/`. Its manifest records source URLs, release dates, hashes, row counts, licences, and match semantics.

The current public artifact is available from the [City feature dump 2026-10-26 release](https://github.com/Jake-Yeo/Petraterrium/releases/tag/data-atlas-2026-10-26).

**The simulation uses FAKE data.** The four simulated countries have real names and approximate marker positions, invented populations, and an unfitted placeholder SEIR model. This is a demonstration, not a forecast or historical validation. The Data tab's real city backbone is separate from those fake simulation inputs.

## Run locally

Requirements: Python 3.13, [uv](https://docs.astral.sh/uv/), and Node.js 22.12+ with npm. The simulator requires no API keys. The Data tab uses a local SQLite database; optional LLM mapping needs an OpenAI API key.

In the first terminal:

```sh
cd backend
uv sync --locked
uv run python scripts/load_cities.py
uv run uvicorn petraterrium.main:app --host 127.0.0.1 --port 8000 --reload
```

In the second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open <http://127.0.0.1:5173>. Vite proxies `/api` to the backend. API documentation is at <http://127.0.0.1:8000/docs>. VS Code also has a **Petraterrium: dev** task after dependencies are installed.

Choose **New experiment**, select countries, set the inclusive day range and seed, and launch. Scrub or play the recorded timeline, inspect the country counts and snapshot receipt, export JSON/CSV, reopen saved runs, or delete them with confirmation. Runs are saved **only in this server process's memory**; a restart clears the list.

## Contracts and reproducibility

[Backend contracts](backend/petraterrium/contracts.py) are the source of truth. The [TypeScript types](frontend/src/contracts.generated.ts) and [runtime JSON Schema](frontend/src/contracts.schema.json) are generated from those Pydantic models. The browser validates HTTP and SSE data using the schema. After editing contracts:

```sh
cd backend
uv run python scripts/export_contracts.py
```

The cache key is SHA-256 of canonical JSON containing the normalized config, engine version, and data version. Country order is normalized. The engine version includes a digest of every backend package source file and the NumPy version; the fake-data version includes a digest of the population catalog. A source, dependency version, config, or data change therefore changes the run identity. Reproducibility across environments uses the committed lockfile and NumPy version.

Each snapshot contains the deterministic run ID, day, country compartments, seed, engine version, and data version. The initial state is recorded on `start_day`; one transition is recorded per following day through `end_day`. Initial infections begin in Italy when selected, otherwise the first selected country in code order.

The placeholder step samples simultaneous bounded binomial transitions S → E → I → R. It preserves integer population per country and uses `numpy.random.default_rng(seed)`. Rates are explicitly unfitted. Mixing uses the selected countries' population-weighted infected prevalence. No timestamps, network, I/O, or clock input enter the engine step loop.

The recorder owns snapshots and sequence-numbered events. HTTP results, final metrics, and SSE all read that same recorder; the browser never simulates or interpolates compartment counts. The line chart connects recorded days, and the scrubber selects exact snapshots. Peak metrics use the earliest day with the maximum recorded infected total, including the initial day.

## API

| Route | Behavior |
| --- | --- |
| `GET /health` | Health and FAKE-data marker |
| `GET /catalog` | Four fake populations, approximate coordinates, versions, and notice |
| `POST /runs` | `202`; new queued run or existing run with cached snapshots and metrics |
| `GET /runs` | Saved runs in the current server process, newest first |
| `GET /runs/{id}` | Config, status, recorded snapshots, metrics, or stored failure |
| `GET /runs/{id}/stream` | Recorded SSE `snapshot` events followed by `run-complete` or `run-failed` |
| `DELETE /runs/{id}` | `204`; delete stored results and stop an active worker |

```sh
curl -s http://127.0.0.1:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"pandemic","countries":["ITA","FRA","DEU","ESP"],"start_day":0,"end_day":160,"seed":42,"parameters":{"transmission":0.38,"progression":0.2,"recovery":0.09,"mixing":0.04,"initial_infected":40}}'
```

Use the returned `run_id` to inspect or stream a run. SSE IDs start at 1 and include the terminal event. Resume **after** an acknowledged event using `Last-Event-ID: 12` or `?after=12`; the header takes precedence. Invalid cursors receive `422`; missing runs receive `404`. Streams send keepalive comments while waiting and terminate on completion or a stored failure. An engine failure moves `queued → running → failed` and stores an error; successful runs finish as `done`.

After a connection error, the browser opens a new EventSource with `?after=` set to its last received sequence ID. Hiding the page or opening a management dialog closes its stream and suspends the renderer; resuming replays any missed recorded events. Scrolling the globe offscreen also suspends its renderer. Switching runs and leaving the page dispose the previous stream. **Reconnect** also reloads the stored run if an interruption needs manual recovery. A backend restart loses the in-memory record, so such runs cannot resume.

## Verify

```sh
cd backend
uv run pytest
uv run ruff check .
uv run python scripts/export_contracts.py --check
cd ../frontend
npm run build
cd ..
git diff --check
```

Browser checks start their own development servers when needed:

```sh
cd frontend
npx playwright install chromium
npm run test:e2e
```

Tests cover known-answer steps, conservation and monotonicity across seeds, byte-identical files against a frozen golden fixture, cache/version invalidation, API status and result identity, sequence resumption, terminal failures, deletion, contract parity, the desktop/mobile workflow, and interrupted SSE reconnection. Browser screenshots and failure traces are local test output and are ignored by Git.

## Scope

- Implemented: one pandemic scenario, four FAKE countries, an in-process scheduler and recorder, deterministic caching, SSE, the globe/timeline/chart workflow, and the [Data atlas](DATA.md) with durable versioned imports.
- Stub: [weekly leader interface](backend/petraterrium/leaders.py) returns no-ops.
- TODO: connecting real atlas data to the simulation, top-metro simulation and density-adjusted city projections, historical Italy validation, calibration, additional scenarios, LLM leaders, ensembles, comparison, custom vectors, Modal workers, durable run-result persistence, authentication, and deployment. These are not implemented here.

Run one API worker for this scaffold. Separate worker processes would have independent stores. Computation is intentionally small and in process; production scheduling, cache eviction, and durable storage are future work.
