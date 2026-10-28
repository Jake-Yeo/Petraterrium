program SyntheticCorporate version "1.0":
  tick_hours = 1 placeholder
  placeholder = "placeholder — agent knowledge, for demo only, to be replaced by research"
  uncertainty = wide
  record_actions = true
  results_title = "Synthetic corporate"
  results_subtitle = "Generic corporate composition"

output overview:
  title = "Overview"
  group_by = all
  display = cards
  record = final
  column population = count() label "Population" format integer

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

population:
  size = 1 placeholder
  mix:
    Customer = 1.0 placeholder

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
  branch buy p = 1.0 if role.customer estimated

decision cashier_day:
  branch work_cashier p = 1.0 if role.cashier and employed estimated

decision employment_day:
  branch work_cashier p = 0.98 if role.cashier and employed and place.open == 1 estimated
  branch quit_job p = 0.02 if role.cashier and employed estimated
  branch job_search p = 1.0 if role.cashier and not employed estimated

decision manager_day:
  branch manage_store p = 0.98 if role.manager and place.open == 1 estimated
  branch fire_worker p = 0.01 if role.manager and place.worker_count > 0 estimated
  branch close_store p = 0.01 if role.manager and place.open == 1 estimated
  branch reopen_store p = 1.0 if role.manager and place.open == 0 estimated

decision family_owner_day:
  branch owner_payout p = 1.0 if role.owner and hour >= 23 and place.cash > 50 estimated
  branch family_manage p = 1.0 if role.owner and hour < 23 estimated

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
