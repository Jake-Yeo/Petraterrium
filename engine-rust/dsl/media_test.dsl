program SyntheticMedia version "1.0":
  tick_hours = 1 placeholder
  placeholder = "placeholder — agent knowledge, for demo only, to be replaced by research"
  uncertainty = wide
  record_actions = false
  results_title = "Synthetic media"
  results_subtitle = "Generic media composition"

output overview:
  title = "Overview"
  group_by = all
  display = cards
  record = final
  column population = count() label "Population" format integer

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

population:
  size = 1 placeholder
  mix:
    User = 1.0 placeholder

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
