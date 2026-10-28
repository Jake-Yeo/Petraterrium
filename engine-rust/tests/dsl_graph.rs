use petraterrium_engine::text_dsl::{build_program_graph, parse_program};
use std::collections::BTreeSet;

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
        .sum::<usize>();
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
    assert_eq!(node("World").vertical_slice, "World");
    assert!(
        node("World")
            .subtree_roles
            .iter()
            .any(|role| role == "worker")
    );
    assert_eq!(node("Reddit").vertical_slice, "Reddit");
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
        node("FinancialPerson")
            .roles_used
            .iter()
            .any(|role| role == "trader")
    );
    assert!(
        store
            .roles_exposed
            .iter()
            .find(|role| role.id == "cashier")
            .is_some_and(|role| !role.conditions.is_empty())
    );
}
