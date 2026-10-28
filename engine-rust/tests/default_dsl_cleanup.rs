const SOURCE: &str = include_str!("../dsl/default.dsl");

#[test]
fn shipped_dsl_contains_only_pool_and_current_sector_architecture() {
    for forbidden in [
        "slice = \"Corporate\"",
        "slice = \"Full system\"",
        "CorporateForest",
        "agent User:",
        "agent RetailPerson:",
        "agent FinancialPerson:",
        "agent Citizen:",
        "agent RoleDemoPerson",
        "TownHouseholds",
        "CanadaHouseholds",
        "SevenBillionHouseholds",
        "DemoNeighbourhoods",
        "SectorAlpha",
        "SectorBeta",
        "MarketAlpha",
        "MarketBeta",
        "StockAlpha",
        "StockBeta",
        "FirmAlpha",
        "FirmBeta",
        "BrandOne",
        "BrandTwo",
        "FranchiseOne",
        "FranchiseTwo",
        "composition StoreA:",
        "composition StoreB:",
        "composition StoreC:",
        "composition StoreD:",
        "for demo only",
        "  flows:",
        "  couplings:",
    ] {
        assert!(!SOURCE.contains(forbidden), "found {forbidden}");
    }
    assert!(SOURCE.contains("agent_pool = World"));
    assert!(SOURCE.contains("slice = \"Conglomerate\""));
    assert!(!SOURCE.contains("represented_population = 6999999999"));
    assert!(!SOURCE.contains("represented_population = 8000000"));
}
