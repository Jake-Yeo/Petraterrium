#[path = "../src/locations.rs"]
mod locations;

use locations::*;
use std::collections::BTreeMap;

fn place(
    id: &str,
    level: LocationLevel,
    parent_id: Option<&str>,
    state: &[(&str, f64)],
) -> LocationPlace {
    LocationPlace {
        id: id.to_owned(),
        name: id.replace('-', " "),
        level,
        parent_id: parent_id.map(str::to_owned),
        accepts_arrivals: true,
        allows_in_person: true,
        capacity: None,
        state: state
            .iter()
            .map(|(key, value)| ((*key).to_owned(), *value))
            .collect::<BTreeMap<_, _>>(),
    }
}

fn hierarchy() -> Vec<LocationPlace> {
    vec![
        place("canada", LocationLevel::Country, None, &[("tax_rate", 0.2)]),
        place(
            "british-columbia",
            LocationLevel::State,
            Some("canada"),
            &[("tax_rate", 0.25)],
        ),
        place(
            "vancouver",
            LocationLevel::City,
            Some("british-columbia"),
            &[("air_quality", 0.8)],
        ),
        place("kitsilano", LocationLevel::District, Some("vancouver"), &[]),
        place(
            "home-1",
            LocationLevel::Building,
            Some("kitsilano"),
            &[("contamination", 0.1)],
        ),
        place(
            "living-room",
            LocationLevel::Room,
            Some("home-1"),
            &[("contamination", 0.3)],
        ),
        place("kitchen", LocationLevel::Room, Some("home-1"), &[]),
    ]
}

fn request() -> LocationTickRequest {
    LocationTickRequest {
        tick: 4,
        places: hierarchy(),
        agents: LocationAgentColumns {
            agent_ids: vec!["avery".to_owned(), "sam".to_owned(), "mira".to_owned()],
            current_location_ids: vec![
                "living-room".to_owned(),
                "living-room".to_owned(),
                "kitchen".to_owned(),
            ],
        },
        movements: vec![],
        history: vec![],
    }
}

#[test]
fn movement_uses_hierarchy_records_history_and_updates_colocation() {
    let mut request = request();
    request.movements.push(LocationMovement {
        agent_index: 2,
        destination_location_id: "living-room".to_owned(),
        expected_parent_id: Some("home-1".to_owned()),
    });

    let result = run_location_tick(request).unwrap();

    assert_eq!(
        result.current_location_ids,
        vec!["living-room", "living-room", "living-room"]
    );
    assert_eq!(
        result.movements[0].route_location_ids,
        vec!["kitchen", "home-1", "living-room"]
    );
    assert_eq!(
        result.history,
        result
            .movements
            .iter()
            .map(|event| {
                LocationHistoryRecord {
                    tick: event.tick,
                    agent_id: event.agent_id.clone(),
                    from_location_id: event.from_location_id.clone(),
                    to_location_id: event.to_location_id.clone(),
                    route_location_ids: event.route_location_ids.clone(),
                }
            })
            .collect::<Vec<_>>()
    );
    assert_eq!(result.co_located_agent_indices[0], vec![1, 2]);
    assert_eq!(result.co_located_agent_indices[2], vec![0, 1]);
    assert_eq!(
        result.effective_place_state["tax_rate"],
        vec![Some(0.25); 3]
    );
    assert_eq!(
        result.effective_place_state["contamination"],
        vec![Some(0.3); 3]
    );
    assert!(face_to_face_allowed(&hierarchy(), &result.current_location_ids, 0, 2).unwrap());
}

#[test]
fn invalid_arrival_is_atomic_and_reports_the_exact_field() {
    let mut request = request();
    request.places[6].accepts_arrivals = false;
    request.movements.push(LocationMovement {
        agent_index: 0,
        destination_location_id: "kitchen".to_owned(),
        expected_parent_id: Some("home-1".to_owned()),
    });

    let error = run_location_tick(request).unwrap_err();

    assert_eq!(error.code, "ARRIVAL_NOT_ALLOWED");
    assert_eq!(error.path, "movements.0.destination_location_id");
}

#[test]
fn arrivals_validate_parent_and_final_capacity() {
    let mut wrong_parent = request();
    wrong_parent.movements.push(LocationMovement {
        agent_index: 2,
        destination_location_id: "living-room".to_owned(),
        expected_parent_id: Some("kitsilano".to_owned()),
    });
    assert_eq!(
        run_location_tick(wrong_parent).unwrap_err().code,
        "ARRIVAL_PARENT_MISMATCH"
    );

    let mut full = request();
    full.places[5].capacity = Some(2);
    full.movements.push(LocationMovement {
        agent_index: 2,
        destination_location_id: "living-room".to_owned(),
        expected_parent_id: Some("home-1".to_owned()),
    });
    assert_eq!(
        run_location_tick(full).unwrap_err().code,
        "LOCATION_CAPACITY_EXCEEDED"
    );
}

#[test]
fn hierarchy_rejects_skipped_levels() {
    let mut invalid = request();
    invalid.places[2].parent_id = Some("canada".to_owned());

    let error = run_location_tick(invalid).unwrap_err();

    assert_eq!(error.code, "INVALID_LOCATION_PARENT");
    assert_eq!(error.path, "places.2.parent_id");
}

#[test]
fn places_that_disallow_in_person_contact_gate_face_to_face_interactions() {
    let mut places = hierarchy();
    places[5].allows_in_person = false;
    let location_ids = vec!["living-room".to_owned(), "living-room".to_owned()];

    assert!(!face_to_face_allowed(&places, &location_ids, 0, 1).unwrap());
}

#[test]
fn travel_between_country_roots_records_both_sides_of_the_route() {
    let request = LocationTickRequest {
        tick: 9,
        places: vec![
            place("canada", LocationLevel::Country, None, &[]),
            place("mexico", LocationLevel::Country, None, &[]),
        ],
        agents: LocationAgentColumns {
            agent_ids: vec!["traveler".to_owned()],
            current_location_ids: vec!["canada".to_owned()],
        },
        movements: vec![LocationMovement {
            agent_index: 0,
            destination_location_id: "mexico".to_owned(),
            expected_parent_id: None,
        }],
        history: vec![],
    };

    let result = run_location_tick(request).unwrap();

    assert_eq!(result.movements[0].route_location_ids, ["canada", "mexico"]);
}
