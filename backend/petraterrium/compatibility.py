import numpy as np
from numpy.typing import NDArray

from .contracts import Parameters, RunConfig
from .data import COUNTRY_BY_CODE
from .dsl import (
    ActionDefinition,
    BehaviourBundle,
    DefaultDefinition,
    Distribution,
    DSLConfig,
    EventDefinition,
    Evidence,
    OutputSpec,
    ParameterDefinition,
    PopulationReference,
    ProbabilitySpec,
    RoleDefinition,
    StateDefinition,
    SystemDefinition,
    TickConfig,
    TransitionDefinition,
)

State = NDArray[np.int64]


def fake_evidence(source: str, uncertainty: float) -> Evidence:
    return Evidence(
        source=source,
        version="FAKE-smoke-v1",
        status="literature_estimate",
        uncertainty=uncertainty,
    )


def initial_state(config: RunConfig) -> State:
    state = np.zeros((len(config.countries), 4), dtype=np.int64)
    state[:, 0] = [COUNTRY_BY_CODE[c].population for c in config.countries]
    origin = config.countries.index("ITA") if "ITA" in config.countries else 0
    state[origin, 0] -= config.parameters.initial_infected
    state[origin, 2] = config.parameters.initial_infected
    return state


def step(state: State, params: Parameters, rng: np.random.Generator) -> State:
    populations = state.sum(axis=1)
    prevalence = state[:, 2] / populations
    shared_prevalence = state[:, 2].sum() / populations.sum()
    force = params.transmission * (
        (1 - params.mixing) * prevalence + params.mixing * shared_prevalence
    )
    exposed = rng.binomial(state[:, 0], -np.expm1(-force))
    infected = rng.binomial(state[:, 1], -np.expm1(-params.progression))
    recovered = rng.binomial(state[:, 2], -np.expm1(-params.recovery))
    next_state = state.copy()
    next_state[:, 0] -= exposed
    next_state[:, 1] += exposed - infected
    next_state[:, 2] += infected - recovered
    next_state[:, 3] += recovered
    return next_state


def compatibility_dsl(config: RunConfig) -> DSLConfig:
    missing_places = sorted(set(config.countries) - set(COUNTRY_BY_CODE))
    if missing_places:
        raise ValueError(
            f"Compatibility run has no population data for {', '.join(missing_places)}; "
            "provide a full DSL and population reference"
        )
    place_populations = {place: COUNTRY_BY_CODE[place].population for place in config.countries}
    place_coordinates = {
        place: (COUNTRY_BY_CODE[place].latitude, COUNTRY_BY_CODE[place].longitude)
        for place in config.countries
    }
    origin = "ITA" if "ITA" in config.countries else config.countries[0]
    overrides = {}
    for place, population in place_populations.items():
        infected = config.parameters.initial_infected if place == origin else 0
        overrides[place] = {
            "health": {
                "susceptible": population - infected,
                "exposed": 0,
                "infected": infected,
                "recovered": 0,
            }
        }
    rate_evidence = fake_evidence("FAKE unfitted compatibility rates", 0.75)
    default_evidence = fake_evidence("FAKE synthetic population defaults", 0.9)
    return DSLConfig(
        id=config.scenario,
        version="compatibility-v1",
        states=[
            StateDefinition(
                id="health",
                values=["susceptible", "exposed", "infected", "recovered"],
                initial=Distribution(
                    values={
                        "susceptible": 1,
                        "exposed": 0,
                        "infected": 0,
                        "recovered": 0,
                    },
                    provenance=default_evidence,
                ),
            )
        ],
        place_states=["population"],
        parameters=[
            ParameterDefinition(
                id="transmission",
                value=config.parameters.transmission,
                unit="hazard_per_day",
                provenance=rate_evidence,
            ),
            ParameterDefinition(
                id="progression",
                value=config.parameters.progression,
                unit="hazard_per_day",
                provenance=rate_evidence,
            ),
            ParameterDefinition(
                id="recovery",
                value=config.parameters.recovery,
                unit="hazard_per_day",
                provenance=rate_evidence,
            ),
            ParameterDefinition(
                id="mixing",
                value=config.parameters.mixing,
                unit="share",
                provenance=rate_evidence,
            ),
        ],
        systems=[
            SystemDefinition(
                id="health-spread",
                state="health",
                transitions=[
                    TransitionDefinition(
                        id="exposure",
                        from_state="susceptible",
                        to_state="exposed",
                        probability=ProbabilitySpec(
                            base=config.parameters.transmission,
                            mode="hazard",
                            time_unit="day",
                            parameter="transmission",
                            source_state="infected",
                            mixing_parameter="mixing",
                        ),
                    ),
                    TransitionDefinition(
                        id="progression",
                        from_state="exposed",
                        to_state="infected",
                        probability=ProbabilitySpec(
                            base=config.parameters.progression,
                            mode="hazard",
                            time_unit="day",
                            parameter="progression",
                        ),
                    ),
                    TransitionDefinition(
                        id="recovery",
                        from_state="infected",
                        to_state="recovered",
                        probability=ProbabilitySpec(
                            base=config.parameters.recovery,
                            mode="hazard",
                            time_unit="day",
                            parameter="recovery",
                        ),
                    ),
                ],
            )
        ],
        actions=[
            ActionDefinition(
                id="routine",
                probability=ProbabilitySpec(base=1, time_unit="hour"),
                duration_minutes=60,
                priority=0,
                meaningful=False,
                loser_outcome="continues",
            )
        ],
        roles=[RoleDefinition(id="citizen", actions=["routine"])],
        default_states=[
            DefaultDefinition(
                id="age",
                distribution=Distribution(
                    values={"20": 0.25, "35": 0.25, "50": 0.25, "65": 0.25},
                    provenance=default_evidence,
                ),
            ),
            DefaultDefinition(
                id="has_friend",
                distribution=Distribution(
                    values={"yes": 0.99, "no": 0.01}, provenance=default_evidence
                ),
            ),
        ],
        behaviour_bundles=[
            BehaviourBundle(
                id="human",
                layer=0,
                values={"trust": 0.5, "compliance": 0.5},
                provenance=default_evidence,
            )
        ],
        events=[
            EventDefinition(
                id="state-rise",
                metric="infected",
                threshold=max(50, config.parameters.initial_infected * 2),
                direction="above",
            )
        ],
        tick=TickConfig(
            tick_hours=24,
            total_ticks=config.end_day - config.start_day,
            snapshot_every_hours=24,
            story_every_days=7,
        ),
        outputs=OutputSpec(),
        population=PopulationReference(
            id="FAKE-compatibility-population",
            version="FAKE-population-v1",
            size=min(sum(place_populations.values()), 4000),
            places=list(config.countries),
            place_populations=place_populations,
            place_coordinates=place_coordinates,
            initial_state_overrides=overrides,
        ),
    )
