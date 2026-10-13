# Design decisions

**Shape.** A plain Python pipeline: plan → draft → critic → revise (≤2, under a $0.25 cap) → extract
memory → human. Each episode row carries a status (`planned → in_review → approved`), so review
gates and resume need no framework. Opus plans, Sonnet writes, Haiku keeps records, and a critic
from another model family (Gemini) judges, so it doesn't share the writer's blind spots.

## 1. How does it remember the story at episode 150?

Layered memory, each layer with a fixed budget, so episode 150's prompt is the same size as episode 5's:

- **Arc position:** act goal and turning point, the previous beat, this beat, the next 3 beats.
- **Rolling recap:** ≤350 words, refreshed every 10 episodes. Act summaries are stored at act ends.
- **Recent episodes:** the last 8 summaries and hooks, plus the previous episode's opening line and final 150 words.
- **Characters and facts:** retrieved, not dumped. That means the main cast, anyone seen in the last
  3 episodes or named in upcoming beats, plus a list of the dead and missing. Facts about those
  entities are capped at 40, with every fact from the last 3 episodes always kept. Each fact records
  the episode and version it came from, and each episode records the ids of the canon its writer saw.
- **Open threads:** sorted by urgency (due soon, overdue, to be introduced).
- **Standing instructions:** every active piece of human feedback.

The world rules and style guide sit in a cached system prompt. The UI shows exactly what the
writer saw for every episode.

## 2. Where does the human step in, and why there?

- **Arc gate:** the cheapest place to change the most, since a bad plan poisons 200 episodes.
- **Episode gate:** after the critic, before canon. Nothing enters memory until approved, so a
  rejected draft never leaks facts. A rejection note is sent to the rewrite.
- **Story direction:** saved as a directive in every future prompt *and* re-plans the next 20
  unwritten beats, so it reaches future episodes by two routes. In the demo, "kill off Harlan"
  rewrote 6 upcoming beats. The planner also noticed Harlan was already dead in canon and staged
  his death on-page instead ([`docs/demo/interventions.md`](docs/demo/interventions.md)).
- **Editing history (ripple review):** an edit to an approved episode becomes a new *version* and a
  tracked ripple with three gates. (1) The human confirms or trims the memory diff before canon
  changes; facts are retracted, never deleted, so restoring a version is exact and needs no model.
  (2) The next 20 episodes are checked cheapest-first: code signals (recorded context ids, text
  matches, the next episode), then a critic call with verifiable quotes, then a smallest-patch
  proposal. The human accepts, edits, keeps or rewrites each in order; an accepted fix re-checks
  later ones. (3) New beats are proposed and applied only on approval. Writing waits meanwhile,
  and each ripple stops at a $0.50 cap.

## 3. How do we catch inconsistency or repetition before a human does?

Code checks catch wrong lengths and dead characters who reappear. The critic checks each draft
against retrieved canon, character status, directives and a one-line index of every earlier
episode, and returns structured problems that trigger a revision. Summary overlap flags
near-repeats. Every critic verdict and human decision is logged to the episode's LangSmith trace,
so critic-vs-human agreement is *measured*: 3 of 4 in the demo. That number sets how far to trust
batch auto-approve. LangSmith experiments score hook, consistency, directives and repetition.

## 4. What breaks first as the story grows, and how would we fix it?

1. **Entity-match retrieval misses** facts about unnamed places and objects, and the fact store
   grows without limit. *Fix:* embeddings, and consolidating facts that supersede each other.
2. **The critic's episode index grows linearly.** *Fix:* retrieve the top-k similar summaries instead.
3. **Recap drift:** summaries of summaries lose detail. *Fix:* also feed the current act summary.
4. **Ripples only look 20 episodes ahead**, and an episode with no recorded context is matched by
   text alone, so a paraphrased dependency can slip through. *Fix:* embed facts and episodes and
   check by similarity. A rewritten episode is drafted from canon, not from its later neighbours.
5. **The critic is stricter than the reader:** 7 revisions in 4 episodes doubled the cost. *Fix:*
   calibrate it against the logged human decisions.
