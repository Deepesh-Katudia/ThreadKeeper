# Threadkeeper: an agentic serial story writer with a human in the loop

## Context
a system that turns a one-line premise into a **200-episode serial** (400–700 words per episode, each ending on a hook) that stays consistent all the way through. A human must be able to approve the arc, review/edit/reject episodes, and give feedback that **carries forward** into later episodes. The system must also resume after stopping, log every run (steps, retries, tokens, cost, latency), cap cost per episode, and estimate the cost of all 200 episodes.
Deliverables: repo + README, live URL (web), full arc plus ≥15 episodes with ≥2 HITL interventions, a screen recording, and a one-page `DECISIONS.md`.
Graders care most about memory design at episode 150, HITL propagation, and honest reasoning. Polish matters less.

Assets: Anthropic API key, LangSmith credits, OpenRouter credits. Language: Python backend (FastAPI on Render) and Next.js frontend (Vercel). Web UI, not a terminal app. Code should read as if a person wrote it: small, plainly named functions with few abstractions.

## Name
**Threadkeeper**: the product's job is to keep every story thread alive and consistent. (Alternatives: *Cliffnote*, *SerialForge*.)

## Tech stack
| Layer | Choice | Why |
|---|---|---|
| Frontend | **Next.js (App Router, TypeScript)** on **Vercel** | Starts as a plain, functional UI. The user will later supply a ready dashboard design and a prompt to restyle it |
| Backend API | **FastAPI** (Python) on **Render** | Typed Pydantic schemas, auto OpenAPI docs, easy to call from Next.js |
| Orchestration | **Plain Python functions + an explicit status field** (no LangGraph) | Review stops are just statuses in the DB, so it resumes for free and every step is readable |
| Storage | **SQLAlchemy 2.0** models. SQLite locally, **Render Postgres** in production via `DATABASE_URL` | Render's free disk is wiped on redeploy, so production needs Postgres. The same code runs on both |
| Long jobs | FastAPI `BackgroundTasks`, with job status stored in the DB and polled by the frontend | Writing an episode takes ~30–90 s. Without a queue, a Render restart just leaves the episode in `drafting`, and it gets retried on resume |
| Access control | Shared passcode header (`X-Access-Key`) + CORS locked to the Vercel domain | Stops strangers from burning API credits on the public URL. Spending caps also set in the Anthropic/OpenRouter consoles |
| Writer model | Claude Sonnet 5.5 (Anthropic SDK) | Prose quality |
| Arc planner | Claude Opus 5.5 (runs once per story, plus replans) | Best at structuring 200 episodes |
| Extractor / summariser | Claude Haiku 4.5 | Cheap structured JSON |
| Critic / judge | A non-Claude model via **OpenRouter** (e.g. a GPT or Gemini model) | Different model family, so the judge isn't grading its own style |
| Tracing + evals | **LangSmith** (`@traceable`, `evaluate()` on datasets) | Covers the "Traceable" requirement plus offline evals |
| Local cost ledger | `llm_calls` table in the DB | Per-episode cost cap and a cost panel in the UI |

## Architecture

```
Premise ─► [Arc Planner] ─► arc plan (8 acts, 200 one-line beats, character arcs)
                 │                         ▲
                 ▼                         │ replan upcoming beats
          HUMAN: approve/edit arc     [Feedback Handler] ◄── HUMAN feedback
                 │                         │ (becomes a standing directive)
                 ▼                         ▼
 for episode N: [Context Builder] ─► [Writer] ─► [Critic] ─(fail, ≤2x)─► [Reviser]
                                                    │ pass
                                                    ▼
                                             [Memory Extractor]  (proposed updates)
                                                    ▼
                                  HUMAN: approve / edit / reject / feedback
                                                    ▼
                                    commit memory updates → episode N+1
```

### Memory for episode 150 (the core of DECISIONS.md)
Every episode's prompt has a **fixed size** no matter how far into the story we are:
1. **Story bible**: premise, tone/style guide, current act goal (always included).
2. **Arc plan**: beats N-1 … N+3, so the writer knows where it's heading.
3. **Rolling summaries**: last ~8 episode summaries (~80 words each), plus the current act summary and a compressed "story so far" (regenerated every 10 episodes).
4. **Character & fact store** (SQLite): characters with status (alive/dead/missing), traits and relationships. Canon facts are stored with `source_episode`. Only the characters and facts relevant to the current beat and the recent cast are retrieved, by entity match.
5. **Open threads**: each has opened_at, a planned payoff episode, and a status. Threads overdue or close to their payoff are pushed into the prompt.
6. **Standing directives**: human feedback such as "slow down the romance" or "Ravi is dead" goes into every prompt until it expires.
7. **Last ~150 words of episode N-1** to carry the voice and the handoff forward.

### Catching inconsistency before the human sees it
- The critic checks the draft against the retrieved facts, character statuses and directives, and returns structured JSON: `contradictions[]`, `repeated_beats[]`, `hook_score`, `word_count_ok`.
- Repetition check: compare the draft summary with past summaries (cheap n-gram/embedding similarity) and flag near-duplicates.
- Hard rules in code: word count 400–700, and dead characters speaking gets flagged.
- Stopping rules: at most 2 revisions, and a per-episode cost cap (e.g. $0.25). When either is hit, the episode goes to the human with the critic's notes attached.

### How HITL feedback propagates
- **Arc gate**: before any writing, the human edits acts, beats and characters inline.
- **Episode gate**: approve / edit text / reject (regenerate with a reason) / feedback.
- Feedback is saved to a `directives` table, and the Feedback Handler replans the **upcoming** beats (e.g. adds a death beat and updates character status). Future episodes follow it because it's in their context and in the plan.
- Edits to past episodes: facts are keyed by episode, so editing episode 40 re-extracts its memory, drops the stale facts, and marks drafted-but-unapproved later episodes as stale. This covers the likely "live twist" in the next round.

### Resume
All state lives in the DB, and each episode has a status (`planned → drafted → in_review → approved`). Opening the app picks up at the first non-approved episode. There's also an "auto-write next K episodes" button that stops at every review gate (or at a gate every K episodes).

## Project layout (monorepo)
```
threadkeeper/
  frontend/                 # Next.js → Vercel (plain UI for now, restyled later from the user's dashboard)
    app/page.tsx                       # list stories + new premise form
    app/stories/[id]/arc/page.tsx      # view/edit/approve arc
    app/stories/[id]/episodes/page.tsx # step through episodes: approve / edit / reject / feedback, "write next"
    app/stories/[id]/memory/page.tsx   # characters, facts, open threads, directives
    app/stories/[id]/costs/page.tsx    # per-episode tokens, cost, latency, retries
    lib/api.ts                         # typed fetch helpers (NEXT_PUBLIC_API_URL)
  backend/                  # FastAPI → Render
    main.py                 # app, CORS, passcode check
    api/routes_stories.py  routes_episodes.py  routes_memory.py
    story/
    config.py               # models, prices, caps (env-driven)
    llm.py                  # call_claude / call_openrouter, cost + latency logging, @traceable
    db.py / models.py       # SQLAlchemy models + session helper
    planner.py              # plan_arc, replan_upcoming_beats
    context.py              # build_episode_context (layered memory)
    writer.py               # draft_episode, revise_episode
    critic.py               # review_draft (LLM) + rule checks
    memory.py               # extract_updates, commit_updates, summarise_act
    feedback.py             # save_directive, apply_feedback
    pipeline.py             # write_next_episode: the whole loop in ~40 readable lines
    prompts/*.md
    evals/  build_dataset.py  run_evals.py   # LangSmith evaluate(): hook, consistency, repetition, directive-adherence, word count
    tests/                                   # pytest: context builder, rule checks, pipeline with a fake LLM, API routes
    requirements.txt  render.yaml  .env.example
  README.md  DECISIONS.md  COSTS.md  .gitignore
```

### Main API endpoints
`POST /stories` (premise → plans arc in background) · `GET /stories/{id}` · `PUT /stories/{id}/arc` · `POST /stories/{id}/arc/approve` · `POST /stories/{id}/episodes/next` (write next, background) · `GET /stories/{id}/episodes/{n}` · `POST .../{n}/approve` · `PUT .../{n}` (human edit → re-extract memory) · `POST .../{n}/reject` (with reason → regenerate) · `POST /stories/{id}/feedback` (directive + replan) · `GET /stories/{id}/memory` · `GET /stories/{id}/costs` · `GET /jobs/{id}`

## Build order (≈6–8 h backend-heavy)
0. Save this plan as `docs/PLAN.md`. Then `git init`, add remote `origin` = https://github.com/Deepesh-Katudia/ThreadKeeper---an-agentic-serial-story-writer-with-a-human-in-the-loop-.git, add `.gitignore` (`.env`, `node_modules`, `*.db`, `.next`, `__pycache__`), first commit `docs: add project plan` (no Claude attribution), and push to `main`.
1. Backend skeleton: config, llm wrapper with cost logging and LangSmith tracing, SQLAlchemy models, tests with a fake LLM.
2. Arc planner and arc endpoints.
3. Context builder, writer, critic, reviser, memory extractor → `write_next_episode` with a background job.
4. Episode review endpoints and the feedback handler with replanning; resume logic.
5. Plain Next.js frontend: stories, arc editor, episode reviewer, memory, costs.
6. LangSmith eval suite; generate the demo: full arc, 15+ episodes, 2+ HITL interventions.
7. README, DECISIONS.md, COSTS.md (200-episode estimate from measured per-episode cost, plus reduction levers: prompt caching of the bible, Haiku for extraction, batch API, fewer critic passes on low-risk episodes); deploy backend to Render (+ Postgres) and frontend to Vercel.
8. Later, driven by the user: restyle the frontend from the dashboard and prompt they provide.

## Git
Conventional commits. Per the user's instruction, **no Claude co-author/attribution lines** in commits or PRs. Repo: https://github.com/Deepesh-Katudia/ThreadKeeper---an-agentic-serial-story-writer-with-a-human-in-the-loop- `.env` stays gitignored; only `.env.example` is committed.

## Verification
- `pytest` passes (fake LLM, so it costs nothing and gives the same result every run).
- Run locally with `uvicorn main:app` + `npm run dev`: create a story → edit/approve arc → write episodes 1–3 → give feedback ("kill off X") → confirm the directive shows up in the ep 4 context and the replanned beats → stop the app, restart it, and check it resumes at the right episode.
- LangSmith: traces show every step, retry, token count and cost; `python evals/run_evals.py` produces scores.
- Costs page per-episode totals match LangSmith.
