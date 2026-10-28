program SyntheticRoles version "1.0":
  tick_hours = 1 placeholder
  placeholder = "placeholder — agent knowledge, for demo only, to be replaced by research"
  uncertainty = wide
  record_actions = true
  results_title = "Synthetic roles"
  results_subtitle = "Merged role decision trees"

output overview:
  title = "Overview"
  group_by = all
  display = cards
  record = final
  column population = count() label "Population" format integer
  column reddit_posts = action_count(reddit_posts, window=run) label "Reddit posts" format integer
  column tiktok_posts = action_count(tiktok_posts, window=run) label "TikTok posts" format integer

place Home:
  state activity = 0 range 0..100000 estimated

agent Person:
  state roles
  trait activity
  trait interest_match
  state location
  initial:
    activity ~ Uniform(min=0.5, max=0.5) placeholder
    interest_match ~ Uniform(min=0.5, max=0.5) placeholder
    location ~ Categorical(Home: 1.0) placeholder
  routine = at_rest

population:
  size = 1 placeholder
  mix:
    Person = 1.0 placeholder

archetype NeitherUsers:
  sample_households = 1
  composition:
    users count = 1 mix Person:1.0
  output population = count()
  output reddit_posts = action_count(reddit_posts, window=run)
  output tiktok_posts = action_count(tiktok_posts, window=run)

archetype RedditUsers:
  sample_households = 1
  roles = redditor
  composition:
    users count = 1 mix Person:1.0
  output population = count()
  output reddit_posts = action_count(reddit_posts, window=run)
  output tiktok_posts = action_count(tiktok_posts, window=run)

archetype TikTokUsers:
  sample_households = 1
  roles = tiktoker
  composition:
    users count = 1 mix Person:1.0
  output population = count()
  output reddit_posts = action_count(reddit_posts, window=run)
  output tiktok_posts = action_count(tiktok_posts, window=run)

archetype BothUsers:
  sample_households = 1
  roles = redditor, tiktoker
  composition:
    users count = 1 mix Person:1.0
  output population = count()
  output reddit_posts = action_count(reddit_posts, window=run)
  output tiktok_posts = action_count(tiktok_posts, window=run)

archetype Joiner:
  sample_households = 1
  composition:
    users count = 1 mix Person:1.0
  initial:
    activity ~ Uniform(min=1, max=1)
  output population = count()
  output reddit_posts = action_count(reddit_posts, window=run)
  output tiktok_posts = action_count(tiktok_posts, window=run)

archetype Quitter:
  sample_households = 1
  roles = redditor
  composition:
    users count = 1 mix Person:1.0
  output population = count()
  output reddit_posts = action_count(reddit_posts, window=run)
  output tiktok_posts = action_count(tiktok_posts, window=run)

decision at_rest:
  branch rest p = 0.80 estimated
  branch join_reddit p = 1.0 if activity > 0.9 and not role.redditor estimated
  branch quit_reddit p = 1.0 if activity < 0.1 and role.redditor estimated

decision at_feed:
  branch scroll p = 0.40 estimated

role redditor:
  decision at_rest:
    branch post_reddit p = 0.05 + activity * 0.10 + interest_match * 0.20 estimated
  decision at_feed:
    branch post_reddit p = 0.30 + activity * 0.20 + interest_match * 0.30 estimated

role tiktoker:
  decision at_rest:
    branch post_tiktok p = 0.04 + activity * 0.08 + interest_match * 0.18 estimated
  decision at_feed:
    branch post_tiktok p = 0.28 + activity * 0.18 + interest_match * 0.28 estimated

action rest:
  aggregate = rests
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome rested p = 1.0 estimated:
    next = at_rest

action scroll:
  aggregate = scrolls
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome scrolled p = 1.0 estimated:
    next = at_feed

action post_reddit:
  aggregate = reddit_posts
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome posted p = 1.0 estimated:
    effect current place activity += 1 estimated

action post_tiktok:
  aggregate = tiktok_posts
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome posted p = 1.0 estimated:
    effect current place activity += 1 estimated

action join_reddit:
  aggregate = role_changes
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome joined p = 1.0 estimated:
    effect self.roles += redditor estimated
    effect self.activity = 0.5 estimated
    next = at_rest

action quit_reddit:
  aggregate = role_changes
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome quit p = 1.0 estimated:
    effect self.roles -= redditor estimated
    next = at_rest

