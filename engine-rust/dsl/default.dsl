program PetraterriumTown version "1.0":
  tick_hours = 1 placeholder
  placeholder = "estimated pending the research pipeline"
  uncertainty = wide
  record_actions = false
  results_title = "Recorded Rust output"
  results_subtitle = "Weighted neighbourhood exemplar statistics"

output overview:
  title = "Pool overview"
  group_by = all
  display = cards
  record = final
  column population = count() label "Simulated pool" format integer
  column money = mean(money) label "Mean money" format number
  column health = mean(health) label "Mean health" format decimal
  column stress = mean(stress) label "Mean stress" format decimal
  column actions = action_rates(per=1000, window=day) label "Action rates / 1,000" format action_rates

output places:
  title = "Places"
  group_by = place
  display = table
  record = daily
  column population = count() label "Pool agents" format integer
  column money = mean(money) label "Money" format number
  column health = mean(health) label "Health" format decimal
  column stress = mean(stress) label "Stress" format decimal
  column actions = action_rates(per=1000, window=day) label "Action rates / 1,000" format action_rates

output agent_types:
  title = "Agent types"
  group_by = agent_type
  display = table
  record = daily
  column population = count() label "Pool agents" format integer
  column money = mean(money) label "Money" format number
  column health = mean(health) label "Health" format decimal
  column stress = mean(stress) label "Stress" format decimal
  column actions = action_rates(per=1000, window=day) label "Action rates / 1,000" format action_rates

policy ExemplarInputs:
  effect field money *= 1 - tax * 0.15 - (price - 1) * 0.05
  effect field stress += unemployment * 0.20 + media_trend * 0.05 + policy * 0.03
  effect decision go_work *= 1 - unemployment

place Home:
  state comfort = 0.8 range 0..1 estimated
  state chaos = 0 range 0..1 estimated

place Work:
  state productivity = 0.7 range 0..1 estimated
  state chaos = 0.1 range 0..1 estimated

place School:
  state learning = 0.8 range 0..1 estimated
  state chaos = 0.1 range 0..1 estimated

place Bar:
  state crowd = 0.5 range 0..1 estimated
  state chaos = 0.2 range 0..1 estimated

place Cinema:
  state crowd = 0.4 range 0..1 estimated
  state enjoyment = 0.7 range 0..1 estimated

place Feed:
  state sentiment = 0 range -1..1 estimated
  state outrage = 0 range 0..1 estimated
  state engagement = 20 range 0..100000 estimated

place Store:
  state cash = 100 range 0..100000 estimated
  state revenue = 0 range 0..100000 estimated
  state profit = 0 range -100000..100000 estimated
  state costs = 0 range 0..100000 estimated
  state price = 10 range 0..1000 estimated
  state wage = 5 range 0..1000 estimated
  state open = 1 range 0..1 estimated

place FranchiseOffice:
  state cash = 500 range 0..1000000 estimated
  state fees = 0 range 0..1000000 estimated

place BrandOffice:
  state cash = 1000 range 0..10000000 estimated
  state profit = 0 range -10000000..10000000 estimated

place ConglomerateOffice:
  state cash = 5000 range 0..100000000 estimated
  state debt = 1000 range 0..100000000 estimated
  state market_cap = 10000 range 0..1000000000 estimated

place Exchange:
  state price = 30 range 0.01..10000 estimated
  state firm_cash = 200 range 0..100000 estimated
  state lender_cash = 1000 range 0..100000 estimated
  state firm_debt = 50 range 0..100000 estimated
  state shares_outstanding = 100 range 1..100000 estimated
  state market_sentiment = 0.2 range -1..1 estimated
  state tariff = 0.05 range 0..1 estimated

place DiplomaticForum:
  state trust = 0.5 range 0..1 estimated

place TransitHub:
  state visits = 0 range 0..100000 estimated

agent Person:
  state roles
  trait age
  trait sex
  trait aggression
  trait has_family
  trait has_spouse
  trait kids
  trait vote_liberal
  trait interest
  trait political_lean
  trait activity
  trait trust
  trait interest_match
  trait agreement
  trait friends_sharing
  trait risk
  trait intent
  state health range 0..1 estimated
  state stress range 0..1 estimated
  state alcohol range 0..1 estimated
  state money range 0..100000 estimated
  state reputation range 0..1 estimated
  state sentiment range -1..1 estimated
  state outrage range 0..1 estimated
  state fatigue range 0..1 estimated
  state employed
  state shares range 0..100000 estimated
  state residence_change range 0..1 estimated
  state tax range 0.10..0.40 estimated
  state unemployment range 0.02..0.15 estimated
  state media_trend range -1..1 estimated
  state price range 0.5..2 estimated
  state policy range -1..1 estimated
  state location
  initial:
    age ~ Normal(mean=38, sd=14, min=18, max=80) estimated
    sex ~ Categorical(female: 0.5, male: 0.5) estimated
    aggression ~ Beta(alpha=2, beta=5) estimated
    has_family ~ Bernoulli(p=clamp((age - 20) / 45, 0, 0.82)) estimated
    has_spouse ~ Bernoulli(p=0.72 if has_family else 0.0) estimated
    kids ~ Poisson(lambda=clamp((age - 24) / 18, 0, 2.8) if has_family else 0, cap=5) estimated
    vote_liberal ~ Bernoulli(p=0.5 if age >= 18 else 0) estimated
    interest ~ Beta(alpha=3, beta=2) estimated
    political_lean ~ Normal(mean=0, sd=0.5, min=-1, max=1) estimated
    activity ~ Beta(alpha=3, beta=3) estimated
    trust ~ Beta(alpha=3, beta=3) estimated
    interest_match ~ Beta(alpha=3, beta=2) estimated
    agreement ~ Beta(alpha=3, beta=2) estimated
    friends_sharing ~ Beta(alpha=2, beta=5) estimated
    risk ~ Beta(alpha=2, beta=2) estimated
    intent ~ Categorical(Counterparty: 1.0) estimated
    health ~ Normal(mean=0.82, sd=0.12, min=0, max=1) estimated
    stress ~ Normal(mean=0.42, sd=0.18, min=0, max=1) estimated
    alcohol ~ Uniform(min=0, max=0.15) estimated
    money ~ LogNormal(mean=7.5, sd=0.7, min=0, max=100000) estimated
    reputation ~ Normal(mean=0.5, sd=0.12, min=0, max=1) estimated
    sentiment ~ Normal(mean=0, sd=0.35, min=-1, max=1) estimated
    outrage ~ Beta(alpha=2, beta=6) estimated
    fatigue ~ Beta(alpha=2, beta=5) estimated
    employed ~ Bernoulli(p=0) estimated
    shares ~ Uniform(min=0, max=10) estimated
    residence_change ~ Uniform(min=0, max=0) estimated
    tax ~ Uniform(min=0.25, max=0.25) estimated
    unemployment ~ Uniform(min=0.06, max=0.06) estimated
    media_trend ~ Uniform(min=0, max=0) estimated
    price ~ Uniform(min=1, max=1) estimated
    policy ~ Uniform(min=0, max=0) estimated
    location ~ Categorical(Home: 1.0) estimated
  routine = where_to_go

agent Student inherits Person:
  role student
  initial:
    age ~ Normal(mean=20, sd=3, min=18, max=28) estimated

agent Worker inherits Person:
  role worker

agent WorkingStudent inherits Student:
  role worker

agent Child inherits Person:
  role child
  initial:
    age ~ Uniform(min=0, max=17) estimated

population:
  size = 1 placeholder
  mix:
    Student = 0.4 estimated
    Worker = 0.6 estimated
  households:
    generate children where kids > 0:
      count = kids
      age ~ Uniform(min=0, max=max(0, age - 18)) estimated
      type = Student if age > 5 else Child
      link = parent, household

archetype HouseholdLiberalUrban:
  default_sample_households = 20
  composition:
    adults count = 2 mix Worker:0.65, Student:0.35
    children count = 1 mix Child:1.0
  initial:
    age ~ Normal(mean=34, sd=12, min=18, max=78)
    aggression ~ Beta(alpha=1.8, beta=5.8)
    health ~ Normal(mean=0.84, sd=0.10, min=0, max=1)
    stress ~ Normal(mean=0.48, sd=0.17, min=0, max=1)
    money ~ LogNormal(mean=7.65, sd=0.72, min=0, max=100000)
    vote_liberal ~ Bernoulli(p=0.76 if age >= 18 else 0.0)
  output population = count()
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)

archetype HouseholdConservativeSuburban:
  default_sample_households = 20
  composition:
    adults count = 2 mix Worker:0.82, Student:0.18
    children count = 1 mix Child:1.0
  initial:
    age ~ Normal(mean=43, sd=13, min=18, max=82)
    aggression ~ Beta(alpha=2.1, beta=5.1)
    health ~ Normal(mean=0.80, sd=0.12, min=0, max=1)
    stress ~ Normal(mean=0.39, sd=0.15, min=0, max=1)
    money ~ LogNormal(mean=7.80, sd=0.65, min=0, max=100000)
    vote_liberal ~ Bernoulli(p=0.28 if age >= 18 else 0.0)
  output population = count()
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)

archetype HouseholdRuralMixed:
  default_sample_households = 20
  composition:
    adults count = 2 mix Worker:0.74, Student:0.26
    children count = 1 mix Child:1.0
  initial:
    age ~ Normal(mean=40, sd=15, min=18, max=84)
    aggression ~ Beta(alpha=2.3, beta=4.8)
    health ~ Normal(mean=0.78, sd=0.14, min=0, max=1)
    stress ~ Normal(mean=0.35, sd=0.16, min=0, max=1)
    money ~ LogNormal(mean=7.30, sd=0.76, min=0, max=100000)
    vote_liberal ~ Bernoulli(p=0.47 if age >= 18 else 0.0)
  output population = count()
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)

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

role household_member:
  kind = partition

role head:
  kind = derived
  derive = oldest_adult

role spouse:
  kind = derived
  derive = spouse_link

role parent:
  kind = derived
  derive = parent_link

role father:
  kind = derived
  derive = male_parent

role mother:
  kind = derived
  derive = female_parent

role media_neither:
  kind = explicit_neither

role not_cashier:
  kind = explicit_neither

role not_customer:
  kind = explicit_neither

role not_owner:
  kind = explicit_neither

role not_trader:
  kind = explicit_neither

role not_migrant:
  kind = explicit_neither

role redditor:
  kind = mass_overlay
  eligibility = age >= 13
  decision where_to_go:
    branch open_reddit p = 0.10 + activity * 0.10 if location != Feed estimated
    branch media_post p = 0.05 + activity * 0.10 if location == Feed estimated
    branch media_comment p = 0.06 + interest_match * 0.10 if location == Feed estimated
    branch media_like p = 0.08 + interest_match * 0.10 if location == Feed estimated
    branch media_share p = 0.04 + agreement * 0.08 if location == Feed estimated

role tiktoker:
  kind = mass_overlay
  eligibility = age >= 13
  decision where_to_go:
    branch open_reddit p = 0.08 + activity * 0.10 if location != Feed estimated
    branch media_share p = 0.08 + activity * 0.10 if location == Feed estimated

role influencer:
  kind = leader
  conflict_group = media_office
  eligibility = age >= 18 and activity >= 0.5
  decision where_to_go:
    branch media_post p = 0.8 if location == Feed estimated

role customer:
  kind = mass_overlay
  eligibility = age >= 13
  decision where_to_go:
    branch enter_store p = 0.10 if location != Store estimated
    branch buy p = 0.35 if location == Store estimated

role cashier:
  kind = mass_overlay
  conflict_group = exclusive_job
  eligibility = age >= 18
  decision where_to_go:
    branch enter_store p = 0.15 if location != Store estimated
    branch work_cashier p = 0.60 if location == Store estimated

role store_manager:
  kind = leader
  conflict_group = business_office
  eligibility = age >= 21
  decision where_to_go:
    branch enter_store p = 0.12 if location != Store estimated
    branch manage_store p = 0.45 if location == Store estimated
    branch transfer_franchise_fee p = 1.0 if hour == 0 and day == 0 estimated

role owner:
  kind = mass_overlay
  eligibility = age >= 21
  decision where_to_go:
    branch enter_store p = 0.12 if location != Store estimated
    branch owner_payout p = 1000 if location == Store estimated

role trader:
  kind = mass_overlay
  eligibility = age >= 18 and risk >= 0.4
  decision where_to_go:
    branch enter_market p = 0.10 if location != Exchange estimated
    branch secondary_buy p = 1000 if location == Exchange estimated
    branch secondary_sell p = 1000 if location == Exchange estimated

role migrant:
  kind = mass_overlay
  eligibility = age >= 18
  decision where_to_go:
    branch migrate_household p = 5 estimated

role commuter:
  kind = mass_overlay
  eligibility = age >= 16
  decision where_to_go:
    branch commute_boundary p = 1000 estimated

role president:
  kind = leader
  conflict_group = national_office
  eligibility = age >= 35
  decision where_to_go:
    branch enter_diplomatic_forum p = 1000 if location != DiplomaticForum estimated
    branch diplomatic_summit p = 1000 if location == DiplomaticForum estimated
    branch enact_policy p = 0.5 if hour == 0 estimated

role prime_minister:
  kind = leader
  conflict_group = national_office
  eligibility = age >= 30
  decision where_to_go:
    branch enter_diplomatic_forum p = 1000 if location != DiplomaticForum estimated
    branch diplomatic_summit p = 1000 if location == DiplomaticForum estimated
    branch enact_policy p = 0.5 if hour == 0 estimated

role governor:
  kind = leader
  conflict_group = regional_office
  eligibility = age >= 30
  decision where_to_go:
    branch enact_state_policy p = 1.0 if hour == 0 and day == 0 estimated

role mayor:
  kind = leader
  conflict_group = municipal_office
  eligibility = age >= 25
  decision where_to_go:
    branch enact_state_policy p = 1.0 if hour == 0 and day == 0 estimated

role brand_manager:
  kind = leader
  conflict_group = business_office
  eligibility = age >= 21
  decision where_to_go:
    branch set_brand_policy p = 1.0 if hour == 0 and day == 0 estimated
    branch transfer_brand_profit p = 1.0 if hour == 0 and day == 0 estimated

role franchise_manager:
  kind = leader
  conflict_group = business_office
  eligibility = age >= 21
  decision where_to_go:
    branch set_franchise_policy p = 1.0 if hour == 0 and day == 0 estimated
    branch transfer_brand_fee p = 1.0 if hour == 0 and day == 0 estimated

role ceo:
  kind = leader
  conflict_group = business_office
  eligibility = age >= 25
  decision where_to_go:
    branch enter_market p = 0.08 if location != Exchange estimated
    branch issue_shares p = 0.08 if location == Exchange estimated
    branch borrow_capital p = 0.08 if location == Exchange estimated
    branch allocate_store_capital p = 1.0 if hour == 0 and day == 0 estimated

role_distribution redditor:
  agent = Person
  group = media_membership
  kind = mass_overlay
  otherwise = media_neither
  overlap = true
  parameters:
    represented_users = 8000000
  share = formula(represented_users / composition_population)
  when = age >= 13 and interest >= 0.3

role_distribution tiktoker:
  agent = Person
  group = media_membership
  kind = mass_overlay
  otherwise = media_neither
  overlap = true
  parameters:
    represented_users = 4000000
  share = formula(represented_users / composition_population)
  when = age >= 13 and activity >= 0.3

role_distribution customer:
  agent = Person
  group = customer_membership
  kind = mass_overlay
  otherwise = not_customer
  overlap = true
  parameters:
    customer_target = 700000000
  share = formula(customer_target / composition_population)
  when = age >= 13

role_distribution cashier:
  agent = Person
  group = cashier_employment
  kind = mass_overlay
  otherwise = not_cashier
  overlap = false
  parameters:
    store_count = 500
    workers_per_store = 4
    cashier_share = 0.25
  share = formula(store_count * workers_per_store * cashier_share / composition_population)
  when = age >= 18 and money >= 0

role_distribution owner:
  agent = Person
  group = ownership_membership
  kind = mass_overlay
  otherwise = not_owner
  overlap = true
  parameters:
    owner_target = 500
  share = formula(owner_target / composition_population)
  when = age >= 21

role_distribution trader:
  agent = Person
  group = market_membership
  kind = mass_overlay
  otherwise = not_trader
  overlap = true
  parameters:
    market_participants = 2000
  share = formula(market_participants / composition_population)
  when = age >= 18 and risk >= 0.4 and money >= 1000

role_distribution migrant:
  agent = Person
  group = migration_membership
  kind = mass_overlay
  otherwise = not_migrant
  overlap = true
  parameters:
    migrant_target = 10000000
  share = formula(migrant_target / composition_population)
  when = age >= 18


action open_reddit:
  aggregate = media_sessions
  duration = Triangular(min=0.05, median=0.10, max=0.25) estimated
  outcome opened p = 1.0 estimated:
    effect self.location = Feed estimated
    next = where_to_go

action media_post:
  aggregate = posts
  duration = Triangular(min=0.05, median=0.20, max=0.50) estimated
  outcome posted p = 0.90 estimated:
    effect self.outrage += 0.001 estimated
    effect self.stress += 0.002 estimated
    effect self.media_trend += 0.02 estimated
    effect place Feed engagement += 1 estimated
    effect self.location = Home estimated
    next = where_to_go
  outcome skipped p = 0.10 estimated:
    effect self.location = Home estimated
    next = where_to_go

action media_comment:
  aggregate = comments
  target = random at Feed
  duration = Triangular(min=0.05, median=0.15, max=0.40) estimated
  outcome commented p = 1.0 estimated:
    effect place Feed engagement += 0.5 estimated
    effect self.location = Home estimated
    next = where_to_go

action media_like:
  aggregate = likes
  duration = Triangular(min=0.02, median=0.05, max=0.15) estimated
  outcome liked p = 1.0 estimated:
    effect place Feed engagement += 0.2 estimated
    effect self.location = Home estimated
    next = where_to_go

action media_share:
  aggregate = shares
  duration = Triangular(min=0.03, median=0.10, max=0.30) estimated
  outcome shared p = 1.0 estimated:
    effect place Feed engagement += 1.5 estimated
    effect self.stress += outrage * 0.01 estimated
    effect self.location = Home estimated
    next = where_to_go

action enter_store:
  aggregate = store_visits
  duration = Triangular(min=0.05, median=0.15, max=0.40) estimated
  outcome entered p = 1.0 estimated:
    effect self.location = Store estimated
    next = where_to_go

action buy:
  aggregate = trade_volume
  target = random at Store where target.role.cashier
  duration = Triangular(min=0.10, median=0.30, max=0.70) estimated
  outcome purchased p = 1.0 if money >= 10 estimated:
    effect self.money -= 10 estimated
    effect target.money += 10 estimated
    effect place Store revenue += 10 estimated
    effect self.location = Home estimated
    next = where_to_go
  outcome declined p = 1.0 if money < 10 estimated:
    effect self.location = Home estimated
    next = where_to_go

action work_cashier:
  aggregate = work_shifts
  target = random at Store where target.role.customer
  duration = Triangular(min=0.20, median=0.50, max=0.90) estimated
  outcome served p = 1.0 estimated:
    effect place Store cash -= 5 estimated
    effect self.money += 5 estimated
    effect self.stress += 0.01 estimated
    effect self.location = Home estimated
    next = where_to_go

action manage_store:
  aggregate = management
  duration = Triangular(min=0.10, median=0.30, max=0.80) estimated
  outcome managed p = 1.0 estimated:
    effect place Store price *= 1.0001 estimated
    effect self.location = Home estimated
    next = where_to_go

action owner_payout:
  aggregate = owner_payouts
  duration = Triangular(min=0.10, median=0.20, max=0.50) estimated
  outcome paid p = 1.0 estimated:
    effect self.money += 10 estimated
    effect place Store cash -= 10 estimated
    effect self.location = Home estimated
    next = where_to_go

action transfer_franchise_fee:
  aggregate = capital_transfers
  duration = Triangular(min=0.10, median=0.20, max=0.50) estimated
  outcome transferred p = 1.0 estimated:
    effect place Store cash -= 10 estimated
    effect place FranchiseOffice cash += 10 estimated
    next = where_to_go

action transfer_brand_fee:
  aggregate = capital_transfers
  duration = Triangular(min=0.10, median=0.20, max=0.50) estimated
  outcome transferred p = 1.0 estimated:
    effect place FranchiseOffice cash -= 10 estimated
    effect place BrandOffice cash += 10 estimated
    next = where_to_go

action transfer_brand_profit:
  aggregate = capital_transfers
  duration = Triangular(min=0.10, median=0.20, max=0.50) estimated
  outcome transferred p = 1.0 estimated:
    effect place BrandOffice cash -= 10 estimated
    effect place ConglomerateOffice cash += 10 estimated
    next = where_to_go

action allocate_store_capital:
  aggregate = capital_transfers
  duration = Triangular(min=0.10, median=0.20, max=0.50) estimated
  outcome allocated p = 1.0 estimated:
    effect place ConglomerateOffice cash -= 10 estimated
    effect place Store cash += 10 estimated
    next = where_to_go

action enter_market:
  aggregate = market_visits
  duration = Triangular(min=0.05, median=0.15, max=0.40) estimated
  outcome entered p = 1.0 estimated:
    effect self.location = Exchange estimated
    next = where_to_go

action secondary_buy:
  aggregate = trade_volume
  target = random at Exchange where target.role.trader and target.shares >= 1
  duration = Triangular(min=0.10, median=0.20, max=0.50) estimated
  outcome filled p = 1.0 estimated:
    effect self.money -= 30 estimated
    effect target.money += 30 estimated
    effect self.shares += 1 estimated
    effect target.shares -= 1 estimated
    effect self.price += 0.01 estimated
    effect place Exchange price *= 1.01 estimated
    effect self.location = Home estimated
    next = where_to_go

action secondary_sell:
  aggregate = trade_volume
  target = random at Exchange where target.role.trader and target.money >= 30
  duration = Triangular(min=0.10, median=0.20, max=0.50) estimated
  outcome filled p = 1.0 estimated:
    effect self.money += 30 estimated
    effect target.money -= 30 estimated
    effect self.shares -= 1 estimated
    effect target.shares += 1 estimated
    effect self.price -= 0.01 estimated
    effect place Exchange price *= 0.99 estimated
    effect self.location = Home estimated
    next = where_to_go

action issue_shares:
  aggregate = issuances
  duration = Triangular(min=0.10, median=0.20, max=0.50) estimated
  outcome issued p = 1.0 estimated:
    effect place Exchange firm_cash += 30 estimated
    effect place Exchange shares_outstanding += 1 estimated
    effect self.location = Home estimated
    next = where_to_go

action borrow_capital:
  aggregate = borrowings
  duration = Triangular(min=0.10, median=0.20, max=0.50) estimated
  outcome borrowed p = 1.0 estimated:
    effect place Exchange lender_cash -= 50 estimated
    effect place Exchange firm_cash += 50 estimated
    effect place Exchange firm_debt += 50 estimated
    effect self.location = Home estimated
    next = where_to_go

action migrate_household:
  aggregate = migrations
  duration = Triangular(min=0.10, median=0.30, max=0.80) estimated
  outcome canada_to_usa p = 1.0 if role.resident_country_Canada estimated:
    effect self.residence = USA estimated
    effect self.household = relocated_household estimated
    effect self.residence_change = 1 estimated
    effect self.location = Home estimated
    next = where_to_go
  outcome usa_to_mexico p = 1.0 if role.resident_country_USA estimated:
    effect self.residence = Mexico estimated
    effect self.household = relocated_household estimated
    effect self.residence_change = 1 estimated
    effect self.location = Home estimated
    next = where_to_go
  outcome mexico_to_canada p = 1.0 if role.resident_country_Mexico estimated:
    effect self.residence = Canada estimated
    effect self.household = relocated_household estimated
    effect self.residence_change = 1 estimated
    effect self.location = Home estimated
    next = where_to_go

action enter_diplomatic_forum:
  aggregate = diplomacy_travel
  duration = Triangular(min=0.10, median=0.30, max=0.80) estimated
  outcome arrived p = 1.0 estimated:
    effect self.location = DiplomaticForum estimated
    next = where_to_go

action commute_boundary:
  aggregate = commuting
  target = random at TransitHub where target.role.commuter and agent != self
  duration = Triangular(min=0.10, median=0.30, max=0.80) estimated
  outcome met p = 1.0 estimated:
    effect self.stress -= 0.01 estimated
    effect target.stress -= 0.01 estimated
    effect place TransitHub visits += 1 estimated
    next = where_to_go

action diplomatic_summit:
  aggregate = diplomacy
  target = random at DiplomaticForum where target.role.president and agent != self
  duration = Triangular(min=0.10, median=0.30, max=0.80) estimated
  outcome agreed p = 0.6 estimated:
    effect relationship with target trust += 0.1 estimated
    effect self.policy += 0.02 estimated
    next = where_to_go
  outcome disagreed p = 0.4 estimated:
    effect relationship with target trust -= 0.05 estimated
    next = where_to_go

action enact_policy:
  aggregate = country_policies
  duration = Triangular(min=0.10, median=0.20, max=0.50) estimated
  outcome enacted p = 1.0 estimated:
    effect self.stress += 0.001 estimated
    effect self.policy += 0.02 estimated
    next = where_to_go

action enact_state_policy:
  aggregate = state_policies
  duration = Triangular(min=0.10, median=0.20, max=0.50) estimated
  outcome enacted p = 1.0 estimated:
    effect self.stress += 0.001 estimated
    effect self.policy += 0.02 estimated
    next = where_to_go

action set_brand_policy:
  aggregate = brand_policies
  duration = Triangular(min=0.10, median=0.20, max=0.50) estimated
  outcome set p = 1.0 estimated:
    effect self.stress += 0.001 estimated
    next = where_to_go

action set_franchise_policy:
  aggregate = franchise_policies
  duration = Triangular(min=0.10, median=0.20, max=0.50) estimated
  outcome set p = 1.0 estimated:
    effect self.stress += 0.001 estimated
    next = where_to_go


composition UrbanLiberal:
  slice = "Physical"
  graph_group = main
  level = neighbourhood
  parameters:
    tax = 0.25
    unemployment = 0.06
    media_trend = 0
    price = 1
    policy = 0
  policies = ExemplarInputs
  households_per_exemplar = 75
  stratum = "dense_urban_high_education"
  stratifiers:
    density = 0.90
    income = 0.70
    household_structure = 0.60
    age = 0.60
    education = 0.80
    household_size = 2.40
  heterogeneity = 0.85
  distribution_status = measured
  provenance = "City and inherited census distributions"
  clock = 1 hours
  sync_up = 1 days
  children:
    HouseholdLiberalUrban: weight = 0.6
    HouseholdConservativeSuburban: weight = 0.2
    HouseholdRuralMixed: weight = 0.2
  places = Home, Work, School, Bar, Cinema
  output population = count()
  output mean_income = mean(money) where age >= 18 with sd

composition SuburbanMixed:
  slice = "Physical"
  graph_group = main
  level = neighbourhood
  parameters:
    tax = 0.25
    unemployment = 0.06
    media_trend = 0
    price = 1
    policy = 0
  policies = ExemplarInputs
  households_per_exemplar = 75
  stratum = "suburban_mixed_households"
  stratifiers:
    density = 0.55
    income = 0.65
    household_structure = 0.80
    age = 0.65
    education = 0.65
    household_size = 2.80
  heterogeneity = 0.55
  distribution_status = inherited
  provenance = "Country distribution inherited by city"
  clock = 1 hours
  sync_up = 1 days
  children:
    HouseholdLiberalUrban: weight = 0.3
    HouseholdConservativeSuburban: weight = 0.5
    HouseholdRuralMixed: weight = 0.2
  places = Home, Work, School, Bar, Cinema
  output population = count()
  output mean_income = mean(money) where age >= 18 with sd

composition RuralMixed:
  slice = "Physical"
  graph_group = main
  level = neighbourhood
  parameters:
    tax = 0.25
    unemployment = 0.06
    media_trend = 0
    price = 1
    policy = 0
  policies = ExemplarInputs
  households_per_exemplar = 75
  stratum = "rural_mixed_households"
  stratifiers:
    density = 0.15
    income = 0.45
    household_structure = 0.75
    age = 0.70
    education = 0.45
    household_size = 3.00
  heterogeneity = 0.25
  distribution_status = inherited
  provenance = "Regional distribution inherited by city"
  clock = 1 hours
  sync_up = 1 days
  children:
    HouseholdLiberalUrban: weight = 0.1
    HouseholdConservativeSuburban: weight = 0.3
    HouseholdRuralMixed: weight = 0.6
  places = Home, Work, School, Bar, Cinema
  output population = count()
  output mean_income = mean(money) where age >= 18 with sd

composition HomogeneousRural:
  slice = "Physical"
  graph_group = main
  level = neighbourhood
  parameters:
    tax = 0.25
    unemployment = 0.06
    media_trend = 0
    price = 1
    policy = 0
  policies = ExemplarInputs
  households_per_exemplar = 75
  stratum = "homogeneous_rural_households"
  stratifiers:
    density = 0.08
    income = 0.40
    household_structure = 0.80
    age = 0.72
    education = 0.40
    household_size = 2.90
  heterogeneity = 0.0
  distribution_status = fallback
  provenance = "Country response fallback; no direct or inherited city distribution"
  clock = 1 hours
  sync_up = 1 days
  children:
    HouseholdLiberalUrban: weight = 0.10
    HouseholdConservativeSuburban: weight = 0.30
    HouseholdRuralMixed: weight = 0.60
  places = Home, Work, School, Bar, Cinema
  output population = count()
  output mean_income = mean(money) where age >= 18 with sd

composition Toronto:
  slice = "Physical"
  graph_group = main
  level = municipality
  distribution_status = measured
  provenance = "Toronto census-derived distribution"
  clock = 1 days
  sync_up = 7 days
  children:
    UrbanLiberal: weight = 0.5
    SuburbanMixed: weight = 0.3333333333333333
    RuralMixed: weight = 0.1666666666666667
  leaders:
    mayor: count = 1
  output population = count()

composition Vancouver:
  slice = "Physical"
  graph_group = main
  level = municipality
  distribution_status = measured
  provenance = "Vancouver census-derived distribution"
  clock = 1 days
  sync_up = 7 days
  children:
    UrbanLiberal: weight = 0.45
    SuburbanMixed: weight = 0.35
    RuralMixed: weight = 0.2
  leaders:
    mayor: count = 1
  output population = count()

composition Lytton:
  slice = "Physical"
  graph_group = main
  level = municipality
  distribution_status = fallback
  provenance = "No city distribution; Canada response fallback"
  clock = 1 days
  sync_up = 7 days
  children:
    HomogeneousRural: weight = 1.0
  leaders:
    mayor: count = 1
  output population = count()

composition LosAngeles:
  slice = "Physical"
  graph_group = main
  level = municipality
  distribution_status = inherited
  provenance = "USA distribution inherited by Los Angeles"
  clock = 1 days
  sync_up = 7 days
  children:
    UrbanLiberal: weight = 0.60
    SuburbanMixed: weight = 0.30
    RuralMixed: weight = 0.10
  leaders:
    mayor: count = 1
  output population = count()

composition Houston:
  slice = "Physical"
  graph_group = main
  level = municipality
  distribution_status = inherited
  provenance = "USA distribution inherited by Houston"
  clock = 1 days
  sync_up = 7 days
  children:
    UrbanLiberal: weight = 0.35
    SuburbanMixed: weight = 0.50
    RuralMixed: weight = 0.15
  leaders:
    mayor: count = 1
  output population = count()

composition MexicoCity:
  slice = "Physical"
  graph_group = main
  level = municipality
  distribution_status = measured
  provenance = "Mexico City census-derived distribution"
  clock = 1 days
  sync_up = 7 days
  children:
    UrbanLiberal: weight = 0.65
    SuburbanMixed: weight = 0.30
    RuralMixed: weight = 0.05
  leaders:
    mayor: count = 1
  output population = count()

composition Monterrey:
  slice = "Physical"
  graph_group = main
  level = municipality
  distribution_status = inherited
  provenance = "Mexico distribution inherited by Monterrey"
  clock = 1 days
  sync_up = 7 days
  children:
    UrbanLiberal: weight = 0.45
    SuburbanMixed: weight = 0.45
    RuralMixed: weight = 0.10
  leaders:
    mayor: count = 1
  output population = count()

composition Ontario:
  slice = "Physical"
  graph_group = main
  level = division
  clock = 7 days
  sync_up = 28 days
  children:
    Toronto: weight = 1.0
  leaders:
    governor: count = 1
  output population = count()

composition BritishColumbia:
  slice = "Physical"
  graph_group = main
  level = division
  clock = 7 days
  sync_up = 28 days
  children:
    Vancouver: weight = 0.99
    Lytton: weight = 0.01
  leaders:
    governor: count = 1
  output population = count()

composition California:
  slice = "Physical"
  graph_group = main
  level = division
  clock = 7 days
  sync_up = 28 days
  children:
    LosAngeles: weight = 1.0
  leaders:
    governor: count = 1
  output population = count()

composition Texas:
  slice = "Physical"
  graph_group = main
  level = division
  clock = 7 days
  sync_up = 28 days
  children:
    Houston: weight = 1.0
  leaders:
    governor: count = 1
  output population = count()

composition CentralMexico:
  slice = "Physical"
  graph_group = main
  level = division
  clock = 7 days
  sync_up = 28 days
  children:
    MexicoCity: weight = 1.0
  leaders:
    governor: count = 1
  output population = count()

composition NorthernMexico:
  slice = "Physical"
  graph_group = main
  level = division
  clock = 7 days
  sync_up = 28 days
  children:
    Monterrey: weight = 1.0
  leaders:
    governor: count = 1
  output population = count()

composition Canada:
  slice = "Physical"
  graph_group = main
  level = country
  clock = 28 days
  sync_up = 84 days
  children:
    Ontario: weight = 0.6666666666666666
    BritishColumbia: weight = 0.3333333333333334
  leaders:
    prime_minister: count = 1
  output population = count()

composition USA:
  slice = "Physical"
  graph_group = main
  level = country
  clock = 28 days
  sync_up = 84 days
  children:
    California: weight = 0.5555555555555556
    Texas: weight = 0.4444444444444444
  leaders:
    president: count = 1
  output population = count()

composition Mexico:
  slice = "Physical"
  graph_group = main
  level = country
  clock = 28 days
  sync_up = 84 days
  children:
    CentralMexico: weight = 0.5882352941176471
    NorthernMexico: weight = 0.4117647058823529
  leaders:
    president: count = 1
  output population = count()

composition World:
  slice = "Physical"
  graph_group = main
  level = world
  clock = 84 days
  sync_up = 84 days
  children:
    Canada: weight = 0.20833333333333334
    USA: weight = 0.625
    Mexico: weight = 0.16666666666666663
  output population = count()
  output mean_income = mean(money) where age >= 18 with sd
  output mean_stress = mean(stress) with sd
  output migration_rate = action_count(migrations, window=run)

composition PersonalFinance:
  slice = "Media"
  graph_group = main
  level = community
  clock = 1 minutes
  sync_up = 1 days
  entity_count = 1
  entity_unit = "community"
  role_targets:
    influencer = 1
  children:
    HouseholdLiberalUrban: weight = 1.0
  leaders:
    influencer: count = 1
  output population = count()
  output posting_rate = action_rate(posts, window=day)

composition Reddit:
  slice = "Media"
  graph_group = main
  level = platform
  clock = 1 days
  sync_up = 7 days
  entity_count = 1
  entity_unit = "platform"
  role_targets:
    redditor = 8000000
    tiktoker = 4000000
  children:
    PersonalFinance: weight = 1.0
  output population = count()
  output posting_rate = action_rate(posts, window=day)

composition BerkshireRetailStore:
  slice = "Conglomerate"
  graph_group = main
  level = store
  clock = 1 days
  sync_up = 7 days
  entity_count = 500
  entity_unit = "stores"
  role_targets:
    cashier = 500
    customer = 700000000
    store_manager = 500
    owner = 500
  children:
    HouseholdConservativeSuburban: weight = 1.0
  places = Store
  leaders:
    store_manager: count = 1
  output population = count()
  output trade_volume = action_count(trade_volume, window=run)
  output owner_payouts = action_count(owner_payouts, window=run)

composition BerkshireRetailFranchise:
  slice = "Conglomerate"
  graph_group = main
  level = franchise
  clock = 7 days
  sync_up = 28 days
  entity_count = 1
  entity_unit = "franchise"
  role_targets:
    franchise_manager = 1
  children:
    BerkshireRetailStore: weight = 1.0
  leaders:
    franchise_manager: count = 1
  output population = count()

composition BerkshireRetailBrand:
  slice = "Conglomerate"
  graph_group = main
  level = brand
  clock = 28 days
  sync_up = 84 days
  entity_count = 1
  entity_unit = "brand"
  role_targets:
    brand_manager = 1
  children:
    BerkshireRetailFranchise: weight = 1.0
  leaders:
    brand_manager: count = 1
  output population = count()

composition BerkshireHathaway:
  slice = "Conglomerate"
  graph_group = main
  level = conglomerate
  clock = 84 days
  sync_up = 84 days
  entity_count = 1
  entity_unit = "conglomerate"
  role_targets:
    ceo = 1
  children:
    BerkshireRetailBrand: weight = 1.0
  leaders:
    ceo: count = 1
  output population = count()
  output owner_payouts = action_count(owner_payouts, window=run)

composition IndependentBusinesses:
  slice = "Independent Businesses"
  graph_group = main
  level = independent_businesses
  clock = 7 days
  sync_up = 28 days
  entity_count = 100
  entity_unit = "firms"
  role_targets:
    owner = 100
    store_manager = 100
  children:
    HouseholdRuralMixed: weight = 1.0
  output population = count()

entity BerkshireHathawayListing:
  field conglomerate_path
  field stock_path
  field legal_identity
  link conglomerate = BerkshireHathaway
  link stock = BerkshireHathawayStock

composition BerkshireHathawayStock:
  slice = "Financial"
  graph_group = main
  level = stock
  clock = 1 days
  sync_up = 7 days
  entity_count = 1
  entity_unit = "stock"
  role_targets:
    trader = 2000
    ceo = 1
  children:
    HouseholdLiberalUrban: weight = 1.0
  places = Exchange
  leaders:
    ceo: count = 1
  output population = count()
  output trade_volume = action_count(trade_volume, window=run)
  output issuances = action_count(issuances, window=run)

composition NewYorkStockExchange:
  slice = "Financial"
  graph_group = main
  level = market
  clock = 7 days
  sync_up = 28 days
  entity_count = 1
  entity_unit = "market"
  children:
    BerkshireHathawayStock: weight = 1.0
  output population = count()
  output trade_volume = action_count(trade_volume, window=run)

composition ConsumerDiscretionary:
  slice = "Financial"
  graph_group = main
  level = sector
  clock = 28 days
  sync_up = 84 days
  entity_count = 1
  entity_unit = "sector"
  children:
    NewYorkStockExchange: weight = 1.0
  output population = count()

composition FinancialEconomy:
  slice = "Financial"
  graph_group = main
  level = economy
  clock = 84 days
  sync_up = 84 days
  entity_count = 1
  entity_unit = "economy"
  role_targets:
    trader = 2000
  children:
    ConsumerDiscretionary: weight = 1.0
  output population = count()
  output trade_volume = action_count(trade_volume, window=run)

composition Petraterrium:
  graph_group = root
  default_run = true
  level = system
  clock = 84 days
  sync_up = 84 days
  agent_pool = World
  children:
    World
    Reddit
    BerkshireHathaway
    IndependentBusinesses
    FinancialEconomy
  output population = count()
