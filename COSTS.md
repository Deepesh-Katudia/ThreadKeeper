# Cost and time for 200 episodes

Measured from the `llm_calls` log of the demo run (*Dead Letter Route*: 59 model calls,
4 approved episodes, one rejection and rewrite, one story-direction re-plan, one evaluation run).
Full breakdown: [`docs/demo/run-stats.md`](docs/demo/run-stats.md).

## What we measured

| Step | Model | Cost per call | Notes |
|---|---|---|---|
| Arc planning (bible + 8 acts) | Claude Opus 5.5 | **$1.23 per plan** | Once per story, ~3.5 min (acts planned in parallel) |
| Draft | Claude Sonnet 5.5 | ~$0.028 | ~19 s |
| Critic | Gemini 2.5 Flash (OpenRouter) | ~$0.002 | ~2 s |
| Revision | Claude Sonnet 5.5 | ~$0.030 | ~13 s; triggered when the critic objects |
| Memory extraction | Claude Haiku 4.5 | ~$0.004 | ~6 s |
| Re-plan after feedback | Claude Opus 5.5 | ~$0.11 | Per human instruction |
| LangSmith evaluation | Gemini 2.5 Flash | ~$0.001 per episode | On demand |

**Per episode: $0.076 on average** ($0.031 to $0.133), about **52 s** of model time.
Revisions drive the spread: episode 1 passed first time ($0.03), episodes 2 and 3 needed two
revisions each ($0.09 and $0.13).

## Estimate for all 200 episodes

| | Cost | Model time |
|---|---|---|
| Arc plan | $1.23 | ~3.5 min |
| 200 episodes × $0.076 | $15.20 | ~2.9 h |
| ~10 feedback re-plans × $0.11 | $1.10 | ~8 min |
| **Total** | **≈ $17.50** | **≈ 3 hours**, plus human review |

The hard ceiling is 200 × the $0.25 per-episode cap = $50. When the cap is hit, the revision
loop stops and the episode goes to the human with the critic's notes attached.

**Wall-clock time** is dominated by human review, not the models. With batch auto-approve
(episodes the critic passes are approved automatically), 200 episodes take about 3 hours of
unattended model time, plus the review of flagged episodes.

## How we'd reduce it

1. **Tune the critic (the biggest lever).** 7 revisions across 4 episodes doubled the writing
   cost. The critic-vs-human table shows the human approved an episode the critic had flagged,
   so the critic is stricter than the reader. Loosening its "revise" threshold, or allowing one
   revision instead of two, cuts about 40%.
2. **Plan acts with Sonnet instead of Opus.** The bible stays on Opus; the 8 act-beat calls
   ($1.05 of the $1.23) drop to about $0.35.
3. **Prompt caching** is on for the stable story bible. Moving the rolling recap ahead of the
   per-episode layers would raise the cache hit rate further.
4. **Batch API (50% off)** for unattended stretches: draft a whole act overnight, review in the morning.
5. **Skip the critic on low-risk beats.** Keep the full loop for beats that open or pay off
   threads; connective episodes get the code checks only.

With 1, 2 and 4 applied, a 200-episode run comes to roughly **$5–8**, depending on how much of it can wait for batch processing.
