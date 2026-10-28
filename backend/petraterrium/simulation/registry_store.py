import json
import os
import tempfile
import threading
from copy import deepcopy
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..markov_builder.models import ConfirmedChainGraph
from .agent_types import ConfirmedAgentTypeRegistry, ResolvedAgentTypeRegistry
from .decision_evidence import DecisionFactorEvidence, DecisionTreeTemplate
from .interaction_trees import InteractionTreeDefinition
from .interactions import InteractionProgramDefinition
from .mobility import MobilityRegistryDefinition
from .population_generation import InitialPopulationMaterialization
from .routines import RoutineRegistryDefinition
from .tree_modules import (
    DecisionTreeDefinition,
    DecisionTreeEdge,
    DecisionTreeModule,
    DecisionTreeNode,
    DecisionTreeProposalAudit,
    DecisionTreeRegistryDefinition,
)


class DecisionEvidenceRegistryDefinition(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )

    version: str = Field(min_length=1)
    templates: list[DecisionTreeTemplate] = Field(default_factory=list)
    evidence: list[DecisionFactorEvidence] = Field(default_factory=list)


def default_simulation_registry_path() -> Path:
    configured = os.getenv("PETRATERRIUM_SIMULATION_REGISTRY_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[2] / "data" / "simulation_registry.json"


class SimulationRegistryStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or default_simulation_registry_path())
        self._lock = threading.RLock()

    def agent_types(self) -> ConfirmedAgentTypeRegistry | None:
        with self._lock:
            if not self.path.exists():
                return None
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            value = payload.get("agent_types")
            return ConfirmedAgentTypeRegistry.model_validate(value) if value else None

    def initial_population(self) -> InitialPopulationMaterialization | None:
        with self._lock:
            if not self.path.exists():
                return None
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            value = payload.get("initial_population")
            return InitialPopulationMaterialization.model_validate(value) if value else None

    def decision_trees(self) -> DecisionTreeRegistryDefinition:
        with self._lock:
            if not self.path.exists():
                return DecisionTreeRegistryDefinition(version="1", trees=[], modules=[])
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            value = payload.get("decision_trees")
            if value is None:
                return DecisionTreeRegistryDefinition(version="1", trees=[], modules=[])
            return DecisionTreeRegistryDefinition.model_validate(value)

    def routines(self) -> RoutineRegistryDefinition | None:
        with self._lock:
            if not self.path.exists():
                return None
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            value = payload.get("routines")
            return RoutineRegistryDefinition.model_validate(value) if value else None

    def decision_evidence(self) -> DecisionEvidenceRegistryDefinition | None:
        with self._lock:
            if not self.path.exists():
                return None
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            value = payload.get("decision_evidence")
            return (
                DecisionEvidenceRegistryDefinition.model_validate_json(json.dumps(value))
                if value
                else None
            )

    def interaction_trees(self) -> list[InteractionTreeDefinition]:
        with self._lock:
            if not self.path.exists():
                return []
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            value = payload.get("interaction_trees", [])
            return [
                InteractionTreeDefinition.model_validate_json(json.dumps(item)) for item in value
            ]

    def interaction_program(self) -> InteractionProgramDefinition | None:
        with self._lock:
            if not self.path.exists():
                return None
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            value = payload.get("interaction_program")
            return InteractionProgramDefinition.model_validate(value) if value else None

    def mobility(self) -> MobilityRegistryDefinition | None:
        with self._lock:
            if not self.path.exists():
                return None
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            value = payload.get("mobility")
            return MobilityRegistryDefinition.model_validate(value) if value else None

    def resolved_agent_types(self) -> ResolvedAgentTypeRegistry:
        registry = self.agent_types()
        return registry.resolved if registry else ResolvedAgentTypeRegistry(types=[])

    def payload_snapshot(self) -> dict:
        with self._lock:
            return deepcopy(self._payload())

    def default_dsl_receipt(self):
        from .default_dsl import DefaultDslReceipt

        with self._lock:
            value = self._payload().get("default_dsl")
            return (
                DefaultDslReceipt.model_validate_json(json.dumps(value))
                if value
                else None
            )

    def install_default_dsl_if_fresh(
        self,
        sections: dict,
        receipt: dict,
    ) -> bool:
        with self._lock:
            payload = self._payload()
            managed_sections = tuple(receipt["managed_sections"])
            if payload.get("default_dsl") is not None:
                return False
            if any(section in payload for section in managed_sections):
                return False
            for section in managed_sections:
                payload[section] = deepcopy(sections[section])
            payload["default_dsl"] = deepcopy(receipt)
            self._write(payload)
            return True

    def replace_default_dsl(
        self,
        sections: dict,
        receipt: dict,
    ) -> None:
        with self._lock:
            payload = self._payload()
            prior = payload.get("default_dsl")
            prior_sections = (
                tuple(prior.get("managed_sections", ()))
                if isinstance(prior, dict)
                else ()
            )
            managed_sections = tuple(receipt["managed_sections"])
            for section in set(prior_sections) - set(managed_sections):
                payload.pop(section, None)
            for section in managed_sections:
                payload[section] = deepcopy(sections[section])
            payload["default_dsl"] = deepcopy(receipt)
            self._write(payload)

    def restore_default_dsl_sections(
        self,
        sections: dict,
        receipt: dict,
    ) -> None:
        with self._lock:
            payload = self._payload()
            managed_sections = set(receipt["managed_sections"])
            unexpected = sorted(set(sections) - managed_sections)
            if unexpected:
                raise ValueError(
                    "Default restore contains unmanaged sections: "
                    + ", ".join(unexpected)
                )
            for section, value in sections.items():
                payload[section] = deepcopy(value)
            payload["default_dsl"] = deepcopy(receipt)
            self._write(payload)

    def save_agent_types(self, registry: ConfirmedAgentTypeRegistry) -> ConfirmedAgentTypeRegistry:
        with self._lock:
            payload = self._payload()
            payload["agent_types"] = registry.model_dump(mode="json")
            self._write(payload)
            return registry

    def save_initial_population(
        self, materialization: InitialPopulationMaterialization
    ) -> InitialPopulationMaterialization:
        with self._lock:
            payload = self._payload()
            payload["initial_population"] = materialization.model_dump(mode="json")
            self._write(payload)
            return materialization

    def save_decision_trees(
        self, registry: DecisionTreeRegistryDefinition
    ) -> DecisionTreeRegistryDefinition:
        with self._lock:
            payload = self._payload()
            payload["decision_trees"] = registry.model_dump(mode="json")
            self._write(payload)
            return registry

    def save_routines(self, registry: RoutineRegistryDefinition) -> RoutineRegistryDefinition:
        with self._lock:
            payload = self._payload()
            payload["routines"] = registry.model_dump(mode="json")
            self._write(payload)
            return registry

    def save_behavior_proposal(
        self,
        agent_types: ConfirmedAgentTypeRegistry,
        routines: RoutineRegistryDefinition,
        decision_trees: DecisionTreeRegistryDefinition,
        proposal: BaseModel,
    ) -> ConfirmedAgentTypeRegistry:
        with self._lock:
            payload = self._payload()
            payload["agent_types"] = agent_types.model_dump(mode="json")
            payload["routines"] = routines.model_dump(mode="json")
            payload["decision_trees"] = decision_trees.model_dump(mode="json")
            payload["agent_behavior_proposal"] = proposal.model_dump(mode="json")
            self._write(payload)
            return agent_types

    def save_decision_evidence(
        self, registry: DecisionEvidenceRegistryDefinition
    ) -> DecisionEvidenceRegistryDefinition:
        with self._lock:
            payload = self._payload()
            payload["decision_evidence"] = registry.model_dump(mode="json")
            self._write(payload)
            return registry

    def save_interaction_tree(
        self, definition: InteractionTreeDefinition
    ) -> InteractionTreeDefinition:
        with self._lock:
            definitions = [item for item in self.interaction_trees() if item.id != definition.id]
            definitions.append(definition)
            definitions.sort(key=lambda item: item.id)
            payload = self._payload()
            payload["interaction_trees"] = [item.model_dump(mode="json") for item in definitions]
            self._write(payload)
            return definition

    def save_interaction_program(
        self, program: InteractionProgramDefinition
    ) -> InteractionProgramDefinition:
        with self._lock:
            payload = self._payload()
            payload["interaction_program"] = program.model_dump(mode="json")
            self._write(payload)
            return program

    def save_mobility(
        self, registry: MobilityRegistryDefinition
    ) -> MobilityRegistryDefinition:
        with self._lock:
            payload = self._payload()
            payload["mobility"] = registry.model_dump(mode="json")
            self._write(payload)
            return registry

    def save_confirmed_chain(self, chain: ConfirmedChainGraph) -> str:
        with self._lock:
            registry = self.decision_trees()
            audit = chain.proposal_audit
            if audit is None:
                proposal_audit = DecisionTreeProposalAudit(
                    origin="manual",
                    source_id="manual",
                    source_label="Manual confirmation",
                    model="none",
                    generated_at=None,
                    prompt_version="not-applicable",
                    message="Confirmed manually without an AI proposal audit.",
                )
                source = (
                    "User-confirmed natural-language proposal · provenance unavailable · "
                    "evidence pending"
                )
            elif audit.provider == "deterministic-parser":
                proposal_audit = DecisionTreeProposalAudit(
                    origin="deterministic",
                    source_id=audit.provider,
                    source_label="Deterministic parser",
                    model=audit.model,
                    generated_at=(
                        audit.model_dump(mode="json").get("generated_at")
                    ),
                    prompt_version=audit.prompt_version,
                    input_tokens=audit.input_tokens,
                    output_tokens=audit.output_tokens,
                    estimated_cost_usd=audit.estimated_cost_usd,
                    message=audit.message,
                )
                source = (
                    "User-confirmed natural-language proposal · deterministic parser · "
                    "evidence pending"
                )
            else:
                source_label = {
                    "openai_cli": "OpenAI CLI",
                    "openai_api": "OpenAI API",
                }.get(audit.provider, audit.provider.replace("_", " ").title())
                proposal_audit = DecisionTreeProposalAudit(
                    origin="ai",
                    source_id=audit.provider,
                    source_label=source_label,
                    model=audit.model,
                    generated_at=(
                        audit.model_dump(mode="json").get("generated_at")
                    ),
                    prompt_version=audit.prompt_version,
                    input_tokens=audit.input_tokens,
                    output_tokens=audit.output_tokens,
                    estimated_cost_usd=audit.estimated_cost_usd,
                    message=audit.message,
                )
                generated_at = (
                    f" · {audit.generated_at.isoformat()}" if audit.generated_at is not None else ""
                )
                source = (
                    f"User-confirmed natural-language proposal · {source_label} · "
                    f"model {audit.model}{generated_at} · evidence pending"
                )
            version = f"revision-{chain.revision}"
            module = DecisionTreeModule(
                id=chain.id,
                version=version,
                name=chain.name,
                description=chain.source_text,
                entry_node=chain.entry_node,
                nodes=[
                    DecisionTreeNode(
                        id=node.id,
                        label=node.label,
                        kind=(
                            "terminal"
                            if node.terminal
                            else "decision"
                            if node.id == chain.entry_node
                            else "action"
                        ),
                        description=node.source_excerpt or "",
                    )
                    for node in chain.nodes
                ],
                edges=[
                    DecisionTreeEdge(
                        id=transition.id,
                        from_node=transition.from_node,
                        to_node=transition.to_node,
                        label=(
                            f"User-confirmed proposal {transition.probability:.6g}; "
                            "evidence pending"
                        ),
                        condition=transition.condition or "",
                    )
                    for transition in chain.transitions
                ],
                source=source,
                status="blocked",
                proposal_audit=proposal_audit,
            )
            tree = DecisionTreeDefinition(
                id=chain.id,
                version=version,
                name=chain.name,
                description=chain.source_text,
                root_module_id=chain.id,
                source=source,
                status="blocked",
                proposal_audit=proposal_audit,
            )
            trees = [item for item in registry.trees if item.id != tree.id]
            modules = [item for item in registry.modules if item.id != module.id]
            saved = DecisionTreeRegistryDefinition(
                version="1",
                trees=[*trees, tree],
                modules=[*modules, module],
            )
            self.save_decision_trees(saved)
            return chain.id

    def _payload(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
        except OSError:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise
