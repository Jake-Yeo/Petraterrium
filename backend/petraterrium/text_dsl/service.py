from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..rust_core import RustCoreClient
from .models import (
    AggregateCacheVersion,
    AggregateEvaluationRequest,
    AggregateEvaluationResult,
    TextDslDiagnostic,
    TextDslDocument,
    TextDslReport,
    TextDslReportDelta,
    TextDslReportValue,
    TextDslRunRequest,
    TextDslRunResult,
    TextDslRunSummary,
    TextDslValidation,
)


def default_text_dsl_root() -> Path:
    configured = os.getenv("PETRATERRIUM_TEXT_DSL_ROOT")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[2] / "data" / "text_dsl"


def shipped_text_dsl_path() -> Path:
    return Path(__file__).resolve().parents[3] / "engine-rust" / "dsl" / "default.dsl"


class TextDslService:
    def __init__(
        self,
        rust: RustCoreClient | None = None,
        root: Path | None = None,
        default_path: Path | None = None,
    ):
        self.rust = rust or RustCoreClient()
        self.root = Path(root or default_text_dsl_root())
        self.default_path = Path(default_path or shipped_text_dsl_path())
        self.active_path = self.root / "active.dsl"
        self.metadata_path = self.root / "active.json"
        self.runs_path = self.root / "runs"
        self.aggregate_cache_path = self.root / "aggregate_cache"
        self._validation_cache: dict[str, TextDslValidation] = {}
        self.root.mkdir(parents=True, exist_ok=True)
        self.runs_path.mkdir(parents=True, exist_ok=True)
        self.aggregate_cache_path.mkdir(parents=True, exist_ok=True)

    def current(self) -> TextDslDocument:
        code = self._code()
        metadata = self._metadata()
        return TextDslDocument(
            code=code,
            source_hash=self._hash(code),
            saved_at=metadata.get("saved_at"),
            validation=self.validate(code),
        )

    def validate(self, code: str) -> TextDslValidation:
        source_hash = self._hash(code)
        cached = self._validation_cache.get(source_hash)
        if cached is not None:
            return cached
        result = self.rust.validate_text_dsl(code)
        diagnostics = tuple(
            TextDslDiagnostic.model_validate(value)
            for value in result.get("diagnostics", [])
        )
        validation = TextDslValidation(
            valid=bool(result.get("valid")),
            program_id=result.get("program_id"),
            version=result.get("version"),
            tick_hours=result.get("tick_hours"),
            adult_population=result.get("adult_population"),
            entities=tuple(str(value) for value in result.get("entities", [])),
            policies=tuple(str(value) for value in result.get("policies", [])),
            roles=tuple(str(value) for value in result.get("roles", [])),
            role_distributions=tuple(
                str(value) for value in result.get("role_distributions", [])
            ),
            spotlights=tuple(str(value) for value in result.get("spotlights", [])),
            archetypes=tuple(str(value) for value in result.get("archetypes", [])),
            composition_archetypes=tuple(
                dict(value) for value in result.get("composition_archetypes", [])
            ),
            weighted_populations=tuple(
                str(value) for value in result.get("weighted_populations", [])
            ),
            aggregate_functions=tuple(
                dict(value) for value in result.get("aggregate_functions", [])
            ),
            compositions=tuple(dict(value) for value in result.get("compositions", [])),
            composition_populations=tuple(
                str(value) for value in result.get("composition_populations", [])
            ),
            neighbourhoods=tuple(str(value) for value in result.get("neighbourhoods", [])),
            neighbourhood_populations=tuple(
                str(value) for value in result.get("neighbourhood_populations", [])
            ),
            diagnostics=diagnostics,
            graph=(dict(result["graph"]) if result.get("graph") is not None else None),
        )
        self._validation_cache[source_hash] = validation
        return validation

    def save(self, code: str, expected_hash: str) -> TextDslDocument:
        current = self.current()
        if current.source_hash != expected_hash:
            raise ValueError("DSL source changed; reload before saving")
        validation = self.validate(code)
        if not validation.valid:
            raise ValueError("DSL has validation errors")
        saved_at = datetime.now(UTC).isoformat()
        self._write(self.active_path, code)
        self._write(
            self.metadata_path,
            json.dumps(
                {"source_hash": self._hash(code), "saved_at": saved_at},
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        return TextDslDocument(
            code=code,
            source_hash=self._hash(code),
            saved_at=saved_at,
            validation=validation,
        )

    def reset(self) -> TextDslDocument:
        self.active_path.unlink(missing_ok=True)
        self.metadata_path.unlink(missing_ok=True)
        return self.current()

    def run(self, request: TextDslRunRequest) -> TextDslRunResult:
        document = self.current()
        if not document.validation.valid:
            raise ValueError("DSL has validation errors")
        tick_hours = document.validation.tick_hours or 1
        ticks = round(request.days * 24 / tick_hours)
        population_id = getattr(request, "population_id", None)
        composition_id = getattr(request, "composition_id", None)
        composition_population_id = getattr(request, "composition_population_id", None)
        neighbourhood_id = getattr(request, "neighbourhood_id", None)
        neighbourhood_population_id = getattr(request, "neighbourhood_population_id", None)
        result = self.rust.run_text_dsl(
            document.code,
            seed=request.seed,
            ticks=ticks,
            population_id=population_id,
            composition_id=composition_id,
            composition_population_id=composition_population_id,
            neighbourhood_id=neighbourhood_id,
            neighbourhood_population_id=neighbourhood_population_id,
        )
        run_id = uuid.uuid4().hex
        created_at = datetime.now(UTC).isoformat()
        reports = tuple(
            TextDslReport.model_validate(report)
            for report in result.get("reports", [])
        )
        baseline = (
            self.get_run(request.baseline_run_id)
            if request.baseline_run_id is not None
            else None
        )
        agents = result.get("state", {}).get("agents", [])
        adult_population = (
            sum(agent.get("parent_id") is None for agent in agents)
            if population_id is not None
            or composition_id is not None
            or composition_population_id is not None
            or neighbourhood_id is not None
            or neighbourhood_population_id is not None
            else document.validation.adult_population or 0
        )
        response = TextDslRunResult(
            run_id=run_id,
            source_hash=document.source_hash,
            seed=request.seed,
            days=request.days,
            ticks=ticks,
            adult_population=adult_population,
            total_agents=len(agents),
            generated_children=max(0, len(agents) - adult_population),
            population_id=(
                population_id
                if composition_id is None
                and composition_population_id is None
                and neighbourhood_id is None
                and neighbourhood_population_id is None
                else (
                    f"composition:{composition_id}"
                    if composition_id is not None
                    else (
                        f"composition_population:{composition_population_id}"
                        if composition_population_id is not None
                        else (
                            f"neighbourhood:{neighbourhood_id}"
                            if neighbourhood_id is not None
                            else f"neighbourhood_population:{neighbourhood_population_id}"
                        )
                    )
                )
            ),
            results_title=str(result.get("results_title", "Results")),
            results_subtitle=str(result.get("results_subtitle", "")),
            reports=reports,
            comparison=self._comparison(reports, baseline.reports if baseline else ()),
            engine_version=str(result.get("engine_version", "unknown")),
            created_at=created_at,
            raw_result=result,
        )
        self._persist(response, result)
        return response

    def evaluate_aggregate(
        self,
        request: AggregateEvaluationRequest,
    ) -> AggregateEvaluationResult:
        document = self.current()
        if not document.validation.valid:
            raise ValueError("DSL has validation errors")
        started = time.perf_counter()
        cached_composition = any(
            value.get("id") == request.function_id and bool(value.get("cached"))
            for value in document.validation.compositions
        )
        if cached_composition:
            result = self.rust.evaluate_cached_composition(
                document.code,
                dsl_source_hash=document.source_hash,
                function_id=request.function_id,
                seed=request.seed,
                days=request.days,
                evaluated_at_day=request.evaluated_at_day,
                inputs=request.inputs,
                branch_inputs=request.branch_inputs,
                input_schedule=list(request.input_schedule),
                events=list(request.events),
                artifacts=self._hierarchy_artifact_catalog(request.function_id),
                force_relearn=request.force_relearn,
            )
        else:
            artifact = self._latest_aggregate_artifact(request.function_id)
            result = self.rust.evaluate_text_dsl_aggregate(
                document.code,
                dsl_source_hash=document.source_hash,
                function_id=request.function_id,
                seed=request.seed,
                days=request.days,
                evaluated_at_day=request.evaluated_at_day,
                inputs=request.inputs,
                events=list(request.events),
                artifact=artifact,
                force_relearn=request.force_relearn,
            )
        elapsed_seconds = time.perf_counter() - started
        learned = dict(result["artifact"])
        returned_artifacts = result.get("artifacts", {request.function_id: learned})
        for function_id, value in returned_artifacts.items():
            artifact = dict(value)
            latest = self._latest_aggregate_artifact(str(function_id))
            if latest is None or int(artifact["version"]) > int(latest["version"]):
                self._persist_aggregate_artifact(str(function_id), artifact)
        return AggregateEvaluationResult(
            function_id=str(result["function_id"]),
            cache_hit=bool(result["cache_hit"]),
            invalidation_reason=result.get("invalidation_reason"),
            agent_ticks=int(result["agent_ticks"]),
            inputs_hash=str(result["inputs_hash"]),
            valid_from=int(result["valid_from"]),
            valid_until=int(result["valid_until"]),
            dsl_source_hash=str(result["dsl_source_hash"]),
            cache_version=int(learned["version"]),
            time_series=tuple(dict(value) for value in result.get("time_series", [])),
            reports=tuple(
                TextDslReport.model_validate(value) for value in result.get("reports", [])
            ),
            elapsed_seconds=elapsed_seconds,
            cache_tree=result.get("cache_tree"),
            feedback_iterations=int(result.get("feedback_iterations", 0)),
            feedback_change_percent=float(result.get("feedback_change_percent", 0.0)),
        )

    def aggregate_versions(self, function_id: str) -> tuple[AggregateCacheVersion, ...]:
        versions = []
        for path in self._aggregate_function_path(function_id).glob("v*.json.gz"):
            artifact = self._read_run(path)
            versions.append(
                AggregateCacheVersion(
                    function_id=str(artifact["function_id"]),
                    version=int(artifact["version"]),
                    dsl_source_hash=str(artifact["dsl_source_hash"]),
                    valid_from=int(artifact["valid_from"]),
                    valid_until=int(artifact["valid_until"]),
                    inputs_hash=str(artifact["inputs_hash"]),
                    learning_agent_ticks=int(artifact["learning_agent_ticks"]),
                )
            )
        return tuple(sorted(versions, key=lambda value: value.version))

    def list_runs(self) -> tuple[TextDslRunSummary, ...]:
        result = []
        for path in sorted(self.runs_path.glob("*.json.gz"), reverse=True):
            payload = self._read_run(path)
            result.append(TextDslRunSummary.model_validate(payload["summary"]))
        return tuple(result)

    def get_run(self, run_id: str) -> TextDslRunResult:
        path = self.runs_path / f"{run_id}.json.gz"
        if not path.exists():
            raise KeyError(run_id)
        view = self._read_run(path)["view"]
        if "reports" not in view:
            view = self._legacy_run_view(view)
        return TextDslRunResult.model_validate(view)

    def _persist(self, view: TextDslRunResult, raw: dict[str, Any]) -> None:
        summary = TextDslRunSummary(
            run_id=view.run_id,
            source_hash=view.source_hash,
            seed=view.seed,
            days=view.days,
            ticks=view.ticks,
            total_agents=view.total_agents,
            population_id=view.population_id,
            created_at=view.created_at,
        )
        payload = {
            "summary": summary.model_dump(mode="json"),
            "view": view.model_dump(mode="json"),
            "raw": raw,
        }
        path = self.runs_path / f"{view.run_id}.json.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))

    def _read_run(self, path: Path) -> dict[str, Any]:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)

    def _latest_aggregate_artifact(self, function_id: str) -> dict[str, Any] | None:
        paths = sorted(self._aggregate_function_path(function_id).glob("v*.json.gz"))
        return self._read_run(paths[-1]) if paths else None

    def _aggregate_artifact_catalog(self) -> dict[str, dict[str, Any]]:
        result = {}
        for path in self.aggregate_cache_path.iterdir():
            if not path.is_dir():
                continue
            artifact = self._latest_aggregate_artifact(path.name)
            if artifact is not None:
                result[path.name] = artifact
        return result

    def _hierarchy_artifact_catalog(
        self,
        function_id: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        result = self._aggregate_artifact_catalog()
        if function_id is not None and function_id in result:
            selected: dict[str, dict[str, Any]] = {}
            pending = [function_id]
            while pending:
                current = pending.pop()
                if current in selected or current not in result:
                    continue
                artifact = result[current]
                selected[current] = artifact
                pending.extend(str(value) for value in artifact.get("dependencies", {}))
            result = selected
        for artifact in result.values():
            artifact["points"] = [
                {**point, "reports": []} for point in artifact.get("points", [])
            ]
        return result

    def _persist_aggregate_artifact(
        self,
        function_id: str,
        artifact: dict[str, Any],
    ) -> None:
        path = self._aggregate_function_path(function_id)
        path.mkdir(parents=True, exist_ok=True)
        target = path / f"v{int(artifact['version']):06}.json.gz"
        with gzip.open(target, "wt", encoding="utf-8") as handle:
            json.dump(artifact, handle, sort_keys=True, separators=(",", ":"))

    def _aggregate_function_path(self, function_id: str) -> Path:
        safe = "".join(
            character
            for character in function_id
            if character.isalnum() or character in "_-"
        )
        if not safe or safe != function_id:
            raise ValueError("Invalid aggregate function ID")
        return self.aggregate_cache_path / safe

    @staticmethod
    def _legacy_run_view(view: dict[str, Any]) -> dict[str, Any]:
        columns = (
            ("population", "Population", "integer"),
            ("mean_money", "Money", "number"),
            ("mean_health", "Health", "decimal"),
            ("mean_stress", "Stress", "decimal"),
            ("fights_per_day", "Fights / day", "integer"),
            ("average_family_size", "Family size", "decimal"),
            ("average_kids_per_family", "Kids / family", "decimal"),
            ("action_rates_per_1000", "Action rates / 1,000", "action_rates"),
        )
        rows = view.get("final_aggregates", [])
        reports = []
        report_ids = {"place": "places", "agent_type": "agent_types"}
        report_titles = {"place": "Places", "agent_type": "Agent types"}
        for group_kind, report_id in report_ids.items():
            selected = [row for row in rows if row.get("group_kind") == group_kind]
            if not selected:
                continue
            reports.append(
                {
                    "id": report_id,
                    "title": report_titles[group_kind],
                    "group_by": group_kind,
                    "display": "table",
                    "record": "final",
                    "columns": [
                        {
                            "id": field,
                            "label": label,
                            "format": format_name,
                            "metric": "Legacy",
                            "line": 1,
                        }
                        for field, label, format_name in columns
                    ],
                    "snapshots": [
                        {
                            "tick": max(int(row.get("tick", 0)) for row in selected),
                            "rows": [
                                {
                                    "group_id": str(row["group_id"]),
                                    "values": {
                                        field: row.get(field, 0)
                                        for field, _, _ in columns
                                    },
                                }
                                for row in selected
                            ],
                        }
                    ],
                }
            )
        event_values = {
            "actions": {
                str(key): float(value)
                for key, value in view.get("action_counts", {}).items()
            },
            "outcomes": {
                str(key): float(value)
                for key, value in view.get("outcome_counts", {}).items()
            },
        }
        if any(event_values.values()):
            reports.append(
                {
                    "id": "event_totals",
                    "title": "Action and outcome totals",
                    "group_by": "all",
                    "display": "cards",
                    "record": "final",
                    "columns": [
                        {
                            "id": field,
                            "label": label,
                            "format": "action_rates",
                            "metric": "Legacy",
                            "line": 1,
                        }
                        for field, label in (
                            ("actions", "Actions"),
                            ("outcomes", "Outcomes"),
                        )
                    ],
                    "snapshots": [
                        {
                            "tick": int(view["ticks"]),
                            "rows": [{"group_id": "All", "values": event_values}],
                        }
                    ],
                }
            )
        comparison = []
        for row in view.get("comparison", []):
            report_id = report_ids.get(row.get("group_kind"))
            if report_id is None:
                continue
            comparison.append(
                {
                    "report_id": report_id,
                    "group_id": str(row["group_id"]),
                    "values": {
                        field: row.get(field, 0)
                        for field, _, _ in columns
                        if field != "average_family_size"
                        and field != "average_kids_per_family"
                    },
                }
            )
        return {
            "run_id": view["run_id"],
            "source_hash": view["source_hash"],
            "seed": view["seed"],
            "days": view["days"],
            "ticks": view["ticks"],
            "adult_population": view["adult_population"],
            "total_agents": view["total_agents"],
            "generated_children": view["generated_children"],
            "population_id": None,
            "results_title": "Recorded Rust output",
            "results_subtitle": "Legacy recorded statistics",
            "reports": reports,
            "comparison": comparison,
            "engine_version": view["engine_version"],
            "created_at": view["created_at"],
        }

    @staticmethod
    def _comparison(
        current: tuple[TextDslReport, ...],
        baseline: tuple[TextDslReport, ...],
    ) -> tuple[TextDslReportDelta, ...]:
        baseline_reports = {report.id: report for report in baseline}
        result = []
        for report in current:
            previous_report = baseline_reports.get(report.id)
            if not report.snapshots or previous_report is None or not previous_report.snapshots:
                continue
            previous_rows = {
                row.group_id: row for row in previous_report.snapshots[-1].rows
            }
            for row in report.snapshots[-1].rows:
                previous = previous_rows.get(row.group_id)
                if previous is None:
                    continue
                values = {
                    key: delta
                    for key, value in row.values.items()
                    if key in previous.values
                    and (delta := TextDslService._value_delta(value, previous.values[key]))
                    is not None
                }
                result.append(
                    TextDslReportDelta(
                        report_id=report.id,
                        group_id=row.group_id,
                        values=values,
                    )
                )
        return tuple(result)

    @staticmethod
    def _value_delta(
        current: TextDslReportValue,
        baseline: TextDslReportValue,
    ) -> TextDslReportValue | None:
        if isinstance(current, (int, float)) and isinstance(baseline, (int, float)):
            return float(current) - float(baseline)
        if isinstance(current, dict) and isinstance(baseline, dict):
            keys = current.keys() | baseline.keys()
            return {
                key: float(current.get(key, 0)) - float(baseline.get(key, 0))
                for key in sorted(keys)
            }
        return None

    def _code(self) -> str:
        path = self.active_path if self.active_path.exists() else self.default_path
        return path.read_text(encoding="utf-8")

    def _metadata(self) -> dict[str, Any]:
        if not self.metadata_path.exists():
            return {}
        return json.loads(self.metadata_path.read_text(encoding="utf-8"))

    @staticmethod
    def _hash(code: str) -> str:
        return "sha256:" + hashlib.sha256(code.encode()).hexdigest()

    @staticmethod
    def _write(path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=path.name, dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
