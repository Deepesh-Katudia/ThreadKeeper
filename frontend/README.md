# Threadkeeper frontend

A plain Next.js UI for the Threadkeeper API: stories, arc editor, episode review, story memory, costs.

```bash
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

- `lib/api.ts`: typed client for every backend endpoint
- `lib/useLoader.ts`, `lib/useStory.ts`, `lib/useJob.ts`: data loading and background-job polling
- `components/EpisodeReview.tsx`: the approve / edit / reject controls
- `components/FeedbackBox.tsx`: story-wide feedback that re-plans upcoming beats
