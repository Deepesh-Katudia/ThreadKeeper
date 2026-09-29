"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ReturnIcon } from "@/components/icons";
import { AutoTextarea, Card, ErrorBox, PaneBody, PaneHeader, Segmented, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { useLoader } from "@/lib/useLoader";

const EXAMPLE_PREMISE =
  "A delivery rider realizes every address on today's route belongs to someone who died in the same building.";

const ABOUT_TABS = {
  about: "Threadkeeper plans and writes a 200-episode serial from a one-line premise. You approve the arc, review every episode, and steer the story with feedback that carries forward.",
  memory: "Each episode is written from a fixed-size memory: the arc plan, a rolling recap, the last eight summaries, the characters and facts in play, open threads, and your standing instructions. Episode 150 costs the same to write as episode 5.",
  controls: "Approve an episode to make it canon. Edit it (even after approval) and its memory is rebuilt. Reject it with a note to get a rewrite. Or give story-wide feedback, which re-plans the next 20 beats.",
};

export default function HomePage() {
  const router = useRouter();
  const { data: stories } = useLoader(api.listStories);
  const [tab, setTab] = useState<keyof typeof ABOUT_TABS>("about");
  const [premise, setPremise] = useState(EXAMPLE_PREMISE);
  const [totalEpisodes, setTotalEpisodes] = useState(200);
  const [error, setError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  async function createStory() {
    setIsCreating(true);
    setError(null);
    try {
      const { story_id } = await api.createStory(premise, totalEpisodes);
      router.push(`/stories/${story_id}`);
    } catch (e) {
      setError((e as Error).message);
      setIsCreating(false);
    }
  }

  const canSubmit = !isCreating && premise.trim().length >= 10;

  return (
    <>
      <PaneHeader title="Serials" />
      <PaneBody className="flex flex-col">
        <div className="mx-auto w-full max-w-2xl">
          <Card className="p-5">
            <h2 className="mb-3 text-xl font-semibold tracking-tight">Threadkeeper</h2>
            <Segmented
              options={[
                { value: "about", label: "About" },
                { value: "memory", label: "Memory" },
                { value: "controls", label: "Controls" },
              ]}
              active={tab}
              onChange={(value) => setTab(value as keyof typeof ABOUT_TABS)}
            />
            <p className="mt-4 text-sm leading-relaxed text-muted">{ABOUT_TABS[tab]}</p>
          </Card>

          {/* On phones the sidebar is hidden, so list the stories here. */}
          {!!stories?.length && (
            <div className="mt-6 space-y-2 md:hidden">
              {stories.map((story) => (
                <Link key={story.id} href={`/stories/${story.id}`} className="block rounded-lg border border-line p-3 hover:bg-subtle">
                  <span className="flex items-start justify-between gap-2">
                    <span className="text-sm font-medium break-words">{story.title || "Planning…"}</span>
                    <StatusBadge status={story.status} />
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="mt-auto pt-8">
          <Card className="mx-auto w-full max-w-3xl p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-base font-semibold">New serial</h3>
              <label className="flex items-center gap-2 text-xs text-muted">
                Episodes
                <input
                  type="number"
                  min={10}
                  max={200}
                  value={totalEpisodes}
                  onChange={(e) => setTotalEpisodes(Number(e.target.value))}
                  className="w-20 rounded-md border border-line bg-field px-2 py-1 text-xs text-fg"
                />
              </label>
            </div>
            <ErrorBox message={error} />
            <div className="mt-2 flex items-end gap-2 rounded-lg border border-line bg-field p-2">
              <AutoTextarea
                value={premise}
                onChange={(e) => setPremise(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && canSubmit) {
                    e.preventDefault();
                    createStory();
                  }
                }}
                placeholder="One-line premise…"
                rows={2}
                className="border-0 bg-transparent focus:border-0"
              />
              <button
                onClick={createStory}
                disabled={!canSubmit}
                title="Plan the arc (Enter)"
                className="mb-1 rounded-md p-2 text-muted hover:bg-subtle hover:text-fg disabled:opacity-40"
              >
                <ReturnIcon />
              </button>
            </div>
            <p className="mt-2 text-[11px] text-faint">
              {isCreating ? "Starting…" : "Enter plans the arc: a story bible, then every act's episode beats. Takes a few minutes and about $1."}
            </p>
          </Card>
        </div>
      </PaneBody>
    </>
  );
}
