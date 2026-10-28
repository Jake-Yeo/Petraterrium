program CachedHierarchy version "1.0":
  tick_hours = 24 placeholder
  placeholder = "placeholder — agent knowledge, for demo only, to be replaced by research"
  uncertainty = wide
  record_actions = true
  results_title = "Cached hierarchy"
  results_subtitle = "Synthetic composition cache"

output overview:
  title = "Overview"
  group_by = all
  display = cards
  record = final
  column population = count() label "Population" format integer
  column mean_income = mean(money) label "Income" format number
  column mean_stress = mean(stress) label "Stress" format decimal
  column vote_share = mean(vote) label "Vote" format decimal
  column fights_per_day = action_count(fights, window=day) label "Fights" format integer

place Shared:
  state activity = 0 range 0..100000 placeholder

agent Person:
  trait vote
  state money range 0..1000 placeholder
  state stress range 0..1 placeholder
  state location
  initial:
    vote ~ Uniform(min=0.5, max=0.5) placeholder
    money ~ Uniform(min=25, max=25) placeholder
    stress ~ Uniform(min=0.25, max=0.25) placeholder
    location ~ Categorical(Shared: 1.0) placeholder
  routine = meet

population:
  size = 1 placeholder
  mix:
    Person = 1.0 placeholder

decision meet:
  branch interact p = 1 placeholder

action interact:
  aggregate = fights
  target = random at Shared where agent != self
  duration = Triangular(min=0.1, median=0.2, max=0.3) placeholder
  outcome met p = 1 placeholder:
    effect relationship with target trust += 1 placeholder
    effect place Shared activity += 1 placeholder
    next = meet

archetype TypeA:
  sample_households = 5
  composition:
    members count = 1 mix Person:1.0
  initial:
    vote ~ Uniform(min=0.8, max=0.8)
    money ~ Uniform(min=10, max=10)
    stress ~ Uniform(min=0.2, max=0.2)
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)

archetype TypeB:
  sample_households = 5
  composition:
    members count = 1 mix Person:1.0
  initial:
    vote ~ Uniform(min=0.6, max=0.6)
    money ~ Uniform(min=20, max=20)
    stress ~ Uniform(min=0.3, max=0.3)
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)

archetype TypeC:
  sample_households = 5
  composition:
    members count = 1 mix Person:1.0
  initial:
    vote ~ Uniform(min=0.4, max=0.4)
    money ~ Uniform(min=30, max=30)
    stress ~ Uniform(min=0.4, max=0.4)
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)

archetype TypeD:
  sample_households = 5
  composition:
    members count = 1 mix Person:1.0
  initial:
    vote ~ Uniform(min=0.2, max=0.2)
    money ~ Uniform(min=40, max=40)
    stress ~ Uniform(min=0.5, max=0.5)
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)

composition NorthOne:
  level = synthetic_neighbourhood
  children:
    TypeA: weight = 1
  places = Shared
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)

composition NorthTwo:
  level = synthetic_neighbourhood
  children:
    TypeB: weight = 1
  places = Shared
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)

composition SouthOne:
  level = synthetic_neighbourhood
  children:
    TypeC: weight = 1
  places = Shared
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)

composition SouthTwo:
  level = synthetic_neighbourhood
  children:
    TypeD: weight = 1
  places = Shared
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)

composition MetroNorth:
  level = synthetic_municipality
  children:
    NorthOne: weight = 2
    NorthTwo: weight = 3
  places = Shared
  parameters:
    tax = 0.25
  adjacency:
    NorthOne <-> NorthTwo distance = 1
  flows:
    commute NorthOne -> NorthTwo rate = formula(clamp(0.20 + unemployment * 0.20 + tax * 0.10 + NorthTwo_mean_stress * 0.05, 0, 0.60)) effect = visit via Shared
    migration NorthTwo -> NorthOne rate = formula(clamp(0.01 + unemployment * 0.04, 0, 0.20)) effect = transfer
  cached:
    sync = 1 days
    max_iterations = 5
    tolerance = 0.01
    feedback:
      mean_stress -> unemployment scale = 0.20
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)
  output commuting_rate = flow_rate(commute)
  output migration_rate = flow_rate(migration)

composition MetroSouth:
  level = synthetic_municipality
  children:
    SouthOne: weight = 1
    SouthTwo: weight = 1
  places = Shared
  parameters:
    tax = 0.25
  adjacency:
    SouthOne <-> SouthTwo distance = 1
  flows:
    commute SouthOne -> SouthTwo rate = formula(clamp(0.15 + unemployment * 0.10 + tax * 0.05, 0, 0.50)) effect = visit via Shared
    migration SouthTwo -> SouthOne rate = formula(clamp(0.01 + unemployment * 0.03, 0, 0.20)) effect = transfer
  cached:
    sync = 1 days
    max_iterations = 5
    tolerance = 0.01
    feedback:
      mean_stress -> unemployment scale = 0.20
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)
  output commuting_rate = flow_rate(commute)
  output migration_rate = flow_rate(migration)

composition Province:
  level = synthetic_division
  children:
    MetroNorth: weight = 3
    MetroSouth: weight = 1
  places = Shared
  parameters:
    tax = 0.25
  adjacency:
    MetroNorth <-> MetroSouth distance = 2
  flows:
    division_visit MetroNorth -> MetroSouth rate = formula(clamp(0.10 + unemployment * 0.10 + tax * 0.04, 0, 0.40)) effect = visit via Shared
    division_transfer MetroSouth -> MetroNorth rate = formula(clamp(0.01 + unemployment * 0.02, 0, 0.10)) effect = transfer
  cached:
    sync = 1 days
    max_iterations = 5
    tolerance = 0.01
    feedback:
      mean_stress -> unemployment scale = 0.15
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)
  output commuting_rate = flow_rate(division_visit)
  output migration_rate = flow_rate(division_transfer)

aggregate_function NorthOne:
  inputs:
    unemployment = 0.10 range 0.00..1.00
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - unemployment * 0.10
    field stress += unemployment * 0.10
  outputs:
    population = formula(unemployment)
    mean_income = formula(unemployment)
    mean_stress = formula(unemployment)
    vote_share = formula(unemployment)
    fights_per_day = formula(unemployment)
  cache:
    valid_for = 30 days
    inputs_hash = hash(unemployment)
    invalidate_on:
      unemployment change > 0.10
      event = disruption, pandemic

aggregate_function NorthTwo:
  inputs:
    unemployment = 0.10 range 0.00..1.00
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - unemployment * 0.10
    field stress += unemployment * 0.10
  outputs:
    population = formula(unemployment)
    mean_income = formula(unemployment)
    mean_stress = formula(unemployment)
    vote_share = formula(unemployment)
    fights_per_day = formula(unemployment)
  cache:
    valid_for = 30 days
    inputs_hash = hash(unemployment)
    invalidate_on:
      unemployment change > 0.10
      event = disruption, pandemic

aggregate_function SouthOne:
  inputs:
    unemployment = 0.10 range 0.00..1.00
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - unemployment * 0.10
    field stress += unemployment * 0.10
  outputs:
    population = formula(unemployment)
    mean_income = formula(unemployment)
    mean_stress = formula(unemployment)
    vote_share = formula(unemployment)
    fights_per_day = formula(unemployment)
  cache:
    valid_for = 30 days
    inputs_hash = hash(unemployment)
    invalidate_on:
      unemployment change > 0.10
      event = disruption, pandemic

aggregate_function SouthTwo:
  inputs:
    unemployment = 0.10 range 0.00..1.00
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - unemployment * 0.10
    field stress += unemployment * 0.10
  outputs:
    population = formula(unemployment)
    mean_income = formula(unemployment)
    mean_stress = formula(unemployment)
    vote_share = formula(unemployment)
    fights_per_day = formula(unemployment)
  cache:
    valid_for = 30 days
    inputs_hash = hash(unemployment)
    invalidate_on:
      unemployment change > 0.10
      event = disruption, pandemic

aggregate_function MetroNorth:
  inputs:
    unemployment = 0.10 range 0.00..1.00
    tax = 0.25 range 0.00..1.00
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - tax * 0.10
  outputs:
    population = formula(unemployment, tax)
    mean_income = formula(unemployment, tax)
    mean_stress = formula(unemployment, tax)
    vote_share = formula(unemployment, tax)
    fights_per_day = formula(unemployment, tax)
    commuting_rate = formula(unemployment, tax)
    migration_rate = formula(unemployment, tax)
  cache:
    valid_for = 30 days
    inputs_hash = hash(unemployment, tax)
    invalidate_on:
      unemployment change > 0.10
      tax change > 0.05
      event = disruption, pandemic

aggregate_function MetroSouth:
  inputs:
    unemployment = 0.10 range 0.00..1.00
    tax = 0.25 range 0.00..1.00
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - tax * 0.10
  outputs:
    population = formula(unemployment, tax)
    mean_income = formula(unemployment, tax)
    mean_stress = formula(unemployment, tax)
    vote_share = formula(unemployment, tax)
    fights_per_day = formula(unemployment, tax)
    commuting_rate = formula(unemployment, tax)
    migration_rate = formula(unemployment, tax)
  cache:
    valid_for = 30 days
    inputs_hash = hash(unemployment, tax)
    invalidate_on:
      unemployment change > 0.10
      tax change > 0.05
      event = disruption, pandemic

aggregate_function Province:
  inputs:
    unemployment = 0.10 range 0.00..1.00
    tax = 0.25 range 0.00..1.00
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - tax * 0.10
  outputs:
    population = formula(unemployment, tax)
    mean_income = formula(unemployment, tax)
    mean_stress = formula(unemployment, tax)
    vote_share = formula(unemployment, tax)
    fights_per_day = formula(unemployment, tax)
    commuting_rate = formula(unemployment, tax)
    migration_rate = formula(unemployment, tax)
  cache:
    valid_for = 30 days
    inputs_hash = hash(unemployment, tax)
    invalidate_on:
      unemployment change > 0.10
      tax change > 0.05
      event = disruption, pandemic

archetype GenericFederation:
  level = country
  child_level = synthetic_division
  parameters:
    tax = 0.25
    federal_strength = 0.70
  output mean_income = mean(money) with sd
  output vote_share = mean(vote) with sd

composition ProvinceAlt:
  level = synthetic_division
  children:
    MetroNorth: weight = 1
    MetroSouth: weight = 3
  places = Shared
  parameters:
    tax = 0.30
    unemployment = 0.12
  adjacency:
    MetroNorth <-> MetroSouth distance = 1
  flows:
    division_exchange MetroNorth -> MetroSouth rate = formula(clamp(0.05 + tax * 0.10, 0, 0.30)) effect = exchange
    division_migration MetroSouth -> MetroNorth rate = formula(clamp(0.01 + unemployment * 0.05, 0, 0.10)) effect = transfer
  cached:
    sync = 5 days
    max_iterations = 1
    tolerance = 0.01
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)
  output trade_balance = flow_count(division_exchange)
  output migration_rate = flow_rate(division_migration)

composition ProvinceB:
  level = synthetic_division
  children:
    MetroNorth: weight = 3
    MetroSouth: weight = 1
  places = Shared
  parameters:
    tax = 0.30
    unemployment = 0.12
    division_policy = 0.10
  adjacency:
    MetroNorth <-> MetroSouth distance = 1
  flows:
    division_exchange MetroNorth -> MetroSouth rate = formula(clamp(0.05 + tax * 0.10, 0, 0.30)) effect = exchange
    division_migration MetroSouth -> MetroNorth rate = formula(clamp(0.01 + unemployment * 0.05, 0, 0.10)) effect = transfer
  cached:
    sync = 5 days
    max_iterations = 1
    tolerance = 0.01
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)
  output trade_balance = flow_count(division_exchange)
  output migration_rate = flow_rate(division_migration)

composition ProvinceBAlt:
  level = synthetic_division
  children:
    MetroNorth: weight = 1
    MetroSouth: weight = 3
  places = Shared
  parameters:
    tax = 0.30
    unemployment = 0.12
  adjacency:
    MetroNorth <-> MetroSouth distance = 1
  flows:
    division_exchange MetroNorth -> MetroSouth rate = formula(clamp(0.05 + tax * 0.10, 0, 0.30)) effect = exchange
    division_migration MetroSouth -> MetroNorth rate = formula(clamp(0.01 + unemployment * 0.05, 0, 0.10)) effect = transfer
  cached:
    sync = 5 days
    max_iterations = 1
    tolerance = 0.01
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)
  output trade_balance = flow_count(division_exchange)
  output migration_rate = flow_rate(division_migration)

composition ProvinceF:
  level = synthetic_division
  children:
    MetroNorth: weight = 2
    MetroSouth: weight = 1
  places = Shared
  parameters:
    tax = 0.30
    unemployment = 0.12
  adjacency:
    MetroNorth <-> MetroSouth distance = 1
  flows:
    division_exchange MetroNorth -> MetroSouth rate = formula(clamp(0.05 + tax * 0.10, 0, 0.30)) effect = exchange
    division_migration MetroSouth -> MetroNorth rate = formula(clamp(0.01 + unemployment * 0.05, 0, 0.10)) effect = transfer
  cached:
    sync = 5 days
    max_iterations = 1
    tolerance = 0.01
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)
  output trade_balance = flow_count(division_exchange)
  output migration_rate = flow_rate(division_migration)

composition ProvinceFAlt:
  level = synthetic_division
  children:
    MetroNorth: weight = 1
    MetroSouth: weight = 2
  places = Shared
  parameters:
    tax = 0.30
    unemployment = 0.12
  adjacency:
    MetroNorth <-> MetroSouth distance = 1
  flows:
    division_exchange MetroNorth -> MetroSouth rate = formula(clamp(0.05 + tax * 0.10, 0, 0.30)) effect = exchange
    division_migration MetroSouth -> MetroNorth rate = formula(clamp(0.01 + unemployment * 0.05, 0, 0.10)) effect = transfer
  cached:
    sync = 5 days
    max_iterations = 1
    tolerance = 0.01
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)
  output trade_balance = flow_count(division_exchange)
  output migration_rate = flow_rate(division_migration)

composition NationA:
  level = country
  template = GenericFederation
  represented_population = 60000000
  children:
    Province: weight = 60
    ProvinceAlt: weight = 40
  places = Shared
  parameters:
    tax = 0.20
    unemployment = 0.08
    tariff = 0.05
    border_policy = 0.70
    infection_rate = 0.03
    infection_modifier = 0.80
  adjacency:
    Province <-> ProvinceAlt distance = 1
  flows:
    country_exchange Province -> ProvinceAlt rate = formula(clamp(0.10 + Province_mean_income / 1000 - tariff * 0.20, 0, 0.60)) effect = exchange
    country_migration ProvinceAlt -> Province rate = formula(clamp(0.01 + unemployment * 0.10 - border_policy * 0.01, 0, 0.12)) effect = transfer
  cached:
    sync = 30 days
    max_iterations = 2
    tolerance = 0.01
    feedback:
      mean_stress -> unemployment scale = 0.20
  output population = count()
  output represented_population = represented_count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)
  output trade_balance = flow_count(country_exchange)
  output migration_rate = flow_rate(country_migration)
  output gdp_proxy = sum(money)

composition NationB:
  level = country
  template = GenericFederation
  represented_population = 40000000
  children:
    ProvinceB: weight = 20
    ProvinceBAlt: weight = 80
  places = Shared
  parameters:
    tax = 0.35
    unemployment = 0.04
    tariff = 0.20
    border_policy = 0.85
    infection_rate = 0.06
    infection_modifier = 0.55
  adjacency:
    ProvinceB <-> ProvinceBAlt distance = 1
  flows:
    country_exchange ProvinceB -> ProvinceBAlt rate = formula(clamp(0.10 + ProvinceB_mean_income / 1000 - tariff * 0.20, 0, 0.60)) effect = exchange
    country_migration ProvinceBAlt -> ProvinceB rate = formula(clamp(0.01 + unemployment * 0.10 - border_policy * 0.01, 0, 0.12)) effect = transfer
  cached:
    sync = 30 days
    max_iterations = 2
    tolerance = 0.01
    feedback:
      mean_stress -> unemployment scale = 0.20
  output population = count()
  output represented_population = represented_count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)
  output trade_balance = flow_count(country_exchange)
  output migration_rate = flow_rate(country_migration)
  output gdp_proxy = sum(money)

composition FictionalNation:
  level = country
  template = GenericFederation
  represented_population = 10000000
  children:
    ProvinceF: weight = 50
    ProvinceFAlt: weight = 50
  places = Shared
  parameters:
    tax = 0.28
    unemployment = 0.10
    tariff = 0.10
    border_policy = 0.60
    infection_rate = 0.02
    infection_modifier = 0.90
  adjacency:
    ProvinceF <-> ProvinceFAlt distance = 1
  flows:
    country_exchange ProvinceF -> ProvinceFAlt rate = formula(clamp(0.10 + ProvinceF_mean_income / 1000 - tariff * 0.20, 0, 0.60)) effect = exchange
    country_migration ProvinceFAlt -> ProvinceF rate = formula(clamp(0.01 + unemployment * 0.10 - border_policy * 0.01, 0, 0.12)) effect = transfer
  cached:
    sync = 30 days
    max_iterations = 2
    tolerance = 0.01
    feedback:
      mean_stress -> unemployment scale = 0.20
  output population = count()
  output represented_population = represented_count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)
  output trade_balance = flow_count(country_exchange)
  output migration_rate = flow_rate(country_migration)
  output gdp_proxy = sum(money)

composition TestWorld:
  level = world
  represented_population = 100000000
  children:
    NationA: weight = 60
    NationB: weight = 40
  places = Shared
  parameters:
    tax = 0.25
    unemployment = 0.06
    tariff = 0.10
    border_policy = 0.75
    infection_rate = 0.05
    global_policy = 0.70
  adjacency:
    NationA <-> NationB distance = 1
  flows:
    trade_a_b NationA -> NationB rate = formula(clamp(0.08 + NationA_gdp_proxy / 10000 + NationB_gdp_proxy / 10000 - tariff * 0.25, 0, 0.70)) effect = exchange
    migration_a_b NationA -> NationB rate = formula(clamp(0.01 + NationB_mean_income / 1000 - NationB_unemployment * 0.10 - border_policy * 0.01, 0, 0.20)) effect = transfer
    travel_a_b NationA -> NationB rate = formula(clamp(0.04 + global_policy * 0.04, 0, 0.20)) effect = visit via Shared
    infection_a_b NationA -> NationB rate = formula(clamp(travel_a_b * infection_rate * NationA_infection_modifier, 0, 0.20)) effect = infection
    policy_a_b NationA -> NationB rate = formula(clamp(global_policy * 0.10 + NationA_vote_share * 0.05, 0, 0.20)) effect = diffusion
  cached:
    sync = 90 days
    max_iterations = 5
    tolerance = 0.01
    feedback:
      mean_stress -> unemployment scale = 0.15
  output population = count()
  output represented_population = represented_count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)
  output trade_balance = flow_count(trade_a_b)
  output migration_rate = flow_rate(migration_a_b)
  output infection_rate = flow_rate(infection_a_b)
  output gdp_proxy = sum(money)

composition NetworkWorld:
  level = world
  children:
    NationA: weight = 40
    NationB: weight = 40
    FictionalNation: weight = 20
  places = Shared
  parameters:
    tax = 0.25
    unemployment = 0.06
    tariff = 0.10
    border_policy = 0.75
    infection_rate = 0.05
  adjacency:
    NationA <-> NationB distance = 1
    NationB <-> FictionalNation distance = 2
  flows:
    adjacent_trade NationA -> NationB rate = formula(clamp(0.10 - tariff * 0.20, 0, 0.40)) effect = exchange
  cached:
    sync = 90 days
    max_iterations = 2
    tolerance = 0.01
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output fights_per_day = action_count(fights, window=day)
  output trade_balance = flow_count(adjacent_trade)

composition_population HundredMillionWorld:
  TestWorld: represented = 100000000

aggregate_function ProvinceAlt:
  inputs:
    tax = 0.25 range 0..1
    unemployment = 0.06 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - tax * 0.10
    field stress += unemployment * 0.10
  outputs:
    population = formula(tax, unemployment)
    mean_income = formula(tax, unemployment)
    mean_stress = formula(tax, unemployment)
    vote_share = formula(tax, unemployment)
    fights_per_day = formula(tax, unemployment)
    trade_balance = formula(tax, unemployment)
    migration_rate = formula(tax, unemployment)
  cache:
    valid_for = 30 days
    inputs_hash = hash(tax, unemployment)
    invalidate_on:
      tax change > 0.10
      unemployment change > 0.10
      event = disruption, pandemic, sanctions

aggregate_function NationA:
  inputs:
    tax = 0.25 range 0..1
    unemployment = 0.06 range 0..1
    tariff = 0.1 range 0..1
    border_policy = 0.75 range 0..1
    infection_rate = 0.05 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - tax * 0.10
    field stress += unemployment * 0.10 + infection_rate * 0.05
  outputs:
    population = formula(tax, unemployment, tariff, border_policy, infection_rate)
    represented_population = formula(tax, unemployment, tariff, border_policy, infection_rate)
    mean_income = formula(tax, unemployment, tariff, border_policy, infection_rate)
    mean_stress = formula(tax, unemployment, tariff, border_policy, infection_rate)
    vote_share = formula(tax, unemployment, tariff, border_policy, infection_rate)
    fights_per_day = formula(tax, unemployment, tariff, border_policy, infection_rate)
    trade_balance = formula(tax, unemployment, tariff, border_policy, infection_rate)
    migration_rate = formula(tax, unemployment, tariff, border_policy, infection_rate)
    gdp_proxy = formula(tax, unemployment, tariff, border_policy, infection_rate)
  cache:
    valid_for = 90 days
    inputs_hash = hash(tax, unemployment, tariff, border_policy, infection_rate)
    invalidate_on:
      tax change > 0.10
      unemployment change > 0.10
      tariff change > 0.10
      border_policy change > 0.10
      infection_rate change > 0.10
      event = disruption, pandemic, sanctions

aggregate_function NationB:
  inputs:
    tax = 0.25 range 0..1
    unemployment = 0.06 range 0..1
    tariff = 0.1 range 0..1
    border_policy = 0.75 range 0..1
    infection_rate = 0.05 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - tax * 0.10
    field stress += unemployment * 0.10 + infection_rate * 0.05
  outputs:
    population = formula(tax, unemployment, tariff, border_policy, infection_rate)
    represented_population = formula(tax, unemployment, tariff, border_policy, infection_rate)
    mean_income = formula(tax, unemployment, tariff, border_policy, infection_rate)
    mean_stress = formula(tax, unemployment, tariff, border_policy, infection_rate)
    vote_share = formula(tax, unemployment, tariff, border_policy, infection_rate)
    fights_per_day = formula(tax, unemployment, tariff, border_policy, infection_rate)
    trade_balance = formula(tax, unemployment, tariff, border_policy, infection_rate)
    migration_rate = formula(tax, unemployment, tariff, border_policy, infection_rate)
    gdp_proxy = formula(tax, unemployment, tariff, border_policy, infection_rate)
  cache:
    valid_for = 90 days
    inputs_hash = hash(tax, unemployment, tariff, border_policy, infection_rate)
    invalidate_on:
      tax change > 0.10
      unemployment change > 0.10
      tariff change > 0.10
      border_policy change > 0.10
      infection_rate change > 0.10
      event = disruption, pandemic, sanctions

aggregate_function FictionalNation:
  inputs:
    tax = 0.25 range 0..1
    unemployment = 0.06 range 0..1
    tariff = 0.1 range 0..1
    border_policy = 0.75 range 0..1
    infection_rate = 0.05 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - tax * 0.10
    field stress += unemployment * 0.10 + infection_rate * 0.05
  outputs:
    population = formula(tax, unemployment, tariff, border_policy, infection_rate)
    represented_population = formula(tax, unemployment, tariff, border_policy, infection_rate)
    mean_income = formula(tax, unemployment, tariff, border_policy, infection_rate)
    mean_stress = formula(tax, unemployment, tariff, border_policy, infection_rate)
    vote_share = formula(tax, unemployment, tariff, border_policy, infection_rate)
    fights_per_day = formula(tax, unemployment, tariff, border_policy, infection_rate)
    trade_balance = formula(tax, unemployment, tariff, border_policy, infection_rate)
    migration_rate = formula(tax, unemployment, tariff, border_policy, infection_rate)
    gdp_proxy = formula(tax, unemployment, tariff, border_policy, infection_rate)
  cache:
    valid_for = 90 days
    inputs_hash = hash(tax, unemployment, tariff, border_policy, infection_rate)
    invalidate_on:
      tax change > 0.10
      unemployment change > 0.10
      tariff change > 0.10
      border_policy change > 0.10
      infection_rate change > 0.10
      event = disruption, pandemic, sanctions

aggregate_function TestWorld:
  inputs:
    tax = 0.25 range 0..1
    unemployment = 0.06 range 0..1
    tariff = 0.1 range 0..1
    border_policy = 0.75 range 0..1
    infection_rate = 0.05 range 0..1
    global_policy = 0.7 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - tax * 0.10
    field stress += unemployment * 0.10 + infection_rate * 0.05
  outputs:
    population = formula(tax, unemployment, tariff, border_policy, infection_rate, global_policy)
    represented_population = formula(tax, unemployment, tariff, border_policy, infection_rate, global_policy)
    mean_income = formula(tax, unemployment, tariff, border_policy, infection_rate, global_policy)
    mean_stress = formula(tax, unemployment, tariff, border_policy, infection_rate, global_policy)
    vote_share = formula(tax, unemployment, tariff, border_policy, infection_rate, global_policy)
    fights_per_day = formula(tax, unemployment, tariff, border_policy, infection_rate, global_policy)
    trade_balance = formula(tax, unemployment, tariff, border_policy, infection_rate, global_policy)
    migration_rate = formula(tax, unemployment, tariff, border_policy, infection_rate, global_policy)
    infection_rate = formula(tax, unemployment, tariff, border_policy, infection_rate, global_policy)
    gdp_proxy = formula(tax, unemployment, tariff, border_policy, infection_rate, global_policy)
  cache:
    valid_for = 90 days
    inputs_hash = hash(tax, unemployment, tariff, border_policy, infection_rate, global_policy)
    invalidate_on:
      tax change > 0.10
      unemployment change > 0.10
      tariff change > 0.10
      border_policy change > 0.10
      infection_rate change > 0.10
      global_policy change > 0.10
      event = disruption, pandemic, sanctions

aggregate_function NetworkWorld:
  inputs:
    tax = 0.25 range 0..1
    unemployment = 0.06 range 0..1
    tariff = 0.1 range 0..1
    border_policy = 0.75 range 0..1
    infection_rate = 0.05 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - tax * 0.10
    field stress += unemployment * 0.10 + infection_rate * 0.05
  outputs:
    population = formula(tax, unemployment, tariff, border_policy, infection_rate)
    mean_income = formula(tax, unemployment, tariff, border_policy, infection_rate)
    mean_stress = formula(tax, unemployment, tariff, border_policy, infection_rate)
    vote_share = formula(tax, unemployment, tariff, border_policy, infection_rate)
    fights_per_day = formula(tax, unemployment, tariff, border_policy, infection_rate)
    trade_balance = formula(tax, unemployment, tariff, border_policy, infection_rate)
  cache:
    valid_for = 90 days
    inputs_hash = hash(tax, unemployment, tariff, border_policy, infection_rate)
    invalidate_on:
      tax change > 0.10
      unemployment change > 0.10
      tariff change > 0.10
      border_policy change > 0.10
      infection_rate change > 0.10
      event = disruption, pandemic, sanctions
aggregate_function ProvinceB:
  inputs:
    tax = 0.25 range 0..1
    unemployment = 0.06 range 0..1
    division_policy = 0.10 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - tax * 0.10
    field money *= 1 - division_policy * 0.01
    field stress += unemployment * 0.10
  outputs:
    population = formula(tax, unemployment, division_policy)
    mean_income = formula(tax, unemployment, division_policy)
    mean_stress = formula(tax, unemployment, division_policy)
    vote_share = formula(tax, unemployment, division_policy)
    fights_per_day = formula(tax, unemployment, division_policy)
    trade_balance = formula(tax, unemployment, division_policy)
    migration_rate = formula(tax, unemployment, division_policy)
  cache:
    valid_for = 30 days
    inputs_hash = hash(tax, unemployment, division_policy)
    invalidate_on:
      tax change > 0.10
      unemployment change > 0.10
      division_policy change > 0.10
      event = disruption, pandemic

aggregate_function ProvinceBAlt:
  inputs:
    tax = 0.25 range 0..1
    unemployment = 0.06 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - tax * 0.10
    field stress += unemployment * 0.10
  outputs:
    population = formula(tax, unemployment)
    mean_income = formula(tax, unemployment)
    mean_stress = formula(tax, unemployment)
    vote_share = formula(tax, unemployment)
    fights_per_day = formula(tax, unemployment)
    trade_balance = formula(tax, unemployment)
    migration_rate = formula(tax, unemployment)
  cache:
    valid_for = 30 days
    inputs_hash = hash(tax, unemployment)
    invalidate_on:
      tax change > 0.10
      unemployment change > 0.10
      event = disruption, pandemic

aggregate_function ProvinceF:
  inputs:
    tax = 0.25 range 0..1
    unemployment = 0.06 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - tax * 0.10
    field stress += unemployment * 0.10
  outputs:
    population = formula(tax, unemployment)
    mean_income = formula(tax, unemployment)
    mean_stress = formula(tax, unemployment)
    vote_share = formula(tax, unemployment)
    fights_per_day = formula(tax, unemployment)
    trade_balance = formula(tax, unemployment)
    migration_rate = formula(tax, unemployment)
  cache:
    valid_for = 30 days
    inputs_hash = hash(tax, unemployment)
    invalidate_on:
      tax change > 0.10
      unemployment change > 0.10
      event = disruption, pandemic

aggregate_function ProvinceFAlt:
  inputs:
    tax = 0.25 range 0..1
    unemployment = 0.06 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  effects:
    field money *= 1 - tax * 0.10
    field stress += unemployment * 0.10
  outputs:
    population = formula(tax, unemployment)
    mean_income = formula(tax, unemployment)
    mean_stress = formula(tax, unemployment)
    vote_share = formula(tax, unemployment)
    fights_per_day = formula(tax, unemployment)
    trade_balance = formula(tax, unemployment)
    migration_rate = formula(tax, unemployment)
  cache:
    valid_for = 30 days
    inputs_hash = hash(tax, unemployment)
    invalidate_on:
      tax change > 0.10
      unemployment change > 0.10
      event = disruption, pandemic

