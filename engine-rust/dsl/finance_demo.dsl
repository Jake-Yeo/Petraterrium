program MarketLab version "1.0":
  tick_hours = 1 placeholder
  placeholder = "estimated pending the research pipeline"
  uncertainty = wide
  record_actions = true
  results_title = "Market laboratory"
  results_subtitle = "DSL-only finance system"

output market_summary:
  title = "Market summary"
  group_by = all
  display = cards
  record = final
  column participants = count() label "Participants" format integer
  column mean_cash = mean(cash) label "Mean cash" format currency
  column mean_holdings = mean(holdings) label "Mean holdings" format decimal
  column price = place_state(Exchange, price) label "Price" format currency
  column buys = action_count(buys, window=run) label "Buys" format integer
  column sells = action_count(sells, window=run) label "Sells" format integer

place Exchange:
  state price = 25 range 1..200 placeholder
  state volume = 0 range 0..100000 placeholder

agent Broker:
  trait risk_tolerance
  state cash range 0..100000 placeholder
  state holdings range 0..1000 placeholder
  state location
  initial:
    risk_tolerance ~ Beta(alpha=2, beta=2) placeholder
    cash ~ LogNormal(mean=7, sd=0.4, min=100, max=100000) placeholder
    holdings ~ Uniform(min=1, max=5) placeholder
    location ~ Categorical(Exchange: 1.0) placeholder
  routine = trade

population:
  size = 12 placeholder
  mix:
    Broker = 1.0 placeholder

decision trade:
  branch buy p = max(0.01, risk_tolerance * (1 - place.price / 200)) if cash >= place.price placeholder
  branch sell p = max(0.01, (1 - risk_tolerance) * place.price / 200) if holdings > 0 placeholder
  branch observe p = 0.15 placeholder

action buy:
  aggregate = buys
  duration = Triangular(min=0.1, median=0.2, max=0.4) placeholder
  outcome filled p = 1 placeholder:
    effect self.cash -= place.price placeholder
    effect self.holdings += 1 placeholder
    effect place Exchange price += 0.02 placeholder
    effect place Exchange volume += 1 placeholder
    next = trade

action sell:
  aggregate = sells
  duration = Triangular(min=0.1, median=0.2, max=0.4) placeholder
  outcome filled p = 1 placeholder:
    effect self.cash += place.price placeholder
    effect self.holdings -= 1 placeholder
    effect place Exchange price -= 0.01 placeholder
    effect place Exchange volume += 1 placeholder
    next = trade

action observe:
  aggregate = observations
  duration = Triangular(min=0.1, median=0.2, max=0.4) placeholder
  outcome wait p = 1 placeholder:
    next = trade

aggregate_function MarketLab:
  inputs:
    liquidity_shock = 0 range -0.2..0.2
  time = 2 days
  time_points = 1, 2
  effects:
    field cash *= 1 + liquidity_shock
    decision buy *= 1 + liquidity_shock
    decision sell *= 1 - liquidity_shock
  outputs:
    mean_cash = formula(liquidity_shock) from mean(cash)
    mean_holdings = formula(liquidity_shock) from mean(holdings)
    mean_price = formula(liquidity_shock) from place_state(Exchange, price)
    buy_count = formula(liquidity_shock) from action_count(buys, window=run)
    sell_count = formula(liquidity_shock) from action_count(sells, window=run)
  cache:
    valid_for = 14 days
    inputs_hash = hash(liquidity_shock)
    invalidate_on:
      liquidity_shock change > 0.05
      event = market_halt
