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
      event = disruption

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
      event = disruption

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
      event = disruption

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
      event = disruption

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
      event = disruption

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
      event = disruption

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
      event = disruption
