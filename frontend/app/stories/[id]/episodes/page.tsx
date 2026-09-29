"use client";

import { useCallback, useState } from "react";

import { EpisodeReview } from "@/components/EpisodeReview";
import { FeedbackBox } from "@/components/FeedbackBox";
import { Button, ErrorBox, Spinner, StatusBadge, StoryNav } from "@/components/ui";
import { api, EpisodeBrief, Job } from "@/lib/api";
import { useJob } from "@/lib/useJob";
import { useStory } from "@/lib/useStory";

const PLANNED_EPISODES_SHOWN = 5;

export default function EpisodesPage() {
  const { storyId, overview, error, setError, reload } = useStory();
  const [selected, setSelected] = useState<number | null>(null);
  const [batchSize, setBatchSize] = useState(1);
  const [autoApprove, setAutoApprove] = useState(false);
  const [jobMessage, setJobMessage] = useState<string | null>(null);

  const { watch, isRunning } = useJob(
    useCallback(
      (finished: Job) => {
        setJobMessage(finished.status === "failed" ? `Failed: ${finished.detail}` : finished.detail || null);
        reload();
      },
      [reload],
    ),
    overview?.running_job ?? null, // picks up a job that was already running, e.g. after a refresh
  );

  if (!overview) return error ? <ErrorBox message={error} /> : <Spinner label="Loading..." />;

  const { story, episodes } = overview;
  const visible = visibleEpisodes(episodes);
  const shown = selected ?? episodeNeedingAttention(episodes);

  async function writeNext() {
    setError(null);
    setJobMessage(null);
    try {
      const { episode, job } = await api.writeNext(storyId, batchSize, autoApprove);
      setSelected(episode);
      watch(job);
      reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const onChanged = async (job?: Job | null) => {
    if (job) watch(job);
    await reload();
  };

  if (story.status === "planning" || story.status === "arc_review" || story.status === "planning_failed") {
    return (
      <div>
        <StoryNav storyId={storyId} title={story.title} />
        <p className="text-zinc-600">Approve the arc plan before writing starts.</p>
      </div>
    );
  }

  return (
    <div>
      <StoryNav storyId={storyId} title={story.title} />
      <ErrorBox message={error} />

      <div className="mb-4 flex flex-wrap items-center gap-3 rounded border border-zinc-200 bg-white p-3">
        <Button onClick={writeNext} disabled={isRunning || overview.next_episode === null}>
          Write episode {overview.next_episode ?? "-"}
          {batchSize > 1 ? ` (+${batchSize - 1} more)` : ""}
        </Button>
        <label className="flex items-center gap-1 text-sm">
          Batch
          <select value={batchSize} onChange={(e) => setBatchSize(Number(e.target.value))} className="rounded border border-zinc-300 px-1 py-0.5">
            {[1, 3, 5, 10, 15].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={autoApprove} onChange={(e) => setAutoApprove(e.target.checked)} />
          Auto-approve episodes the critic passes (stops at the first one it flags)
        </label>
        {isRunning && <Spinner label="Working... (drafting, critic review, memory extraction)" />}
        {!isRunning && jobMessage && <span className="text-sm text-zinc-600">{jobMessage}</span>}
      </div>

      <div className="grid gap-6 md:grid-cols-[260px_1fr]">
        <aside className="max-h-[75vh] overflow-y-auto rounded border border-zinc-200 bg-white">
          {visible.map((episode) => (
            <button
              key={episode.number}
              onClick={() => setSelected(episode.number)}
              className={`flex w-full items-start gap-2 border-b border-zinc-100 p-2 text-left text-sm hover:bg-zinc-50 ${
                shown === episode.number ? "bg-zinc-100" : ""
              }`}
            >
              <span className="w-7 text-right text-zinc-400">{episode.number}</span>
              <span className="flex-1">
                <span className="block truncate">{episode.title || episode.beat}</span>
                <span className="mt-0.5 flex gap-1">
                  <StatusBadge status={episode.status} />
                  {episode.was_edited_by_human && <span className="text-xs text-violet-700">edited</span>}
                  {episode.passed_critic === false && episode.status !== "approved" && (
                    <span className="text-xs text-red-600">critic flagged</span>
                  )}
                </span>
              </span>
            </button>
          ))}
        </aside>

        <div className="space-y-6">
          {shown !== null ? (
            <EpisodeReview
              key={`${shown}-${episodes.find((e) => e.number === shown)?.status}`}
              storyId={storyId}
              number={shown}
              isBusy={isRunning}
              onChanged={onChanged}
            />
          ) : (
            <p className="text-zinc-500">Write the first episode to get started.</p>
          )}
          <FeedbackBox storyId={storyId} isBusy={isRunning} onSubmitted={onChanged} />
        </div>
      </div>
    </div>
  );
}

/** The episode a reviewer most likely wants: one waiting on them, else the latest approved. */
function episodeNeedingAttention(episodes: EpisodeBrief[]): number | null {
  const waiting = episodes.find((e) => ["in_review", "failed", "stale", "drafting"].includes(e.status));
  const lastApproved = [...episodes].reverse().find((e) => e.status === "approved");
  return waiting?.number ?? lastApproved?.number ?? null;
}

/** Everything written so far, plus the next few planned beats. */
function visibleEpisodes(episodes: EpisodeBrief[]): EpisodeBrief[] {
  const firstPlanned = episodes.findIndex((e) => e.status === "planned");
  if (firstPlanned === -1) return episodes;
  return episodes.filter((e, index) => e.status !== "planned" || index < firstPlanned + PLANNED_EPISODES_SHOWN);
}
