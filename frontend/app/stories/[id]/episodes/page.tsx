"use client";

import { useCallback, useState } from "react";

import { EpisodeReview } from "@/components/EpisodeReview";
import { FeedbackBox } from "@/components/FeedbackBox";
import { SearchIcon } from "@/components/icons";
import { Button, ErrorBox, PaneBody, Spinner, StatusBadge, StoryNav } from "@/components/ui";
import { api, EpisodeBrief, Job } from "@/lib/api";
import { useJob } from "@/lib/useJob";
import { useStory } from "@/lib/useStory";

const PLANNED_EPISODES_SHOWN = 5;

export default function EpisodesPage() {
  const { storyId, overview, error, setError, reload } = useStory();
  const [selected, setSelected] = useState<number | null>(null);
  const [search, setSearch] = useState("");
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

  if (!overview) {
    return <PaneBody>{error ? <ErrorBox message={error} /> : <Spinner label="Loading…" />}</PaneBody>;
  }

  const { story, episodes } = overview;

  if (["planning", "arc_review", "planning_failed"].includes(story.status)) {
    return (
      <>
        <StoryNav storyId={storyId} title={story.title} />
        <PaneBody><p className="text-sm text-muted">Approve the arc plan before writing starts.</p></PaneBody>
      </>
    );
  }

  const shown = selected ?? episodeNeedingAttention(episodes);
  const visible = filterEpisodes(visibleEpisodes(episodes), search);
  const waitingForReview = episodes.find((e) => e.status === "in_review");
  const canWrite = !isRunning && !waitingForReview && overview.next_episode !== null;

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

  const onChanged = (job?: Job | null) => {
    if (job) watch(job);
    reload();
  };

  return (
    <>
      <StoryNav storyId={storyId} title={story.title} />
      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        {/* Left: the episode list, like a prompt library */}
        <aside className="flex max-h-72 flex-col border-b border-line md:max-h-none md:w-80 md:shrink-0 md:border-r md:border-b-0">
          <div className="border-b border-line p-3">
            <label className="flex items-center gap-2 rounded-md border border-line bg-bg px-2.5 py-1.5 text-sm">
              <SearchIcon className="h-3.5 w-3.5 text-faint" />
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search" className="w-full bg-transparent text-sm placeholder:text-faint focus:outline-none" />
            </label>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {visible.map((episode) => (
              <button
                key={episode.number}
                onClick={() => setSelected(episode.number)}
                className={`flex w-full items-start gap-3 border-b border-line px-3 py-2.5 text-left transition ${
                  shown === episode.number ? "bg-subtle" : "hover:bg-subtle/50"
                }`}
              >
                <span className="w-6 shrink-0 pt-0.5 text-right text-xs text-faint">{episode.number}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm break-words">{episode.title || episode.beat}</span>
                  <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <StatusBadge status={episode.status} />
                    {episode.was_edited_by_human && <span className="text-[11px] text-violet-400">edited</span>}
                    {episode.passed_critic === false && episode.status !== "approved" && (
                      <span className="text-[11px] text-red-400">critic flagged</span>
                    )}
                  </span>
                </span>
              </button>
            ))}
            {visible.length === 0 && <p className="p-3 text-xs text-faint">No episodes match.</p>}
          </div>
        </aside>

        {/* Right: controls, the episode, and the story-wide feedback composer */}
        <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex min-h-[41px] flex-wrap items-center gap-2 border-b border-line px-4 py-1.5">
            <Button
              variant="primary"
              onClick={writeNext}
              disabled={!canWrite}
              title={waitingForReview ? `Approve, edit or reject episode ${waitingForReview.number} first` : undefined}
            >
              Write episode {overview.next_episode ?? "–"}{batchSize > 1 ? ` +${batchSize - 1}` : ""}
            </Button>
            {waitingForReview && !isRunning && (
              <span className="text-xs text-amber-400">Review episode {waitingForReview.number} first</span>
            )}
            <select value={batchSize} onChange={(e) => setBatchSize(Number(e.target.value))} className="rounded-md border border-line bg-bg px-2 py-1 text-xs" title="How many episodes to write">
              {[1, 3, 5, 10, 15].map((n) => <option key={n} value={n}>{n} at a time</option>)}
            </select>
            <label className="flex items-center gap-1.5 text-xs text-muted">
              <input type="checkbox" checked={autoApprove} onChange={(e) => setAutoApprove(e.target.checked)} className="accent-current" />
              Auto-approve what the critic passes
            </label>
            {isRunning && <Spinner label="Drafting, reviewing, extracting memory…" />}
            {!isRunning && jobMessage && <span className="text-xs break-words text-muted">{jobMessage}</span>}
          </div>

          <PaneBody className="space-y-4">
            <ErrorBox message={error} />
            {shown !== null ? (
              <EpisodeReview
                key={`${shown}-${episodes.find((e) => e.number === shown)?.status}`}
                storyId={storyId}
                number={shown}
                isBusy={isRunning}
                onChanged={onChanged}
              />
            ) : (
              <p className="text-sm text-muted">Write the first episode to get started.</p>
            )}
          </PaneBody>

          <div className="border-t border-line p-3">
            <FeedbackBox storyId={storyId} isBusy={isRunning} onSubmitted={onChanged} />
          </div>
        </section>
      </div>
    </>
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

function filterEpisodes(episodes: EpisodeBrief[], search: string): EpisodeBrief[] {
  const wanted = search.trim().toLowerCase();
  if (!wanted) return episodes;
  return episodes.filter((e) => `${e.number} ${e.title} ${e.beat}`.toLowerCase().includes(wanted));
}
