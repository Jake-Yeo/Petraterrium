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

place SchoolDistrict:
  scope = composition
  state attendance = 0 range 0..100000 placeholder
  state capacity = 0.78 range 0..1 placeholder

place Hospital:
  scope = composition
  state visits = 0 range 0..100000 placeholder
  state capacity = 0.74 range 0..1 placeholder

place ShoppingCentre:
  scope = composition
  state visits = 0 range 0..100000 placeholder
  state activity = 0.62 range 0..1 placeholder

place Transit:
  scope = composition
  state riders = 0 range 0..100000 placeholder
  state reliability = 0.76 range 0..1 placeholder

composition Toronto:
  level = municipality
  children:
    UrbanLiberal: weight = 120
    SuburbanMixed: weight = 80
    RuralMixed: weight = 40
  institutions = Work, School, Bar, Cinema, SchoolDistrict, Hospital, ShoppingCentre, Transit
  parameters:
    policy_tax = 0.23
    transit_access = 0.81
    unemployment_national = 0.06
  adjacency:
    UrbanLiberal <-> SuburbanMixed distance = 1
    SuburbanMixed <-> RuralMixed distance = 1.5
  flows:
    commute_urban_suburban UrbanLiberal -> SuburbanMixed rate = formula(clamp(0.1042 + unemployment_national * 0.80 + transit_access * 0.04 - policy_tax * 0.02, 0, 0.50)) effect = visit via Transit
    commute_suburban_urban SuburbanMixed -> UrbanLiberal rate = formula(clamp(0.0783 + unemployment_national * 0.70 + transit_access * 0.03 - policy_tax * 0.02, 0, 0.45)) effect = visit via Transit
    migrate_rural_suburban RuralMixed -> SuburbanMixed rate = formula(clamp(0.022 + unemployment_national * 0.30 + economic_shock * 0.10, 0, 0.20)) effect = transfer
  cached:
    sync = 1 days
    max_iterations = 1
    tolerance = 0.01
    feedback:
      mean_stress -> economic_shock scale = 0.10
  output population = count()
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()
  output fights_per_day = action_count(fights, window=day)
  output commuting_rate = flow_rate(commute_urban_suburban)
  output migration_rate = flow_rate(migrate_rural_suburban)

composition Vancouver:
  level = municipality
  children:
    UrbanLiberal: weight = 90
    SuburbanMixed: weight = 60
    RuralMixed: weight = 30
  institutions = Work, School, Bar, Cinema, SchoolDistrict, Hospital, ShoppingCentre, Transit
  parameters:
    policy_tax = 0.21
    transit_access = 0.84
    unemployment_national = 0.055
  adjacency:
    UrbanLiberal <-> SuburbanMixed distance = 1
    SuburbanMixed <-> RuralMixed distance = 1.7
  flows:
    commute_urban_suburban UrbanLiberal -> SuburbanMixed rate = formula(clamp(0.1266 + unemployment_national * 0.80 + transit_access * 0.04 - policy_tax * 0.02, 0, 0.50)) effect = visit via Transit
    commute_suburban_urban SuburbanMixed -> UrbanLiberal rate = formula(clamp(0.1005 + unemployment_national * 0.70 + transit_access * 0.03 - policy_tax * 0.02, 0, 0.45)) effect = visit via Transit
    migrate_rural_suburban RuralMixed -> SuburbanMixed rate = formula(clamp(0.01625 + unemployment_national * 0.25 + economic_shock * 0.10, 0, 0.20)) effect = transfer
  cached:
    sync = 1 days
    max_iterations = 1
    tolerance = 0.01
    feedback:
      mean_stress -> economic_shock scale = 0.10
  output population = count()
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()
  output fights_per_day = action_count(fights, window=day)
  output commuting_rate = flow_rate(commute_urban_suburban)
  output migration_rate = flow_rate(migrate_rural_suburban)

composition Ontario:
  level = division
  children:
    Toronto: weight = 100
    Vancouver: weight = 50
  institutions = Work, School, Bar, Cinema, Transit
  parameters:
    provincial_policy_tax = 0.25
    policy_tax = 0.25
    media_trend = 0.00
    transit_available = 0.78
    unemployment_national = 0.06
  adjacency:
    Toronto <-> Vancouver distance = 3
  flows:
    intermunicipal_visit Toronto -> Vancouver rate = formula(clamp(0.08 + unemployment_national * 0.40 + transit_available * 0.03 - provincial_policy_tax * 0.01 + Toronto_mean_stress * 0.02, 0, 0.30)) effect = visit via Transit
    intermunicipal_transfer Vancouver -> Toronto rate = formula(clamp(0.005 + unemployment_national * 0.10 + economic_shock * 0.05, 0, 0.08)) effect = transfer
  cached:
    sync = 1 days
    max_iterations = 5
    tolerance = 0.01
    feedback:
      mean_stress -> economic_shock scale = 0.08
  output population = count()
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()
  output fights_per_day = action_count(fights, window=day)
  output commuting_rate = flow_rate(intermunicipal_visit)
  output migration_rate = flow_rate(intermunicipal_transfer)
  output gdp_proxy = sum(money)

aggregate_function Toronto:
  inputs:
    policy_tax = 0.23 range 0.10..0.40
    economic_shock = 0.00 range -0.20..0.20
    transit_access = 0.81 range 0.40..1.00
    unemployment_national = 0.06 range 0.02..0.15
  time = 30 days
  time_points = 1, 7, 30
  effects:
    field money *= 1 - policy_tax * 0.23 + economic_shock * 0.20
    field stress += economic_shock * 0.24 + policy_tax * 0.04
  outputs:
    population = formula(policy_tax, economic_shock, transit_access, unemployment_national)
    mean_income = formula(policy_tax, economic_shock, transit_access, unemployment_national)
    mean_stress = formula(policy_tax, economic_shock, transit_access, unemployment_national)
    mean_health = formula(policy_tax, economic_shock, transit_access, unemployment_national)
    vote_liberal_share = formula(policy_tax, economic_shock, transit_access, unemployment_national)
    mean_kids_per_family = formula(policy_tax, economic_shock, transit_access, unemployment_national)
    fights_per_day = formula(policy_tax, economic_shock, transit_access, unemployment_national)
    commuting_rate = formula(policy_tax, economic_shock, transit_access, unemployment_national)
    migration_rate = formula(policy_tax, economic_shock, transit_access, unemployment_national)
  cache:
    valid_for = 30 days
    inputs_hash = hash(policy_tax, economic_shock, transit_access, unemployment_national)
    invalidate_on:
      policy_tax change > 0.05
      economic_shock change > 0.10
      transit_access change > 0.10
      unemployment_national change > 0.02
      event = disruption, election

aggregate_function Vancouver:
  inputs:
    policy_tax = 0.21 range 0.10..0.40
    economic_shock = 0.00 range -0.20..0.20
    transit_access = 0.84 range 0.40..1.00
    unemployment_national = 0.055 range 0.02..0.15
  time = 30 days
  time_points = 1, 7, 30
  effects:
    field money *= 1 - policy_tax * 0.21 + economic_shock * 0.19
    field stress += economic_shock * 0.22 + policy_tax * 0.03
  outputs:
    population = formula(policy_tax, economic_shock, transit_access, unemployment_national)
    mean_income = formula(policy_tax, economic_shock, transit_access, unemployment_national)
    mean_stress = formula(policy_tax, economic_shock, transit_access, unemployment_national)
    mean_health = formula(policy_tax, economic_shock, transit_access, unemployment_national)
    vote_liberal_share = formula(policy_tax, economic_shock, transit_access, unemployment_national)
    mean_kids_per_family = formula(policy_tax, economic_shock, transit_access, unemployment_national)
    fights_per_day = formula(policy_tax, economic_shock, transit_access, unemployment_national)
    commuting_rate = formula(policy_tax, economic_shock, transit_access, unemployment_national)
    migration_rate = formula(policy_tax, economic_shock, transit_access, unemployment_national)
  cache:
    valid_for = 30 days
    inputs_hash = hash(policy_tax, economic_shock, transit_access, unemployment_national)
    invalidate_on:
      policy_tax change > 0.05
      economic_shock change > 0.10
      transit_access change > 0.10
      unemployment_national change > 0.02
      event = disruption, election

aggregate_function Ontario:
  inputs:
    provincial_policy_tax = 0.25 range 0.10..0.40
    policy_tax = 0.25 range 0.10..0.40
    media_trend = 0.00 range -1.00..1.00
    economic_shock = 0.00 range -0.20..0.20
    transit_available = 0.78 range 0.40..1.00
    unemployment_national = 0.06 range 0.02..0.15
  time = 30 days
  time_points = 1, 7, 30
  effects:
    field money *= 1 - provincial_policy_tax * 0.22 + economic_shock * 0.18
    field stress += economic_shock * 0.21 + provincial_policy_tax * 0.03
  outputs:
    population = formula(provincial_policy_tax, policy_tax, media_trend, economic_shock, transit_available, unemployment_national)
    mean_income = formula(provincial_policy_tax, policy_tax, media_trend, economic_shock, transit_available, unemployment_national)
    mean_stress = formula(provincial_policy_tax, policy_tax, media_trend, economic_shock, transit_available, unemployment_national)
    mean_health = formula(provincial_policy_tax, policy_tax, media_trend, economic_shock, transit_available, unemployment_national)
    vote_liberal_share = formula(provincial_policy_tax, policy_tax, media_trend, economic_shock, transit_available, unemployment_national)
    mean_kids_per_family = formula(provincial_policy_tax, policy_tax, media_trend, economic_shock, transit_available, unemployment_national)
    fights_per_day = formula(provincial_policy_tax, policy_tax, media_trend, economic_shock, transit_available, unemployment_national)
    commuting_rate = formula(provincial_policy_tax, policy_tax, media_trend, economic_shock, transit_available, unemployment_national)
    migration_rate = formula(provincial_policy_tax, policy_tax, media_trend, economic_shock, transit_available, unemployment_national)
    gdp_proxy = formula(provincial_policy_tax, policy_tax, media_trend, economic_shock, transit_available, unemployment_national)
  cache:
    valid_for = 30 days
    inputs_hash = hash(provincial_policy_tax, policy_tax, media_trend, economic_shock, transit_available, unemployment_national)
    invalidate_on:
      provincial_policy_tax change > 0.05
      policy_tax change > 0.05
      media_trend change > 0.20
      economic_shock change > 0.10
      transit_available change > 0.10
      unemployment_national change > 0.02
      event = disruption, election

archetype CountryFederalDemocracy:
  level = country
  child_level = division
  parameters:
    national_policy_tax = 0.25
    federal_structure = 0.80
  output mean_income = mean(money) where age >= 18 with sd
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd

composition BritishColumbia:
  level = division
  children:
    Vancouver: weight = 90
    Toronto: weight = 10
  institutions = Work, School, Bar, Cinema, Transit
  parameters:
    policy_tax = 0.23
    unemployment_national = 0.06
    transit_available = 0.82
    economic_shock = 0.00
  adjacency:
    Vancouver <-> Toronto distance = 1
  flows:
    internal_exchange Vancouver -> Toronto rate = formula(clamp(0.05 + transit_available * 0.04 - policy_tax * 0.02, 0, 0.25)) effect = exchange
    internal_migration Toronto -> Vancouver rate = formula(clamp(0.005 + unemployment_national * 0.08 + economic_shock * 0.03, 0, 0.08)) effect = transfer
  cached:
    sync = 5 days
    max_iterations = 1
    tolerance = 0.01
  output population = count()
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()
  output fights_per_day = action_count(fights, window=day)
  output trade_balance = flow_count(internal_exchange)
  output migration_rate = flow_rate(internal_migration)
  output gdp_proxy = sum(money)

composition California:
  level = division
  children:
    Toronto: weight = 70
    Vancouver: weight = 30
  institutions = Work, School, Bar, Cinema, Transit
  parameters:
    policy_tax = 0.24
    unemployment_national = 0.055
    transit_available = 0.76
    economic_shock = 0.00
  adjacency:
    Toronto <-> Vancouver distance = 1
  flows:
    internal_exchange Toronto -> Vancouver rate = formula(clamp(0.05 + transit_available * 0.04 - policy_tax * 0.02, 0, 0.25)) effect = exchange
    internal_migration Vancouver -> Toronto rate = formula(clamp(0.005 + unemployment_national * 0.08 + economic_shock * 0.03, 0, 0.08)) effect = transfer
  cached:
    sync = 5 days
    max_iterations = 1
    tolerance = 0.01
  output population = count()
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()
  output fights_per_day = action_count(fights, window=day)
  output trade_balance = flow_count(internal_exchange)
  output migration_rate = flow_rate(internal_migration)
  output gdp_proxy = sum(money)

composition Texas:
  level = division
  children:
    Toronto: weight = 30
    Vancouver: weight = 70
  institutions = Work, School, Bar, Cinema, Transit
  parameters:
    policy_tax = 0.2
    unemployment_national = 0.05
    transit_available = 0.68
    economic_shock = 0.00
  adjacency:
    Toronto <-> Vancouver distance = 1
  flows:
    internal_exchange Toronto -> Vancouver rate = formula(clamp(0.05 + transit_available * 0.04 - policy_tax * 0.02, 0, 0.25)) effect = exchange
    internal_migration Vancouver -> Toronto rate = formula(clamp(0.005 + unemployment_national * 0.08 + economic_shock * 0.03, 0, 0.08)) effect = transfer
  cached:
    sync = 5 days
    max_iterations = 1
    tolerance = 0.01
  output population = count()
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()
  output fights_per_day = action_count(fights, window=day)
  output trade_balance = flow_count(internal_exchange)
  output migration_rate = flow_rate(internal_migration)
  output gdp_proxy = sum(money)

composition CentralMexico:
  level = division
  children:
    Toronto: weight = 45
    Vancouver: weight = 55
  institutions = Work, School, Bar, Cinema, Transit
  parameters:
    policy_tax = 0.19
    unemployment_national = 0.075
    transit_available = 0.62
    economic_shock = 0.00
  adjacency:
    Toronto <-> Vancouver distance = 1
  flows:
    internal_exchange Toronto -> Vancouver rate = formula(clamp(0.05 + transit_available * 0.04 - policy_tax * 0.02, 0, 0.25)) effect = exchange
    internal_migration Vancouver -> Toronto rate = formula(clamp(0.005 + unemployment_national * 0.08 + economic_shock * 0.03, 0, 0.08)) effect = transfer
  cached:
    sync = 5 days
    max_iterations = 1
    tolerance = 0.01
  output population = count()
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()
  output fights_per_day = action_count(fights, window=day)
  output trade_balance = flow_count(internal_exchange)
  output migration_rate = flow_rate(internal_migration)
  output gdp_proxy = sum(money)

composition NorthernMexico:
  level = division
  children:
    Toronto: weight = 35
    Vancouver: weight = 65
  institutions = Work, School, Bar, Cinema, Transit
  parameters:
    policy_tax = 0.18
    unemployment_national = 0.07
    transit_available = 0.66
    economic_shock = 0.00
  adjacency:
    Toronto <-> Vancouver distance = 1
  flows:
    internal_exchange Toronto -> Vancouver rate = formula(clamp(0.05 + transit_available * 0.04 - policy_tax * 0.02, 0, 0.25)) effect = exchange
    internal_migration Vancouver -> Toronto rate = formula(clamp(0.005 + unemployment_national * 0.08 + economic_shock * 0.03, 0, 0.08)) effect = transfer
  cached:
    sync = 5 days
    max_iterations = 1
    tolerance = 0.01
  output population = count()
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()
  output fights_per_day = action_count(fights, window=day)
  output trade_balance = flow_count(internal_exchange)
  output migration_rate = flow_rate(internal_migration)
  output gdp_proxy = sum(money)

composition Canada:
  level = country
  template = CountryFederalDemocracy
  represented_population = 40000000
  children:
    Ontario: weight = 100
    BritishColumbia: weight = 50
  institutions = Transit
  parameters:
    national_policy_tax = 0.25
    policy_tax = 0.25
    media_trend = 0.00
    economic_shock = 0.00
    unemployment_national = 0.06
    transit_available = 0.82
    border_policy = 0.82
    tariff = 0.15
    infection_modifier = 0.08
    federal_structure = 0.72
  adjacency:
    Ontario <-> BritishColumbia distance = 1
  flows:
    division_exchange Ontario -> BritishColumbia rate = formula(clamp(0.04 + Ontario_gdp_proxy / 1000000000 - tariff * 0.10 + federal_structure * 0.01, 0, 0.30)) effect = exchange
    division_migration BritishColumbia -> Ontario rate = formula(clamp(0.005 + unemployment_national * 0.08 + border_policy * 0.02, 0, 0.08)) effect = transfer
    division_travel Ontario -> BritishColumbia rate = formula(clamp(0.03 + transit_available * 0.02, 0, 0.15)) effect = visit via Transit
  cached:
    sync = 30 days
    max_iterations = 2
    tolerance = 0.01
    feedback:
      mean_stress -> economic_shock scale = 0.05
  output population = count()
  output represented_population = represented_count()
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()
  output fights_per_day = action_count(fights, window=day)
  output gdp_proxy = sum(money)
  output trade_balance = flow_count(division_exchange)
  output migration_rate = flow_rate(division_migration)

composition USA:
  level = country
  template = CountryFederalDemocracy
  represented_population = 335000000
  children:
    California: weight = 100
    Texas: weight = 80
  institutions = Transit
  parameters:
    national_policy_tax = 0.22
    policy_tax = 0.22
    media_trend = 0.00
    economic_shock = 0.00
    unemployment_national = 0.05
    transit_available = 0.78
    border_policy = 0.78
    tariff = 0.25
    infection_modifier = 0.12
    federal_structure = 0.68
  adjacency:
    California <-> Texas distance = 1
  flows:
    division_exchange California -> Texas rate = formula(clamp(0.04 + California_gdp_proxy / 1000000000 - tariff * 0.10 + federal_structure * 0.01, 0, 0.30)) effect = exchange
    division_migration Texas -> California rate = formula(clamp(0.005 + unemployment_national * 0.08 + border_policy * 0.02, 0, 0.08)) effect = transfer
    division_travel California -> Texas rate = formula(clamp(0.03 + transit_available * 0.02, 0, 0.15)) effect = visit via Transit
  cached:
    sync = 30 days
    max_iterations = 2
    tolerance = 0.01
    feedback:
      mean_stress -> economic_shock scale = 0.05
  output population = count()
  output represented_population = represented_count()
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()
  output fights_per_day = action_count(fights, window=day)
  output gdp_proxy = sum(money)
  output trade_balance = flow_count(division_exchange)
  output migration_rate = flow_rate(division_migration)

composition Mexico:
  level = country
  template = CountryFederalDemocracy
  represented_population = 130000000
  children:
    CentralMexico: weight = 100
    NorthernMexico: weight = 70
  institutions = Transit
  parameters:
    national_policy_tax = 0.19
    policy_tax = 0.19
    media_trend = 0.00
    economic_shock = 0.00
    unemployment_national = 0.075
    transit_available = 0.64
    border_policy = 0.64
    tariff = 0.35
    infection_modifier = 0.06
    federal_structure = 0.8
  adjacency:
    CentralMexico <-> NorthernMexico distance = 1
  flows:
    division_exchange CentralMexico -> NorthernMexico rate = formula(clamp(0.04 + CentralMexico_gdp_proxy / 1000000000 - tariff * 0.10 + federal_structure * 0.01, 0, 0.30)) effect = exchange
    division_migration NorthernMexico -> CentralMexico rate = formula(clamp(0.005 + unemployment_national * 0.08 + border_policy * 0.02, 0, 0.08)) effect = transfer
    division_travel CentralMexico -> NorthernMexico rate = formula(clamp(0.03 + transit_available * 0.02, 0, 0.15)) effect = visit via Transit
  cached:
    sync = 30 days
    max_iterations = 2
    tolerance = 0.01
    feedback:
      mean_stress -> economic_shock scale = 0.05
  output population = count()
  output represented_population = represented_count()
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()
  output fights_per_day = action_count(fights, window=day)
  output gdp_proxy = sum(money)
  output trade_balance = flow_count(division_exchange)
  output migration_rate = flow_rate(division_migration)

composition World:
  level = world
  represented_population = 6999999999
  children:
    Canada: weight = 100
    USA: weight = 300
    Mexico: weight = 80
  institutions = Transit
  parameters:
    global_interest_rate = 0.04
    global_trade_policy = 0.70
    policy_tax = 0.23
    media_trend = 0.00
    economic_shock = 0.00
    unemployment_national = 0.06
    border_policy = 0.72
    tariff = 0.10
    infection_rate = 0.04
  adjacency:
    Canada <-> USA distance = 1
    USA <-> Mexico distance = 1
  flows:
    canada_usa_trade Canada -> USA rate = formula(clamp(0.04 + Canada_gdp_proxy / 1000000000 + USA_gdp_proxy / 3000000000 + global_trade_policy * 0.04 - tariff * 0.12, 0, 0.40)) effect = exchange
    usa_mexico_trade USA -> Mexico rate = formula(clamp(0.03 + USA_gdp_proxy / 3000000000 + Mexico_gdp_proxy / 1000000000 + global_trade_policy * 0.03 - tariff * 0.10, 0, 0.35)) effect = exchange
    mexico_usa_migration Mexico -> USA rate = formula(clamp(0.005 + Mexico_unemployment_national * 0.10 + USA_mean_income / 100000 - border_policy * 0.01, 0, 0.10)) effect = transfer
    usa_canada_travel USA -> Canada rate = formula(clamp(0.03 + global_trade_policy * 0.02, 0, 0.12)) effect = visit via Transit
    usa_canada_infection USA -> Canada rate = formula(clamp(usa_canada_travel + infection_rate * 0.20 + USA_infection_modifier * 0.02, 0, 0.15)) effect = infection
    usa_canada_policy USA -> Canada rate = formula(clamp(global_trade_policy * 0.10 + media_trend * 0.02, 0, 0.20)) effect = diffusion
  cached:
    sync = 90 days
    max_iterations = 5
    tolerance = 0.01
    feedback:
      mean_stress -> economic_shock scale = 0.04
  output population = count()
  output represented_population = represented_count()
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_liberal_share = mean(vote_liberal) where age >= 18 with sd
  output mean_kids_per_family = kids_per_family()
  output fights_per_day = action_count(fights, window=day)
  output gdp_proxy = sum(money)
  output world_trade_volume = flow_count(canada_usa_trade)
  output world_migration_rate = flow_rate(mexico_usa_migration)
  output world_infection_rate = flow_rate(usa_canada_infection)

composition_population WorldHouseholds:
  World: represented = 6999999999

composition_population SevenBillionWorld:
  World: represented = 6999999999

aggregate_function BritishColumbia:
  inputs:
    policy_tax = 0.22 range 0.10..0.40
    economic_shock = 0.00 range -0.20..0.20
    unemployment_national = 0.06 range 0.02..0.15
  time = 30 days
  time_points = 1, 7, 30
  effects:
    field money *= 1 - policy_tax * 0.20 + economic_shock * 0.18
    field stress += economic_shock * 0.20 + unemployment_national * 0.20
  outputs:
    population = formula(policy_tax, economic_shock, unemployment_national)
    mean_income = formula(policy_tax, economic_shock, unemployment_national)
    mean_stress = formula(policy_tax, economic_shock, unemployment_national)
    mean_health = formula(policy_tax, economic_shock, unemployment_national)
    vote_liberal_share = formula(policy_tax, economic_shock, unemployment_national)
    mean_kids_per_family = formula(policy_tax, economic_shock, unemployment_national)
    fights_per_day = formula(policy_tax, economic_shock, unemployment_national)
    trade_balance = formula(policy_tax, economic_shock, unemployment_national)
    migration_rate = formula(policy_tax, economic_shock, unemployment_national)
    gdp_proxy = formula(policy_tax, economic_shock, unemployment_national)
  cache:
    valid_for = 30 days
    inputs_hash = hash(policy_tax, economic_shock, unemployment_national)
    invalidate_on:
      policy_tax change > 0.05
      economic_shock change > 0.10
      unemployment_national change > 0.02
      event = pandemic, sanctions, election

aggregate_function California:
  inputs:
    policy_tax = 0.22 range 0.10..0.40
    economic_shock = 0.00 range -0.20..0.20
    unemployment_national = 0.06 range 0.02..0.15
  time = 30 days
  time_points = 1, 7, 30
  effects:
    field money *= 1 - policy_tax * 0.20 + economic_shock * 0.18
    field stress += economic_shock * 0.20 + unemployment_national * 0.20
  outputs:
    population = formula(policy_tax, economic_shock, unemployment_national)
    mean_income = formula(policy_tax, economic_shock, unemployment_national)
    mean_stress = formula(policy_tax, economic_shock, unemployment_national)
    mean_health = formula(policy_tax, economic_shock, unemployment_national)
    vote_liberal_share = formula(policy_tax, economic_shock, unemployment_national)
    mean_kids_per_family = formula(policy_tax, economic_shock, unemployment_national)
    fights_per_day = formula(policy_tax, economic_shock, unemployment_national)
    trade_balance = formula(policy_tax, economic_shock, unemployment_national)
    migration_rate = formula(policy_tax, economic_shock, unemployment_national)
    gdp_proxy = formula(policy_tax, economic_shock, unemployment_national)
  cache:
    valid_for = 30 days
    inputs_hash = hash(policy_tax, economic_shock, unemployment_national)
    invalidate_on:
      policy_tax change > 0.05
      economic_shock change > 0.10
      unemployment_national change > 0.02
      event = pandemic, sanctions, election

aggregate_function Texas:
  inputs:
    policy_tax = 0.22 range 0.10..0.40
    economic_shock = 0.00 range -0.20..0.20
    unemployment_national = 0.06 range 0.02..0.15
  time = 30 days
  time_points = 1, 7, 30
  effects:
    field money *= 1 - policy_tax * 0.20 + economic_shock * 0.18
    field stress += economic_shock * 0.20 + unemployment_national * 0.20
  outputs:
    population = formula(policy_tax, economic_shock, unemployment_national)
    mean_income = formula(policy_tax, economic_shock, unemployment_national)
    mean_stress = formula(policy_tax, economic_shock, unemployment_national)
    mean_health = formula(policy_tax, economic_shock, unemployment_national)
    vote_liberal_share = formula(policy_tax, economic_shock, unemployment_national)
    mean_kids_per_family = formula(policy_tax, economic_shock, unemployment_national)
    fights_per_day = formula(policy_tax, economic_shock, unemployment_national)
    trade_balance = formula(policy_tax, economic_shock, unemployment_national)
    migration_rate = formula(policy_tax, economic_shock, unemployment_national)
    gdp_proxy = formula(policy_tax, economic_shock, unemployment_national)
  cache:
    valid_for = 30 days
    inputs_hash = hash(policy_tax, economic_shock, unemployment_national)
    invalidate_on:
      policy_tax change > 0.05
      economic_shock change > 0.10
      unemployment_national change > 0.02
      event = pandemic, sanctions, election

aggregate_function CentralMexico:
  inputs:
    policy_tax = 0.22 range 0.10..0.40
    economic_shock = 0.00 range -0.20..0.20
    unemployment_national = 0.06 range 0.02..0.15
  time = 30 days
  time_points = 1, 7, 30
  effects:
    field money *= 1 - policy_tax * 0.20 + economic_shock * 0.18
    field stress += economic_shock * 0.20 + unemployment_national * 0.20
  outputs:
    population = formula(policy_tax, economic_shock, unemployment_national)
    mean_income = formula(policy_tax, economic_shock, unemployment_national)
    mean_stress = formula(policy_tax, economic_shock, unemployment_national)
    mean_health = formula(policy_tax, economic_shock, unemployment_national)
    vote_liberal_share = formula(policy_tax, economic_shock, unemployment_national)
    mean_kids_per_family = formula(policy_tax, economic_shock, unemployment_national)
    fights_per_day = formula(policy_tax, economic_shock, unemployment_national)
    trade_balance = formula(policy_tax, economic_shock, unemployment_national)
    migration_rate = formula(policy_tax, economic_shock, unemployment_national)
    gdp_proxy = formula(policy_tax, economic_shock, unemployment_national)
  cache:
    valid_for = 30 days
    inputs_hash = hash(policy_tax, economic_shock, unemployment_national)
    invalidate_on:
      policy_tax change > 0.05
      economic_shock change > 0.10
      unemployment_national change > 0.02
      event = pandemic, sanctions, election

aggregate_function NorthernMexico:
  inputs:
    policy_tax = 0.22 range 0.10..0.40
    economic_shock = 0.00 range -0.20..0.20
    unemployment_national = 0.06 range 0.02..0.15
  time = 30 days
  time_points = 1, 7, 30
  effects:
    field money *= 1 - policy_tax * 0.20 + economic_shock * 0.18
    field stress += economic_shock * 0.20 + unemployment_national * 0.20
  outputs:
    population = formula(policy_tax, economic_shock, unemployment_national)
    mean_income = formula(policy_tax, economic_shock, unemployment_national)
    mean_stress = formula(policy_tax, economic_shock, unemployment_national)
    mean_health = formula(policy_tax, economic_shock, unemployment_national)
    vote_liberal_share = formula(policy_tax, economic_shock, unemployment_national)
    mean_kids_per_family = formula(policy_tax, economic_shock, unemployment_national)
    fights_per_day = formula(policy_tax, economic_shock, unemployment_national)
    trade_balance = formula(policy_tax, economic_shock, unemployment_national)
    migration_rate = formula(policy_tax, economic_shock, unemployment_national)
    gdp_proxy = formula(policy_tax, economic_shock, unemployment_national)
  cache:
    valid_for = 30 days
    inputs_hash = hash(policy_tax, economic_shock, unemployment_national)
    invalidate_on:
      policy_tax change > 0.05
      economic_shock change > 0.10
      unemployment_national change > 0.02
      event = pandemic, sanctions, election

aggregate_function Canada:
  inputs:
    national_policy_tax = 0.25 range 0.1..0.4
    policy_tax = 0.25 range 0.1..0.4
    media_trend = 0.0 range -1..1
    economic_shock = 0.0 range -0.2..0.2
    unemployment_national = 0.06 range 0.02..0.15
    border_policy = 0.82 range 0..1
    tariff = 0.15 range 0..0.5
    infection_modifier = 0.08 range 0..1
  time = 30 days
  time_points = 1, 7, 30
  effects:
    field money *= 1 - national_policy_tax * 0.18 + economic_shock * 0.15
    field stress += economic_shock * 0.18 + unemployment_national * 0.18
  outputs:
    population = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    represented_population = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    mean_income = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    mean_stress = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    mean_health = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    vote_liberal_share = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    mean_kids_per_family = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    fights_per_day = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    gdp_proxy = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    trade_balance = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    migration_rate = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
  cache:
    valid_for = 90 days
    inputs_hash = hash(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    invalidate_on:
      national_policy_tax change > 0.05
      policy_tax change > 0.05
      media_trend change > 0.20
      economic_shock change > 0.10
      unemployment_national change > 0.02
      border_policy change > 0.10
      tariff change > 0.05
      infection_modifier change > 0.10
      event = pandemic, sanctions, war, election

aggregate_function USA:
  inputs:
    national_policy_tax = 0.22 range 0.1..0.4
    policy_tax = 0.22 range 0.1..0.4
    media_trend = 0.0 range -1..1
    economic_shock = 0.0 range -0.2..0.2
    unemployment_national = 0.05 range 0.02..0.15
    border_policy = 0.78 range 0..1
    tariff = 0.25 range 0..0.5
    infection_modifier = 0.12 range 0..1
  time = 30 days
  time_points = 1, 7, 30
  effects:
    field money *= 1 - national_policy_tax * 0.18 + economic_shock * 0.15
    field stress += economic_shock * 0.18 + unemployment_national * 0.18
  outputs:
    population = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    represented_population = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    mean_income = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    mean_stress = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    mean_health = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    vote_liberal_share = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    mean_kids_per_family = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    fights_per_day = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    gdp_proxy = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    trade_balance = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    migration_rate = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
  cache:
    valid_for = 90 days
    inputs_hash = hash(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    invalidate_on:
      national_policy_tax change > 0.05
      policy_tax change > 0.05
      media_trend change > 0.20
      economic_shock change > 0.10
      unemployment_national change > 0.02
      border_policy change > 0.10
      tariff change > 0.05
      infection_modifier change > 0.10
      event = pandemic, sanctions, war, election

aggregate_function Mexico:
  inputs:
    national_policy_tax = 0.19 range 0.1..0.4
    policy_tax = 0.19 range 0.1..0.4
    media_trend = 0.0 range -1..1
    economic_shock = 0.0 range -0.2..0.2
    unemployment_national = 0.075 range 0.02..0.15
    border_policy = 0.64 range 0..1
    tariff = 0.35 range 0..0.5
    infection_modifier = 0.06 range 0..1
  time = 30 days
  time_points = 1, 7, 30
  effects:
    field money *= 1 - national_policy_tax * 0.18 + economic_shock * 0.15
    field stress += economic_shock * 0.18 + unemployment_national * 0.18
  outputs:
    population = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    represented_population = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    mean_income = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    mean_stress = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    mean_health = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    vote_liberal_share = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    mean_kids_per_family = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    fights_per_day = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    gdp_proxy = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    trade_balance = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    migration_rate = formula(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
  cache:
    valid_for = 90 days
    inputs_hash = hash(national_policy_tax, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_modifier)
    invalidate_on:
      national_policy_tax change > 0.05
      policy_tax change > 0.05
      media_trend change > 0.20
      economic_shock change > 0.10
      unemployment_national change > 0.02
      border_policy change > 0.10
      tariff change > 0.05
      infection_modifier change > 0.10
      event = pandemic, sanctions, war, election

aggregate_function World:
  inputs:
    global_interest_rate = 0.04 range 0..0.2
    global_trade_policy = 0.7 range 0..1
    policy_tax = 0.23 range 0.1..0.4
    media_trend = 0 range -1..1
    economic_shock = 0 range -0.2..0.2
    unemployment_national = 0.06 range 0.02..0.15
    border_policy = 0.72 range 0..1
    tariff = 0.1 range 0..0.5
    infection_rate = 0.04 range 0..0.5
  time = 30 days
  time_points = 1, 7, 30
  effects:
    field money *= 1 - global_interest_rate * 0.10 + economic_shock * 0.12
    field stress += economic_shock * 0.15 + infection_rate * 0.08
  outputs:
    population = formula(global_interest_rate, global_trade_policy, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_rate)
    represented_population = formula(global_interest_rate, global_trade_policy, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_rate)
    mean_income = formula(global_interest_rate, global_trade_policy, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_rate)
    mean_stress = formula(global_interest_rate, global_trade_policy, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_rate)
    mean_health = formula(global_interest_rate, global_trade_policy, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_rate)
    vote_liberal_share = formula(global_interest_rate, global_trade_policy, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_rate)
    mean_kids_per_family = formula(global_interest_rate, global_trade_policy, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_rate)
    fights_per_day = formula(global_interest_rate, global_trade_policy, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_rate)
    gdp_proxy = formula(global_interest_rate, global_trade_policy, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_rate)
    world_trade_volume = formula(global_interest_rate, global_trade_policy, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_rate)
    world_migration_rate = formula(global_interest_rate, global_trade_policy, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_rate)
    world_infection_rate = formula(global_interest_rate, global_trade_policy, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_rate)
  cache:
    valid_for = 90 days
    inputs_hash = hash(global_interest_rate, global_trade_policy, policy_tax, media_trend, economic_shock, unemployment_national, border_policy, tariff, infection_rate)
    invalidate_on:
      global_interest_rate change > 0.02
      global_trade_policy change > 0.10
      policy_tax change > 0.05
      media_trend change > 0.20
      economic_shock change > 0.10
      unemployment_national change > 0.02
      border_policy change > 0.10
      tariff change > 0.05
      infection_rate change > 0.05
      event = pandemic, sanctions, war, election

entity Post:
  field topic
  field source
  state sentiment range -1..1 estimated
  state engagement range 0..100000 estimated
  state age_hours range 0..720 estimated
  owner = source

policy ModerationPolicy:
  effect decision media_post *= 1 - norm_strictness * moderation_compliance * 0.30
  effect decision media_share *= 1 - norm_strictness * moderation_compliance * 0.20
  effect decision media_post *= 1 - topic_closure * moderation_compliance * 0.90

place Feed:
  scope = composition
  state sentiment = 0 range -1..1 estimated
  state outrage = 0 range 0..1 estimated
  state engagement = 20 range 0..100000 estimated
  state age_hours = 0 range 0..720 estimated
  state viral_posts = 0 range 0..100000 estimated
  state topic_trend = 0 range 0..1 estimated
  state norm_strictness = 0.5 range 0..1 estimated

place Square:
  scope = composition
  state crowd = 0 range 0..100000 estimated

agent User:
  scope = composition
  trait interest
  trait political_lean
  trait activity
  trait trust
  trait interest_match
  trait agreement
  trait friends_sharing
  trait topic
  state sentiment range -1..1 estimated
  state stress range 0..1 estimated
  state outrage range 0..1 estimated
  state fatigue range 0..1 estimated
  state location
  initial:
    interest ~ Normal(mean=0.5, sd=0.2, min=0, max=1) placeholder
    political_lean ~ Normal(mean=0, sd=0.5, min=-1, max=1) placeholder
    activity ~ Beta(alpha=2, beta=5) placeholder
    trust ~ Beta(alpha=3, beta=3) placeholder
    interest_match ~ Beta(alpha=3, beta=2) placeholder
    agreement ~ Beta(alpha=3, beta=2) placeholder
    friends_sharing ~ Beta(alpha=2, beta=5) placeholder
    topic ~ Categorical(finance: 0.5, civic: 0.5) placeholder
    sentiment ~ Normal(mean=0, sd=0.35, min=-1, max=1) placeholder
    stress ~ Normal(mean=0.35, sd=0.1, min=0, max=1) placeholder
    outrage ~ Beta(alpha=2, beta=6) placeholder
    fatigue ~ Beta(alpha=2, beta=5) placeholder
    location ~ Categorical(Feed: 1.0) placeholder
  routine = at_feed

agent InfluencerUser inherits User:
  scope = composition
  role influencer

agent Citizen:
  scope = composition
  trait vote_liberal
  trait political_lean
  trait trust
  state stress range 0..1 estimated
  state media_outrage range 0..1 estimated
  state location
  initial:
    vote_liberal ~ Bernoulli(p=0.5) placeholder
    political_lean ~ Normal(mean=0, sd=0.5, min=-1, max=1) placeholder
    trust ~ Beta(alpha=3, beta=3) placeholder
    stress ~ Normal(mean=0.35, sd=0.1, min=0, max=1) placeholder
    media_outrage ~ Uniform(min=0, max=0) placeholder
    location ~ Categorical(Square: 1.0) placeholder
  routine = physical_day

archetype UserActive:
  sample_households = 25
  composition:
    users count = 1 mix User:1.0
  initial:
    activity ~ Beta(alpha=5, beta=2)
    sentiment ~ Normal(mean=0.35, sd=0.30, min=-1, max=1)
    outrage ~ Beta(alpha=2, beta=5)
    fatigue ~ Beta(alpha=2, beta=6)
  decision media_post multiplier = 1.30
  decision media_share multiplier = 1.20
  output population = count()
  output posting_rate = action_rate(posts, window=day)
  output comment_rate = action_rate(comments, window=day)
  output like_rate = action_rate(likes, window=day)
  output share_rate = action_rate(shares, window=day)
  output mean_sentiment = mean(sentiment) with sd
  output mean_outrage = mean(outrage) with sd
  output polarization = sd(sentiment)
  output viral_posts = action_count(viral_posts, window=day)
  output spotlight_posts = action_count(spotlight_posts, window=day)

archetype UserLurker:
  sample_households = 49
  composition:
    users count = 1 mix User:1.0
  initial:
    activity ~ Beta(alpha=1.5, beta=7)
    sentiment ~ Normal(mean=0.25, sd=0.28, min=-1, max=1)
    outrage ~ Beta(alpha=1.5, beta=7)
    fatigue ~ Beta(alpha=3, beta=4)
  decision media_post multiplier = 0.35
  decision media_share multiplier = 0.45
  output population = count()
  output posting_rate = action_rate(posts, window=day)
  output comment_rate = action_rate(comments, window=day)
  output like_rate = action_rate(likes, window=day)
  output share_rate = action_rate(shares, window=day)
  output mean_sentiment = mean(sentiment) with sd
  output mean_outrage = mean(outrage) with sd
  output polarization = sd(sentiment)
  output viral_posts = action_count(viral_posts, window=day)
  output spotlight_posts = action_count(spotlight_posts, window=day)

archetype UserPoster:
  sample_households = 25
  composition:
    users count = 1 mix User:1.0
  initial:
    activity ~ Beta(alpha=4, beta=3)
    sentiment ~ Normal(mean=0.30, sd=0.35, min=-1, max=1)
    outrage ~ Beta(alpha=3, beta=4)
    fatigue ~ Beta(alpha=2, beta=5)
  decision media_post multiplier = 1.10
  decision media_share multiplier = 1.05
  output population = count()
  output posting_rate = action_rate(posts, window=day)
  output comment_rate = action_rate(comments, window=day)
  output like_rate = action_rate(likes, window=day)
  output share_rate = action_rate(shares, window=day)
  output mean_sentiment = mean(sentiment) with sd
  output mean_outrage = mean(outrage) with sd
  output polarization = sd(sentiment)
  output viral_posts = action_count(viral_posts, window=day)
  output spotlight_posts = action_count(spotlight_posts, window=day)

spotlight agent InfluencerX:
  sample_households = 1
  composition:
    individual count = 1 mix InfluencerUser:1.0
  initial:
    activity ~ Uniform(min=0.95, max=0.95)
    trust ~ Uniform(min=0.85, max=0.85)
    interest_match ~ Uniform(min=0.9, max=0.9)
    agreement ~ Uniform(min=0.8, max=0.8)
    sentiment ~ Uniform(min=0.7, max=0.7)
    outrage ~ Uniform(min=0.8, max=0.8)
    fatigue ~ Uniform(min=0.05, max=0.05)
  output population = count()
  output posting_rate = action_rate(posts, window=day)
  output comment_rate = action_rate(comments, window=day)
  output like_rate = action_rate(likes, window=day)
  output share_rate = action_rate(shares, window=day)
  output mean_sentiment = mean(sentiment) with sd
  output mean_outrage = mean(outrage) with sd
  output polarization = sd(sentiment)
  output viral_posts = action_count(viral_posts, window=day)
  output spotlight_posts = action_count(spotlight_posts, window=day)

archetype PhysicalMass:
  sample_households = 100
  composition:
    people count = 1 mix Citizen:1.0
  initial:
    vote_liberal ~ Bernoulli(p=0.5)
    stress ~ Normal(mean=0.35, sd=0.1, min=0, max=1)
    media_outrage ~ Uniform(min=0, max=0)
  output population = count()
  output protest_rate = action_rate(protests, window=day)
  output fights_per_day = action_count(protests, window=day)
  output mean_stress = mean(stress) with sd
  output vote_liberal_share = mean(vote_liberal) with sd

decision at_feed:
  branch media_post p = clamp(0.02 + activity * 0.25 + outrage * 0.12, 0, 1) if not role.influencer estimated
  branch media_comment p = clamp(0.04 + activity * 0.18 + interest_match * 0.15, 0, 1) estimated
  branch media_like p = clamp(0.08 + activity * 0.12 + interest_match * 0.25, 0, 1) estimated
  branch media_share p = clamp(0.02 + activity * 0.20 + agreement * 0.15 + outrage * 0.20 + trust * 0.10 + friends_sharing * 0.10 + clamp(0.10 + place.engagement * 0.001 + interest_match * 0.30 - place.age_hours * 0.01, 0, 1) * 0.20, 0, 1) estimated
  branch media_follow p = clamp(interest_match * 0.15 + trust * 0.10, 0, 1) estimated
  branch media_mute p = clamp(fatigue * 0.20 + (1 - trust) * 0.10, 0, 1) estimated
  branch media_scroll p = clamp(0.10 + fatigue * 0.30, 0, 1) estimated
  branch media_viral p = clamp((place.engagement - 30) / 100, 0, 0.35) estimated
  branch spotlight_post p = 1.0 if role.influencer estimated
  branch media_idle p = clamp(0.20 + fatigue * 0.20, 0, 1) estimated

decision physical_day:
  branch protest p = clamp(0.50 + media_outrage * 0.20 + stress * 0.05, 0, 0.9) estimated
  branch physical_idle p = 1.0 estimated

action media_post:
  aggregate = posts
  duration = Triangular(min=0.05, median=0.20, max=0.50) estimated
  outcome posted p = 0.90 estimated:
    effect self.outrage += 0.001 estimated
    effect place Feed sentiment += sentiment * 0.01 estimated
    effect place Feed engagement += 1 estimated
    next = at_feed
  outcome skipped p = 0.10 estimated:
    next = at_feed

action media_comment:
  aggregate = comments
  duration = Triangular(min=0.05, median=0.15, max=0.40) estimated
  target = random at Feed
  outcome commented p = 0.85 estimated:
    effect place Feed engagement += 0.5 estimated
    next = at_feed
  outcome skipped p = 0.15 estimated:
    next = at_feed

action media_like:
  aggregate = likes
  duration = Triangular(min=0.02, median=0.05, max=0.15) estimated
  target = random at Feed
  outcome liked p = 0.92 estimated:
    effect place Feed engagement += 0.2 estimated
    next = at_feed
  outcome skipped p = 0.08 estimated:
    next = at_feed

action media_share:
  aggregate = shares
  duration = Triangular(min=0.03, median=0.10, max=0.30) estimated
  target = random at Feed
  outcome shared p = 0.82 estimated:
    effect place Feed engagement += 1.5 estimated
    effect place Feed outrage += outrage * 0.01 estimated
    next = at_feed
  outcome skipped p = 0.18 estimated:
    next = at_feed

action media_follow:
  aggregate = follows
  duration = Triangular(min=0.03, median=0.08, max=0.20) estimated
  target = random at Feed
  outcome followed p = 0.75 estimated:
    effect relationship with target trust += 0.10 estimated
    next = at_feed
  outcome skipped p = 0.25 estimated:
    next = at_feed

action media_mute:
  aggregate = mutes
  duration = Triangular(min=0.03, median=0.08, max=0.20) estimated
  target = random at Feed
  outcome muted p = 0.70 estimated:
    effect self.fatigue -= 0.05 estimated
    next = at_feed
  outcome skipped p = 0.30 estimated:
    next = at_feed

action media_scroll:
  aggregate = scrolls
  duration = Triangular(min=0.05, median=0.20, max=0.50) estimated
  outcome scrolled p = 0.95 estimated:
    effect self.fatigue += 0.01 estimated
    effect place Feed age_hours += 0.05 estimated
    next = at_feed
  outcome stopped p = 0.05 estimated:
    next = at_feed

action media_viral:
  aggregate = viral_posts
  duration = Triangular(min=0.03, median=0.10, max=0.25) estimated
  outcome spread p = 0.80 estimated:
    effect place Feed viral_posts += 1 estimated
    effect place Feed engagement += 3 estimated
    effect self.outrage += 0.002 estimated
    next = at_feed
  outcome faded p = 0.20 estimated:
    next = at_feed

action spotlight_post:
  aggregate = spotlight_posts
  duration = Triangular(min=0.05, median=0.15, max=0.40) estimated
  record = topic, sentiment, source, place.engagement, place.age_hours
  outcome amplified p = 0.95 estimated:
    effect place Feed sentiment += sentiment * 0.12 estimated
    effect place Feed outrage += outrage * 0.10 estimated
    effect all at Feed sentiment where agent != self += sentiment * 0.0001 estimated
    effect all at Feed sentiment where agent != self *= 1 + outrage * 0.00002 estimated
    effect all at Feed outrage where agent != self += 0.0001 estimated
    effect place Feed engagement += 8 estimated
    next = at_feed
  outcome ignored p = 0.05 estimated:
    next = at_feed

action media_idle:
  aggregate = idle
  duration = Triangular(min=0.05, median=0.20, max=0.50) estimated
  outcome waited p = 1.0 estimated:
    next = at_feed

action protest:
  aggregate = protests
  duration = Triangular(min=0.20, median=0.50, max=0.90) estimated
  outcome joined p = 0.80 estimated:
    effect self.stress += 0.02 estimated
    effect place Square crowd += 1 estimated
    next = physical_day
  outcome stayed p = 0.20 estimated:
    next = physical_day

action physical_idle:
  aggregate = physical_idle
  duration = Triangular(min=0.20, median=0.50, max=0.90) estimated
  outcome stayed p = 1.0 estimated:
    effect self.stress -= 0.002 estimated
    next = physical_day

composition PersonalFinance:
  level = community
  represented_population = 5000000
  children:
    UserActive: weight = 20
    UserLurker: weight = 60
    UserPoster: weight = 20
    InfluencerX: weight = 1
  places = Feed
  parameters:
    norm_strictness = 0.25
    moderation_compliance = 0.80
    topic_closure = 0.10
    viral_threshold = 30
  policies = ModerationPolicy
  cached:
    sync = 1 days
    max_iterations = 3
    tolerance = 0.01
    feedback:
      mean_outrage -> feedback_signal scale = 0.10
  output population = count()
  output represented_population = represented_count()
  output posting_rate = action_rate(posts, window=day)
  output comment_rate = action_rate(comments, window=day)
  output like_rate = action_rate(likes, window=day)
  output share_rate = action_rate(shares, window=day)
  output mean_sentiment = mean(sentiment) with sd
  output mean_outrage = mean(outrage) with sd
  output polarization = sd(sentiment)
  output viral_posts = action_count(viral_posts, window=day)
  output spotlight_posts = action_count(spotlight_posts, window=day)

composition CivicForum:
  level = community
  represented_population = 3000000
  children:
    UserActive: weight = 15
    UserLurker: weight = 65
    UserPoster: weight = 20
  places = Feed
  parameters:
    norm_strictness = 0.85
    moderation_compliance = 0.80
    topic_closure = 0.20
    viral_threshold = 30
  policies = ModerationPolicy
  cached:
    sync = 1 days
    max_iterations = 3
    tolerance = 0.01
    feedback:
      mean_outrage -> feedback_signal scale = 0.10
  output population = count()
  output represented_population = represented_count()
  output posting_rate = action_rate(posts, window=day)
  output comment_rate = action_rate(comments, window=day)
  output like_rate = action_rate(likes, window=day)
  output share_rate = action_rate(shares, window=day)
  output mean_sentiment = mean(sentiment) with sd
  output mean_outrage = mean(outrage) with sd
  output polarization = sd(sentiment)
  output viral_posts = action_count(viral_posts, window=day)
  output spotlight_posts = action_count(spotlight_posts, window=day)

composition Reddit:
  level = platform
  represented_population = 8000000
  children:
    PersonalFinance: weight = 5
    CivicForum: weight = 3
  places = Feed
  parameters:
    viral_threshold = 5
  adjacency:
    PersonalFinance <-> CivicForum distance = 1
  flows:
    viral_spread PersonalFinance -> CivicForum rate = formula(clamp((PersonalFinance_viral_posts - viral_threshold) / 100, 0, 0.50)) effect = diffusion
    audience_shift PersonalFinance -> CivicForum rate = formula(clamp(0.002 + PersonalFinance_mean_outrage * 0.002, 0, 0.01)) effect = transfer
  cached:
    sync = 1 days
    max_iterations = 3
    tolerance = 0.01
    feedback:
      mean_outrage -> feedback_signal scale = 0.05
  output population = count()
  output represented_population = represented_count()
  output posting_rate = action_rate(posts, window=day)
  output comment_rate = action_rate(comments, window=day)
  output like_rate = action_rate(likes, window=day)
  output share_rate = action_rate(shares, window=day)
  output mean_sentiment = mean(sentiment) with sd
  output mean_outrage = mean(outrage) with sd
  output polarization = sd(sentiment)
  output viral_posts = action_count(viral_posts, window=day)
  output spotlight_posts = action_count(spotlight_posts, window=day)
  output viral_spread = flow_rate(viral_spread)

composition PhysicalTown:
  level = physical_module
  children:
    PhysicalMass: weight = 100
  places = Square
  cached:
    sync = 1 days
    max_iterations = 2
    tolerance = 0.01
  output population = count()
  output protest_rate = action_rate(protests, window=day)
  output fights_per_day = action_count(protests, window=day)
  output mean_stress = mean(stress) with sd
  output vote_liberal_share = mean(vote_liberal) with sd

composition CoupledTownMedia:
  level = coupled_modules
  children:
    PhysicalTown: weight = 1
    Reddit: weight = 1
  cached:
    sync = 1 days
    max_iterations = 5
    tolerance = 0.01
  couplings:
    physical_to_media PhysicalTown -> Reddit input = signal value = formula(clamp(PhysicalTown_fights_per_day / 100 + external_event * 0.20, 0, 1)) cadence = sync
    media_outage_to_physical Reddit -> PhysicalTown input = media_outrage value = formula(clamp(Reddit_mean_outrage, 0, 1)) cadence = sync
    media_sentiment_to_physical Reddit -> PhysicalTown input = media_sentiment value = formula(clamp(Reddit_mean_sentiment, -1, 1)) cadence = sync
  boundaries:
    citizen_media_identity PhysicalTown -> Reddit fields = political_lean, trust, stress
  output population = count()
  output posting_rate = action_rate(posts, window=day)
  output share_rate = action_rate(shares, window=day)
  output mean_sentiment = mean(sentiment) with sd
  output mean_outrage = mean(outrage) with sd
  output polarization = sd(sentiment)
  output protest_rate = action_rate(protests, window=day)
  output mean_stress = mean(stress) with sd
  output vote_liberal_share = mean(vote_liberal) with sd
  output fights_per_day = action_count(protests, window=day)
  output physical_to_media = flow_rate(physical_to_media)
  output media_to_physical = flow_rate(media_outage_to_physical)

composition_population MediaUsers:
  Reddit: represented = 8000000

aggregate_function UserActive:
  inputs:
    norm_strictness = 0.5 range 0..1
    signal = 0 range 0..1
    feedback_signal = 0 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(norm_strictness, signal, feedback_signal)
    posting_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(posts, window=day)
    comment_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(comments, window=day)
    like_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(likes, window=day)
    share_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(shares, window=day)
    mean_sentiment = formula(norm_strictness, signal, feedback_signal)
    mean_outrage = formula(norm_strictness, signal, feedback_signal)
    polarization = formula(norm_strictness, signal, feedback_signal)
    viral_posts = formula(norm_strictness, signal, feedback_signal) from action_count(viral_posts, window=day)
    spotlight_posts = formula(norm_strictness, signal, feedback_signal) from action_count(spotlight_posts, window=day)
  cache:
    valid_for = 30 days
    inputs_hash = hash(norm_strictness, signal, feedback_signal)
    invalidate_on:
      norm_strictness change > 1.00
      signal change > 1.00
      feedback_signal change > 1.00
      event = spotlight_post, physical_event, moderation_change

aggregate_function UserLurker:
  inputs:
    norm_strictness = 0.5 range 0..1
    signal = 0 range 0..1
    feedback_signal = 0 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(norm_strictness, signal, feedback_signal)
    posting_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(posts, window=day)
    comment_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(comments, window=day)
    like_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(likes, window=day)
    share_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(shares, window=day)
    mean_sentiment = formula(norm_strictness, signal, feedback_signal)
    mean_outrage = formula(norm_strictness, signal, feedback_signal)
    polarization = formula(norm_strictness, signal, feedback_signal)
    viral_posts = formula(norm_strictness, signal, feedback_signal) from action_count(viral_posts, window=day)
    spotlight_posts = formula(norm_strictness, signal, feedback_signal) from action_count(spotlight_posts, window=day)
  cache:
    valid_for = 30 days
    inputs_hash = hash(norm_strictness, signal, feedback_signal)
    invalidate_on:
      norm_strictness change > 1.00
      signal change > 1.00
      feedback_signal change > 1.00
      event = spotlight_post, physical_event, moderation_change

aggregate_function UserPoster:
  inputs:
    norm_strictness = 0.5 range 0..1
    signal = 0 range 0..1
    feedback_signal = 0 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(norm_strictness, signal, feedback_signal)
    posting_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(posts, window=day)
    comment_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(comments, window=day)
    like_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(likes, window=day)
    share_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(shares, window=day)
    mean_sentiment = formula(norm_strictness, signal, feedback_signal)
    mean_outrage = formula(norm_strictness, signal, feedback_signal)
    polarization = formula(norm_strictness, signal, feedback_signal)
    viral_posts = formula(norm_strictness, signal, feedback_signal) from action_count(viral_posts, window=day)
    spotlight_posts = formula(norm_strictness, signal, feedback_signal) from action_count(spotlight_posts, window=day)
  cache:
    valid_for = 30 days
    inputs_hash = hash(norm_strictness, signal, feedback_signal)
    invalidate_on:
      norm_strictness change > 1.00
      signal change > 1.00
      feedback_signal change > 1.00
      event = spotlight_post, physical_event, moderation_change

aggregate_function InfluencerX:
  inputs:
    norm_strictness = 0.5 range 0..1
    signal = 0 range 0..1
    feedback_signal = 0 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(norm_strictness, signal, feedback_signal)
    posting_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(posts, window=day)
    comment_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(comments, window=day)
    like_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(likes, window=day)
    share_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(shares, window=day)
    mean_sentiment = formula(norm_strictness, signal, feedback_signal)
    mean_outrage = formula(norm_strictness, signal, feedback_signal)
    polarization = formula(norm_strictness, signal, feedback_signal)
    viral_posts = formula(norm_strictness, signal, feedback_signal) from action_count(viral_posts, window=day)
    spotlight_posts = formula(norm_strictness, signal, feedback_signal) from action_count(spotlight_posts, window=day)
  cache:
    valid_for = 30 days
    inputs_hash = hash(norm_strictness, signal, feedback_signal)
    invalidate_on:
      norm_strictness change > 1.00
      signal change > 1.00
      feedback_signal change > 1.00
      event = spotlight_post, physical_event, moderation_change

aggregate_function PersonalFinance:
  inputs:
    norm_strictness = 0.5 range 0..1
    signal = 0 range 0..1
    feedback_signal = 0 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  effects:
    decision media_share *= 1 + signal * 0.30
    field sentiment = 0.30 + signal * 0.05
    field outrage = 0.45 + signal * 0.10 + feedback_signal * 0.02
  outputs:
    population = formula(norm_strictness, signal, feedback_signal)
    posting_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(posts, window=day)
    comment_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(comments, window=day)
    like_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(likes, window=day)
    share_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(shares, window=day)
    mean_sentiment = formula(norm_strictness, signal, feedback_signal)
    mean_outrage = formula(norm_strictness, signal, feedback_signal)
    polarization = formula(norm_strictness, signal, feedback_signal)
    viral_posts = formula(norm_strictness, signal, feedback_signal) from action_count(viral_posts, window=day)
    spotlight_posts = formula(norm_strictness, signal, feedback_signal) from action_count(spotlight_posts, window=day)
  cache:
    valid_for = 30 days
    inputs_hash = hash(norm_strictness, signal, feedback_signal)
    invalidate_on:
      norm_strictness change > 0.10
      signal change > 0.10
      feedback_signal change > 1.00
      event = spotlight_post, physical_event, moderation_change

aggregate_function CivicForum:
  inputs:
    norm_strictness = 0.5 range 0..1
    signal = 0 range 0..1
    feedback_signal = 0 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  effects:
    decision media_share *= 1 + signal * 0.30
    field sentiment = 0.30 + signal * 0.05
    field outrage = 0.45 + signal * 0.10 + feedback_signal * 0.02
  outputs:
    population = formula(norm_strictness, signal, feedback_signal)
    posting_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(posts, window=day)
    comment_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(comments, window=day)
    like_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(likes, window=day)
    share_rate = formula(norm_strictness, signal, feedback_signal) from action_rate(shares, window=day)
    mean_sentiment = formula(norm_strictness, signal, feedback_signal)
    mean_outrage = formula(norm_strictness, signal, feedback_signal)
    polarization = formula(norm_strictness, signal, feedback_signal)
    viral_posts = formula(norm_strictness, signal, feedback_signal) from action_count(viral_posts, window=day)
    spotlight_posts = formula(norm_strictness, signal, feedback_signal) from action_count(spotlight_posts, window=day)
  cache:
    valid_for = 30 days
    inputs_hash = hash(norm_strictness, signal, feedback_signal)
    invalidate_on:
      norm_strictness change > 0.10
      signal change > 0.10
      feedback_signal change > 1.00
      event = spotlight_post, physical_event, moderation_change

aggregate_function Reddit:
  inputs:
    signal = 0 range 0..1
    feedback_signal = 0 range 0..1
    viral_threshold = 5 range 0..1000
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(signal, feedback_signal, viral_threshold)
    represented_population = formula(signal, feedback_signal, viral_threshold)
    posting_rate = formula(signal, feedback_signal, viral_threshold)
    comment_rate = formula(signal, feedback_signal, viral_threshold)
    like_rate = formula(signal, feedback_signal, viral_threshold)
    share_rate = formula(signal, feedback_signal, viral_threshold)
    mean_sentiment = formula(signal, feedback_signal, viral_threshold)
    mean_outrage = formula(signal, feedback_signal, viral_threshold)
    polarization = formula(signal, feedback_signal, viral_threshold)
    viral_posts = formula(signal, feedback_signal, viral_threshold)
    spotlight_posts = formula(signal, feedback_signal, viral_threshold)
    viral_spread = formula(signal, feedback_signal, viral_threshold)
  cache:
    valid_for = 30 days
    inputs_hash = hash(signal, feedback_signal, viral_threshold)
    invalidate_on:
      signal change > 0.10
      feedback_signal change > 1.00
      viral_threshold change > 10
      event = spotlight_post, physical_event, moderation_change

aggregate_function PhysicalMass:
  inputs:
    media_outrage = 0 range 0..1
    media_sentiment = 0 range -1..1
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(media_outrage, media_sentiment)
    protest_rate = formula(media_outrage, media_sentiment) from action_rate(protests, window=day)
    fights_per_day = formula(media_outrage, media_sentiment) from action_count(protests, window=day)
    mean_stress = formula(media_outrage, media_sentiment)
    vote_liberal_share = formula(media_outrage, media_sentiment)
  cache:
    valid_for = 30 days
    inputs_hash = hash(media_outrage, media_sentiment)
    invalidate_on:
      media_outrage change > 1.00
      media_sentiment change > 2.00
      event = media_spike

aggregate_function PhysicalTown:
  inputs:
    media_outrage = 0 range 0..1
    media_sentiment = 0 range -1..1
  time = 30 days
  time_points = 1, 15, 30
  effects:
    decision protest *= 1 + media_outrage * 0.20
    field stress += media_outrage * 0.10
    field vote_liberal = 0.5 + media_sentiment * 0.15
  outputs:
    population = formula(media_outrage, media_sentiment)
    protest_rate = formula(media_outrage, media_sentiment)
    fights_per_day = formula(media_outrage, media_sentiment)
    mean_stress = formula(media_outrage, media_sentiment)
    vote_liberal_share = formula(media_outrage, media_sentiment)
  cache:
    valid_for = 30 days
    inputs_hash = hash(media_outrage, media_sentiment)
    invalidate_on:
      media_outrage change > 0.10
      media_sentiment change > 0.10
      event = media_spike

aggregate_function CoupledTownMedia:
  inputs:
    external_event = 0 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(external_event)
    posting_rate = formula(external_event)
    share_rate = formula(external_event)
    mean_sentiment = formula(external_event)
    mean_outrage = formula(external_event)
    polarization = formula(external_event)
    protest_rate = formula(external_event)
    mean_stress = formula(external_event)
    vote_liberal_share = formula(external_event)
    fights_per_day = formula(external_event)
    physical_to_media = formula(external_event)
    media_to_physical = formula(external_event)
  cache:
    valid_for = 30 days
    inputs_hash = hash(external_event)
    invalidate_on:
      external_event change > 0.10
      event = spotlight_post, physical_event, media_spike

place Store:
  scope = composition
  state cash = 100 range 0..100000 estimated
  state revenue = 0 range 0..100000 estimated
  state price = 10 range 0..1000 estimated
  state wage = 5 range 0..1000 estimated
  state costs = 0 range 0..100000 estimated
  state profit = 0 range -100000..100000 estimated
  state open = 1 range 0..1 estimated
  state worker_count = 1 range 0..1000 estimated

agent RetailPerson:
  scope = composition
  state money range 0..100000 estimated
  state stress range 0..1 estimated
  state employer
  state employed
  state location
  initial:
    money ~ Uniform(min=0, max=0) placeholder
    stress ~ Uniform(min=0.2, max=0.2) placeholder
    employer ~ Categorical(none: 1.0) placeholder
    employed ~ Bernoulli(p=0) placeholder
    location ~ Categorical(Store: 1.0) placeholder
  routine = idle_day

agent Customer inherits RetailPerson:
  scope = composition
  role customer
  initial:
    money ~ Uniform(min=100, max=100) placeholder
  routine = customer_day

agent Cashier inherits RetailPerson:
  scope = composition
  role cashier
  initial:
    employer ~ Categorical(Store: 1.0) placeholder
    employed ~ Bernoulli(p=1) placeholder
  routine = cashier_day

agent ManagedCashier inherits Cashier:
  scope = composition
  routine = employment_day

agent StoreManager inherits RetailPerson:
  scope = composition
  role manager
  initial:
    employer ~ Categorical(Store: 1.0) placeholder
    employed ~ Bernoulli(p=1) placeholder
  routine = manager_day

agent FamilyOwner inherits StoreManager:
  scope = composition
  role owner
  routine = family_owner_day

archetype StoreTeam:
  sample_households = 1
  composition:
    customers count = 1 mix Customer:1.0
    cashiers count = 1 mix Cashier:1.0
  output population = count()
  output mean_money = mean(money)
  output mean_stress = mean(stress)
  output purchase_count = action_count(purchases, window=run)
  output work_count = action_count(work_shifts, window=run)

archetype ManagedStoreTeam:
  sample_households = 1
  composition:
    customers count = 1 mix Customer:1.0
    cashiers count = 1 mix ManagedCashier:1.0
    managers count = 1 mix StoreManager:1.0
  output population = count()
  output mean_money = mean(money)
  output mean_stress = mean(stress)
  output purchase_count = action_count(purchases, window=run)
  output work_count = action_count(work_shifts, window=run)

archetype FamilyStoreTeam:
  sample_households = 1
  composition:
    customers count = 1 mix Customer:1.0
    cashiers count = 1 mix ManagedCashier:1.0
    owners count = 1 mix FamilyOwner:1.0
  output population = count()
  output mean_money = mean(money)
  output mean_stress = mean(stress)
  output purchase_count = action_count(purchases, window=run)
  output work_count = action_count(work_shifts, window=run)

decision idle_day:
  branch idle p = 1.0 estimated

decision customer_day:
  branch idle p = 0 estimated

decision cashier_day:
  branch idle p = 0 estimated

decision employment_day:
  branch idle p = 0 estimated
  branch idle p = 0 estimated
  branch idle p = 0 estimated

decision manager_day:
  branch idle p = 0 estimated
  branch idle p = 0 estimated
  branch idle p = 0 estimated
  branch idle p = 0 estimated

decision family_owner_day:
  branch idle p = 0 estimated
  branch idle p = 0 estimated

action idle:
  aggregate = idle
  duration = Triangular(min=0.2, median=0.5, max=0.9) estimated
  outcome waited p = 1.0 estimated:
    next = idle_day

action buy:
  aggregate = purchases
  duration = Triangular(min=0.2, median=0.5, max=0.9) estimated
  target = random at current place where target.role.cashier
  outcome purchased p = 1.0 if money >= place.price estimated:
    effect self.money -= place.price estimated
    effect current place cash += place.price estimated
    effect current place revenue += place.price estimated
    next = customer_day
  outcome declined p = 1.0 if money < place.price estimated:
    next = customer_day

action work_cashier:
  aggregate = work_shifts
  duration = Triangular(min=0.2, median=0.5, max=0.9) estimated
  target = random at current place where target.role.customer
  outcome served p = 1.0 if place.cash >= place.wage estimated:
    effect current place cash -= place.wage estimated
    effect self.money += place.wage estimated
    effect self.stress += 0.01 estimated
    next = cashier_day
  outcome unpaid p = 1.0 if place.cash < place.wage estimated:
    next = cashier_day

action quit_job:
  aggregate = employment_changes
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome quit p = 1.0 estimated:
    effect self.employer = None estimated
    effect self.employed = 0 estimated
    effect current place worker_count -= 1 estimated
    next = employment_day

action job_search:
  aggregate = employment_searches
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  target = random at current place where target.role.manager or target.role.owner
  outcome hired p = 0.25 if target.employed estimated:
    effect self.employer = Store estimated
    effect self.employed = 1 estimated
    effect current place worker_count += 1 estimated
    effect relationship with target employment += 1 estimated
    next = employment_day
  outcome searching p = 0.75 estimated:
    next = employment_day

action manage_store:
  aggregate = management
  duration = Triangular(min=0.1, median=0.3, max=0.8) estimated
  outcome managed p = 1.0 estimated:
    effect current place price *= 1.0001 estimated
    effect current place wage *= 1.00005 estimated
    next = manager_day

action family_manage:
  aggregate = management
  duration = Triangular(min=0.1, median=0.3, max=0.8) estimated
  outcome managed p = 1.0 estimated:
    effect current place price *= 1.0001 estimated
    effect current place wage *= 1.00005 estimated
    next = family_owner_day

action fire_worker:
  aggregate = employment_changes
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  target = random at current place where target.role.cashier and target.employed
  outcome fired p = 1.0 estimated:
    effect target.employer = None estimated
    effect target.employed = 0 estimated
    effect current place worker_count -= 1 estimated
    target_next = employment_day
    next = manager_day

action close_store:
  aggregate = store_status_changes
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome closed p = 1.0 estimated:
    effect current place open = 0 estimated
    next = manager_day

action reopen_store:
  aggregate = store_status_changes
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome reopened p = 1.0 estimated:
    effect current place open = 1 estimated
    next = manager_day

action owner_payout:
  aggregate = owner_payouts
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome paid p = 1.0 estimated:
    effect self.money += place.cash * 0.10 estimated
    effect current place cash -= place.cash * 0.10 estimated
    next = family_owner_day

composition TransactionStore:
  level = site
  children:
    StoreTeam: weight = 1
  places = Store
  output population = count()
  output mean_money = mean(money)
  output mean_stress = mean(stress)
  output purchase_count = action_count(purchases, window=run)
  output work_count = action_count(work_shifts, window=run)
  output cash = place_state(Store, cash)
  output revenue = place_state(Store, revenue)

composition StoreA:
  level = site
  allocation_leaf = true
  children:
    ManagedStoreTeam: weight = 1
  places = Store
  parameters:
    revenue = 100
    wages = 20
    rent = 10
    franchise_fee = 5
    price_policy = 1
    wage_policy = 1
  cached:
    sync = 1 days
    max_iterations = 2
    tolerance = 0.01
  output population = count()
  output revenue = formula(revenue * price_policy)
  output wages = formula(wages * wage_policy)
  output costs = formula(wages * wage_policy + rent + franchise_fee)
  output profit = formula(revenue * price_policy - wages * wage_policy - rent - franchise_fee)
  output payout = formula(profit)
  output cash = formula(0)

composition StoreB:
  level = site
  allocation_leaf = true
  children:
    ManagedStoreTeam: weight = 1
  places = Store
  parameters:
    revenue = 80
    wages = 18
    rent = 8
    franchise_fee = 4
    price_policy = 1
    wage_policy = 1
  cached:
    sync = 1 days
    max_iterations = 2
    tolerance = 0.01
  output population = count()
  output revenue = formula(revenue * price_policy)
  output wages = formula(wages * wage_policy)
  output costs = formula(wages * wage_policy + rent + franchise_fee)
  output profit = formula(revenue * price_policy - wages * wage_policy - rent - franchise_fee)
  output payout = formula(profit)
  output cash = formula(0)

composition FamilyStore:
  level = site
  allocation_leaf = true
  children:
    FamilyStoreTeam: weight = 1
  places = Store
  parameters:
    revenue = 60
    wages = 15
    rent = 5
    franchise_fee = 0
    price_policy = 1
    wage_policy = 1
  cached:
    sync = 1 days
    max_iterations = 2
    tolerance = 0.01
  output population = count()
  output revenue = formula(revenue * price_policy)
  output wages = formula(wages * wage_policy)
  output costs = formula(wages * wage_policy + rent + franchise_fee)
  output profit = formula(revenue * price_policy - wages * wage_policy - rent - franchise_fee)
  output payout = formula(profit)
  output cash = formula(0)
  output owner_payout = formula(profit)

composition StoreC:
  level = site
  allocation_leaf = true
  children:
    ManagedStoreTeam: weight = 1
  places = Store
  parameters:
    revenue = 90
    wages = 19
    rent = 9
    franchise_fee = 4
    price_policy = 1
    wage_policy = 1
  cached:
    sync = 1 days
    max_iterations = 2
    tolerance = 0.01
  output population = count()
  output revenue = formula(revenue * price_policy)
  output wages = formula(wages * wage_policy)
  output costs = formula(wages * wage_policy + rent + franchise_fee)
  output profit = formula(revenue * price_policy - wages * wage_policy - rent - franchise_fee)
  output payout = formula(profit)
  output cash = formula(0)

composition StoreD:
  level = site
  allocation_leaf = true
  children:
    ManagedStoreTeam: weight = 1
  places = Store
  parameters:
    revenue = 70
    wages = 16
    rent = 7
    franchise_fee = 3
    price_policy = 1
    wage_policy = 1
  cached:
    sync = 1 days
    max_iterations = 2
    tolerance = 0.01
  output population = count()
  output revenue = formula(revenue * price_policy)
  output wages = formula(wages * wage_policy)
  output costs = formula(wages * wage_policy + rent + franchise_fee)
  output profit = formula(revenue * price_policy - wages * wage_policy - rent - franchise_fee)
  output payout = formula(profit)
  output cash = formula(0)

composition FranchiseOne:
  level = branch
  children:
    StoreA: weight = 1
    StoreB: weight = 1
  parameters:
    costs = 7
    price_policy = 1
    wage_policy = 1
  cached:
    sync = 30 days
    max_iterations = 3
    tolerance = 0.01
  output population = count()
  output revenue = formula(sum.revenue)
  output wages = formula(sum.wages)
  output costs = formula(costs)
  output profit = formula(sum.payout - costs)
  output payout = formula(profit)
  output cash = formula(0)

composition FranchiseTwo:
  level = branch
  children:
    StoreC: weight = 1
  parameters:
    costs = 6
    price_policy = 1
    wage_policy = 1
  cached:
    sync = 30 days
    max_iterations = 3
    tolerance = 0.01
  output population = count()
  output revenue = formula(sum.revenue)
  output wages = formula(sum.wages)
  output costs = formula(costs)
  output profit = formula(sum.payout - costs)
  output payout = formula(profit)
  output cash = formula(0)

composition BrandOne:
  level = label
  children:
    FranchiseOne: weight = 1
    FranchiseTwo: weight = 1
  parameters:
    costs = 9
    price_policy = 1
    wage_policy = 1
  cached:
    sync = 90 days
    max_iterations = 3
    tolerance = 0.01
  output population = count()
  output revenue = formula(sum.revenue)
  output wages = formula(sum.wages)
  output costs = formula(costs)
  output profit = formula(sum.payout - costs)
  output payout = formula(profit)
  output cash = formula(0)

composition BrandTwo:
  level = label
  children:
    StoreD: weight = 1
  parameters:
    costs = 3
    price_policy = 1
    wage_policy = 1
  cached:
    sync = 90 days
    max_iterations = 3
    tolerance = 0.01
  output population = count()
  output revenue = formula(sum.revenue)
  output wages = formula(sum.wages)
  output costs = formula(costs)
  output profit = formula(sum.payout - costs)
  output payout = formula(profit)
  output cash = formula(0)

composition ConglomerateRoot:
  level = parent
  children:
    BrandOne: weight = 1
    BrandTwo: weight = 1
  parameters:
    costs = 11
    debt = 50
    valuation_multiple = 10
    price_policy = 1
    wage_policy = 1
  cached:
    sync = 90 days
    max_iterations = 3
    tolerance = 0.01
  output population = count()
  output revenue = formula(sum.revenue)
  output wages = formula(sum.wages)
  output profit = formula(sum.payout - costs)
  output cash = formula(profit)
  output debt = formula(debt)
  output market_cap = formula(profit * valuation_multiple - debt)

composition CorporateForest:
  level = forest
  children:
    ConglomerateRoot: weight = 1
    FamilyStore: weight = 1
  parameters:
    price_policy = 1
    wage_policy = 1
  cached:
    sync = 90 days
    max_iterations = 3
    tolerance = 0.01
  output population = count()
  output total_revenue = formula(sum.revenue)
  output total_wages = formula(sum.wages)
  output total_profit = formula(sum.profit)
  output conglomerate_profit = formula(ConglomerateRoot.profit)
  output independent_profit = formula(FamilyStore.profit)

composition PhysicalRetail:
  level = physical_module
  children:
    StoreTeam: weight = 1
  places = Store
  cached:
    sync = 1 days
    max_iterations = 2
    tolerance = 0.01
  output population = count()
  output purchase_count = action_count(purchases, window=day)
  output work_count = action_count(work_shifts, window=day)
  output mean_money = mean(money)
  output mean_stress = mean(stress)

composition CoupledPhysicalCorporate:
  level = coupled_modules
  children:
    PhysicalRetail: weight = 1
    CorporateForest: weight = 1
  cached:
    sync = 90 days
    max_iterations = 5
    tolerance = 0.01
  couplings:
    demand_to_price PhysicalRetail -> CorporateForest input = price_policy value = formula(clamp(1 + PhysicalRetail_purchase_count * 0, 0.5, 2)) cadence = sync
    profit_to_demand CorporateForest -> PhysicalRetail input = demand value = formula(clamp(CorporateForest_total_profit / 500, 0, 1)) cadence = sync
  boundaries:
    retail_identity PhysicalRetail -> CorporateForest fields = money, stress
  output population = count()
  output purchase_count = action_count(purchases, window=day)
  output work_count = action_count(work_shifts, window=day)
  output mean_money = mean(money)
  output mean_stress = mean(stress)
  output total_profit = formula(CorporateForest.total_profit)
  output demand_to_price = flow_rate(demand_to_price)
  output profit_to_demand = flow_rate(profit_to_demand)

composition NorthStores:
  level = area
  children:
    StoreA: weight = 0.5 count = 2
    StoreB: weight = 0.5 count = 2
  output population = count()

composition SouthStores:
  level = area
  children:
    FamilyStore: weight = 1.0 count = 3
  output population = count()

composition RegionalStores:
  level = allocation
  authoritative_total = 7
  sample_budget = 3
  children:
    NorthStores: weight = 0.5
    SouthStores: weight = 0.5
  output population = count()
  output represented_total = represented_total()

composition DallasStores:
  level = municipality_allocation
  children:
    StoreA: weight = 0.5
    StoreB: weight = 0.5
  output population = count()

composition AustinStores:
  level = municipality_allocation
  children:
    StoreC: weight = 1.0
  output population = count()

composition HoustonStores:
  level = municipality_allocation
  children:
    StoreD: weight = 1.0
  output population = count()

composition TexasStoreDistribution:
  level = division_allocation
  authoritative_total = 500
  sample_budget = 30
  children:
    DallasStores: weight = 0.40
    AustinStores: weight = 0.30
    HoustonStores: weight = 0.30
  output population = count()
  output represented_total = represented_total()

aggregate_function StoreTeam:
  inputs:
    demand = 0.5 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(demand)
    mean_money = formula(demand)
    mean_stress = formula(demand)
    purchase_count = formula(demand) from action_count(purchases, window=run)
    work_count = formula(demand) from action_count(work_shifts, window=run)
  cache:
    valid_for = 90 days
    inputs_hash = hash(demand)
    invalidate_on:
      demand change > 1
      event = demand_change

aggregate_function ManagedStoreTeam:
  inputs:
    demand = 0.5 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(demand)
    mean_money = formula(demand)
    mean_stress = formula(demand)
    purchase_count = formula(demand) from action_count(purchases, window=run)
    work_count = formula(demand) from action_count(work_shifts, window=run)
  cache:
    valid_for = 90 days
    inputs_hash = hash(demand)
    invalidate_on:
      demand change > 0.05
      event = demand_change

aggregate_function FamilyStoreTeam:
  inputs:
    demand = 0.5 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(demand)
    mean_money = formula(demand)
    mean_stress = formula(demand)
    purchase_count = formula(demand) from action_count(purchases, window=run)
    work_count = formula(demand) from action_count(work_shifts, window=run)
  cache:
    valid_for = 90 days
    inputs_hash = hash(demand)
    invalidate_on:
      demand change > 0.05
      event = demand_change

aggregate_function StoreA:
  inputs:
    revenue = 100 range 0..1000
    wages = 20 range 0..1000
    rent = 10 range 0..1000
    franchise_fee = 5 range 0..1000
    price_policy = 1 range 0.5..2
    wage_policy = 1 range 0.5..2
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(revenue, wages, rent, franchise_fee, price_policy, wage_policy)
    revenue = formula(revenue, price_policy)
    wages = formula(wages, wage_policy)
    profit = formula(revenue, wages, rent, franchise_fee, price_policy, wage_policy)
  cache:
    valid_for = 90 days
    inputs_hash = hash(revenue, wages, rent, franchise_fee, price_policy, wage_policy)
    invalidate_on:
      revenue change > 1
      wages change > 1
      rent change > 1
      franchise_fee change > 1
      price_policy change > 0.01
      wage_policy change > 0.01
      event = price_change, wage_change

aggregate_function StoreB:
  inputs:
    revenue = 80 range 0..1000
    wages = 18 range 0..1000
    rent = 8 range 0..1000
    franchise_fee = 4 range 0..1000
    price_policy = 1 range 0.5..2
    wage_policy = 1 range 0.5..2
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(revenue, wages, rent, franchise_fee, price_policy, wage_policy)
    revenue = formula(revenue, price_policy)
    wages = formula(wages, wage_policy)
    profit = formula(revenue, wages, rent, franchise_fee, price_policy, wage_policy)
  cache:
    valid_for = 90 days
    inputs_hash = hash(revenue, wages, rent, franchise_fee, price_policy, wage_policy)
    invalidate_on:
      revenue change > 1
      wages change > 1
      rent change > 1
      franchise_fee change > 1
      price_policy change > 0.01
      wage_policy change > 0.01
      event = price_change, wage_change

aggregate_function FamilyStore:
  inputs:
    revenue = 60 range 0..1000
    wages = 15 range 0..1000
    rent = 5 range 0..1000
    franchise_fee = 0 range 0..1000
    price_policy = 1 range 0.5..2
    wage_policy = 1 range 0.5..2
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(revenue, wages, rent, franchise_fee, price_policy, wage_policy)
    revenue = formula(revenue, price_policy)
    wages = formula(wages, wage_policy)
    profit = formula(revenue, wages, rent, franchise_fee, price_policy, wage_policy)
  cache:
    valid_for = 90 days
    inputs_hash = hash(revenue, wages, rent, franchise_fee, price_policy, wage_policy)
    invalidate_on:
      revenue change > 1
      wages change > 1
      rent change > 1
      franchise_fee change > 1
      price_policy change > 0.01
      wage_policy change > 0.01
      event = price_change, wage_change

aggregate_function StoreC:
  inputs:
    revenue = 90 range 0..1000
    wages = 19 range 0..1000
    rent = 9 range 0..1000
    franchise_fee = 4 range 0..1000
    price_policy = 1 range 0.5..2
    wage_policy = 1 range 0.5..2
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(revenue, wages, rent, franchise_fee, price_policy, wage_policy)
    revenue = formula(revenue, price_policy)
    wages = formula(wages, wage_policy)
    profit = formula(revenue, wages, rent, franchise_fee, price_policy, wage_policy)
  cache:
    valid_for = 90 days
    inputs_hash = hash(revenue, wages, rent, franchise_fee, price_policy, wage_policy)
    invalidate_on:
      revenue change > 1
      wages change > 1
      rent change > 1
      franchise_fee change > 1
      price_policy change > 0.01
      wage_policy change > 0.01
      event = price_change, wage_change

aggregate_function StoreD:
  inputs:
    revenue = 70 range 0..1000
    wages = 16 range 0..1000
    rent = 7 range 0..1000
    franchise_fee = 3 range 0..1000
    price_policy = 1 range 0.5..2
    wage_policy = 1 range 0.5..2
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(revenue, wages, rent, franchise_fee, price_policy, wage_policy)
    revenue = formula(revenue, price_policy)
    wages = formula(wages, wage_policy)
    profit = formula(revenue, wages, rent, franchise_fee, price_policy, wage_policy)
  cache:
    valid_for = 90 days
    inputs_hash = hash(revenue, wages, rent, franchise_fee, price_policy, wage_policy)
    invalidate_on:
      revenue change > 1
      wages change > 1
      rent change > 1
      franchise_fee change > 1
      price_policy change > 0.01
      wage_policy change > 0.01
      event = price_change, wage_change

aggregate_function FranchiseOne:
  inputs:
    price_policy = 1 range 0.5..2
    wage_policy = 1 range 0.5..2
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(price_policy, wage_policy)
    revenue = formula(price_policy, wage_policy)
    wages = formula(price_policy, wage_policy)
    profit = formula(price_policy, wage_policy)
  cache:
    valid_for = 90 days
    inputs_hash = hash(price_policy, wage_policy)
    invalidate_on:
      price_policy change > 0.01
      wage_policy change > 0.01
      event = branch_change

aggregate_function FranchiseTwo:
  inputs:
    price_policy = 1 range 0.5..2
    wage_policy = 1 range 0.5..2
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(price_policy, wage_policy)
    revenue = formula(price_policy, wage_policy)
    wages = formula(price_policy, wage_policy)
    profit = formula(price_policy, wage_policy)
  cache:
    valid_for = 90 days
    inputs_hash = hash(price_policy, wage_policy)
    invalidate_on:
      price_policy change > 0.01
      wage_policy change > 0.01
      event = branch_change

aggregate_function BrandOne:
  inputs:
    price_policy = 1 range 0.5..2
    wage_policy = 1 range 0.5..2
  time = 90 days
  time_points = 1, 30, 90
  outputs:
    population = formula(price_policy, wage_policy)
    revenue = formula(price_policy, wage_policy)
    wages = formula(price_policy, wage_policy)
    profit = formula(price_policy, wage_policy)
  cache:
    valid_for = 180 days
    inputs_hash = hash(price_policy, wage_policy)
    invalidate_on:
      price_policy change > 0.01
      wage_policy change > 0.01
      event = brand_change

aggregate_function BrandTwo:
  inputs:
    price_policy = 1 range 0.5..2
    wage_policy = 1 range 0.5..2
  time = 90 days
  time_points = 1, 30, 90
  outputs:
    population = formula(price_policy, wage_policy)
    revenue = formula(price_policy, wage_policy)
    wages = formula(price_policy, wage_policy)
    profit = formula(price_policy, wage_policy)
  cache:
    valid_for = 180 days
    inputs_hash = hash(price_policy, wage_policy)
    invalidate_on:
      price_policy change > 0.01
      wage_policy change > 0.01
      event = brand_change

aggregate_function ConglomerateRoot:
  inputs:
    price_policy = 1 range 0.5..2
    wage_policy = 1 range 0.5..2
  time = 90 days
  time_points = 1, 30, 90
  outputs:
    population = formula(price_policy, wage_policy)
    revenue = formula(price_policy, wage_policy)
    wages = formula(price_policy, wage_policy)
    profit = formula(price_policy, wage_policy)
    cash = formula(price_policy, wage_policy)
    debt = formula(price_policy, wage_policy)
    market_cap = formula(price_policy, wage_policy)
  cache:
    valid_for = 180 days
    inputs_hash = hash(price_policy, wage_policy)
    invalidate_on:
      price_policy change > 0.01
      wage_policy change > 0.01
      event = capital_change

aggregate_function CorporateForest:
  inputs:
    price_policy = 1 range 0.5..2
    wage_policy = 1 range 0.5..2
  time = 90 days
  time_points = 1, 30, 90
  outputs:
    population = formula(price_policy, wage_policy)
    total_revenue = formula(price_policy, wage_policy)
    total_wages = formula(price_policy, wage_policy)
    total_profit = formula(price_policy, wage_policy)
    conglomerate_profit = formula(price_policy, wage_policy)
    independent_profit = formula(price_policy, wage_policy)
  effects:
    decision buy *= 2 - price_policy
  cache:
    valid_for = 180 days
    inputs_hash = hash(price_policy, wage_policy)
    invalidate_on:
      price_policy change > 0.01
      wage_policy change > 0.01
      event = forest_change

aggregate_function PhysicalRetail:
  inputs:
    demand = 0.5 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  effects:
    decision buy *= 0.5 + demand
  outputs:
    population = formula(demand)
    purchase_count = formula(demand)
    work_count = formula(demand)
    mean_money = formula(demand)
    mean_stress = formula(demand)
  cache:
    valid_for = 90 days
    inputs_hash = hash(demand)
    invalidate_on:
      demand change > 0.05
      event = demand_change

aggregate_function CoupledPhysicalCorporate:
  inputs:
    external_demand = 0.5 range 0..1
  time = 180 days
  time_points = 1, 30, 90, 180
  outputs:
    population = formula(external_demand)
    purchase_count = formula(external_demand)
    work_count = formula(external_demand)
    mean_money = formula(external_demand)
    mean_stress = formula(external_demand)
    total_profit = formula(external_demand)
    demand_to_price = formula(external_demand)
    profit_to_demand = formula(external_demand)
  cache:
    valid_for = 180 days
    inputs_hash = hash(external_demand)
    invalidate_on:
      external_demand change > 0.05
      event = retail_change

role customer:
  decision customer_day:
    branch buy p = 1.0 estimated

role cashier:
  decision cashier_day:
    branch work_cashier p = 1.0 if employed estimated
  decision employment_day:
    branch work_cashier p = 0.98 if employed and place.open == 1 estimated
    branch quit_job p = 0.02 if employed estimated
    branch job_search p = 1.0 if not employed estimated

role manager:
  decision manager_day:
    branch manage_store p = 0.98 if place.open == 1 estimated
    branch fire_worker p = 0.01 if place.worker_count > 0 estimated
    branch close_store p = 0.01 if place.open == 1 estimated
    branch reopen_store p = 1.0 if place.open == 0 estimated
  decision at_sync:
    branch set_store_schedule p = 1.0 if hour == 0 estimated

role owner:
  decision family_owner_day:
    branch owner_payout p = 1.0 if hour >= 23 and place.cash > 50 estimated
    branch family_manage p = 1.0 if hour < 23 estimated

action set_store_schedule:
  aggregate = store_schedules
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  record = agent, tick
  outcome set p = 1.0 estimated:
    effect self.stress += 0.001 estimated
    next = at_sync

entity ListedFirmAlpha:
  field corporate_path
  field stock_path
  field legal_identity
  link corporate = FirmAlpha
  link stock = StockAlpha

entity ListedFirmBeta:
  field corporate_path
  field stock_path
  field legal_identity
  link corporate = FirmBeta
  link stock = StockBeta

entity FamilyEnterprise:
  field corporate_path
  field legal_identity
  link corporate = FamilyBusiness

place ExchangeA:
  scope = composition
  state price = 10 range 0.01..10000 estimated
  state firm_cash = 100 range 0..100000 estimated
  state lender_cash = 1000 range 0..100000 estimated
  state firm_debt = 0 range 0..100000 estimated
  state shares_outstanding = 100 range 1..100000 estimated
  state loan_amount = 50 range 0..10000 estimated
  state repayment_amount = 20 range 0..10000 estimated
  state interest_rate = 0.05 range 0..1 estimated
  state market_sentiment = 0.2 range -1..1 estimated

place ExchangeB:
  scope = composition
  state price = 20 range 0.01..10000 estimated
  state firm_cash = 150 range 0..100000 estimated
  state lender_cash = 1200 range 0..100000 estimated
  state firm_debt = 20 range 0..100000 estimated
  state shares_outstanding = 80 range 1..100000 estimated
  state loan_amount = 40 range 0..10000 estimated
  state repayment_amount = 15 range 0..10000 estimated
  state interest_rate = 0.04 range 0..1 estimated
  state market_sentiment = 0.1 range -1..1 estimated

agent FinancialPerson:
  scope = composition
  state roles
  trait intent
  trait risk
  trait activity
  trait interest
  state money range 0..100000 estimated
  state shares range 0..100000 estimated
  state stress range 0..1 estimated
  state location
  initial:
    intent ~ Categorical(Counterparty: 1.0) placeholder
    risk ~ Uniform(min=0.5, max=0.5) placeholder
    activity ~ Uniform(min=0.5, max=0.5) placeholder
    interest ~ Uniform(min=0.5, max=0.5) placeholder
    money ~ Uniform(min=0, max=0) placeholder
    shares ~ Uniform(min=0, max=0) placeholder
    stress ~ Uniform(min=0.2, max=0.2) placeholder
    location ~ Categorical(ExchangeA: 1.0) placeholder
  routine = market_action

role trader:
  decision market_action:
    branch secondary_buy p = 1.0 if intent == Buy and money >= place.price estimated
    branch secondary_sell p = 1.0 if intent == Sell and shares >= 1 estimated
    branch new_issuance p = 1.0 if intent == Issue and money >= place.price estimated

role ceo:
  decision market_action:
    branch borrow_capital p = 1.0 if intent == Borrow and place.lender_cash >= place.loan_amount estimated
    branch accrue_interest p = 1.0 if intent == Interest and place.firm_debt > 0 estimated
    branch repay_loan p = 1.0 if intent == Repay and place.firm_cash >= place.repayment_amount estimated
  decision at_sync:
    branch allocate_capital p = 1.0 if hour == 0 and (day == 0 or day == 90 or day == 180 or day == 270) estimated

role president:
  decision at_sync:
    branch enact_policy p = 1.0 if hour == 0 and (day == 0 or day == 90 or day == 180 or day == 270) estimated

role governor:
  decision at_sync:
    branch enact_state_policy p = 1.0 if hour == 0 and (day == 0 or day == 90 or day == 180 or day == 270) estimated

role mayor:
  decision at_sync:
    branch set_city_budget p = 1.0 if hour == 0 and (day == 0 or day == 90 or day == 180 or day == 270) estimated

role brand_manager:
  decision at_sync:
    branch set_brand_policy p = 1.0 if hour == 0 and (day == 0 or day == 90 or day == 180 or day == 270) estimated

role franchise_manager:
  decision at_sync:
    branch set_franchise_policy p = 1.0 if hour == 0 and (day == 0 or day == 90 or day == 180 or day == 270) estimated

role influencer:
  decision at_sync:
    branch post_spotlight p = 1.0 if hour == 0 and (day == 0 or day == 90 or day == 180 or day == 270) estimated

decision market_action:
  branch market_wait p = 1.0 if intent == Counterparty estimated

action market_wait:
  aggregate = market_waits
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome waited p = 1.0 estimated:
    next = market_action

action secondary_buy:
  aggregate = secondary_buys
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  target = random at current place where target.role.trader and target.intent == Counterparty and target.shares >= 1
  outcome filled p = 1.0 estimated:
    effect self.money -= place.price estimated
    effect target.money += place.price estimated
    effect self.shares += 1 estimated
    effect target.shares -= 1 estimated
    effect current place price *= 1.01 estimated
    next = market_action

action secondary_sell:
  aggregate = secondary_sells
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  target = random at current place where target.role.trader and target.intent == Counterparty and target.money >= place.price
  outcome filled p = 1.0 estimated:
    effect self.money += place.price estimated
    effect target.money -= place.price estimated
    effect self.shares -= 1 estimated
    effect target.shares += 1 estimated
    effect current place price *= 0.99 estimated
    next = market_action

action new_issuance:
  aggregate = issuances
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome issued p = 1.0 estimated:
    effect self.money -= place.price estimated
    effect self.shares += 1 estimated
    effect current place firm_cash += place.price estimated
    effect current place shares_outstanding += 1 estimated
    effect current place price = place.price * place.shares_outstanding / (place.shares_outstanding + 1) estimated
    next = market_action

action borrow_capital:
  aggregate = borrowings
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome borrowed p = 1.0 estimated:
    effect current place lender_cash -= place.loan_amount estimated
    effect current place firm_cash += place.loan_amount estimated
    effect current place firm_debt += place.loan_amount estimated
    next = market_action

action accrue_interest:
  aggregate = interest_accruals
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome accrued p = 1.0 estimated:
    effect current place firm_debt += place.firm_debt * place.interest_rate estimated
    next = market_action

action repay_loan:
  aggregate = repayments
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome repaid p = 1.0 estimated:
    effect current place firm_cash -= place.repayment_amount estimated
    effect current place lender_cash += place.repayment_amount estimated
    effect current place firm_debt -= min(place.firm_debt, place.repayment_amount) estimated
    next = market_action

action allocate_capital:
  aggregate = capital_allocations
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome allocated p = 1.0 estimated:
    effect self.stress += 0.001 estimated
    next = at_sync

action enact_policy:
  aggregate = country_policies
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  record = agent, tick
  outcome enacted p = 1.0 estimated:
    effect self.stress += 0.001 estimated
    next = at_sync

action enact_state_policy:
  aggregate = state_policies
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  record = agent, tick
  outcome enacted p = 1.0 estimated:
    effect self.stress += 0.001 estimated
    next = at_sync

action set_city_budget:
  aggregate = city_budgets
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  record = agent, tick
  outcome set p = 1.0 estimated:
    effect self.stress += 0.001 estimated
    next = at_sync

action set_brand_policy:
  aggregate = brand_policies
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  record = agent, tick
  outcome set p = 1.0 estimated:
    effect self.stress += 0.001 estimated
    next = at_sync

action set_franchise_policy:
  aggregate = franchise_policies
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  record = agent, tick
  outcome set p = 1.0 estimated:
    effect self.stress += 0.001 estimated
    next = at_sync

action post_spotlight:
  aggregate = spotlight_posts
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  record = agent, tick
  outcome posted p = 1.0 estimated:
    effect self.stress += 0.001 estimated
    next = at_sync

archetype BuyerActor:
  sample_households = 1
  roles = trader
  composition:
    people count = 1 mix FinancialPerson:1.0
  initial:
    intent ~ Categorical(Buy: 1.0)
    money ~ Uniform(min=100, max=100)
    shares ~ Uniform(min=0, max=0)
  output population = count()
  output mean_money = mean(money)
  output trade_count = action_count(secondary_buys, window=day)

archetype SellerCounterparty:
  sample_households = 1
  roles = trader
  composition:
    people count = 1 mix FinancialPerson:1.0
  initial:
    intent ~ Categorical(Counterparty: 1.0)
    money ~ Uniform(min=0, max=0)
    shares ~ Uniform(min=1, max=1)
  output population = count()
  output mean_money = mean(money)
  output trade_count = action_count(secondary_buys, window=day)

archetype SellerActor:
  sample_households = 1
  roles = trader
  composition:
    people count = 1 mix FinancialPerson:1.0
  initial:
    intent ~ Categorical(Sell: 1.0)
    money ~ Uniform(min=0, max=0)
    shares ~ Uniform(min=1, max=1)
  output population = count()
  output mean_money = mean(money)

archetype BuyerCounterparty:
  sample_households = 1
  roles = trader
  composition:
    people count = 1 mix FinancialPerson:1.0
  initial:
    intent ~ Categorical(Counterparty: 1.0)
    money ~ Uniform(min=100, max=100)
    shares ~ Uniform(min=0, max=0)
  output population = count()
  output mean_money = mean(money)

archetype IssuerActor:
  sample_households = 1
  roles = trader, ceo
  composition:
    people count = 1 mix FinancialPerson:1.0
  initial:
    intent ~ Categorical(Issue: 1.0)
    money ~ Uniform(min=100, max=100)
  output population = count()
  output mean_money = mean(money)

archetype BorrowerActor:
  sample_households = 1
  roles = ceo
  composition:
    people count = 1 mix FinancialPerson:1.0
  initial:
    intent ~ Categorical(Borrow: 1.0)
  output population = count()
  output mean_money = mean(money)

archetype InterestActor:
  sample_households = 1
  roles = ceo
  composition:
    people count = 1 mix FinancialPerson:1.0
  initial:
    intent ~ Categorical(Interest: 1.0)
  output population = count()
  output mean_money = mean(money)

archetype RepayerActor:
  sample_households = 1
  roles = ceo
  composition:
    people count = 1 mix FinancialPerson:1.0
  initial:
    intent ~ Categorical(Repay: 1.0)
  output population = count()
  output mean_money = mean(money)

archetype LedgerCohort:
  sample_households = 1
  composition:
    ledgers count = 1 mix FinancialLedgerState:1.0
  initial:
    intent ~ Categorical(Counterparty: 1.0)
  output population = count()

composition SecondaryBuyLab:
  level = transaction_lab
  children:
    BuyerActor: weight = 1
    SellerCounterparty: weight = 1
  places = ExchangeA
  output population = count()
  output trader_money = sum(money)
  output price = place_state(ExchangeA, price)
  output firm_cash = place_state(ExchangeA, firm_cash)
  output lender_cash = place_state(ExchangeA, lender_cash)
  output debt = place_state(ExchangeA, firm_debt)
  output shares_outstanding = place_state(ExchangeA, shares_outstanding)
  output market_cap = formula(price * shares_outstanding)
  output total_money = formula(trader_money + firm_cash + lender_cash)

composition SecondarySellLab:
  level = transaction_lab
  children:
    SellerActor: weight = 1
    BuyerCounterparty: weight = 1
  places = ExchangeA
  output population = count()
  output trader_money = sum(money)
  output price = place_state(ExchangeA, price)
  output firm_cash = place_state(ExchangeA, firm_cash)
  output lender_cash = place_state(ExchangeA, lender_cash)
  output debt = place_state(ExchangeA, firm_debt)
  output shares_outstanding = place_state(ExchangeA, shares_outstanding)
  output market_cap = formula(price * shares_outstanding)
  output total_money = formula(trader_money + firm_cash + lender_cash)

composition IssuanceLab:
  level = transaction_lab
  children:
    IssuerActor: weight = 1
  places = ExchangeA
  output population = count()
  output trader_money = sum(money)
  output price = place_state(ExchangeA, price)
  output firm_cash = place_state(ExchangeA, firm_cash)
  output lender_cash = place_state(ExchangeA, lender_cash)
  output debt = place_state(ExchangeA, firm_debt)
  output shares_outstanding = place_state(ExchangeA, shares_outstanding)
  output market_cap = formula(price * shares_outstanding)
  output total_money = formula(trader_money + firm_cash + lender_cash)

composition BorrowLab:
  level = transaction_lab
  children:
    BorrowerActor: weight = 1
  places = ExchangeA
  output population = count()
  output trader_money = sum(money)
  output price = place_state(ExchangeA, price)
  output firm_cash = place_state(ExchangeA, firm_cash)
  output lender_cash = place_state(ExchangeA, lender_cash)
  output debt = place_state(ExchangeA, firm_debt)
  output shares_outstanding = place_state(ExchangeA, shares_outstanding)
  output market_cap = formula(price * shares_outstanding)
  output total_money = formula(trader_money + firm_cash + lender_cash)

composition InterestLab:
  level = transaction_lab
  children:
    InterestActor: weight = 1
  places = ExchangeA
  output population = count()
  output firm_cash = place_state(ExchangeA, firm_cash)
  output debt = place_state(ExchangeA, firm_debt)

composition RepayLab:
  level = transaction_lab
  children:
    RepayerActor: weight = 1
  places = ExchangeA
  output population = count()
  output trader_money = sum(money)
  output price = place_state(ExchangeA, price)
  output firm_cash = place_state(ExchangeA, firm_cash)
  output lender_cash = place_state(ExchangeA, lender_cash)
  output debt = place_state(ExchangeA, firm_debt)
  output shares_outstanding = place_state(ExchangeA, shares_outstanding)
  output market_cap = formula(price * shares_outstanding)
  output total_money = formula(trader_money + firm_cash + lender_cash)

composition StockAlpha:
  level = stock
  children:
    LedgerCohort: weight = 1
  parameters:
    profit = 100
    revenue = 500
    growth = 0.10
    interest_rate = 0.05
    market_sentiment = 0.20
    payout_ratio = 0.40
    cash = 200
    debt = 50
    shares_outstanding = 100
  cached:
    sync = 1 days
    max_iterations = 2
    tolerance = 0.01
  output population = count()
  output profit = formula(profit)
  output revenue = formula(revenue)
  output growth = formula(growth)
  output price = formula(profit * 0.20 + revenue * 0.02 + growth * 10 - interest_rate * 20 + market_sentiment * 5)
  output dividend = formula(max(0, (profit * payout_ratio + cash * 0.02 - debt * 0.01) / shares_outstanding))
  output shares_outstanding = formula(shares_outstanding)
  output market_cap = formula(price * shares_outstanding)
  output firm_cash = formula(cash)
  output debt = formula(debt)

composition StockBeta:
  level = stock
  children:
    LedgerCohort: weight = 1
  parameters:
    profit = 60
    revenue = 300
    growth = 0.05
    interest_rate = 0.04
    market_sentiment = 0.10
    payout_ratio = 0.30
    cash = 150
    debt = 20
    shares_outstanding = 80
  cached:
    sync = 1 days
    max_iterations = 2
    tolerance = 0.01
  output population = count()
  output profit = formula(profit)
  output revenue = formula(revenue)
  output growth = formula(growth)
  output price = formula(profit * 0.20 + revenue * 0.02 + growth * 10 - interest_rate * 20 + market_sentiment * 5)
  output dividend = formula(max(0, (profit * payout_ratio + cash * 0.02 - debt * 0.01) / shares_outstanding))
  output shares_outstanding = formula(shares_outstanding)
  output market_cap = formula(price * shares_outstanding)
  output firm_cash = formula(cash)
  output debt = formula(debt)

agent FinancialLeaderPerson inherits FinancialPerson:
  scope = composition
  routine = at_sync

agent FinancialLedgerState:
  scope = composition
  state location
  initial:
    location ~ Categorical(ExchangeA: 1.0) placeholder
  routine = ledger_idle

decision ledger_idle:
  branch ledger_wait p = 1.0 estimated

action ledger_wait:
  aggregate = ledger_waits
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome waited p = 1.0 estimated:
    next = ledger_idle

archetype CEOAlpha:
  sample_households = 1
  roles = ceo
  composition:
    leaders count = 1 mix FinancialLeaderPerson:1.0
  output population = count()

archetype CEOBeta:
  sample_households = 1
  roles = ceo
  composition:
    leaders count = 1 mix FinancialLeaderPerson:1.0
  output population = count()

archetype PresidentLeader:
  sample_households = 1
  roles = president
  composition:
    leaders count = 1 mix FinancialLeaderPerson:1.0
  output population = count()

archetype TexasGovernorLeader:
  sample_households = 1
  roles = governor
  composition:
    leaders count = 1 mix FinancialLeaderPerson:1.0
  output population = count()

archetype CaliforniaGovernorLeader:
  sample_households = 1
  roles = governor
  composition:
    leaders count = 1 mix FinancialLeaderPerson:1.0
  output population = count()

archetype DallasMayorLeader:
  sample_households = 1
  roles = mayor
  composition:
    leaders count = 1 mix FinancialLeaderPerson:1.0
  output population = count()

archetype BrandLeader:
  sample_households = 1
  roles = brand_manager
  composition:
    leaders count = 1 mix FinancialLeaderPerson:1.0
  output population = count()

archetype FranchiseLeader:
  sample_households = 1
  roles = franchise_manager
  composition:
    leaders count = 1 mix FinancialLeaderPerson:1.0
  output population = count()

archetype StoreLeader:
  sample_households = 1
  roles = manager
  composition:
    leaders count = 1 mix FinancialLeaderPerson:1.0
  output population = count()

spotlight agent CommunityInfluencer:
  sample_households = 1
  roles = influencer
  composition:
    leaders count = 1 mix FinancialLeaderPerson:1.0
  output population = count()

composition CanadaLeadership:
  level = country_leadership
  children:
    PresidentLeader: weight = 1
    LedgerCohort: weight = 1
  parameters:
    policy_effect = 0.10
  leaders:
    president: count = 1
  output population = count()
  output policy_effect = formula(policy_effect)

composition TexasLeadership:
  level = division_leadership
  children:
    TexasGovernorLeader: weight = 1
    LedgerCohort: weight = 1
  parameters:
    policy_effect = 0.20
  leaders:
    governor: count = 1
  output population = count()
  output policy_effect = formula(policy_effect)

composition CaliforniaLeadership:
  level = division_leadership
  children:
    CaliforniaGovernorLeader: weight = 1
    LedgerCohort: weight = 1
  parameters:
    policy_effect = 0.15
  leaders:
    governor: count = 1
  output population = count()
  output policy_effect = formula(policy_effect)

composition DallasLeadership:
  level = municipality_leadership
  children:
    DallasMayorLeader: weight = 1
    LedgerCohort: weight = 1
  parameters:
    policy_effect = 0.05
  leaders:
    mayor: count = 1
  output population = count()
  output policy_effect = formula(policy_effect)

composition BrandLeadership:
  level = brand_leadership
  children:
    BrandLeader: weight = 1
    LedgerCohort: weight = 1
  leaders:
    brand_manager: count = 1
  output population = count()

composition FranchiseLeadership:
  level = franchise_leadership
  children:
    FranchiseLeader: weight = 1
    LedgerCohort: weight = 1
  leaders:
    franchise_manager: count = 1
  output population = count()

composition StoreLeadership:
  level = store_leadership
  children:
    StoreLeader: weight = 1
    LedgerCohort: weight = 1
  leaders:
    manager: count = 1
  output population = count()

composition CommunityLeadership:
  level = community_leadership
  children:
    CommunityInfluencer: weight = 1
    LedgerCohort: weight = 1
  leaders:
    influencer: count = 1
  output population = count()

composition FirmAlpha:
  level = conglomerate
  children:
    LedgerCohort: weight = 1
    CEOAlpha: weight = 1
  parameters:
    profit = 100
    revenue = 500
    growth = 0.10
    cash = 200
    debt = 50
    firm_a_price = 31
    firm_a_market_cap = 3100
    interest_rate = 0.05
    labour_market = 0.60
    costs = 100
    competitor_price = 12
  cached:
    sync = 90 days
    max_iterations = 3
    tolerance = 0.01
  leaders:
    ceo: count = 1
  output population = count()
  output profit = formula(profit)
  output revenue = formula(revenue)
  output growth = formula(growth)
  output cash = formula(cash)
  output debt = formula(debt)
  output capital_allocation = formula(max(0, firm_a_price * 0.5 + firm_a_market_cap * 0.02 + cash * 0.1 - debt * 0.05 - interest_rate * 100))
  output expansion = formula(max(0, capital_allocation / max(profit, 1)))
  output wage_policy = formula(1 + capital_allocation / 1000 + profit / 10000 + labour_market * 0.05)
  output price_policy = formula(1 + capital_allocation / 2000 + costs / 10000 - competitor_price / 1000)

composition FirmBeta:
  level = conglomerate
  children:
    LedgerCohort: weight = 1
    CEOBeta: weight = 1
  parameters:
    profit = 60
    revenue = 300
    growth = 0.05
    cash = 150
    debt = 20
    firm_b_price = 18.2
    firm_b_market_cap = 1456
    interest_rate = 0.04
    labour_market = 0.55
    costs = 70
    competitor_price = 11
  cached:
    sync = 90 days
    max_iterations = 3
    tolerance = 0.01
  leaders:
    ceo: count = 1
  output population = count()
  output profit = formula(profit)
  output revenue = formula(revenue)
  output growth = formula(growth)
  output cash = formula(cash)
  output debt = formula(debt)
  output capital_allocation = formula(max(0, firm_b_price * 0.5 + firm_b_market_cap * 0.02 + cash * 0.1 - debt * 0.05 - interest_rate * 100))
  output expansion = formula(max(0, capital_allocation / max(profit, 1)))
  output wage_policy = formula(1 + capital_allocation / 1000 + profit / 10000 + labour_market * 0.05)
  output price_policy = formula(1 + capital_allocation / 2000 + costs / 10000 - competitor_price / 1000)

composition FamilyBusiness:
  level = independent_business
  children:
    LedgerCohort: weight = 1
  parameters:
    profit = 40
    cash = 40
  cached:
    sync = 90 days
    max_iterations = 2
    tolerance = 0.01
  output population = count()
  output profit = formula(profit)
  output cash = formula(cash)

composition ListedCorporateForest:
  level = corporate_forest
  children:
    FirmAlpha: weight = 1
    FirmBeta: weight = 1
    FamilyBusiness: weight = 1
  parameters:
    firm_a_price = 31
    firm_a_market_cap = 3100
    firm_b_price = 18.2
    firm_b_market_cap = 1456
  cached:
    sync = 90 days
    max_iterations = 4
    tolerance = 0.01
  output population = count()
  output firm_a_profit = formula(FirmAlpha.profit)
  output firm_a_revenue = formula(FirmAlpha.revenue)
  output firm_a_cash = formula(FirmAlpha.cash)
  output firm_a_capital_allocation = formula(FirmAlpha.capital_allocation)
  output firm_a_expansion = formula(FirmAlpha.expansion)
  output firm_a_wage_policy = formula(FirmAlpha.wage_policy)
  output firm_a_price_policy = formula(FirmAlpha.price_policy)
  output firm_b_profit = formula(FirmBeta.profit)
  output firm_b_revenue = formula(FirmBeta.revenue)
  output firm_b_cash = formula(FirmBeta.cash)
  output firm_b_capital_allocation = formula(FirmBeta.capital_allocation)
  output firm_b_expansion = formula(FirmBeta.expansion)
  output firm_b_wage_policy = formula(FirmBeta.wage_policy)
  output firm_b_price_policy = formula(FirmBeta.price_policy)
  output family_profit = formula(FamilyBusiness.profit)
  output family_cash = formula(FamilyBusiness.cash)

composition MarketAlpha:
  level = market
  children:
    StockAlpha: weight = 1
  cached:
    sync = 1 days
    max_iterations = 2
    tolerance = 0.01
  output population = count()
  output alpha_profit = formula(StockAlpha.profit)
  output alpha_revenue = formula(StockAlpha.revenue)
  output alpha_growth = formula(StockAlpha.growth)
  output alpha_price = formula(StockAlpha.price)
  output alpha_dividend = formula(StockAlpha.dividend)
  output alpha_market_cap = formula(StockAlpha.market_cap)
  output alpha_firm_cash = formula(StockAlpha.firm_cash)

composition MarketBeta:
  level = market
  children:
    StockBeta: weight = 1
  cached:
    sync = 1 days
    max_iterations = 2
    tolerance = 0.01
  output population = count()
  output beta_profit = formula(StockBeta.profit)
  output beta_revenue = formula(StockBeta.revenue)
  output beta_growth = formula(StockBeta.growth)
  output beta_price = formula(StockBeta.price)
  output beta_dividend = formula(StockBeta.dividend)
  output beta_market_cap = formula(StockBeta.market_cap)
  output beta_firm_cash = formula(StockBeta.firm_cash)

composition SectorAlpha:
  level = sector
  children:
    MarketAlpha: weight = 1
  cached:
    sync = 1 days
    max_iterations = 2
    tolerance = 0.01
  output population = count()
  output alpha_profit = formula(MarketAlpha.alpha_profit)
  output alpha_revenue = formula(MarketAlpha.alpha_revenue)
  output alpha_growth = formula(MarketAlpha.alpha_growth)
  output alpha_price = formula(MarketAlpha.alpha_price)
  output alpha_dividend = formula(MarketAlpha.alpha_dividend)
  output alpha_market_cap = formula(MarketAlpha.alpha_market_cap)
  output alpha_firm_cash = formula(MarketAlpha.alpha_firm_cash)

composition SectorBeta:
  level = sector
  children:
    MarketBeta: weight = 1
  cached:
    sync = 1 days
    max_iterations = 2
    tolerance = 0.01
  output population = count()
  output beta_profit = formula(MarketBeta.beta_profit)
  output beta_revenue = formula(MarketBeta.beta_revenue)
  output beta_growth = formula(MarketBeta.beta_growth)
  output beta_price = formula(MarketBeta.beta_price)
  output beta_dividend = formula(MarketBeta.beta_dividend)
  output beta_market_cap = formula(MarketBeta.beta_market_cap)
  output beta_firm_cash = formula(MarketBeta.beta_firm_cash)

composition FinancialEconomy:
  level = financial_economy
  children:
    SectorAlpha: weight = 1
    SectorBeta: weight = 1
  parameters:
    firm_a_profit = 100
    firm_b_profit = 60
    interest_rate = 0.05
    market_sentiment = 0.25
    trader_signal = 0
  cached:
    sync = 1 days
    max_iterations = 4
    tolerance = 0.01
  output population = count()
  output alpha_price = formula(firm_a_profit * 0.20 + SectorAlpha.alpha_revenue * 0.02 + SectorAlpha.alpha_growth * 10 - interest_rate * 20 + market_sentiment * 5 + trader_signal)
  output alpha_dividend = formula(max(0, (firm_a_profit * 0.40 + SectorAlpha.alpha_firm_cash * 0.02 - 50 * 0.01) / 100))
  output alpha_market_cap = formula(alpha_price * 100)
  output alpha_firm_cash = formula(SectorAlpha.alpha_firm_cash)
  output beta_price = formula(firm_b_profit * 0.20 + SectorBeta.beta_revenue * 0.02 + SectorBeta.beta_growth * 10 - interest_rate * 20 + market_sentiment * 5 + trader_signal)
  output beta_dividend = formula(max(0, (firm_b_profit * 0.30 + SectorBeta.beta_firm_cash * 0.02 - 20 * 0.01) / 80))
  output beta_market_cap = formula(beta_price * 80)
  output beta_firm_cash = formula(SectorBeta.beta_firm_cash)

composition UnifiedRolePopulation:
  level = physical_population
  children:
    BuyerActor: weight = 1
    SellerCounterparty: weight = 1
  places = ExchangeA
  cached:
    sync = 1 days
    max_iterations = 2
    tolerance = 0.01
  output population = count()
  output trader_money = sum(money)
  output trader_stress = mean(stress)
  output trade_count = action_count(secondary_buys, window=day)

composition CorporateFinancialSystem:
  level = coupled_corporate_financial
  report_descendants = true
  children:
    ListedCorporateForest: weight = 1
    FinancialEconomy: weight = 1
    UnifiedRolePopulation: weight = 1
  parameters:
    macro_signal = 0
  cached:
    sync = 90 days
    max_iterations = 5
    tolerance = 0.01
  couplings:
    alpha_profit_to_market ListedCorporateForest -> FinancialEconomy input = firm_a_profit value = formula(ListedCorporateForest_firm_a_profit) cadence = sync
    beta_profit_to_market ListedCorporateForest -> FinancialEconomy input = firm_b_profit value = formula(ListedCorporateForest_firm_b_profit) cadence = sync
    trader_signal_to_market UnifiedRolePopulation -> FinancialEconomy input = trader_signal value = formula(clamp(UnifiedRolePopulation_trade_count / 100, 0, 1)) cadence = sync
    alpha_price_to_corporate FinancialEconomy -> ListedCorporateForest input = firm_a_price value = formula(FinancialEconomy_alpha_price) cadence = sync
    alpha_cap_to_corporate FinancialEconomy -> ListedCorporateForest input = firm_a_market_cap value = formula(FinancialEconomy_alpha_market_cap) cadence = sync
    beta_price_to_corporate FinancialEconomy -> ListedCorporateForest input = firm_b_price value = formula(FinancialEconomy_beta_price) cadence = sync
    beta_cap_to_corporate FinancialEconomy -> ListedCorporateForest input = firm_b_market_cap value = formula(FinancialEconomy_beta_market_cap) cadence = sync
  output population = count()
  output firm_a_profit = formula(ListedCorporateForest.firm_a_profit)
  output firm_b_profit = formula(ListedCorporateForest.firm_b_profit)
  output family_profit = formula(ListedCorporateForest.family_profit)
  output alpha_price = formula(FinancialEconomy.alpha_price + macro_signal)
  output alpha_dividend = formula(FinancialEconomy.alpha_dividend)
  output alpha_market_cap = formula(FinancialEconomy.alpha_market_cap)
  output beta_price = formula(FinancialEconomy.beta_price)
  output beta_dividend = formula(FinancialEconomy.beta_dividend)
  output beta_market_cap = formula(FinancialEconomy.beta_market_cap)
  output firm_a_capital_allocation = formula(ListedCorporateForest.firm_a_capital_allocation)
  output firm_b_capital_allocation = formula(ListedCorporateForest.firm_b_capital_allocation)
  output alpha_profit_to_market = flow_rate(alpha_profit_to_market)
  output alpha_price_to_corporate = flow_rate(alpha_price_to_corporate)

aggregate_function FinancialEconomy:
  inputs:
    firm_a_profit = 100 range 0..10000
    firm_b_profit = 60 range 0..10000
    interest_rate = 0.05 range 0..1
    market_sentiment = 0.25 range -1..1
    trader_signal = 0 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(firm_a_profit, firm_b_profit, interest_rate, market_sentiment, trader_signal)
    alpha_price = formula(firm_a_profit, firm_b_profit, interest_rate, market_sentiment, trader_signal)
    alpha_dividend = formula(firm_a_profit, firm_b_profit, interest_rate, market_sentiment, trader_signal)
    alpha_market_cap = formula(firm_a_profit, firm_b_profit, interest_rate, market_sentiment, trader_signal)
    alpha_firm_cash = formula(firm_a_profit, firm_b_profit, interest_rate, market_sentiment, trader_signal)
    beta_price = formula(firm_a_profit, firm_b_profit, interest_rate, market_sentiment, trader_signal)
    beta_dividend = formula(firm_a_profit, firm_b_profit, interest_rate, market_sentiment, trader_signal)
    beta_market_cap = formula(firm_a_profit, firm_b_profit, interest_rate, market_sentiment, trader_signal)
    beta_firm_cash = formula(firm_a_profit, firm_b_profit, interest_rate, market_sentiment, trader_signal)
  cache:
    valid_for = 90 days
    inputs_hash = hash(firm_a_profit, firm_b_profit, interest_rate, market_sentiment, trader_signal)
    invalidate_on:
      firm_a_profit change > 1
      firm_b_profit change > 1
      interest_rate change > 0.01
      market_sentiment change > 0.05
      trader_signal change > 0.05
      event = earnings, rate_change, sentiment_change

aggregate_function ListedCorporateForest:
  inputs:
    firm_a_price = 31 range 0..10000
    firm_a_market_cap = 3100 range 0..1000000
    firm_b_price = 18.2 range 0..10000
    firm_b_market_cap = 1456 range 0..1000000
  time = 90 days
  time_points = 1, 30, 90
  outputs:
    population = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    firm_a_profit = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    firm_a_revenue = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    firm_a_cash = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    firm_a_capital_allocation = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    firm_a_expansion = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    firm_a_wage_policy = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    firm_a_price_policy = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    firm_b_profit = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    firm_b_revenue = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    firm_b_cash = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    firm_b_capital_allocation = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    firm_b_expansion = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    firm_b_wage_policy = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    firm_b_price_policy = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    family_profit = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    family_cash = formula(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
  cache:
    valid_for = 180 days
    inputs_hash = hash(firm_a_price, firm_a_market_cap, firm_b_price, firm_b_market_cap)
    invalidate_on:
      firm_a_price change > 0.5
      firm_a_market_cap change > 50
      firm_b_price change > 0.5
      firm_b_market_cap change > 50
      event = capital_change

aggregate_function LedgerCohort:
  inputs:
    signal = 0 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(signal)
  cache:
    valid_for = 90 days
    inputs_hash = hash(signal)
    invalidate_on:
      signal change > 1
      event = ledger_change

aggregate_function CEOAlpha:
  inputs:
    signal = 0 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(signal)
  cache:
    valid_for = 90 days
    inputs_hash = hash(signal)
    invalidate_on:
      signal change > 1
      event = leader_change

aggregate_function CEOBeta:
  inputs:
    signal = 0 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(signal)
  cache:
    valid_for = 90 days
    inputs_hash = hash(signal)
    invalidate_on:
      signal change > 1
      event = leader_change

aggregate_function BuyerActor:
  inputs:
    trader_signal = 0 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(trader_signal)
    mean_money = formula(trader_signal)
    trade_count = formula(trader_signal) from action_count(secondary_buys, window=day)
  cache:
    valid_for = 90 days
    inputs_hash = hash(trader_signal)
    invalidate_on:
      trader_signal change > 1
      event = trader_change

aggregate_function SellerCounterparty:
  inputs:
    trader_signal = 0 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(trader_signal)
    mean_money = formula(trader_signal)
    trade_count = formula(trader_signal) from action_count(secondary_buys, window=day)
  cache:
    valid_for = 90 days
    inputs_hash = hash(trader_signal)
    invalidate_on:
      trader_signal change > 1
      event = trader_change

aggregate_function StockAlpha:
  inputs:
    firm_a_profit = 100 range 0..10000
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(firm_a_profit)
    profit = formula(firm_a_profit)
    revenue = formula(firm_a_profit)
    growth = formula(firm_a_profit)
    price = formula(firm_a_profit)
    dividend = formula(firm_a_profit)
    shares_outstanding = formula(firm_a_profit)
    market_cap = formula(firm_a_profit)
    firm_cash = formula(firm_a_profit)
    debt = formula(firm_a_profit)
  cache:
    valid_for = 90 days
    inputs_hash = hash(firm_a_profit)
    invalidate_on:
      firm_a_profit change > 1
      event = earnings

aggregate_function StockBeta:
  inputs:
    firm_b_profit = 60 range 0..10000
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(firm_b_profit)
    profit = formula(firm_b_profit)
    revenue = formula(firm_b_profit)
    growth = formula(firm_b_profit)
    price = formula(firm_b_profit)
    dividend = formula(firm_b_profit)
    shares_outstanding = formula(firm_b_profit)
    market_cap = formula(firm_b_profit)
    firm_cash = formula(firm_b_profit)
    debt = formula(firm_b_profit)
  cache:
    valid_for = 90 days
    inputs_hash = hash(firm_b_profit)
    invalidate_on:
      firm_b_profit change > 1
      event = earnings

aggregate_function MarketAlpha:
  inputs:
    firm_a_profit = 100 range 0..10000
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(firm_a_profit)
    alpha_profit = formula(firm_a_profit)
    alpha_revenue = formula(firm_a_profit)
    alpha_growth = formula(firm_a_profit)
    alpha_price = formula(firm_a_profit)
    alpha_dividend = formula(firm_a_profit)
    alpha_market_cap = formula(firm_a_profit)
    alpha_firm_cash = formula(firm_a_profit)
  cache:
    valid_for = 90 days
    inputs_hash = hash(firm_a_profit)
    invalidate_on:
      firm_a_profit change > 1
      event = earnings

aggregate_function MarketBeta:
  inputs:
    firm_b_profit = 60 range 0..10000
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(firm_b_profit)
    beta_profit = formula(firm_b_profit)
    beta_revenue = formula(firm_b_profit)
    beta_growth = formula(firm_b_profit)
    beta_price = formula(firm_b_profit)
    beta_dividend = formula(firm_b_profit)
    beta_market_cap = formula(firm_b_profit)
    beta_firm_cash = formula(firm_b_profit)
  cache:
    valid_for = 90 days
    inputs_hash = hash(firm_b_profit)
    invalidate_on:
      firm_b_profit change > 1
      event = earnings

aggregate_function SectorAlpha:
  inputs:
    firm_a_profit = 100 range 0..10000
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(firm_a_profit)
    alpha_profit = formula(firm_a_profit)
    alpha_revenue = formula(firm_a_profit)
    alpha_growth = formula(firm_a_profit)
    alpha_price = formula(firm_a_profit)
    alpha_dividend = formula(firm_a_profit)
    alpha_market_cap = formula(firm_a_profit)
    alpha_firm_cash = formula(firm_a_profit)
  cache:
    valid_for = 90 days
    inputs_hash = hash(firm_a_profit)
    invalidate_on:
      firm_a_profit change > 1
      event = earnings

aggregate_function SectorBeta:
  inputs:
    firm_b_profit = 60 range 0..10000
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(firm_b_profit)
    beta_profit = formula(firm_b_profit)
    beta_revenue = formula(firm_b_profit)
    beta_growth = formula(firm_b_profit)
    beta_price = formula(firm_b_profit)
    beta_dividend = formula(firm_b_profit)
    beta_market_cap = formula(firm_b_profit)
    beta_firm_cash = formula(firm_b_profit)
  cache:
    valid_for = 90 days
    inputs_hash = hash(firm_b_profit)
    invalidate_on:
      firm_b_profit change > 1
      event = earnings

aggregate_function FirmAlpha:
  inputs:
    profit = 100 range 0..10000
    revenue = 500 range 0..100000
    firm_a_price = 31 range 0..10000
    firm_a_market_cap = 3100 range 0..1000000
  time = 90 days
  time_points = 1, 30, 90
  outputs:
    population = formula(profit, revenue, firm_a_price, firm_a_market_cap)
    profit = formula(profit, revenue, firm_a_price, firm_a_market_cap)
    revenue = formula(profit, revenue, firm_a_price, firm_a_market_cap)
    growth = formula(profit, revenue, firm_a_price, firm_a_market_cap)
    cash = formula(profit, revenue, firm_a_price, firm_a_market_cap)
    debt = formula(profit, revenue, firm_a_price, firm_a_market_cap)
    capital_allocation = formula(profit, revenue, firm_a_price, firm_a_market_cap)
    expansion = formula(profit, revenue, firm_a_price, firm_a_market_cap)
    wage_policy = formula(profit, revenue, firm_a_price, firm_a_market_cap)
    price_policy = formula(profit, revenue, firm_a_price, firm_a_market_cap)
  cache:
    valid_for = 180 days
    inputs_hash = hash(profit, revenue, firm_a_price, firm_a_market_cap)
    invalidate_on:
      profit change > 1
      revenue change > 5
      firm_a_price change > 0.5
      firm_a_market_cap change > 50
      event = capital_change

aggregate_function FirmBeta:
  inputs:
    profit = 60 range 0..10000
    revenue = 300 range 0..100000
    firm_b_price = 18.2 range 0..10000
    firm_b_market_cap = 1456 range 0..1000000
  time = 90 days
  time_points = 1, 30, 90
  outputs:
    population = formula(profit, revenue, firm_b_price, firm_b_market_cap)
    profit = formula(profit, revenue, firm_b_price, firm_b_market_cap)
    revenue = formula(profit, revenue, firm_b_price, firm_b_market_cap)
    growth = formula(profit, revenue, firm_b_price, firm_b_market_cap)
    cash = formula(profit, revenue, firm_b_price, firm_b_market_cap)
    debt = formula(profit, revenue, firm_b_price, firm_b_market_cap)
    capital_allocation = formula(profit, revenue, firm_b_price, firm_b_market_cap)
    expansion = formula(profit, revenue, firm_b_price, firm_b_market_cap)
    wage_policy = formula(profit, revenue, firm_b_price, firm_b_market_cap)
    price_policy = formula(profit, revenue, firm_b_price, firm_b_market_cap)
  cache:
    valid_for = 180 days
    inputs_hash = hash(profit, revenue, firm_b_price, firm_b_market_cap)
    invalidate_on:
      profit change > 1
      revenue change > 5
      firm_b_price change > 0.5
      firm_b_market_cap change > 50
      event = capital_change

aggregate_function FamilyBusiness:
  inputs:
    signal = 0 range 0..1
  time = 90 days
  time_points = 1, 30, 90
  outputs:
    population = formula(signal)
    profit = formula(signal)
    cash = formula(signal)
  cache:
    valid_for = 180 days
    inputs_hash = hash(signal)
    invalidate_on:
      signal change > 1
      event = family_change

aggregate_function UnifiedRolePopulation:
  inputs:
    trader_signal = 0 range 0..1
  time = 30 days
  time_points = 1, 15, 30
  outputs:
    population = formula(trader_signal)
    trader_money = formula(trader_signal)
    trader_stress = formula(trader_signal)
    trade_count = formula(trader_signal)
  cache:
    valid_for = 90 days
    inputs_hash = hash(trader_signal)
    invalidate_on:
      trader_signal change > 1
      event = trader_change

aggregate_function CorporateFinancialSystem:
  inputs:
    macro_signal = 0 range 0..1
  time = 90 days
  time_points = 1, 30, 90
  outputs:
    population = formula(macro_signal)
    firm_a_profit = formula(macro_signal)
    firm_b_profit = formula(macro_signal)
    family_profit = formula(macro_signal)
    alpha_price = formula(macro_signal)
    alpha_dividend = formula(macro_signal)
    alpha_market_cap = formula(macro_signal)
    beta_price = formula(macro_signal)
    beta_dividend = formula(macro_signal)
    beta_market_cap = formula(macro_signal)
    firm_a_capital_allocation = formula(macro_signal)
    firm_b_capital_allocation = formula(macro_signal)
    alpha_profit_to_market = formula(macro_signal)
    alpha_price_to_corporate = formula(macro_signal)
  cache:
    valid_for = 180 days
    inputs_hash = hash(macro_signal)
    invalidate_on:
      macro_signal change > 0.05
      event = macro_change

role redditor:
  decision at_home:
    branch post_on_reddit p = 0.05 + activity * 0.10 + interest * 0.20 estimated
  decision at_feed:
    branch post_on_reddit p = 0.30 + activity * 0.20 + interest * 0.30 estimated

role tiktoker:
  decision at_home:
    branch post_on_tiktok p = 0.04 + activity * 0.08 + interest * 0.18 estimated
  decision at_feed:
    branch post_on_tiktok p = 0.28 + activity * 0.18 + interest * 0.28 estimated

role_distribution cashier:
  agent = DemandRolePerson
  parameters:
    store_count = 500
    workers_per_store = 4
    cashier_share = 0.25
    population = 10000
  share = formula(store_count * workers_per_store * cashier_share / population)
  when = age >= 18 and money >= 0

role_distribution trader:
  agent = DemandRolePerson
  parameters:
    market_participants = 2000
    population = 10000
  share = formula(market_participants / population)
  when = age >= 18 and risk >= 0.4 and money >= 1000

role_distribution redditor:
  agent = DemandRolePerson
  parameters:
    represented_users = 5000
    population = 10000
  share = formula(represented_users / population)
  when = age >= 13 and interest >= 0.3

role_distribution tiktoker:
  agent = DemandRolePerson
  parameters:
    represented_users = 4000
    population = 10000
  share = formula(represented_users / population)
  when = age >= 13 and activity >= 0.3

agent RoleDemoPerson inherits Person:
  scope = composition
  state roles
  trait risk
  trait activity
  trait interest
  trait interest_match
  trait agreement
  trait trust
  trait friends_sharing
  state sentiment range -1..1 estimated
  state outrage range 0..1 estimated
  state fatigue range 0..1 estimated
  initial:
    risk ~ Beta(alpha=2, beta=2) placeholder
    activity ~ Beta(alpha=3, beta=3) placeholder
    interest ~ Beta(alpha=3, beta=2) placeholder
    interest_match ~ Beta(alpha=3, beta=2) placeholder
    agreement ~ Beta(alpha=3, beta=2) placeholder
    trust ~ Beta(alpha=3, beta=3) placeholder
    friends_sharing ~ Beta(alpha=2, beta=5) placeholder
    sentiment ~ Normal(mean=0, sd=0.3, min=-1, max=1) placeholder
    outrage ~ Beta(alpha=2, beta=6) placeholder
    fatigue ~ Beta(alpha=2, beta=5) placeholder
    location ~ Categorical(Home: 1.0) placeholder
  routine = at_home

agent FeedRoleDemoPerson inherits RoleDemoPerson:
  scope = composition
  initial:
    location ~ Categorical(Feed: 1.0) placeholder
  routine = at_feed

agent DemandRolePerson inherits RoleDemoPerson:
  scope = composition

archetype NeitherRoleDemo:
  sample_households = 10
  composition:
    people count = 1 mix RoleDemoPerson:1.0
  output population = count()
  output reddit_posts = action_count(role_reddit_posts, window=run)
  output tiktok_posts = action_count(role_tiktok_posts, window=run)

archetype RedditRoleDemo:
  sample_households = 10
  roles = redditor
  composition:
    people count = 1 mix RoleDemoPerson:1.0
  output population = count()
  output reddit_posts = action_count(role_reddit_posts, window=run)
  output tiktok_posts = action_count(role_tiktok_posts, window=run)

archetype TikTokRoleDemo:
  sample_households = 10
  roles = tiktoker
  composition:
    people count = 1 mix RoleDemoPerson:1.0
  output population = count()
  output reddit_posts = action_count(role_reddit_posts, window=run)
  output tiktok_posts = action_count(role_tiktok_posts, window=run)

archetype BothRoleDemo:
  sample_households = 10
  roles = redditor, tiktoker
  composition:
    people count = 1 mix RoleDemoPerson:1.0
  output population = count()
  output reddit_posts = action_count(role_reddit_posts, window=run)
  output tiktok_posts = action_count(role_tiktok_posts, window=run)

archetype BothFeedRoleDemo:
  sample_households = 10
  roles = redditor, tiktoker
  composition:
    people count = 1 mix FeedRoleDemoPerson:1.0
  output population = count()
  output reddit_posts = action_count(role_reddit_posts, window=run)
  output tiktok_posts = action_count(role_tiktok_posts, window=run)

archetype DemandRoleCohort:
  sample_households = 100
  composition:
    people count = 1 mix DemandRolePerson:1.0
  output population = count()
  output reddit_posts = action_count(role_reddit_posts, window=run)
  output tiktok_posts = action_count(role_tiktok_posts, window=run)

composition RoleActionDemo:
  level = role_action_demo
  children:
    NeitherRoleDemo: weight = 1
    RedditRoleDemo: weight = 1
    TikTokRoleDemo: weight = 1
    BothRoleDemo: weight = 1
    BothFeedRoleDemo: weight = 1
  places = Home, Work, School, Bar, Cinema, Feed
  output population = count()
  output reddit_posts = action_count(role_reddit_posts, window=run)
  output tiktok_posts = action_count(role_tiktok_posts, window=run)

composition RoleDemandDemo:
  level = role_distribution_demo
  children:
    DemandRoleCohort: weight = 1
  places = Home
  output population = count()
  output reddit_posts = action_count(role_reddit_posts, window=run)
  output tiktok_posts = action_count(role_tiktok_posts, window=run)

action post_on_reddit:
  aggregate = role_reddit_posts
  duration = Triangular(min=0.05, median=0.15, max=0.40) estimated
  outcome posted p = 1.0 estimated:
    effect self.stress += 0.001 estimated

action post_on_tiktok:
  aggregate = role_tiktok_posts
  duration = Triangular(min=0.05, median=0.15, max=0.40) estimated
  outcome posted p = 1.0 estimated:
    effect self.stress += 0.001 estimated

agent RoleJoinerPerson inherits RoleDemoPerson:
  scope = composition
  routine = join_platform

agent RoleQuitterPerson inherits RoleDemoPerson:
  scope = composition
  role redditor
  routine = quit_platform

decision join_platform:
  branch become_redditor p = clamp(0.20 + activity * 0.30 + interest * 0.30, 0, 1) estimated

decision quit_platform:
  branch quit_reddit p = clamp(0.20 + fatigue * 0.50, 0, 1) estimated

action become_redditor:
  aggregate = role_changes
  duration = Triangular(min=0.05, median=0.10, max=0.25) estimated
  outcome joined p = 1.0 estimated:
    effect self.roles += redditor estimated
    next = at_home

action quit_reddit:
  aggregate = role_changes
  duration = Triangular(min=0.05, median=0.10, max=0.25) estimated
  outcome quit p = 1.0 estimated:
    effect self.roles -= redditor estimated
    next = at_home

archetype RoleJoinerDemo:
  sample_households = 10
  composition:
    people count = 1 mix RoleJoinerPerson:1.0
  initial:
    activity ~ Uniform(min=1, max=1)
    interest ~ Uniform(min=1, max=1)
  output population = count()
  output role_changes = action_count(role_changes, window=run)
  output reddit_posts = action_count(role_reddit_posts, window=run)

archetype RoleQuitterDemo:
  sample_households = 10
  composition:
    people count = 1 mix RoleQuitterPerson:1.0
  initial:
    fatigue ~ Uniform(min=1, max=1)
  output population = count()
  output role_changes = action_count(role_changes, window=run)
  output reddit_posts = action_count(role_reddit_posts, window=run)

composition RoleChangeDemo:
  level = role_change_demo
  children:
    RoleJoinerDemo: weight = 1
    RoleQuitterDemo: weight = 1
  places = Home, Work, School, Bar, Cinema, Feed
  output population = count()
  output role_changes = action_count(role_changes, window=run)
  output reddit_posts = action_count(role_reddit_posts, window=run)
