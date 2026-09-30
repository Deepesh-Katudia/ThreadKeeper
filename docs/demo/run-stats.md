# Dead Letter Route: measured run statistics

From the `llm_calls` log: 59 model calls, 4 approved episodes.

## Projection for the full serial

- Average per approved episode: **$0.076** and **52s** of model time
- Arc planning: **$1.23** per plan (this story was planned 2 times, $2.46 in total)
- All 200 episodes: about **$16.48** and **2.9 hours** of model time, plus human review
- Hard ceiling from the per-episode cap: 200 x $0.25 = $50

## By step

| Step | Model | Calls | Failed | Tokens in | Tokens out | Cost | Avg latency |
|---|---|---|---|---|---|---|---|
| plan_act | claude-opus-5-5 | 16 | 0 | 92,473 | 86,362 | $2.097 | 66.1s |
| plan_bible | claude-opus-5-5 | 2 | 0 | 3,328 | 17,539 | $0.367 | 102.8s |
| revise | claude-sonnet-5-5 | 7 | 0 | 37,253 | 12,802 | $0.207 | 12.7s |
| draft | claude-sonnet-5-5 | 6 | 0 | 25,396 | 10,828 | $0.165 | 19.3s |
| replan_beats | claude-opus-5-5 | 1 | 0 | 7,961 | 3,930 | $0.111 | 45.8s |
| extract_memory | claude-haiku-4-5 | 6 | 1 | 11,811 | 2,513 | $0.024 | 6.5s |
| critic | google/gemini-2.5-flash | 13 | 0 | 44,537 | 3,021 | $0.021 | 2.3s |
| eval | google/gemini-2.5-flash | 8 | 0 | 5,938 | 703 | $0.004 | 2.0s |

## Per episode

| Ep | Calls | Revisions | Cost | Model time |
|---|---|---|---|---|
| 1 | 3 | 0 | $0.031 | 32s |
| 2 | 7 | 2 | $0.088 | 53s |
| 3 | 10 | 2 | $0.133 | 87s |
| 4 | 5 | 1 | $0.053 | 35s |

## LangSmith evaluation (4 episodes, $0.004)

- **word count**: 100%
- **no repetition**: 100%
- **hook**: 100%
- **consistency**: 100%
- **follows directives**: -

Experiment: https://smith.langchain.com/o/4422c697-1f24-4d4c-9ec7-10561218f97a/datasets/1c01c428-71aa-4376-ad76-68224ebe66b2/compare?selectedSessions=f46b497c-94d1-4407-8c29-ca355cac6af9
