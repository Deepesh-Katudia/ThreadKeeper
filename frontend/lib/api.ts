// Typed helpers for talking to the Threadkeeper backend.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ACCESS_KEY_STORAGE = "threadkeeper-access-key";

export type StoryStatus = "planning" | "planning_failed" | "arc_review" | "writing" | "finished";
export type EpisodeStatus = "planned" | "drafting" | "in_review" | "approved" | "failed" | "stale";

export interface Story {
  id: number;
  premise: string;
  title: string;
  logline: string;
  setting: string;
  style_guide: string;
  status: StoryStatus;
  total_episodes: number;
  story_so_far: string;
  story_so_far_through: number;
  approved_episodes?: number;
}

export interface Act {
  number: number;
  title: string;
  goal: string;
  turning_point: string;
  first_episode: number;
  last_episode: number;
  summary: string;
}

export interface Character {
  id: number;
  name: string;
  role: string;
  description: string;
  planned_arc: string;
  status: string;
  status_changed_in: number;
  first_episode: number;
  last_seen_episode: number;
}

export interface EpisodeBrief {
  number: number;
  act_number: number;
  beat: string;
  status: EpisodeStatus;
  title: string;
  passed_critic: boolean | null;
  was_edited_by_human: boolean;
}

export interface Problem {
  kind: string;
  detail: string;
}

export interface CriticReport {
  final?: { problems: Problem[]; hook_score: number; follows_beat: boolean; verdict: string; advice: string };
  attempts?: { stage: string; words?: number; verdict?: string; hook_score?: number; reason?: string; problems?: Problem[] }[];
  passed?: boolean;
  possible_repeats_of?: number[];
  cost_usd?: number;
  context_sent?: Record<string, string>;
}

export interface Episode extends EpisodeBrief {
  text: string;
  word_count: number;
  summary: string;
  hook: string;
  characters_present: string[];
  critic_report: CriticReport;
  pending_memory: Record<string, unknown>;
  revision_count: number;
  human_note: string;
  error: string;
}

export interface Job {
  id: number;
  story_id: number;
  kind: string;
  status: "running" | "done" | "failed";
  detail: string;
}

export interface StoryOverview {
  story: Story;
  acts: Act[];
  characters: Character[];
  episodes: EpisodeBrief[];
  next_episode: number | null;
  running_job: Job | null;
  latest_job: Job | null;
}

export interface Fact {
  id: number;
  subject: string;
  statement: string;
  source_episode: number;
}

export interface Thread {
  id: number;
  title: string;
  description: string;
  opened_episode: number;
  payoff_episode: number;
  status: string;
  resolved_episode: number;
}

export interface Directive {
  id: number;
  text: string;
  given_after_episode: number;
  expires_after_episode: number;
  is_active: boolean;
  replan_summary: string;
}

export interface Memory {
  story_so_far: string;
  story_so_far_through: number;
  acts: Act[];
  characters: Character[];
  facts: Fact[];
  threads: Thread[];
  directives: Directive[];
}

export interface Costs {
  total_cost_usd: number;
  planning_cost_usd: number;
  eval_cost_usd: number;
  cost_cap_per_episode_usd: number;
  per_episode: {
    episode: number;
    cost_usd: number;
    input_tokens: number;
    output_tokens: number;
    latency_ms: number;
    calls: number;
    failed_calls: number;
    revisions: number;
  }[];
  projection: {
    based_on_episodes: number;
    average_cost_per_episode_usd?: number;
    average_seconds_per_episode?: number;
    estimated_total_cost_usd?: number;
    estimated_total_hours?: number;
  };
  recent_calls: {
    id: number;
    episode_number: number;
    step: string;
    model: string;
    input_tokens: number;
    output_tokens: number;
    cache_read_tokens: number;
    cost_usd: number;
    latency_ms: number;
    succeeded: boolean;
    error: string;
  }[];
}

export type EvaluatorKey = "word_count" | "no_repetition" | "hook" | "consistency" | "follows_directives";

export interface EvaluationRun {
  id: number;
  experiment_name: string;
  experiment_url: string;
  episodes_scored: number;
  scores: Partial<Record<EvaluatorKey, number | null>>;
  per_episode: ({ episode: number; comments: Partial<Record<EvaluatorKey, string>> } & Partial<Record<EvaluatorKey, number | null>>)[];
  cost_usd: number;
  created_at: string | null;
}

export interface Evaluations {
  langsmith_enabled: boolean;
  project_url: string | null;
  judge_model: string;
  approved_episodes: number;
  estimated_cost_usd: number;
  evaluations: EvaluationRun[];
  critic_vs_human: {
    agreement: number | null;
    rows: { episode: number; critic_passed: boolean; hook_score: number | null; revisions: number; human: string; agrees: boolean }[];
  };
}

export function getAccessKey(): string {
  try {
    return localStorage.getItem(ACCESS_KEY_STORAGE) ?? "";
  } catch {
    return "";
  }
}

export function setAccessKey(key: string): void {
  try {
    localStorage.setItem(ACCESS_KEY_STORAGE, key);
  } catch {
    // Storage can be blocked (private mode); the key just won't be remembered.
  }
}

const FALLBACK_MESSAGES: Record<number, string> = {
  401: "The access key is missing or wrong. Set it with the key button at the bottom of the sidebar.",
  404: "That doesn't exist (any more). It may have been deleted.",
  409: "That can't be done right now. Refresh the page and try again.",
  422: "Some of the values entered aren't valid. Please check them and try again.",
  500: "Something went wrong on the server. Please try again.",
  502: "The AI model call failed. Please try again in a moment.",
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-Access-Key": getAccessKey(),
        ...(options.headers ?? {}),
      },
    });
  } catch {
    throw new Error("Can't reach the Threadkeeper server. Check that the backend is running and try again.");
  }
  if (!response.ok) {
    throw new Error(await readableError(response));
  }
  return response.json() as Promise<T>;
}

/** The backend sends plain sentences; anything else is turned into one here. */
async function readableError(response: Response): Promise<string> {
  const fallback = FALLBACK_MESSAGES[response.status] ?? `Something went wrong (error ${response.status}). Please try again.`;
  try {
    const body = await response.json();
    if (typeof body.detail === "string" && body.detail.trim()) return body.detail;
    if (Array.isArray(body.detail)) {
      const messages = body.detail.map((item: { msg?: string }) => item.msg).filter(Boolean);
      if (messages.length) return messages.join(". ") + ".";
    }
  } catch {
    // Not JSON: use the fallback.
  }
  return fallback;
}

const post = <T>(path: string, body: unknown = {}) => request<T>(path, { method: "POST", body: JSON.stringify(body) });
const put = <T>(path: string, body: unknown) => request<T>(path, { method: "PUT", body: JSON.stringify(body) });

export const api = {
  listStories: () => request<Story[]>("/stories"),
  createStory: (premise: string, totalEpisodes: number) =>
    post<{ story_id: number; job: Job }>("/stories", { premise, total_episodes: totalEpisodes }),
  replanFromScratch: (storyId: number) => post<{ job: Job }>(`/stories/${storyId}/plan`),
  overview: (storyId: number) => request<StoryOverview>(`/stories/${storyId}`),
  editArc: (
    storyId: number,
    beats: { number: number; beat: string }[],
    characters: Partial<Character>[] = [],
  ) => put<{ ok: boolean }>(`/stories/${storyId}/arc`, { beats, characters }),
  approveArc: (storyId: number) => post<{ ok: boolean }>(`/stories/${storyId}/arc/approve`),

  writeNext: (storyId: number, count: number, autoApprove: boolean) =>
    post<{ episode: number; job: Job }>(`/stories/${storyId}/episodes/next`, { count, auto_approve: autoApprove }),
  episode: (storyId: number, number: number) => request<Episode>(`/stories/${storyId}/episodes/${number}`),
  approveEpisode: (storyId: number, number: number) => post<{ ok: boolean }>(`/stories/${storyId}/episodes/${number}/approve`),
  editEpisode: (storyId: number, number: number, text: string, title?: string) =>
    put<Episode>(`/stories/${storyId}/episodes/${number}`, { text, title }),
  rejectEpisode: (storyId: number, number: number, reason: string, rewriteNow = true) =>
    post<{ job: Job | null }>(`/stories/${storyId}/episodes/${number}/reject`, { reason, rewrite_now: rewriteNow }),

  giveFeedback: (storyId: number, text: string, expiresAfterEpisode = 0) =>
    post<{ job: Job }>(`/stories/${storyId}/feedback`, { text, expires_after_episode: expiresAfterEpisode }),
  retireDirective: (storyId: number, directiveId: number) =>
    request<{ ok: boolean }>(`/stories/${storyId}/directives/${directiveId}`, { method: "DELETE" }),

  memory: (storyId: number) => request<Memory>(`/stories/${storyId}/memory`),
  costs: (storyId: number) => request<Costs>(`/stories/${storyId}/costs`),
  job: (jobId: number) => request<Job>(`/jobs/${jobId}`),

  evaluations: (storyId: number) => request<Evaluations>(`/stories/${storyId}/evaluations`),
  runEvaluation: (storyId: number) => post<{ job: Job }>(`/stories/${storyId}/evaluations`),
};
