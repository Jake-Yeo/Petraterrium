import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class RustCoreError(RuntimeError):
    def __init__(self, code: str, message: str, path: str | None = None):
        self.code = code
        self.message = message
        self.path = path
        location = f" at {path}" if path else ""
        super().__init__(f"{code}{location}: {message}")


class RustCoreClient:
    def __init__(
        self,
        binary_path: str | Path | None = None,
        *,
        build_if_missing: bool = True,
    ):
        self.repository_root = Path(__file__).resolve().parents[3]
        self.manifest_path = self.repository_root / "engine-rust" / "Cargo.toml"
        self.profile = os.environ.get("PETRATERRIUM_RUST_CORE_PROFILE", "release")
        configured_path = binary_path or os.environ.get("PETRATERRIUM_RUST_CORE_BINARY")
        self.managed_binary = configured_path is None
        self.binary_path = (
            Path(configured_path).expanduser().resolve()
            if configured_path
            else self._default_binary_path()
        )
        if build_if_missing and self.managed_binary and self._needs_build():
            self._build()
        elif not self.binary_path.is_file():
            raise RustCoreError(
                "RUST_CORE_NOT_BUILT",
                f"Rust engine binary does not exist at {self.binary_path}",
            )

    def _default_binary_path(self) -> Path:
        target_profile = "release" if self.profile == "release" else "debug"
        return self.repository_root / "engine-rust" / "target" / target_profile / (
            "petraterrium-engine.exe" if os.name == "nt" else "petraterrium-engine"
        )

    def _needs_build(self) -> bool:
        if not self.binary_path.is_file():
            return True
        binary_mtime = self.binary_path.stat().st_mtime_ns
        build_inputs = [self.manifest_path, self.manifest_path.with_name("Cargo.lock")]
        build_inputs.extend((self.manifest_path.parent / "src").rglob("*.rs"))
        return any(path.stat().st_mtime_ns > binary_mtime for path in build_inputs)

    def _build(self) -> None:
        command = [
            "cargo",
            "build",
            "--manifest-path",
            str(self.manifest_path),
            "--locked",
            "--quiet",
        ]
        if self.profile == "release":
            command.append("--release")
        completed = subprocess.run(
            command,
            cwd=self.repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RustCoreError("RUST_CORE_BUILD_FAILED", detail)
        if not self.binary_path.is_file():
            raise RustCoreError(
                "RUST_CORE_BUILD_FAILED",
                f"Cargo completed without producing {self.binary_path}",
            )

    def call(self, request: Mapping[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(request, separators=(",", ":"), sort_keys=True)
        completed = subprocess.run(
            [str(self.binary_path)],
            cwd=self.repository_root,
            input=f"{encoded}\n",
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or f"Process exited {completed.returncode}"
            raise RustCoreError("RUST_CORE_PROCESS_FAILED", detail)
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if len(lines) != 1:
            raise RustCoreError(
                "RUST_CORE_PROTOCOL_ERROR",
                f"Expected one response line, received {len(lines)}",
            )
        try:
            response = json.loads(lines[0])
        except json.JSONDecodeError as error:
            raise RustCoreError("RUST_CORE_PROTOCOL_ERROR", str(error)) from error
        if not response.get("ok"):
            detail = response.get("error") or {}
            raise RustCoreError(
                str(detail.get("code", "RUST_CORE_ERROR")),
                str(detail.get("message", "Rust core rejected the request")),
                detail.get("path"),
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise RustCoreError(
                "RUST_CORE_PROTOCOL_ERROR",
                "Successful response did not contain an object result",
            )
        result["protocol_version"] = response.get("protocol_version")
        result["engine_version"] = response.get("engine_version")
        return result

    def health(self) -> dict[str, Any]:
        return self.call({"operation": "health"})

    def run_aggregate_dsl(
        self,
        dsl: Any,
        *,
        seed: int,
        ticks: int | None = None,
        tick_hours: float | None = None,
        snapshot_every_ticks: int | None = None,
    ) -> dict[str, Any]:
        payload = _model_payload(dsl)
        tick = payload.get("tick", {})
        resolved_ticks = ticks if ticks is not None else tick.get("total_ticks")
        resolved_tick_hours = tick_hours if tick_hours is not None else tick.get("tick_hours")
        if resolved_ticks is None or resolved_tick_hours is None:
            raise RustCoreError(
                "MISSING_TICK_CONFIG",
                "ticks and tick_hours must be provided directly or in dsl.tick",
            )
        if snapshot_every_ticks is None:
            snapshot_hours = tick.get("snapshot_every_hours", resolved_tick_hours)
            snapshot_every_ticks = max(1, round(snapshot_hours / resolved_tick_hours))
        return self.call(
            {
                "operation": "run_aggregate_dsl",
                "seed": seed,
                "ticks": resolved_ticks,
                "tick_hours": resolved_tick_hours,
                "snapshot_every_ticks": snapshot_every_ticks,
                "dsl": payload,
            }
        )

    def run_agents(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self.call({**request, "operation": "run_agents"})

    def run_location_tick(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self.call({**request, "operation": "run_location_tick"})

    def run_interaction_tree(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self.call({**request, "operation": "run_interaction_tree"})

    def validate_text_dsl(self, source: str) -> dict[str, Any]:
        return self.call({"operation": "validate_text_dsl", "source": source})

    def run_text_dsl(
        self,
        source: str,
        *,
        seed: int,
        ticks: int,
        total_represented_pool: int | None = None,
        role_parameters: Mapping[str, Mapping[str, float]] | None = None,
        dsl_source_hash: str | None = None,
        exemplar_cache: Mapping[str, Mapping[str, Any]] | None = None,
        exemplar_inputs: Mapping[str, Mapping[str, float]] | None = None,
        events: list[str] | None = None,
        continuation: Mapping[str, Any] | None = None,
        composition_id: str | None = None,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "operation": "run_text_dsl",
            "source": source,
            "seed": seed,
            "ticks": ticks,
        }
        if total_represented_pool is not None:
            request["total_represented_pool"] = total_represented_pool
        if dsl_source_hash is not None:
            request["dsl_source_hash"] = dsl_source_hash
        if exemplar_cache is not None:
            request["exemplar_cache"] = {
                exemplar_id: dict(entry) for exemplar_id, entry in exemplar_cache.items()
            }
        if exemplar_inputs is not None:
            request["exemplar_inputs"] = {
                exemplar_id: dict(inputs) for exemplar_id, inputs in exemplar_inputs.items()
            }
        if events is not None:
            request["events"] = list(events)
        if role_parameters is not None:
            request["role_parameters"] = {
                role: dict(parameters) for role, parameters in role_parameters.items()
            }
        if continuation is not None:
            request["continuation"] = dict(continuation)
        if composition_id is not None:
            request["composition_id"] = composition_id
        return self.call(request)

    def evaluate_text_dsl_aggregate(
        self,
        source: str,
        *,
        dsl_source_hash: str,
        function_id: str,
        seed: int,
        days: int,
        evaluated_at_day: int,
        inputs: Mapping[str, float],
        events: list[str],
        artifact: Mapping[str, Any] | None = None,
        force_relearn: bool = False,
    ) -> dict[str, Any]:
        return self.call(
            {
                "operation": "evaluate_aggregate",
                "source": source,
                "dsl_source_hash": dsl_source_hash,
                "function_id": function_id,
                "seed": seed,
                "days": days,
                "evaluated_at_day": evaluated_at_day,
                "inputs": dict(inputs),
                "events": events,
                "artifact": dict(artifact) if artifact is not None else None,
                "force_relearn": force_relearn,
            }
        )

    def run_compiled_markov(
        self,
        program: Any,
        compilation: Any,
        **execution: Any,
    ) -> dict[str, Any]:
        from .markov_adapter import compiled_markov_request

        request = compiled_markov_request(program, compilation, **execution)
        return self.run_agents(request)

    def csr_matvec(
        self,
        matrix: Mapping[str, Any],
        values: list[float],
        *,
        normalize_rows: bool = False,
    ) -> list[float]:
        result = self.call(
            {
                "operation": "csr_matvec",
                "matrix": matrix,
                "values": values,
                "normalize_rows": normalize_rows,
            }
        )
        return result["values"]


def _model_payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json")
    elif isinstance(value, Mapping):
        payload = dict(value)
    else:
        raise TypeError("dsl must be a mapping or expose model_dump")
    if not isinstance(payload, dict):
        raise TypeError("dsl payload must be an object")
    return payload
