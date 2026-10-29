use petraterrium_engine::text_dsl::{build_program_graph, parse_program};
use std::collections::BTreeSet;

const SOURCE: &str = include_str!("../dsl/default.dsl");

#[test]
fn graph_contains_current_physical_hierarchy_and_four_sector_metadata() {
    let program = parse_program(SOURCE).unwrap();
    let graph = build_program_graph(&program).unwrap();
    let ids = graph
        .nodes
        .iter()
        .map(|node| node.id.as_str())
        .collect::<BTreeSet<_>>();
    for id in [
        "World",
        "Canada",
        "USA",
        "Mexico",
        "Toronto",
        "Vancouver",
        "Lytton",
        "LosAngeles",
        "Houston",
        "MexicoCity",
        "Monterrey",
        "Reddit",
        "BerkshireHathaway",
        "FinancialEconomy",
    ] {
        assert!(ids.contains(id), "{id}");
    }
    let slices = graph
        .slices
        .iter()
        .filter(|slice| slice.group == "main")
        .map(|slice| slice.id.as_str())
        .collect::<BTreeSet<_>>();
    assert_eq!(
        slices,
        BTreeSet::from(["Conglomerate", "Financial", "Media", "Physical"])
    );
    assert!(graph.edges.iter().all(|edge| edge.kind != "coupling"));
}

#[test]
fn graph_exposes_strata_clocks_provenance_and_current_leaders() {
    let program = parse_program(SOURCE).unwrap();
    let graph = build_program_graph(&program).unwrap();
    let node = |id: &str| graph.nodes.iter().find(|node| node.id == id).unwrap();
    let urban = node("UrbanLiberal");
    assert_eq!(urban.exemplar_households, Some(75));
    assert_eq!(urban.stratum.as_deref(), Some("dense_urban_high_education"));
    assert_eq!(urban.clock_minutes, 60);
    assert_eq!(urban.sync_up_minutes, Some(1_440));
    assert!(urban.provenance.is_some());
    for (node_id, role_id) in [
        ("USA", "president"),
        ("Mexico", "president"),
        ("Canada", "prime_minister"),
        ("Toronto", "mayor"),
        ("Ontario", "governor"),
        ("Texas", "governor"),
        ("California", "governor"),
        ("BerkshireRetailBrand", "brand_manager"),
        ("BerkshireRetailFranchise", "franchise_manager"),
        ("BerkshireRetailStore", "store_manager"),
        ("PersonalFinance", "influencer"),
        ("BerkshireHathaway", "ceo"),
    ] {
        assert!(
            node(node_id)
                .roles_exposed
                .iter()
                .any(|role| role.id == role_id && role.leader),
            "{node_id}.{role_id}"
        );
    }
}

#[test]
fn graph_metadata_errors_keep_source_lines() {
    let missing_slice = SOURCE.replacen(
        "composition USA:\n  slice = \"Physical\"\n  graph_group = main",
        "composition USA:\n  graph_group = main",
        1,
    );
    let error = parse_program(&missing_slice).unwrap_err();
    assert_eq!(error.code, "MISSING_COMPOSITION_SLICE");
    assert!(error.line > 0);

    let bad_probability = SOURCE.replacen(
        "    Canada: weight = 0.20833333333333334",
        "    Canada: weight = 0.30833333333333334",
        1,
    );
    let error = parse_program(&bad_probability).unwrap_err();
    assert_eq!(error.code, "INVALID_DISTRIBUTION_SUM");
    assert!(error.line > 0);
}
