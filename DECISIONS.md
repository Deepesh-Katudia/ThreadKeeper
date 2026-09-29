# Design decisions

**Shape.** A plain Python pipeline, not an agent framework: plan → draft → critic → (revise ≤2) →
extract memory → human. Every episode row has a status (`planned → drafting → in_review → approved`),
so human review gates and resuming come for free, with nothing hidden in a graph runtime.
Four models, each doing one job: Opus plans, Sonnet writes, Haiku keeps records, and a
non-Claude model critiques, so the judge doesn't share the writer's blind spots.

## 1. How does it remember the story at episode 150?

Nothing is stuffed into context. The prompt is built from layers, each with a fixed budget, so
episode 150's prompt is about the same size as episode 5's (`backend/story/context.py`):

| Layer | What goes in | Where it comes from |
|---|---|---|
| Arc position | act goal, act-ending turning point, previous beat, this beat, next 3 beats | arc plan (episode rows) |
| Story so far | ≤350-word recap | re-summarised every 10 episodes and at act ends |
| Recent episodes | last 8 summaries and hooks, plus the final 150 words of the previous episode | per-episode summaries |
| Characters in play | main cast, anyone on the page in the last 3 episodes, anyone the upcoming beats name; plus a one-line list of the dead and missing | character store |
| Canon facts | facts about those characters or the beat's subjects, plus the 10 newest (≤40) | fact store, each fact tagged with `source_episode` |
| Open threads | sorted by urgency: due soon, overdue, to be introduced | thread store, planned payoff episode |
| Standing instructions | every active piece of human feedback | directives table |

The system prompt (world rules, style guide, main cast) is identical on every call and cached.
Retrieval is by entity match, not embeddings. That is cheap, predictable and easy to inspect: the UI
shows exactly what the writer saw for every episode.

## 2. Where does the human step in, and why there?

- **Arc gate (before writing).** This is where changes are cheapest and have the biggest effect.
  A bad plan poisons 200 episodes.
- **Episode gate (after the critic, before canon).** The human sees the draft, the critic's report,
  and the memory it would add. Nothing becomes canon until approved, so a rejected draft never
  leaks facts.
- **Feedback ("slow down the romance", "kill off Ravi").** This is saved as a *directive* in every
  future prompt, and the next 20 unwritten beats are re-planned around it. Feedback reaches future
  episodes through two routes: the prompt and the plan.
- **Editing history.** Editing an approved episode deletes the memory it produced (facts, deaths,
  threads, all keyed by episode), re-extracts from the new text, rebuilds the recap if needed,
  and marks later unapproved drafts *stale*.
- **Optional batch mode** auto-approves episodes the critic passes and stops at the first one it
  flags. The human's attention goes where the risk is.

## 3. How do we catch inconsistency or repetition before a human does?

- Code rules: word count, and dead characters named in a draft (flagged for the critic to judge).
- The critic, from another model family, checks the draft against the retrieved canon, character
  statuses, directives, the recent summaries and a one-line index of *every* earlier episode. It
  returns structured problems (contradiction / repetition / directive / hook score). "Revise"
  triggers a rewrite, capped at 2 revisions and a per-episode dollar limit.
- After extraction, the new summary's word overlap with every earlier summary flags near-repeats.
- Every critic verdict and every human decision is logged to the episode's LangSmith trace, so
  critic-vs-human agreement is measured over time instead of assumed. That number decides how
  much to trust batch auto-approve. On-demand LangSmith experiments score consistency, hooks,
  directive-following and repetition across all approved episodes.

## 4. What breaks first as the story grows, and how would we fix it?

1. **Fact retrieval by entity match.** Facts about places or objects that go unnamed in the beat
   get missed, and the fact store grows without limit. *Fix:* embeddings over facts, plus
   periodic fact consolidation ("Ravi's arm is broken" → "healed" retires the old fact).
2. **The critic's earlier-episode index** grows linearly (~20 tokens per episode). Around episode 300+
   it gets expensive. *Fix:* embed summaries and retrieve the top-k similar ones.
3. **Recap drift.** Summaries of summaries lose detail. *Fix:* keep act summaries as a second tier
   (already stored) and feed the current act's summary in addition to the rolling recap.
4. **Editing history far back** (e.g. episode 40 when we're at 150) repairs memory but not the
   *prose* of episodes 41–150. *Fix:* use the facts' provenance to find later episodes that relied on
   the changed facts and queue them for a human-approved "continuity patch" rewrite.
5. **Name matching.** Two characters sharing a first name confuse the lookups. *Fix:* stable character IDs
   in extraction output.
