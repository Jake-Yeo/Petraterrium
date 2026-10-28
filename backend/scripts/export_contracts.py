import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from petraterrium.ai_settings import (
    AIConnectionTest,
    AISettingsUpdate,
    AISettingsView,
    AISourceProvenance,
)
from petraterrium.atlas.auto_import_contracts import (
    AutoImportAttemptView,
    AutoImportBatchPromotionRequest,
    AutoImportBatchRequest,
    AutoImportBatchView,
    AutoImportEvidenceView,
    AutoImportMappingReview,
    AutoImportPromotionRequest,
    AutoImportQueuePageView,
    AutoImportRerunRequest,
)
from petraterrium.atlas.contracts import (
    AtlasOverview,
    AtlasScopes,
    ChoiceEvidenceCatalog,
    CityDetail,
    FieldCoverage,
    HierarchyOverview,
    ImportCommit,
    ImportHistory,
    ImportMetadata,
    ImportPreview,
    ImportVersion,
    MappingConfirmation,
    Promotion,
    SourceCatalog,
    SourceFetch,
    UniversalFeatureOverview,
    ValidationReport,
)
from petraterrium.contracts import (
    ActionLogEntry,
    AgentDetail,
    AgentPointList,
    Catalog,
    DailySnapshot,
    DecisionGraph,
    DSLRender,
    EnsembleUpdate,
    PlaceDetail,
    RunComplete,
    RunCreated,
    RunDetail,
    RunFailed,
    RunList,
    StoryDetail,
    StoryList,
)
from petraterrium.dsl import DSLConfig, DSLValidationResult
from petraterrium.markov_builder.models import (
    ChainProposalRequest,
    ChainProposalResult,
    ChainValidationResult,
    ConfirmationResult,
    ConfirmChainRequest,
)
from petraterrium.simulation.agent_behavior_proposals import (
    AgentBehaviorProposalDraft,
    BehaviorEvidenceRequirement,
    ConfirmAgentBehaviorProposalRequest,
    ConfirmedAgentBehaviorBundle,
)
from petraterrium.simulation.agent_type_routes import (
    AgentTypeProposalRequest,
    AgentTypeRegistryView,
)
from petraterrium.simulation.agent_types import (
    AgentTypeProposalDraft,
    ConfirmAgentTypeProposalRequest,
    ConfirmedAgentTypeRegistry,
)
from petraterrium.simulation.atlas_population import (
    AtlasPopulationFeatureCoverage,
    AtlasPopulationRequest,
    AtlasPopulationResult,
)
from petraterrium.simulation.decision_evidence_routes import (
    ConfirmDecisionEvidenceRegistryRequest,
    DecisionEvidenceDetail,
    DecisionEvidenceRegistryView,
    DecisionEvidenceValidation,
)
from petraterrium.simulation.initial_agents import InitialAgentDetail, InitialAgentPage
from petraterrium.simulation.interaction_program_routes import (
    ConfirmInteractionProgramRequest,
    InteractionProgramValidation,
    InteractionProgramValidationIssue,
    InteractionProgramView,
)
from petraterrium.simulation.interaction_trees import (
    InteractionTreeDefinition,
    InteractionTreeRequest,
    InteractionTreeResult,
    InteractionTreeSummary,
)
from petraterrium.simulation.interactions import (
    InteractionBreakdown,
    InteractionEventDetail,
    InteractionPage,
    InteractionProgramDefinition,
    InteractionQuery,
    RelationshipKindEvidence,
)
from petraterrium.simulation.locations import LocationAgentDetail, LocationRunSnapshot
from petraterrium.simulation.mobility_routes import (
    ConfirmMobilityRequest,
    MobilityRegistryView,
)
from petraterrium.simulation.population_generation import (
    InitialPopulationMaterialization,
    InitialPopulationRequest,
    InitialPopulationValidation,
)
from petraterrium.simulation.population_routes import InitialPopulationStatus
from petraterrium.simulation.routines_routes import (
    ConfirmRoutineRegistryRequest,
    RoutineRegistryView,
)
from petraterrium.simulation.run_service import (
    RunAgentDetail,
    RunAgentPage,
    RunEventPage,
    SimulationRunConfig,
    SimulationRunView,
)
from petraterrium.simulation.tree_routes import (
    ConfirmDecisionTreeRegistryRequest,
    DecisionTreeRegistryView,
)

TARGET = Path(__file__).resolve().parents[2] / "frontend" / "src"
DSL_TARGET = Path(__file__).resolve().parents[2] / "shared" / "dsl-schema"
SHARED_TYPES_TARGET = Path(__file__).resolve().parents[2] / "shared" / "types"


def typescript_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    if "anyOf" in schema:
        return " | ".join(typescript_type(item) for item in schema["anyOf"])
    kind = schema.get("type")
    if kind == "array":
        if "prefixItems" in schema:
            return "[" + ", ".join(typescript_type(item) for item in schema["prefixItems"]) + "]"
        return f"Array<{typescript_type(schema['items'])}>"
    if kind == "object":
        required = schema.get("required", [])
        fields = [
            f"  {name}{'' if name in required else '?'}: {typescript_type(value)};"
            for name, value in schema.get("properties", {}).items()
        ]
        if isinstance(schema.get("additionalProperties"), dict):
            fields.append(f"  [key: string]: {typescript_type(schema['additionalProperties'])};")
        elif schema.get("additionalProperties") is True:
            fields.append("  [key: string]: unknown;")
        return "{\n" + "\n".join(fields) + "\n}"
    if kind is None:
        return "unknown"
    return {
        "integer": "number",
        "number": "number",
        "string": "string",
        "boolean": "boolean",
        "null": "null",
    }[kind]


def artifacts() -> dict[Path, str]:
    adapter = TypeAdapter(
        Catalog
        | ActionLogEntry
        | AgentDetail
        | AgentPointList
        | DailySnapshot
        | DecisionGraph
        | DSLRender
        | EnsembleUpdate
        | PlaceDetail
        | RunComplete
        | RunFailed
        | RunDetail
        | RunCreated
        | RunList
        | StoryDetail
        | StoryList
        | DSLConfig
        | DSLValidationResult
        | AtlasOverview
        | AtlasScopes
        | ChoiceEvidenceCatalog
        | CityDetail
        | FieldCoverage
        | HierarchyOverview
        | ImportCommit
        | ImportHistory
        | ImportMetadata
        | ImportPreview
        | ImportVersion
        | MappingConfirmation
        | Promotion
        | SourceCatalog
        | SourceFetch
        | UniversalFeatureOverview
        | ValidationReport
        | AutoImportAttemptView
        | AutoImportBatchPromotionRequest
        | AutoImportBatchRequest
        | AutoImportBatchView
        | AutoImportEvidenceView
        | AutoImportMappingReview
        | AutoImportPromotionRequest
        | AutoImportQueuePageView
        | AutoImportRerunRequest
        | AIConnectionTest
        | AISettingsUpdate
        | AISettingsView
        | AISourceProvenance
        | ChainProposalRequest
        | ChainProposalResult
        | ChainValidationResult
        | ConfirmationResult
        | ConfirmChainRequest
        | AgentTypeProposalRequest
        | AgentTypeRegistryView
        | AgentTypeProposalDraft
        | ConfirmAgentTypeProposalRequest
        | ConfirmedAgentTypeRegistry
        | AgentBehaviorProposalDraft
        | BehaviorEvidenceRequirement
        | ConfirmAgentBehaviorProposalRequest
        | ConfirmedAgentBehaviorBundle
        | AtlasPopulationFeatureCoverage
        | AtlasPopulationRequest
        | AtlasPopulationResult
        | ConfirmDecisionEvidenceRegistryRequest
        | DecisionEvidenceDetail
        | DecisionEvidenceRegistryView
        | DecisionEvidenceValidation
        | InitialAgentDetail
        | InitialAgentPage
        | InteractionTreeDefinition
        | InteractionTreeRequest
        | InteractionTreeResult
        | InteractionTreeSummary
        | ConfirmInteractionProgramRequest
        | InteractionProgramValidation
        | InteractionProgramValidationIssue
        | InteractionProgramView
        | InteractionBreakdown
        | InteractionEventDetail
        | InteractionProgramDefinition
        | InteractionPage
        | InteractionQuery
        | RelationshipKindEvidence
        | LocationAgentDetail
        | LocationRunSnapshot
        | ConfirmMobilityRequest
        | MobilityRegistryView
        | InitialPopulationMaterialization
        | InitialPopulationRequest
        | InitialPopulationValidation
        | InitialPopulationStatus
        | ConfirmRoutineRegistryRequest
        | RoutineRegistryView
        | RunAgentDetail
        | RunAgentPage
        | RunEventPage
        | SimulationRunConfig
        | SimulationRunView
        | ConfirmDecisionTreeRegistryRequest
        | DecisionTreeRegistryView
    )
    schema = adapter.json_schema(mode="serialization")
    schema["$id"] = "petraterrium-contracts"
    definitions = schema["$defs"]
    types = "\n\n".join(
        f"export type {name} = {typescript_type(value)};"
        for name, value in sorted(definitions.items())
    )
    return {
        TARGET / "contracts.schema.json": json.dumps(schema, indent=2) + "\n",
        TARGET / "contracts.generated.ts": types + "\n",
        SHARED_TYPES_TARGET / "contracts.generated.ts": types + "\n",
        DSL_TARGET / "petraterrium-dsl.schema.json": json.dumps(
            DSLConfig.model_json_schema(mode="serialization"), indent=2
        )
        + "\n",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args()
    for path, content in artifacts().items():
        if options.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(
                    f"Outdated contracts: {path}. Run python scripts/export_contracts.py"
                )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)


if __name__ == "__main__":
    main()
