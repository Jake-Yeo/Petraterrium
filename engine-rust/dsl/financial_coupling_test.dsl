program SyntheticFinancialCoupling version "1.0":
  tick_hours = 1 placeholder
  placeholder = "placeholder — agent knowledge, for demo only, to be replaced by research"
  uncertainty = wide
  record_actions = true
  results_title = "Synthetic corporate and financial peers"
  results_subtitle = "Generic conservation and coupling"

output overview:
  title = "Overview"
  group_by = all
  display = cards
  record = final
  column population = count() label "Population" format integer

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

population:
  size = 1 placeholder
  mix:
    FinancialPerson = 1.0 placeholder

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

role manager:
  decision at_sync:
    branch set_store_schedule p = 1.0 if hour == 0 estimated

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

action set_store_schedule:
  aggregate = store_schedules
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
