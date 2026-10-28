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
