use petraterrium_engine::text_dsl::{build_program_graph, parse_program};
use std::collections::{BTreeMap, BTreeSet};

const SOURCE: &str = include_str!("../dsl/default.dsl");

#[test]
fn graph_contains_every_validated_composition_archetype_and_agent_once() {
    let program = parse_program(SOURCE).unwrap();
    let graph = build_program_graph(&program).unwrap();
    let expected = program.compositions.len() + program.archetypes.len() + program.agents.len();
    assert_eq!(graph.nodes.len(), expected);
    let ids = graph
        .nodes
        .iter()
        .map(|node| node.id.as_str())
        .collect::<BTreeSet<_>>();
    for id in program
        .compositions
        .iter()
        .map(|item| item.id.as_str())
        .chain(program.archetypes.iter().map(|item| item.id.as_str()))
        .chain(program.agents.iter().map(|item| item.id.as_str()))
    {
        assert!(ids.contains(id), "{id}");
    }
}

#[test]
fn graph_edges_exactly_match_composition_entries_couplings_and_boundaries() {
    let program = parse_program(SOURCE).unwrap();
    let graph = build_program_graph(&program).unwrap();
    let parent_edges = program
        .compositions
        .iter()
        .map(|composition| composition.entries.len())
        .sum::<usize>()
        + program
            .archetypes
            .iter()
            .map(|archetype| {
                archetype
                    .composition
                    .iter()
                    .flat_map(|group| &group.mix)
                    .map(|entry| {
                        let mut id = entry.agent_type.as_str();
                        while let Some(parent) = program
                            .agents
                            .iter()
                            .find(|agent| agent.id == id)
                            .and_then(|agent| agent.parent.as_deref())
                        {
                            id = parent;
                        }
                        id
                    })
                    .collect::<BTreeSet<_>>()
                    .len()
            })
            .sum::<usize>()
        + program
            .agents
            .iter()
            .filter(|agent| agent.parent.is_some())
            .count();
    let coupling_edges = program
        .compositions
        .iter()
        .map(|composition| composition.couplings.len() + composition.boundaries.len())
        .sum::<usize>();
    assert_eq!(
        graph
            .edges
            .iter()
            .filter(|edge| edge.kind == "parent_child")
            .count(),
        parent_edges
    );
    assert_eq!(
        graph
            .edges
            .iter()
            .filter(|edge| edge.kind == "coupling")
            .count(),
        coupling_edges
    );
}

#[test]
fn graph_exposes_generic_lines_counts_roles_cache_and_sync_metadata() {
    let program = parse_program(SOURCE).unwrap();
    let graph = build_program_graph(&program).unwrap();
    let node = |id: &str| graph.nodes.iter().find(|node| node.id == id).unwrap();
    let store = node("StoreA");
    assert_eq!(
        store.line,
        program
            .compositions
            .iter()
            .find(|item| item.id == "StoreA")
            .unwrap()
            .line
    );
    assert!(store.cached);
    assert!(store.roles_exposed.iter().any(|role| role.id == "cashier"));
    assert!(store.roles_exposed.iter().any(|role| role.id == "manager"));
    assert!(
        node("FirmAlpha")
            .roles_exposed
            .iter()
            .any(|role| role.id == "ceo" && role.leader)
    );
    assert_eq!(node("World").simulated_count, Some(180));
    assert_eq!(node("World").represented_count, Some(6_999_999_999));
    assert_eq!(node("World").vertical_slice, "Physical");
    assert!(
        node("World")
            .subtree_roles
            .iter()
            .any(|role| role == "worker")
    );
    assert_eq!(node("Reddit").vertical_slice, "Media");
    let coupling = graph
        .edges
        .iter()
        .find(|edge| edge.id == "alpha_profit_to_market")
        .unwrap();
    assert_eq!(coupling.sync_interval_days, Some(90));
    assert!(
        coupling
            .formula
            .as_deref()
            .unwrap()
            .contains("firm_a_profit")
    );
    assert!(coupling.line > 0);
    assert!(
        store
            .roles_exposed
            .iter()
            .find(|role| role.id == "cashier")
            .is_some_and(|role| !role.conditions.is_empty())
    );
}

#[test]
fn graph_uses_declared_slices_categories_shared_parents_and_orphans() {
    let program = parse_program(SOURCE).unwrap();
    let graph = build_program_graph(&program).unwrap();
    let main = graph
        .slices
        .iter()
        .filter(|slice| slice.group == "main")
        .map(|slice| slice.id.as_str())
        .collect::<BTreeSet<_>>();
    assert_eq!(
        main,
        BTreeSet::from(["Corporate", "Financial", "Media", "Physical"])
    );
    assert!(
        graph
            .slices
            .iter()
            .any(|slice| slice.group == "coupled" && slice.id == "Full system")
    );
    let nodes = graph
        .nodes
        .iter()
        .map(|node| (node.id.as_str(), node))
        .collect::<BTreeMap<_, _>>();
    let expected_parents = BTreeSet::from([
        "BritishColumbia",
        "California",
        "CentralMexico",
        "NorthernMexico",
        "Ontario",
        "Texas",
    ]);
    assert_eq!(
        nodes["Toronto"]
            .parent_ids
            .iter()
            .map(String::as_str)
            .collect::<BTreeSet<_>>(),
        expected_parents
    );
    assert_eq!(nodes["Vancouver"].also_used_in.len(), 6);
    assert!(
        graph
            .orphan_agents
            .iter()
            .all(|id| nodes[id.as_str()].node_kind == "agent")
    );
    assert!(!graph.slices.iter().any(|slice| slice.id == "Person"));
    assert_eq!(nodes["Person"].vertical_slice, "Physical");
    assert!(!nodes["Person"].parent_ids.is_empty());
    assert_eq!(
        nodes["WorkingStudent"].inherits_from.as_deref(),
        Some("Student")
    );
}

#[test]
fn graph_links_required_leaders_with_sources_and_actions() {
    let program = parse_program(SOURCE).unwrap();
    let graph = build_program_graph(&program).unwrap();
    let required = [
        ("USA", "president"),
        ("Canada", "president"),
        ("Texas", "governor"),
        ("California", "governor"),
        ("BrandOne", "brand_manager"),
        ("BrandTwo", "brand_manager"),
        ("FranchiseOne", "franchise_manager"),
        ("FranchiseTwo", "franchise_manager"),
        ("StoreA", "manager"),
        ("StoreB", "manager"),
        ("StoreC", "manager"),
        ("StoreD", "manager"),
        ("PersonalFinance", "influencer"),
    ];
    for (node_id, role_id) in required {
        let node = graph.nodes.iter().find(|node| node.id == node_id).unwrap();
        let role = node
            .roles_exposed
            .iter()
            .find(|role| role.id == role_id)
            .unwrap_or_else(|| panic!("{node_id} missing {role_id}"));
        assert!(role.actions.len() > 0, "{node_id}.{role_id}");
        assert!(
            role.sources.iter().any(|source| source.kind == "leader"),
            "{node_id}.{role_id} missing leader source"
        );
    }
    let dallas = graph
        .nodes
        .iter()
        .find(|node| node.id == "DallasLeadership")
        .unwrap();
    assert_eq!(dallas.graph_group, "lab");
}

#[test]
fn declared_graph_metadata_and_probability_errors_keep_source_lines() {
    let missing_slice = SOURCE.replacen(
        "composition USA:\n  slice = \"Physical\"\n  graph_group = main",
        "composition USA:\n  graph_group = main",
        1,
    );
    let error = parse_program(&missing_slice).unwrap_err();
    assert_eq!(error.code, "MISSING_COMPOSITION_SLICE");
    assert!(error.line > 0);

    let bad_probability = SOURCE.replacen(
        "    Canada: weight = 0.208333333333333",
        "    Canada: weight = 0.308333333333333",
        1,
    );
    let error = parse_program(&bad_probability).unwrap_err();
    assert_eq!(error.code, "INVALID_DISTRIBUTION_SUM");
    assert!(error.line > 0);
}
