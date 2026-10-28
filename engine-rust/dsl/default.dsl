program PetraterriumTown version "1.0":
  tick_hours = 1 placeholder
  placeholder = "placeholder — agent knowledge, for demo only, to be replaced by research"
  uncertainty = wide
  record_actions = false
  results_title = "Recorded Rust output"
  results_subtitle = "DSL-defined small-group statistics"

output overview:
  title = "Town overview"
  group_by = all
  display = cards
  record = final
  column population = count() label "Population" format integer
  column money = mean(money) label "Mean money" format number
  column health = mean(health) label "Mean health" format decimal
  column stress = mean(stress) label "Mean stress" format decimal
  column fights = action_count(fights, window=day) label "Fights / day" format integer

output places:
  title = "Places"
  group_by = place
  display = table
  record = daily
  column population = count() label "Population" format integer
  column money = mean(money) label "Money" format number
  column health = mean(health) label "Health" format decimal
  column stress = mean(stress) label "Stress" format decimal
  column fights = action_count(fights, window=day) label "Fights / day" format integer
  column family_size = family_size() label "Family size" format decimal
  column kids = kids_per_family() label "Kids / family" format decimal
  column actions = action_rates(per=1000, window=day) label "Action rates / 1,000" format action_rates

output agent_types:
  title = "Agent types"
  group_by = agent_type
  display = table
  record = daily
  column population = count() label "Population" format integer
  column money = mean(money) label "Money" format number
  column health = mean(health) label "Health" format decimal
  column stress = mean(stress) label "Stress" format decimal
  column actions = action_rates(per=1000, window=day) label "Action rates / 1,000" format action_rates

place Home:
  state comfort = 0.8 range 0..1 placeholder
  state chaos = 0.0 range 0..1 placeholder

place Work:
  state productivity = 0.7 range 0..1 placeholder
  state chaos = 0.1 range 0..1 placeholder

place School:
  state learning = 0.8 range 0..1 placeholder
  state chaos = 0.1 range 0..1 placeholder

place Bar:
  state crowd = 0.5 range 0..1 placeholder
  state chaos = 0.2 range 0..1 placeholder

place Cinema:
  state crowd = 0.4 range 0..1 placeholder
  state enjoyment = 0.7 range 0..1 placeholder

agent Person:
  trait age
  trait aggression
  trait has_family
  trait has_spouse
  trait kids
  state health range 0..1 placeholder
  state stress range 0..1 placeholder
  state alcohol range 0..1 placeholder
  state money range 0..100000 placeholder
  state reputation range 0..1 placeholder
  state location
  initial:
    age ~ Normal(mean=38, sd=14, min=18, max=80) placeholder
    aggression ~ Beta(alpha=2, beta=5) placeholder
    health ~ Normal(mean=0.82, sd=0.12, min=0, max=1) placeholder
    stress ~ Normal(mean=0.42, sd=0.18, min=0, max=1) placeholder
    money ~ LogNormal(mean=7.5, sd=0.7, min=0, max=100000) placeholder
    has_family ~ Bernoulli(p=clamp((age - 20) / 45, 0, 0.82)) placeholder
    has_spouse ~ Bernoulli(p=0.72 if has_family else 0.0) placeholder
    kids ~ Poisson(lambda=clamp((age - 24) / 18, 0, 2.8) if has_family else 0, cap=5) placeholder
    alcohol ~ Uniform(min=0, max=0.15) placeholder
    reputation ~ Normal(mean=0.5, sd=0.12, min=0, max=1) placeholder
    location ~ Categorical(Home: 1.0) placeholder
  routine = where_to_go

agent Student inherits Person:
  role student
  initial:
    age ~ Normal(mean=20, sd=3, min=18, max=28) placeholder

agent Worker inherits Person:
  role worker

agent WorkingStudent inherits Student:
  role worker

agent Child inherits Person:
  role child
  initial:
    age ~ Uniform(min=0, max=17) placeholder

population:
  size = 100 placeholder
  mix:
    Student = 0.4 placeholder
    Worker = 0.6 placeholder
  households:
    generate children where kids > 0:
      count = kids
      age ~ Uniform(min=0, max=max(0, age - 18)) placeholder
      type = Student if age > 5 else Child
      link = parent, household

archetype HouseholdLiberalUrban:
  sample_households = 20
  composition:
    adults count = 2 mix Worker:0.65, Student:0.35
    children count = 1 mix Child:1.0
  initial:
    age ~ Normal(mean=34, sd=12, min=0, max=78)
    aggression ~ Beta(alpha=1.8, beta=5.8)
    health ~ Normal(mean=0.84, sd=0.10, min=0, max=1)
    stress ~ Normal(mean=0.48, sd=0.17, min=0, max=1)
    money ~ LogNormal(mean=7.65, sd=0.72, min=0, max=100000)
    vote_liberal ~ Bernoulli(p=0.76 if age >= 18 else 0.0)
    has_family ~ Bernoulli(p=clamp((age - 22) / 44, 0, 0.78))
    has_spouse ~ Bernoulli(p=0.66 if has_family else 0.0)
    kids ~ Poisson(lambda=clamp((age - 25) / 20, 0, 2.2) if has_family else 0, cap=5)
  decision go_bar multiplier = 1.20
  decision go_work multiplier = 0.95
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()

archetype HouseholdConservativeSuburban:
  sample_households = 20
  composition:
    adults count = 2 mix Worker:0.82, Student:0.18
    children count = 1 mix Child:1.0
  initial:
    age ~ Normal(mean=43, sd=13, min=0, max=82)
    aggression ~ Beta(alpha=2.1, beta=5.1)
    health ~ Normal(mean=0.80, sd=0.12, min=0, max=1)
    stress ~ Normal(mean=0.39, sd=0.15, min=0, max=1)
    money ~ LogNormal(mean=7.80, sd=0.65, min=0, max=100000)
    vote_liberal ~ Bernoulli(p=0.28 if age >= 18 else 0.0)
    has_family ~ Bernoulli(p=clamp((age - 20) / 38, 0, 0.88))
    has_spouse ~ Bernoulli(p=0.78 if has_family else 0.0)
    kids ~ Poisson(lambda=clamp((age - 23) / 17, 0, 2.9) if has_family else 0, cap=5)
  decision go_bar multiplier = 0.62
  decision go_work multiplier = 1.12
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()

archetype HouseholdRuralMixed:
  sample_households = 20
  composition:
    adults count = 2 mix Worker:0.74, Student:0.26
    children count = 1 mix Child:1.0
  initial:
    age ~ Normal(mean=40, sd=15, min=0, max=84)
    aggression ~ Beta(alpha=2.3, beta=4.8)
    health ~ Normal(mean=0.78, sd=0.14, min=0, max=1)
    stress ~ Normal(mean=0.35, sd=0.16, min=0, max=1)
    money ~ LogNormal(mean=7.30, sd=0.76, min=0, max=100000)
    vote_liberal ~ Bernoulli(p=0.47 if age >= 18 else 0.0)
    has_family ~ Bernoulli(p=clamp((age - 19) / 39, 0, 0.86))
    has_spouse ~ Bernoulli(p=0.72 if has_family else 0.0)
    kids ~ Poisson(lambda=clamp((age - 22) / 16, 0, 3.2) if has_family else 0, cap=5)
  decision go_bar multiplier = 0.82
  decision go_work multiplier = 1.04
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()

aggregate_function HouseholdLiberalUrban:
  inputs:
    policy_tax = 0.25 range 0.10..0.40
    media_trend = 0.00 range -1.00..1.00
    economic_shock = 0.00 range -0.20..0.20
    unemployment_national = 0.06 range 0.02..0.15
  time = 30 days
  time_points = 1, 7, 14, 30
  effects:
    field money *= 1 - policy_tax * 0.25 + economic_shock * 0.20
    field stress += economic_shock * 0.25 + unemployment_national * 0.30 - media_trend * 0.05
    field vote_liberal += media_trend * 0.15 - policy_tax * 0.05
    decision go_work *= 1 - unemployment_national
    decision go_bar *= 1 + media_trend * 0.10
  outputs:
    mean_income = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_stress = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    vote_liberal_share = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_health = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_kids_per_family = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    fights_per_day = formula(policy_tax, media_trend, economic_shock, unemployment_national) from action_count(fights, window=day)
  cache:
    valid_for = 30 days
    inputs_hash = hash(policy_tax, media_trend, economic_shock, unemployment_national)
    invalidate_on:
      policy_tax change > 0.05
      media_trend change > 0.20
      economic_shock change > 0.10
      unemployment_national change > 0.02
      event = disaster, pandemic, election

aggregate_function HouseholdConservativeSuburban:
  inputs:
    policy_tax = 0.25 range 0.10..0.40
    media_trend = 0.00 range -1.00..1.00
    economic_shock = 0.00 range -0.20..0.20
    unemployment_national = 0.06 range 0.02..0.15
  time = 30 days
  time_points = 1, 7, 14, 30
  effects:
    field money *= 1 - policy_tax * 0.22 + economic_shock * 0.18
    field stress += economic_shock * 0.22 + unemployment_national * 0.28 - media_trend * 0.03
    field vote_liberal += media_trend * 0.08 - policy_tax * 0.08
    decision go_work *= 1 - unemployment_national
    decision go_bar *= 1 + media_trend * 0.06
  outputs:
    mean_income = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_stress = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    vote_liberal_share = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_health = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_kids_per_family = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    fights_per_day = formula(policy_tax, media_trend, economic_shock, unemployment_national) from action_count(fights, window=day)
  cache:
    valid_for = 30 days
    inputs_hash = hash(policy_tax, media_trend, economic_shock, unemployment_national)
    invalidate_on:
      policy_tax change > 0.05
      media_trend change > 0.20
      economic_shock change > 0.10
      unemployment_national change > 0.02
      event = disaster, pandemic, election

aggregate_function HouseholdRuralMixed:
  inputs:
    policy_tax = 0.25 range 0.10..0.40
    media_trend = 0.00 range -1.00..1.00
    economic_shock = 0.00 range -0.20..0.20
    unemployment_national = 0.06 range 0.02..0.15
  time = 30 days
  time_points = 1, 7, 14, 30
  effects:
    field money *= 1 - policy_tax * 0.20 + economic_shock * 0.16
    field stress += economic_shock * 0.20 + unemployment_national * 0.25 - media_trend * 0.02
    field vote_liberal += media_trend * 0.10 - policy_tax * 0.06
    decision go_work *= 1 - unemployment_national
    decision go_bar *= 1 + media_trend * 0.08
  outputs:
    mean_income = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_stress = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    vote_liberal_share = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_health = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_kids_per_family = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    fights_per_day = formula(policy_tax, media_trend, economic_shock, unemployment_national) from action_count(fights, window=day)
  cache:
    valid_for = 30 days
    inputs_hash = hash(policy_tax, media_trend, economic_shock, unemployment_national)
    invalidate_on:
      policy_tax change > 0.05
      media_trend change > 0.20
      economic_shock change > 0.10
      unemployment_national change > 0.02
      event = disaster, pandemic, election

population TownHouseholds:
  HouseholdLiberalUrban: weight = 40
  HouseholdConservativeSuburban: weight = 35
  HouseholdRuralMixed: weight = 25

population CanadaHouseholds:
  HouseholdLiberalUrban: weight = 2800000
  HouseholdConservativeSuburban: weight = 3200000
  HouseholdRuralMixed: weight = 1900000

population SevenBillionHouseholds:
  HouseholdLiberalUrban: weight = 933333333
  HouseholdConservativeSuburban: weight = 816666667
  HouseholdRuralMixed: weight = 583333333

neighbourhood UrbanLiberal:
  households:
    HouseholdLiberalUrban: weight = 60
    HouseholdConservativeSuburban: weight = 20
    HouseholdRuralMixed: weight = 20
  places = Home, Work, School, Bar, Cinema
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()
  output fights_per_day = action_count(fights, window=day)

neighbourhood SuburbanMixed:
  households:
    HouseholdLiberalUrban: weight = 30
    HouseholdConservativeSuburban: weight = 50
    HouseholdRuralMixed: weight = 20
  places = Home, Work, School, Bar, Cinema
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()
  output fights_per_day = action_count(fights, window=day)

neighbourhood RuralMixed:
  households:
    HouseholdLiberalUrban: weight = 10
    HouseholdConservativeSuburban: weight = 30
    HouseholdRuralMixed: weight = 60
  places = Home, Work, School, Bar, Cinema
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()
  output fights_per_day = action_count(fights, window=day)

neighbourhood_population DemoNeighbourhoods:
  UrbanLiberal: weight = 100
  SuburbanMixed: weight = 100
  RuralMixed: weight = 100

aggregate_function UrbanLiberal:
  inputs:
    policy_tax = 0.25 range 0.10..0.40
    media_trend = 0.00 range -1.00..1.00
    economic_shock = 0.00 range -0.20..0.20
    unemployment_national = 0.06 range 0.02..0.15
  time = 30 days
  time_points = 1, 7, 14, 30
  effects:
    field money *= 1 - policy_tax * 0.24 + economic_shock * 0.20
    field stress += economic_shock * 0.24 + unemployment_national * 0.30 - media_trend * 0.05
    field vote_liberal += media_trend * 0.14 - policy_tax * 0.05
    decision go_work *= 1 - unemployment_national
    decision go_bar *= 1 + media_trend * 0.10
  outputs:
    mean_income = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_stress = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    vote_liberal_share = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_health = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_kids_per_family = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    fights_per_day = formula(policy_tax, media_trend, economic_shock, unemployment_national)
  cache:
    valid_for = 30 days
    inputs_hash = hash(policy_tax, media_trend, economic_shock, unemployment_national)
    invalidate_on:
      policy_tax change > 0.05
      media_trend change > 0.20
      economic_shock change > 0.10
      unemployment_national change > 0.02
      event = disaster, pandemic, election

aggregate_function SuburbanMixed:
  inputs:
    policy_tax = 0.25 range 0.10..0.40
    media_trend = 0.00 range -1.00..1.00
    economic_shock = 0.00 range -0.20..0.20
    unemployment_national = 0.06 range 0.02..0.15
  time = 30 days
  time_points = 1, 7, 14, 30
  effects:
    field money *= 1 - policy_tax * 0.22 + economic_shock * 0.18
    field stress += economic_shock * 0.22 + unemployment_national * 0.28 - media_trend * 0.04
    field vote_liberal += media_trend * 0.10 - policy_tax * 0.06
    decision go_work *= 1 - unemployment_national
    decision go_bar *= 1 + media_trend * 0.08
  outputs:
    mean_income = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_stress = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    vote_liberal_share = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_health = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_kids_per_family = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    fights_per_day = formula(policy_tax, media_trend, economic_shock, unemployment_national)
  cache:
    valid_for = 30 days
    inputs_hash = hash(policy_tax, media_trend, economic_shock, unemployment_national)
    invalidate_on:
      policy_tax change > 0.05
      media_trend change > 0.20
      economic_shock change > 0.10
      unemployment_national change > 0.02
      event = disaster, pandemic, election

aggregate_function RuralMixed:
  inputs:
    policy_tax = 0.25 range 0.10..0.40
    media_trend = 0.00 range -1.00..1.00
    economic_shock = 0.00 range -0.20..0.20
    unemployment_national = 0.06 range 0.02..0.15
  time = 30 days
  time_points = 1, 7, 14, 30
  effects:
    field money *= 1 - policy_tax * 0.20 + economic_shock * 0.16
    field stress += economic_shock * 0.20 + unemployment_national * 0.25 - media_trend * 0.02
    field vote_liberal += media_trend * 0.10 - policy_tax * 0.06
    decision go_work *= 1 - unemployment_national
    decision go_bar *= 1 + media_trend * 0.08
  outputs:
    mean_income = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_stress = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    vote_liberal_share = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_health = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    mean_kids_per_family = formula(policy_tax, media_trend, economic_shock, unemployment_national)
    fights_per_day = formula(policy_tax, media_trend, economic_shock, unemployment_national)
  cache:
    valid_for = 30 days
    inputs_hash = hash(policy_tax, media_trend, economic_shock, unemployment_national)
    invalidate_on:
      policy_tax change > 0.05
      media_trend change > 0.20
      economic_shock change > 0.10
      unemployment_national change > 0.02
      event = disaster, pandemic, election

decision where_to_go:
  branch go_work p = 0.70 if role.worker and hour >= 6 and hour < 10 placeholder
  branch go_school p = 0.78 if role.student and hour >= 6 and hour < 10 placeholder
  branch go_bar p = max(0.01, 0.20 + stress * 0.20) if age >= 18 and hour >= 17 placeholder
  branch go_cinema p = 0.12 if hour >= 17 placeholder
  branch stay_home p = max(0.01, 0.45 + stress * 0.20) placeholder

decision at_work:
  branch work p = 0.78 if hour < 17 placeholder
  branch talk_at_work p = 0.16 placeholder
  branch go_home p = 0.35 if hour >= 16 placeholder

decision at_school:
  branch study p = 0.82 if hour < 16 placeholder
  branch talk_at_school p = 0.12 placeholder
  branch go_home p = 0.40 if hour >= 15 placeholder

decision at_bar:
  branch drink p = max(0.01, 0.45 + stress * 0.15) placeholder
  branch talk_at_bar p = 0.32 placeholder
  branch start_fight p = max(0.01, aggression * 0.80 + alcohol * 0.35) placeholder
  branch go_home p = max(0.01, 0.22 + stress * 0.10) placeholder

decision at_cinema:
  branch watch_movie p = 0.82 placeholder
  branch talk_at_cinema p = 0.08 placeholder
  branch go_home p = 0.18 placeholder

decision at_home:
  branch rest p = max(0.01, 0.55 + stress * 0.25) placeholder
  branch family_time p = 0.35 if has_family placeholder
  branch go_bar p = 0.22 if age >= 18 and hour >= 17 placeholder
  branch go_cinema p = 0.12 if hour >= 17 placeholder
  branch sleep p = 0.85 if hour >= 21 or hour < 6 placeholder

action go_work:
  aggregate = travel
  duration = Triangular(min=0.20, median=0.45, max=0.90) placeholder
  outcome arrive p = 1.0 placeholder:
    effect self.location = Work placeholder
    next = at_work

action go_school:
  aggregate = travel
  duration = Triangular(min=0.15, median=0.35, max=0.75) placeholder
  outcome arrive p = 1.0 placeholder:
    effect self.location = School placeholder
    next = at_school

action go_bar:
  aggregate = travel
  duration = Triangular(min=0.10, median=0.30, max=0.70) placeholder
  outcome arrive p = 1.0 placeholder:
    effect self.location = Bar placeholder
    effect place Bar crowd += 0.02 placeholder
    next = at_bar

action go_cinema:
  aggregate = travel
  duration = Triangular(min=0.10, median=0.25, max=0.60) placeholder
  outcome arrive p = 1.0 placeholder:
    effect self.location = Cinema placeholder
    effect place Cinema crowd += 0.02 placeholder
    next = at_cinema

action go_home:
  aggregate = travel
  duration = Triangular(min=0.10, median=0.30, max=0.80) placeholder
  outcome arrive p = 1.0 placeholder:
    effect self.location = Home placeholder
    next = at_home

action stay_home:
  aggregate = home
  duration = Triangular(min=0.10, median=0.40, max=0.90) placeholder
  outcome settle p = 1.0 placeholder:
    effect self.location = Home placeholder
    next = at_home

action work:
  aggregate = work
  duration = Triangular(min=4.0, median=7.5, max=10.0) placeholder
  long = true placeholder
  outcome productive p = max(0.01, 0.72 - stress * 0.20) placeholder:
    effect self.money += 160 placeholder
    effect self.stress += 0.06 placeholder
    effect place Work productivity += 0.01 placeholder
    next = at_work
  outcome difficult p = max(0.01, 0.28 + stress * 0.20) placeholder:
    effect self.money += 120 placeholder
    effect self.stress += 0.16 placeholder
    effect self.health -= 0.03 placeholder
    next = at_work

action study:
  aggregate = study
  duration = Triangular(min=2.0, median=5.5, max=8.0) placeholder
  long = true placeholder
  outcome learned p = max(0.01, 0.78 - stress * 0.15) placeholder:
    effect self.stress -= 0.05 placeholder
    effect self.reputation += 0.03 placeholder
    effect place School learning += 0.01 placeholder
    next = at_school
  outcome overwhelmed p = max(0.01, 0.22 + stress * 0.15) placeholder:
    effect self.stress += 0.15 placeholder
    next = at_school

action drink:
  aggregate = drinks
  duration = Triangular(min=0.20, median=0.60, max=1.0) placeholder
  outcome moderate p = max(0.01, 0.68 - aggression * 0.15) placeholder:
    effect self.alcohol += 0.18 placeholder
    effect self.stress -= 0.08 placeholder
    next = at_bar
  outcome heavy p = max(0.01, 0.32 + aggression * 0.15) placeholder:
    effect self.alcohol += 0.38 placeholder
    effect self.health -= 0.04 placeholder
    effect self.stress += 0.04 placeholder
    next = at_bar

action talk_at_work:
  aggregate = talks
  target = random at Work where agent != self
  duration = Triangular(min=0.05, median=0.20, max=0.50) placeholder
  outcome friendly p = 0.82 placeholder:
    effect self.stress -= 0.04 placeholder
    effect target.stress -= 0.03 placeholder
    effect relationship with target trust += 0.08 placeholder
    next = at_work
  outcome awkward p = 0.18 placeholder:
    effect self.stress += 0.03 placeholder
    next = at_work

action talk_at_school:
  aggregate = talks
  target = random at School where agent != self
  duration = Triangular(min=0.05, median=0.20, max=0.50) placeholder
  outcome friendly p = 0.86 placeholder:
    effect self.stress -= 0.05 placeholder
    effect target.stress -= 0.03 placeholder
    effect relationship with target trust += 0.08 placeholder
    next = at_school
  outcome awkward p = 0.14 placeholder:
    effect self.stress += 0.03 placeholder
    next = at_school

action talk_at_bar:
  aggregate = talks
  target = random at Bar where agent != self
  duration = Triangular(min=0.05, median=0.25, max=0.60) placeholder
  outcome friendly p = max(0.01, 0.76 - alcohol * 0.15) placeholder:
    effect self.stress -= 0.06 placeholder
    effect target.stress -= 0.04 placeholder
    effect relationship with target trust += 0.10 placeholder
    next = at_bar
  outcome hostile p = max(0.01, 0.24 + alcohol * 0.15) placeholder:
    effect self.stress += 0.08 placeholder
    effect target.stress += 0.10 placeholder
    effect relationship with target trust -= 0.12 placeholder
    effect place Bar chaos += 0.04 placeholder
    next = at_bar

action talk_at_cinema:
  aggregate = talks
  target = random at Cinema where agent != self
  duration = Triangular(min=0.02, median=0.10, max=0.30) placeholder
  outcome quiet p = 0.82 placeholder:
    effect relationship with target trust += 0.03 placeholder
    next = at_cinema
  outcome disruptive p = 0.18 placeholder:
    effect all at Cinema stress where agent != self += 0.03 placeholder
    effect place Cinema enjoyment -= 0.04 placeholder
    next = at_cinema

action watch_movie:
  aggregate = movies
  duration = Triangular(min=1.2, median=1.9, max=3.0) placeholder
  long = true placeholder
  outcome enjoyed p = max(0.01, 0.78 - stress * 0.15) placeholder:
    effect self.stress -= 0.16 placeholder
    effect place Cinema enjoyment += 0.02 placeholder
    next = at_cinema
  outcome bored p = max(0.01, 0.22 + stress * 0.15) placeholder:
    effect self.stress += 0.04 placeholder
    next = at_cinema

action rest:
  aggregate = rest
  duration = Triangular(min=0.30, median=0.80, max=1.0) placeholder
  outcome recovered p = 0.84 placeholder:
    effect self.stress -= 0.14 placeholder
    effect self.health += 0.03 placeholder
    next = at_home
  outcome restless p = 0.16 placeholder:
    effect self.stress += 0.03 placeholder
    next = at_home

action family_time:
  aggregate = family_time
  duration = Triangular(min=0.30, median=0.90, max=1.0) placeholder
  outcome connected p = 0.86 placeholder:
    effect self.stress -= 0.12 placeholder
    effect self.reputation += 0.03 placeholder
    next = at_home
  outcome tense p = max(0.01, 0.14 + stress * 0.10) placeholder:
    effect self.stress += 0.08 placeholder
    next = at_home

action sleep:
  aggregate = sleep
  duration = Triangular(min=6.0, median=8.0, max=10.0) placeholder
  long = true placeholder
  outcome rested p = 0.82 placeholder:
    effect self.stress -= 0.20 placeholder
    effect self.health += 0.04 placeholder
    next = where_to_go
  outcome poor_sleep p = max(0.01, 0.18 + stress * 0.12) placeholder:
    effect self.stress += 0.06 placeholder
    next = where_to_go

action start_fight:
  aggregate = fights
  target = random at Bar where agent != self
  duration = Triangular(min=0.05, median=0.25, max=0.80) placeholder
  outcome fight_back p = max(0.01, 0.30 + target.aggression * 0.25) placeholder:
    effect self.health -= 0.14 placeholder
    effect target.health -= 0.12 placeholder
    effect self.stress += 0.22 placeholder
    effect target.stress += 0.24 placeholder
    effect self.reputation += 0.08 placeholder
    effect relationship with target trust -= 0.40 placeholder
    effect all at Bar stress where agent != self += 0.08 placeholder
    effect place Bar chaos += 0.30 placeholder
    next = at_bar
  outcome target_runs p = max(0.01, 0.24 - target.aggression * 0.10) placeholder:
    effect target.location = Home placeholder
    target_next = at_home
    effect target.stress += 0.20 placeholder
    effect self.reputation += 0.05 placeholder
    effect relationship with target trust -= 0.25 placeholder
    effect all at Bar stress where agent != self += 0.05 placeholder
    effect place Bar chaos += 0.16 placeholder
    next = at_bar
  outcome bystanders_intervene p = 0.28 placeholder:
    effect self.stress += 0.10 placeholder
    effect target.stress += 0.10 placeholder
    effect all at Bar stress where agent != self += 0.04 placeholder
    effect place Bar chaos += 0.08 placeholder
    next = at_bar
  outcome police_called p = max(0.01, 0.18 + place.chaos * 0.12) placeholder:
    effect self.money -= 120 placeholder
    effect self.reputation -= 0.12 placeholder
    effect target.stress += 0.12 placeholder
    effect all at Bar stress where agent != self += 0.12 placeholder
    effect place Bar chaos -= 0.20 placeholder
    next = at_bar
