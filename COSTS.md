# Cost and time estimate for 200 episodes

> **Status: estimate from token math.** This will be replaced with measured numbers from the demo run
> (the Costs & traces page projects the full run from real approved episodes).

Prices ($ per million tokens, input / output): Opus 5.5 4 / 20 · Sonnet 5.5 2 / 10 ·
Haiku 4.5 1 / 5 · critic on OpenRouter (Gemini Flash class) ≈ 0.3 / 2.5.

| Step | Model | Tokens per episode (in / out) | $ per episode |
|---|---|---|---|
| Draft | Sonnet | ~7.5k (1.5k of it cached) / ~2.5k incl. thinking | ~0.040 |
| Critic | OpenRouter | ~9k / ~0.5k | ~0.004 |
| Revision (assume 40% of episodes need 1) | Sonnet + critic | | ~0.018 |
| Memory extraction | Haiku | ~2k / ~0.6k | ~0.005 |
| Recap every 10 episodes | Haiku | | ~0.001 |
| **Per episode** | | | **≈ $0.07** |

- **Planning once**: bible plus 8 act calls on Opus ≈ $1. Replans on feedback ≈ $0.05 each.
- **200 episodes**: ≈ 200 × $0.07 + $1 ≈ **$15**, with a hard ceiling of 200 × $0.25 cap = $50.
- **Time**: about 45–90 s of model time per episode (draft ≈ 30–50 s, critic and extraction ≈ 10 s,
  revisions add more) → **about 3–5 hours** of model time for the whole serial, plus human review.

## How to reduce it

1. **Prompt caching** of the stable prefix is already on. Moving more stable layers (story-so-far,
   act info) ahead of the volatile ones raises the hit rate further.
2. **Batch API (50% off)** for unattended stretches: draft a whole act overnight and review in the morning.
3. **Lower writer effort / skip the critic** on low-risk "connective" beats. Keep the full loop for
   beats that open or pay off threads.
4. **Cheaper critic first, escalate on doubt**: run the rule checks and a small model, and call the
   strong critic only when they flag something.
5. **Parallelise within an act** after human sign-off on its first episodes. The wall-clock time drops
   ~5×, at some risk to continuity.
