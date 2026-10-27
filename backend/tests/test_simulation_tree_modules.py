import pytest

from petraterrium.simulation.tree_modules import (
    DecisionTreeDefinition,
    DecisionTreeEdge,
    DecisionTreeModule,
    DecisionTreeModuleRegistry,
    DecisionTreeNode,
    DecisionTreeRegistryDefinition,
    TreeFilter,
)


def node(
    node_id: str,
    label: str,
    kind: str = "decision",
    target_module_id: str | None = None,
) -> DecisionTreeNode:
    return DecisionTreeNode.model_validate(
        {
            "id": node_id,
            "label": label,
            "kind": kind,
            "target_module_id": target_module_id,
        }
    )


def module(
    module_id: str,
    name: str,
    nodes: list[DecisionTreeNode],
    edges: list[tuple[str, str, str]],
    source: str = "Time Use Survey 2025",
) -> DecisionTreeModule:
    return DecisionTreeModule(
        id=module_id,
        version="2025.1",
        name=name,
        entry_node=nodes[0].id,
        nodes=nodes,
        edges=[
            DecisionTreeEdge(id=edge_id, from_node=source_id, to_node=target_id)
            for edge_id, source_id, target_id in edges
        ],
        source=source,
        status="ready",
    )


def tree(
    tree_id: str,
    name: str,
    root_module_id: str,
    agent_types: list[str],
    places: list[str],
    source: str = "Time Use Survey 2025",
    status: str = "ready",
) -> DecisionTreeDefinition:
    return DecisionTreeDefinition.model_validate(
        {
            "id": tree_id,
            "version": "2025.1",
            "name": name,
            "root_module_id": root_module_id,
            "agent_type_ids": agent_types,
            "place_ids": places,
            "source": source,
            "status": status,
        }
    )


def registry() -> DecisionTreeModuleRegistry:
    social = module(
        "social_choice",
        "Social choice",
        [
            node("choose", "Choose an evening activity"),
            node("open_bar", "Open bar visit", "module_reference", "bar_visit"),
            node("stay_home", "Stay home", "terminal"),
        ],
        [("choose_bar", "choose", "open_bar"), ("choose_home", "choose", "stay_home")],
    )
    bar = module(
        "bar_visit",
        "Bar visit",
        [
            node("arrive", "Arrive at bar", "action"),
            node("meet_friend", "Meet a friend", "action"),
            node("leave", "Leave bar", "terminal"),
        ],
        [("arrive_meet", "arrive", "meet_friend"), ("meet_leave", "meet_friend", "leave")],
        "Canada General Social Survey 2024",
    )
    return DecisionTreeModuleRegistry(
        DecisionTreeRegistryDefinition(
            version="1",
            trees=[
                tree(
                    "evening_routine",
                    "Evening routine",
                    "social_choice",
                    ["worker", "student"],
                    ["canada"],
                ),
                tree(
                    "bar_arrival",
                    "Bar arrival",
                    "bar_visit",
                    ["worker"],
                    ["canada", "japan"],
                    "Canada General Social Survey 2024",
                ),
            ],
            modules=[social, bar],
        )
    )


def test_registry_opens_roots_and_explicit_submodule_references():
    catalog = registry()

    assert catalog.validation.valid
    root = catalog.root("evening_routine")
    assert root.module.id == "social_choice"
    assert catalog.referenced_module("social_choice", "open_bar").id == "bar_visit"

    references = catalog.references_for("bar_visit").references
    assert [(item.kind, item.id, item.node_id) for item in references] == [
        ("module_node", "social_choice", "open_bar"),
        ("tree_root", "bar_arrival", None),
    ]


def test_search_matches_nodes_with_joined_tree_filters():
    catalog = registry()

    result = catalog.search(
        "friend",
        TreeFilter(
            agent_type_id="worker",
            place_id="canada",
            source="Time Use Survey 2025",
            status="ready",
        ),
    )

    assert [
        (match.tree_id, match.module_id, match.node_id) for match in result.matches
    ] == [("evening_routine", "bar_visit", "meet_friend")]
    assert catalog.search("friend", TreeFilter(place_id="mexico")).matches == []


def test_broken_references_and_unreachable_nodes_block_registry_validation():
    broken_root = module(
        "broken_root",
        "Broken root",
        [
            node("start", "Start"),
            node("missing", "Missing module", "module_reference", "unknown_module"),
            node("orphan", "Orphan", "terminal"),
        ],
        [("start_missing", "start", "missing")],
    )
    catalog = DecisionTreeModuleRegistry(
        DecisionTreeRegistryDefinition(
            version="1",
            trees=[tree("broken_tree", "Broken tree", "broken_root", [], [])],
            modules=[broken_root],
        )
    )

    assert not catalog.validation.valid
    assert catalog.validation.broken_references[0].target_module_id == "unknown_module"
    assert catalog.validation.unreachable_nodes == {"broken_root": ["orphan"]}
    assert {issue.code for issue in catalog.validation.issues} == {
        "broken_module_reference",
        "unreachable_nodes",
    }
    with pytest.raises(KeyError, match="references missing module unknown_module"):
        catalog.referenced_module("broken_root", "missing")


def test_module_reference_cycles_are_reported_once_in_canonical_order():
    first = module(
        "first",
        "First",
        [node("next", "Next", "module_reference", "second")],
        [],
    )
    second = module(
        "second",
        "Second",
        [node("back", "Back", "module_reference", "first")],
        [],
    )
    catalog = DecisionTreeModuleRegistry(
        DecisionTreeRegistryDefinition(
            version="1",
            trees=[tree("cyclic", "Cyclic", "first", [], [])],
            modules=[first, second],
        )
    )

    assert not catalog.validation.valid
    assert catalog.validation.reference_cycles == [["first", "second", "first"]]
    assert [issue.code for issue in catalog.validation.issues] == [
        "module_reference_cycle"
    ]


def test_decision_edge_evidence_link_is_stable_and_complete():
    linked = DecisionTreeEdge(
        id="choose_bar",
        from_node="choose",
        to_node="open_bar",
        decision_id="go_out_friday",
        evidence_edge_id="leave_home",
    )

    assert linked.decision_id == "go_out_friday"
    assert linked.evidence_edge_id == "leave_home"

    with pytest.raises(
        ValueError,
        match="both decision_id and evidence_edge_id",
    ):
        DecisionTreeEdge(
            id="choose_home",
            from_node="choose",
            to_node="stay_home",
            decision_id="go_out_friday",
        )


def test_ready_module_rejects_free_text_conditions():
    definition = registry().definition
    social = definition.modules[0]
    conditioned = social.edges[0].model_copy(
        update={"condition": "Friday after work"}
    )
    updated = social.model_copy(update={"edges": [conditioned, *social.edges[1:]]})

    validation = DecisionTreeModuleRegistry(
        definition.model_copy(update={"modules": [updated, *definition.modules[1:]]})
    ).validation

    assert not validation.valid
    assert validation.issues[-1].code == "free_text_condition_non_executable"
    assert "typed evidence predicates" in validation.issues[-1].message
