use petraterrium_engine::text_dsl::{
    CachedCompositionEvaluationResult, CachedCompositionProtocolRequest, CompositionCacheMetadata,
    DslReport, DslReportValue, DslRunResult, LearnedAggregateArtifact, ScheduledAggregateInputs,
    evaluate_cached_composition, parse_program, run_composition,
};
use std::collections::{BTreeMap, BTreeSet};

const SOURCE: &str = include_str!("../dsl/media_test.dsl");

fn hash(source: &str) -> String {
    let value = source
        .as_bytes()
        .iter()
        .fold(0xcbf29ce484222325_u64, |hash, byte| {
            (hash ^ u64::from(*byte)).wrapping_mul(0x100000001b3)
        });
    format!("test:{value:016x}")
}

fn request(
    source: &str,
    function_id: &str,
    days: u32,
    artifacts: BTreeMap<String, LearnedAggregateArtifact>,
) -> CachedCompositionProtocolRequest {
    CachedCompositionProtocolRequest {
        source: source.to_owned(),
        dsl_source_hash: hash(source),
        function_id: function_id.to_owned(),
        seed: 1,
        days,
        evaluated_at_day: 0,
        inputs: BTreeMap::new(),
        branch_inputs: BTreeMap::new(),
        input_schedule: Vec::new(),
        events: BTreeSet::new(),
        artifacts,
        force_relearn: false,
    }
}

fn evaluate(
    source: &str,
    request: CachedCompositionProtocolRequest,
) -> CachedCompositionEvaluationResult {
    evaluate_cached_composition(parse_program(source).unwrap(), request).unwrap()
}

fn run(source: &str, composition: &str, days: u64) -> DslRunResult {
    run_composition(parse_program(source).unwrap(), composition, 1, days * 24).unwrap()
}

fn report<'a>(result: &'a CachedCompositionEvaluationResult, id: &str) -> &'a DslReport {
    result
        .reports
        .iter()
        .find(|report| report.id == id)
        .unwrap()
}

fn root_value(result: &DslRunResult, id: &str) -> f64 {
    result
        .reports
        .iter()
        .find(|report| report.id == "compositions")
        .unwrap()
        .snapshots[0]
        .rows[0]
        .values[id]
        .clone()
        .number()
}

fn cached_value(result: &CachedCompositionEvaluationResult, id: &str) -> f64 {
    result.time_series.last().unwrap().outputs[id].mean
}

fn metadata<'a>(tree: &'a CompositionCacheMetadata, id: &str) -> &'a CompositionCacheMetadata {
    if tree.function_id == id {
        return tree;
    }
    tree.children
        .iter()
        .find_map(|child| find_metadata(child, id))
        .unwrap()
}

fn find_metadata<'a>(
    tree: &'a CompositionCacheMetadata,
    id: &str,
) -> Option<&'a CompositionCacheMetadata> {
    if tree.function_id == id {
        return Some(tree);
    }
    tree.children
        .iter()
        .find_map(|child| find_metadata(child, id))
}

fn compact(
    mut artifacts: BTreeMap<String, LearnedAggregateArtifact>,
) -> BTreeMap<String, LearnedAggregateArtifact> {
    for artifact in artifacts.values_mut() {
        for point in &mut artifact.points {
            point.reports.clear();
        }
    }
    artifacts
}

trait ReportNumber {
    fn number(self) -> f64;
}

impl ReportNumber for DslReportValue {
    fn number(self) -> f64 {
        match self {
            DslReportValue::Number(value) => value,
            value => panic!("expected number, got {value:?}"),
        }
    }
}

#[test]
fn parser_and_generic_composition_accept_media_without_physical_levels() {
    let program = parse_program(SOURCE).unwrap();
    assert_eq!(program.entities[0].id, "Post");
    assert_eq!(program.policies[0].id, "ModerationPolicy");
    assert!(
        program
            .archetypes
            .iter()
            .find(|archetype| archetype.id == "InfluencerX")
            .unwrap()
            .spotlight
    );
    let reddit = program
        .compositions
        .iter()
        .find(|composition| composition.id == "Reddit")
        .unwrap();
    assert_eq!(reddit.level, "platform");
    assert!(reddit.entries.iter().all(|entry| {
        program
            .compositions
            .iter()
            .find(|composition| composition.id == entry.child)
            .is_some_and(|composition| composition.level == "community")
    }));
    assert_eq!(
        run_composition(program, "Reddit", 1, 0)
            .unwrap()
            .state
            .agents
            .len(),
        100
    );

    let bad_user = SOURCE.replacen("mix InfluencerUser:1.0", "mix MissingUser:1.0", 1);
    let error = parse_program(&bad_user).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_ARCHETYPE_AGENT");
    assert!(error.line > 0);

    let bad_community = SOURCE.replacen(
        "    PersonalFinance: weight = 5",
        "    MissingCommunity: weight = 5",
        1,
    );
    let error = parse_program(&bad_community).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_COMPOSITION_CHILD");
    assert!(error.line > 0);

    let bad_platform = SOURCE.replacen(
        "PhysicalTown -> Reddit input = signal",
        "PhysicalTown -> MissingPlatform input = signal",
        1,
    );
    let error = parse_program(&bad_platform).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_COMPOSITION_COUPLING_CHILD");
    assert!(error.line > 0);

    let renamed = SOURCE.replace("CivicForum", "NewForum");
    let result = run(&renamed, "Reddit", 0);
    assert_eq!(result.state.agents.len(), 100);
}

#[test]
fn recommendation_viral_threshold_and_moderation_are_dsl_probabilities() {
    let low_engagement = SOURCE.replacen(
        "state engagement = 20 range 0..100000 estimated",
        "state engagement = 5 range 0..100000 estimated",
        1,
    );
    let high_engagement = SOURCE.replacen(
        "state engagement = 20 range 0..100000 estimated",
        "state engagement = 80 range 0..100000 estimated",
        1,
    );
    let low = run(&low_engagement, "PersonalFinance", 7);
    let high = run(&high_engagement, "PersonalFinance", 7);
    assert!(root_value(&high, "share_rate") > root_value(&low, "share_rate"));
    assert!(root_value(&high, "viral_posts") > root_value(&low, "viral_posts"));

    let strict = SOURCE.replacen(
        "    norm_strictness = 0.25",
        "    norm_strictness = 0.95",
        1,
    );
    let moderate = run(SOURCE, "PersonalFinance", 7);
    let strict = run(&strict, "PersonalFinance", 7);
    assert!(root_value(&strict, "posting_rate") > 0.0);
    assert!(root_value(&strict, "share_rate") > 0.0);
    assert!(root_value(&strict, "posting_rate") < root_value(&moderate, "posting_rate"));
    assert!(root_value(&strict, "share_rate") < root_value(&moderate, "share_rate"));
    let closed_topic = SOURCE.replacen("    topic_closure = 0.10", "    topic_closure = 1.00", 1);
    let closed_topic = run(&closed_topic, "PersonalFinance", 7);
    assert!(root_value(&closed_topic, "posting_rate") > 0.0);
    assert!(
        root_value(&closed_topic, "posting_rate") < root_value(&moderate, "posting_rate") * 0.5
    );
    assert!(SOURCE.contains("0.10 + place.engagement * 0.001"));
    assert!(SOURCE.contains("policies = ModerationPolicy"));
}

#[test]
fn spotlight_event_is_individual_recorded_and_weighted_above_mass_posts() {
    let without_spotlight = SOURCE.replacen("    InfluencerX: weight = 1\n", "", 1);
    let with = run(SOURCE, "PersonalFinance", 10);
    let without = run(&without_spotlight, "PersonalFinance", 10);
    assert!(root_value(&with, "mean_sentiment") > root_value(&without, "mean_sentiment"));
    assert!(root_value(&with, "mean_outrage") > root_value(&without, "mean_outrage"));
    assert!(!with.actions.is_empty());
    assert!(
        with.actions
            .iter()
            .all(|action| action.action.ends_with("spotlight_post"))
    );
    assert!(with.actions.iter().all(|action| {
        action.values.contains_key("sentiment")
            && action.values.contains_key("source")
            && action.values.contains_key("place.engagement")
    }));

    let low_outrage = SOURCE.replacen(
        "outrage ~ Uniform(min=0.8, max=0.8)",
        "outrage ~ Uniform(min=0.05, max=0.05)",
        1,
    );
    let high = run(SOURCE, "PersonalFinance", 10);
    let low = run(&low_outrage, "PersonalFinance", 10);
    assert!(root_value(&high, "mean_outrage") > root_value(&low, "mean_outrage"));
    assert!(root_value(&high, "polarization") > root_value(&low, "polarization"));
}

#[test]
fn cached_media_reuses_branches_and_couples_both_directions_daily() {
    let cold = evaluate(
        SOURCE,
        request(SOURCE, "CoupledTownMedia", 30, BTreeMap::new()),
    );
    assert!(cold.agent_ticks > 0);
    let artifacts = compact(cold.artifacts.clone());
    let warm = evaluate(
        SOURCE,
        request(SOURCE, "CoupledTownMedia", 30, artifacts.clone()),
    );
    assert!(warm.cache_hit);
    assert_eq!(warm.agent_ticks, 0);
    assert!(cached_value(&warm, "physical_to_media") > 0.0);
    assert!(cached_value(&warm, "media_to_physical") > 0.0);
    assert!(cached_value(&warm, "mean_stress") <= 1.0);
    for id in [
        "CoupledTownMedia",
        "Reddit",
        "PersonalFinance",
        "CivicForum",
        "UserActive",
        "PhysicalTown",
        "PhysicalMass",
    ] {
        assert!(metadata(&warm.cache_tree, id).cached, "{id}");
    }

    let media = evaluate(SOURCE, request(SOURCE, "Reddit", 30, artifacts.clone()));
    assert!(media.cache_hit);
    assert_eq!(media.agent_ticks, 0);

    let mut changed_request = request(SOURCE, "CoupledTownMedia", 30, artifacts.clone());
    changed_request.branch_inputs.insert(
        "PersonalFinance".to_owned(),
        BTreeMap::from([("signal".to_owned(), 0.8)]),
    );
    let changed = evaluate(SOURCE, changed_request);
    assert_eq!(changed.agent_ticks, 0);
    assert!(!metadata(&changed.cache_tree, "PersonalFinance").cached);
    assert!(!metadata(&changed.cache_tree, "Reddit").cached);
    assert!(!metadata(&changed.cache_tree, "CoupledTownMedia").cached);
    assert!(metadata(&changed.cache_tree, "CivicForum").cached);

    let mut blocked_request = request(SOURCE, "Reddit", 30, artifacts.clone());
    blocked_request
        .inputs
        .insert("viral_threshold".to_owned(), 1000.0);
    let blocked = evaluate(SOURCE, blocked_request);
    assert_eq!(cached_value(&blocked, "viral_spread"), 0.0);
    assert!(cached_value(&media, "viral_spread") > 0.0);

    let mut long_request = request(SOURCE, "CoupledTownMedia", 90, artifacts);
    long_request.input_schedule.push(ScheduledAggregateInputs {
        day: 30,
        values: BTreeMap::from([("external_event".to_owned(), 0.8)]),
    });
    let long = evaluate(SOURCE, long_request);
    assert_eq!(long.agent_ticks, 0);
    let day_30 = long
        .time_series
        .iter()
        .find(|point| point.day == 30)
        .unwrap();
    let day_90 = long
        .time_series
        .iter()
        .find(|point| point.day == 90)
        .unwrap();
    assert_ne!(day_30.outputs, day_90.outputs);
    assert_eq!(report(&long, "composition_flows").snapshots.len(), 90);
}

#[test]
fn coupling_is_explicit_and_sync_cadence_is_dsl_controlled() {
    let mut minute_source = SOURCE.replace(
        "tick_hours = 1 placeholder",
        "tick_hours = 0.0166666667 estimated",
    );
    minute_source = minute_source
        .lines()
        .flat_map(|line| {
            if line.starts_with("  duration = ") {
                vec![line.to_owned(), "  long = true estimated".to_owned()]
            } else {
                vec![line.to_owned()]
            }
        })
        .collect::<Vec<_>>()
        .join("\n");
    minute_source.push('\n');
    let minute_run = run_composition(
        parse_program(&minute_source).unwrap(),
        "PersonalFinance",
        1,
        1_440,
    )
    .unwrap();
    assert_eq!(minute_run.completed_ticks, 1_440);

    let coupled = run(SOURCE, "CoupledTownMedia", 30);
    let mut physical = coupled
        .state
        .agents
        .iter()
        .filter(|agent| agent.id.starts_with("PhysicalTown__"))
        .collect::<Vec<_>>();
    let mut media = coupled
        .state
        .agents
        .iter()
        .filter(|agent| agent.id.starts_with("Reddit__"))
        .collect::<Vec<_>>();
    physical.sort_by(|left, right| left.id.cmp(&right.id));
    media.sort_by(|left, right| left.id.cmp(&right.id));
    assert_eq!(physical.len(), media.len());
    for field in ["political_lean", "trust", "stress"] {
        assert_eq!(physical[0].value(field), media[0].value(field), "{field}");
    }
    let uncoupled_source = SOURCE
        .replace(
            "  couplings:\n    physical_to_media PhysicalTown -> Reddit input = signal value = formula(clamp(PhysicalTown_fights_per_day / 100 + external_event * 0.20, 0, 1)) cadence = sync\n    media_outage_to_physical Reddit -> PhysicalTown input = media_outrage value = formula(clamp(Reddit_mean_outrage, 0, 1)) cadence = sync\n    media_sentiment_to_physical Reddit -> PhysicalTown input = media_sentiment value = formula(clamp(Reddit_mean_sentiment, -1, 1)) cadence = sync\n",
            "",
        )
        .replace("  output physical_to_media = flow_rate(physical_to_media)\n", "")
        .replace("  output media_to_physical = flow_rate(media_outage_to_physical)\n", "")
        .replace("    physical_to_media = formula(external_event)\n", "")
        .replace("    media_to_physical = formula(external_event)\n", "");
    let uncoupled = run(&uncoupled_source, "CoupledTownMedia", 30);
    assert_ne!(
        root_value(&coupled, "mean_stress"),
        root_value(&uncoupled, "mean_stress")
    );
    assert_ne!(
        root_value(&coupled, "mean_outrage"),
        root_value(&uncoupled, "mean_outrage")
    );

    let weekly = SOURCE.replacen(
        "composition CoupledTownMedia:\n  level = coupled_modules\n  children:\n    PhysicalTown: weight = 1\n    Reddit: weight = 1\n  cached:\n    sync = 1 days",
        "composition CoupledTownMedia:\n  level = coupled_modules\n  children:\n    PhysicalTown: weight = 1\n    Reddit: weight = 1\n  cached:\n    sync = 7 days",
        1,
    );
    let daily_cold = evaluate(
        SOURCE,
        request(SOURCE, "CoupledTownMedia", 30, BTreeMap::new()),
    );
    let weekly_cold = evaluate(
        &weekly,
        request(&weekly, "CoupledTownMedia", 30, BTreeMap::new()),
    );
    let coupling_rows = |result: &CachedCompositionEvaluationResult| {
        report(result, "composition_flows")
            .snapshots
            .iter()
            .flat_map(|snapshot| &snapshot.rows)
            .filter(|row| {
                row.values.get("effect") == Some(&DslReportValue::Text("coupling".to_owned()))
            })
            .count()
    };
    assert_eq!(coupling_rows(&daily_cold), 90);
    assert_eq!(coupling_rows(&weekly_cold), 15);
}

#[test]
fn detailed_monolith_and_cached_coupling_stay_within_ten_percent() {
    let source = SOURCE.replacen("    InfluencerX: weight = 1\n", "", 1);
    let detailed = run(&source, "CoupledTownMedia", 30);
    let cold = evaluate(
        &source,
        request(&source, "CoupledTownMedia", 30, BTreeMap::new()),
    );
    let cached = evaluate(
        &source,
        request(&source, "CoupledTownMedia", 30, compact(cold.artifacts)),
    );
    assert_eq!(cached.agent_ticks, 0);
    for metric in [
        "protest_rate",
        "mean_sentiment",
        "mean_outrage",
        "vote_liberal_share",
    ] {
        let monolith = root_value(&detailed, metric);
        let coupled = cached_value(&cached, metric);
        eprintln!("{metric}: monolith={monolith}, coupled={coupled}");
        assert!(
            (monolith - coupled).abs() / monolith.abs().max(1e-9) <= 0.10,
            "{metric}: monolith={monolith}, coupled={coupled}"
        );
    }
}
