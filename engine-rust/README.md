# Petraterrium Rust core

The binary accepts newline-delimited JSON on standard input and writes one response per line to standard output. Every response carries `protocol_version`, `engine_version`, `ok`, and either `result` or a structured `error`.

Supported operations:

- `health` reports the numeric implementation and update discipline.
- `run_aggregate_dsl` executes the existing aggregate DSL states, systems, parameters, population, and tick scaling.
- `run_agents` executes reusable evidence-backed Markov modules over struct-of-arrays agent columns.
- `csr_matvec` applies a sparse CSR matrix directly for integration and validation.

`run_agents` requires every transition probability and meaningful-action probability to carry source, version, evidence status, and uncertainty. Only `present` and `measured` evidence may execute. Null probabilities, inherited or imputed values, literature estimates, and unmatched conditional transition rules are rejected before initialization or sampling. Conditional rules are evaluated over declared trait, memory, time, place-state, and neighbour-state inputs. Each active node's resolved outgoing probabilities must sum to one.

Deterministic sampling uses a seeded ChaCha8 stream pinned by `Cargo.lock`. Aggregate results return the seed, tick duration, place order, state-value order, and each recorded count matrix so the Python wrapper can construct versioned snapshot contracts without recomputing state.

Aggregate DSL execution treats `population.size` as the representative-agent count and `population.place_populations` as represented mass. They may differ. Aggregate state matrices and conservation checks use represented place mass.

Agent state, active module, place, traits, and persisted memory are column vectors. A tick reads current columns, computes all selected transitions, writes a second buffer, applies module routing, then swaps buffers. Place shards are evaluated independently. Border, media, and weekly-leader payloads cross shard boundaries only at their configured synchronization cadence. Weekly leader decisions and all LLM work are external payloads; the core never invokes an LLM.

CSR neighbour edges are restricted to agents in the same place shard. Cross-place influence is rejected and must arrive as a versioned border synchronization payload.

Routine actions come from schedule-table rows. Meaningful actions evaluate every agent with the seeded generator and enqueue only winners. Neighbour inputs use a CSR sparse adjacency matrix-vector multiplication.

The Python adapter executes an evidence-resolved backend `MarkovProgram` without copying draft probabilities into the Rust request:

```python
result = RustCoreClient().run_compiled_markov(
    program,
    compilation,
    seed=93,
    ticks=2,
    tick_hours=24,
    agents=agent_columns,
    places=place_shards,
)
```

The exact adapter API is `compiled_markov_request(program, compilation, *, seed, ticks, tick_hours, agents, places, start_hour=0, start_weekday=0, input_bindings=None, network=None, schedules=(), meaningful_actions=(), synchronization=None)`. It returns a `run_agents` request. Every compiled probability must have `status == "resolved"` and a numeric evidence value or the adapter raises `UNRESOLVED_MARKOV_PROBABILITY` before starting Rust. The compiler's place, time, and trait stratum are emitted as rule conditions, so a rate fitted for one context cannot leak into another. Categorical trait columns carry an ordered dictionary with source and version; the adapter encodes labels and Rust validates every code against that dictionary. An absent dictionary, unknown label, or unmatched agent fails before sampling. Evidence source, version, status, uncertainty, source date, evidence id and kind, and confidence bounds cross the bridge unchanged. State updates remain double-buffered in the Rust core.

Build and run:

```sh
cargo build --manifest-path engine-rust/Cargo.toml --release
printf '%s\n' '{"operation":"health"}' | engine-rust/target/release/petraterrium-engine
```
