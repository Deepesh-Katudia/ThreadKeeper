# Threadkeeper

An agentic system that writes a **200-episode serial story** from a one-line premise, with a
human in the loop who approves the arc, reviews every episode, and steers the story with
feedback that carries forward.

- **Backend**: Python, FastAPI, SQLAlchemy on Supabase Postgres (SQLite also works for offline use)
- **Frontend**: Next.js on Vercel
- **Models**: Claude Opus 5.5 plans the arc, Claude Sonnet 5.5 writes, Claude Haiku 4.5 keeps the
  continuity records, and a non-Claude model on OpenRouter plays the critic
- **Tracing and evals**: LangSmith, plus a per-call cost ledger in the database

How it remembers, where the human steps in, and what breaks first are covered in
[DECISIONS.md](DECISIONS.md). Cost and time estimates are in [COSTS.md](COSTS.md).

## How it works

```
premise → [plan bible: cast, 8 acts, threads] → [plan 200 beats, one act per call, in parallel]
        → HUMAN edits / approves the arc
        → for each episode:
             build context (layered memory, fixed size)
             → draft (Sonnet) → critic (other model family) → revise, at most 2 times, under a $ cap
             → extract memory (summary, facts, deaths, threads)
             → HUMAN approves / edits / rejects with a note / gives story-wide feedback
             → approved memory becomes canon; recap refreshed every 10 episodes
```

Every step, retry, token count, cost and latency is written to the `llm_calls` table (shown on
the **Costs & traces** page) and traced in LangSmith when `LANGSMITH_TRACING=true`.

## Run it locally (about 5 minutes)

Requirements: Python 3.11+, Node 20+.

```bash
# 1. Backend
cd backend
python -m venv .venv
.venv/Scripts/activate            # Windows. On macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # fill in DATABASE_URL (Supabase) and the API keys
uvicorn main:app --reload         # http://localhost:8000/docs

# 2. Frontend (new terminal)
cd frontend
npm install
cp .env.example .env.local        # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                       # http://localhost:3000
```

Without `OPENROUTER_API_KEY`, the critic falls back to Claude Haiku and logs a warning.

## Using it

1. **Home**: enter a premise and press *Plan the arc*. Planning takes a few minutes.
2. **Arc plan**: read and edit the cast, the acts and all 200 beats, then approve.
3. **Episodes**: press *Write episode N*. Each draft arrives with the critic's report, the memory
   it would add, and the exact context the writer saw. Then:
   - **Approve**: its facts, deaths and threads become canon.
   - **Edit text**: works on approved episodes too. The episode's memory is re-extracted and
     later drafts are marked stale.
   - **Reject…**: add a note; it is rewritten with that note.
   - **Steer the rest of the story**: feedback becomes a standing instruction in every future
     prompt, and the next 20 unwritten beats are re-planned around it.
   - **Batch + auto-approve**: writes several episodes and stops at the first one the critic flags.
4. **Resume**: close everything and come back later. State lives in the database, so writing
   continues at the first unapproved episode.

## Tests and evals

```bash
cd backend
pytest -q                               # uses a fake model, costs nothing
python -m evals.run_evals --story 1     # LangSmith: word count, repetition, hook, consistency, directives
```

## Deploy

- **Database → Supabase**: use the "Session pooler" connection string as `DATABASE_URL`. Tables are
  created on first start with Row Level Security on, so Supabase's public REST API can't read them.
- **Backend → Render**: `render.yaml` creates the web service. Set `DATABASE_URL`,
  `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `LANGSMITH_API_KEY`, `ACCESS_KEY` and
  `FRONTEND_ORIGINS` (your Vercel URL) in the Render dashboard.
- **Frontend → Vercel**: root directory `frontend`, env var `NEXT_PUBLIC_API_URL` = the Render URL.
- Set spending limits in the Anthropic and OpenRouter consoles. The app itself caps each episode
  at `EPISODE_COST_CAP_USD` (default $0.25) and allows at most `MAX_REVISIONS` (default 2).
