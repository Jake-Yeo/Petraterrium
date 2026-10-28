use petraterrium_engine::text_dsl::{DslReportValue, DslRunResult, parse_program, run_composition};

const SOURCE: &str = include_str!("../dsl/financial_coupling_test.dsl");

fn run(source: &str, composition: &str, ticks: u64) -> DslRunResult {
    run_composition(parse_program(source).unwrap(), composition, 1, ticks).unwrap()
}

fn value(result: &DslRunResult, id: &str) -> f64 {
    let value = &result
        .reports
        .iter()
        .find(|report| report.id == "compositions")
        .unwrap()
        .snapshots[0]
        .rows[0]
        .values[id];
    match value {
        DslReportValue::Number(value) => *value,
        value => panic!("expected number, got {value:?}"),
    }
}

#[test]
fn listed_and_unlisted_entities_declare_the_expected_hinges() {
    let program = parse_program(SOURCE).unwrap();
    let alpha = program
        .entities
        .iter()
        .find(|entity| entity.id == "ListedFirmAlpha")
        .unwrap();
    assert_eq!(alpha.links["corporate"], "FirmAlpha");
    assert_eq!(alpha.links["stock"], "StockAlpha");
    let family = program
        .entities
        .iter()
        .find(|entity| entity.id == "FamilyEnterprise")
        .unwrap();
    assert_eq!(family.links["corporate"], "FamilyBusiness");
    assert!(!family.links.contains_key("stock"));
}

#[test]
fn secondary_buy_and_sell_conserve_money_without_changing_firm_cash() {
    for composition in ["SecondaryBuyLab", "SecondarySellLab"] {
        let before = run(SOURCE, composition, 0);
        let after = run(SOURCE, composition, 1);
        assert!(
            after.actions.iter().any(|action| {
                action.action.ends_with("secondary_buy")
                    || action.action.ends_with("secondary_sell")
            }),
            "{composition}: {:?} {:?}",
            after.actions,
            after.state.agents
        );
        assert_eq!(value(&before, "total_money"), value(&after, "total_money"));
        assert_eq!(value(&before, "firm_cash"), value(&after, "firm_cash"));
        assert_ne!(
            value(&before, "price"),
            value(&after, "price"),
            "{composition}"
        );
        assert_ne!(
            value(&before, "market_cap"),
            value(&after, "market_cap"),
            "{composition}"
        );
    }
}

#[test]
fn issuance_moves_trader_money_to_firm_cash_and_dilutes_price() {
    let before = run(SOURCE, "IssuanceLab", 0);
    let after = run(SOURCE, "IssuanceLab", 1);
    assert_eq!(value(&before, "total_money"), value(&after, "total_money"));
    assert_eq!(
        value(&after, "firm_cash"),
        value(&before, "firm_cash") + 10.0
    );
    assert_eq!(
        value(&after, "shares_outstanding"),
        value(&before, "shares_outstanding") + 1.0
    );
    assert!(value(&after, "price") < value(&before, "price"));
    assert!((value(&after, "market_cap") - value(&before, "market_cap")).abs() < 1e-9);
}

#[test]
fn borrowing_interest_and_repayment_follow_conserved_dsl_flows() {
    let borrowed = run(SOURCE, "BorrowLab", 1);
    assert_eq!(value(&borrowed, "firm_cash"), 150.0);
    assert_eq!(value(&borrowed, "lender_cash"), 950.0);
    assert_eq!(value(&borrowed, "debt"), 50.0);
    assert_eq!(value(&borrowed, "total_money"), 1100.0);

    let indebted = SOURCE.replacen("state firm_debt = 0 range", "state firm_debt = 50 range", 1);
    let interest = run(&indebted, "InterestLab", 1);
    assert_eq!(value(&interest, "debt"), 52.5);
    assert_eq!(value(&interest, "firm_cash"), 100.0);

    let repayable = indebted.replacen(
        "state firm_cash = 100 range",
        "state firm_cash = 150 range",
        1,
    );
    let repaid = run(&repayable, "RepayLab", 1);
    assert_eq!(value(&repaid, "firm_cash"), 130.0);
    assert_eq!(value(&repaid, "lender_cash"), 1020.0);
    assert_eq!(value(&repaid, "debt"), 30.0);
    assert_eq!(value(&repaid, "total_money"), 1150.0);
}

#[test]
fn price_dividend_and_market_cap_are_exact_formulas_distinct_from_cash() {
    let baseline = run(SOURCE, "StockAlpha", 0);
    assert_eq!(value(&baseline, "price"), 31.0);
    assert!((value(&baseline, "dividend") - 0.435).abs() < 1e-12);
    assert_eq!(value(&baseline, "market_cap"), 3100.0);
    assert_eq!(value(&baseline, "firm_cash"), 200.0);

    let repriced = SOURCE.replacen("market_sentiment = 0.20", "market_sentiment = 0.80", 1);
    let repriced = run(&repriced, "StockAlpha", 0);
    assert!(value(&repriced, "price") > value(&baseline, "price"));
    assert!(value(&repriced, "market_cap") > value(&baseline, "market_cap"));
    assert_eq!(value(&repriced, "firm_cash"), value(&baseline, "firm_cash"));
}

#[test]
fn minute_financial_ticks_use_the_same_generic_runtime() {
    let minute_source = SOURCE
        .replacen(
            "tick_hours = 1 placeholder",
            "tick_hours = 0.016666666666666666 placeholder",
            1,
        )
        .replace(
            "Triangular(min=0.1, median=0.2, max=0.5)",
            "Triangular(min=0.001, median=0.005, max=0.01)",
        );
    let result = run_composition(
        parse_program(&minute_source).unwrap(),
        "SecondaryBuyLab",
        1,
        1_440,
    )
    .unwrap();
    assert_eq!(result.completed_ticks, 1_440);
}
