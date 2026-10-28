from petraterrium.simulation.initial_agents import (
    FamilyRelationship,
    HouseholdMember,
    InitialAgentDetail,
    InitialAgentListItem,
    InitialInteractionCounterpart,
)
from petraterrium.simulation.interactions import InteractionListItem
from petraterrium.simulation.locations import LocationAgentDetail, LocationAgentSummary
from petraterrium.simulation.population_generation import HouseholdMemberSeed
from petraterrium.simulation.run_service import (
    AgentInteractionDetail,
    PreparedRustRun,
    RunAgentDetail,
    RunAgentSummary,
)


def test_population_and_agent_views_use_only_synthetic_agent_ids():
    models = (
        HouseholdMemberSeed,
        FamilyRelationship,
        InitialInteractionCounterpart,
        HouseholdMember,
        InitialAgentListItem,
        InitialAgentDetail,
        PreparedRustRun,
        RunAgentSummary,
        RunAgentDetail,
        AgentInteractionDetail,
        InteractionListItem,
        LocationAgentSummary,
        LocationAgentDetail,
    )

    for model in models:
        assert "name" not in model.model_fields
        assert "display_name" not in model.model_fields
        assert "agent_names" not in model.model_fields
        assert "other_agent_name" not in model.model_fields
        assert "initiator_name" not in model.model_fields
        assert "target_name" not in model.model_fields
