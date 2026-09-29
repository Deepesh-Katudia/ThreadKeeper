"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button, ErrorBox, Section, Spinner, StatusBadge, StoryNav } from "@/components/ui";
import { api, Character } from "@/lib/api";
import { useStory } from "@/lib/useStory";

const PLANNING_POLL_MS = 4000;

export default function ArcPlanPage() {
  const { storyId, overview, error, setError, reload } = useStory();
  const [editedBeats, setEditedBeats] = useState<Record<number, string>>({});
  const [editedCharacters, setEditedCharacters] = useState<Record<number, Partial<Character>>>({});
  const [openAct, setOpenAct] = useState<number | null>(1);
  const [isSaving, setIsSaving] = useState(false);

  const status = overview?.story.status;
  const isPlanning = status === "planning";

  // While the arc is being planned there's nothing to edit yet; just keep checking.
  useEffect(() => {
    if (!isPlanning) return;
    const timer = setInterval(reload, PLANNING_POLL_MS);
    return () => clearInterval(timer);
  }, [isPlanning, reload]);

  if (!overview) return error ? <ErrorBox message={error} /> : <Spinner label="Loading..." />;

  const { story, acts, episodes, characters } = overview;
  const canEdit = status === "arc_review" || status === "writing";
  const unsavedCount = Object.keys(editedBeats).length + Object.keys(editedCharacters).length;

  async function run(action: () => Promise<unknown>) {
    setIsSaving(true);
    setError(null);
    try {
      await action();
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setIsSaving(false);
    }
  }

  const saveChanges = () =>
    run(async () => {
      const beats = Object.entries(editedBeats).map(([number, beat]) => ({ number: Number(number), beat }));
      const people = Object.entries(editedCharacters).map(([id, changes]) => {
        const original = characters.find((c) => c.id === Number(id))!;
        return { ...original, ...changes };
      });
      await api.editArc(storyId, beats, people);
      setEditedBeats({});
      setEditedCharacters({});
    });

  const approveArc = () => run(() => api.approveArc(storyId));
  const planAgain = () => run(() => api.replanFromScratch(storyId));

  return (
    <div>
      <StoryNav storyId={storyId} title={story.title} />
      <ErrorBox message={error} />

      <div className="mb-6 flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-bold">{story.title || "Planning your serial..."}</h1>
          <p className="mt-1 text-zinc-600">{story.logline || story.premise}</p>
        </div>
        <StatusBadge status={story.status} />
      </div>

      {isPlanning && <Spinner label="Planning the story bible and all episode beats. This takes a few minutes." />}

      {status === "planning_failed" && (
        <div className="space-y-3">
          <ErrorBox message={`Planning failed: ${overview.latest_job?.detail ?? "unknown error"}`} />
          <Button onClick={planAgain} disabled={isSaving}>Try planning again</Button>
        </div>
      )}

      {canEdit && (
        <>
          <div className="sticky top-0 z-10 mb-6 flex items-center gap-3 border-b border-zinc-200 bg-zinc-50 py-3">
            <Button onClick={saveChanges} disabled={isSaving || unsavedCount === 0}>
              Save {unsavedCount || ""} change{unsavedCount === 1 ? "" : "s"}
            </Button>
            {status === "arc_review" ? (
              <>
                <Button onClick={approveArc} disabled={isSaving || unsavedCount > 0}>Approve arc &amp; start writing</Button>
                <Button variant="secondary" onClick={planAgain} disabled={isSaving}>Throw away &amp; re-plan</Button>
              </>
            ) : (
              <Link href={`/stories/${storyId}/episodes`} className="text-sm underline">Go to episodes →</Link>
            )}
          </div>

          <Section title="Setting & style">
            <div className="grid gap-4 md:grid-cols-2">
              <p className="whitespace-pre-wrap rounded border border-zinc-200 bg-white p-3 text-sm">{story.setting}</p>
              <p className="whitespace-pre-wrap rounded border border-zinc-200 bg-white p-3 text-sm">{story.style_guide}</p>
            </div>
          </Section>

          <Section title={`Characters (${characters.length})`}>
            <div className="grid gap-3 md:grid-cols-2">
              {characters.map((person) => {
                const edits = editedCharacters[person.id] ?? {};
                const update = (field: keyof Character, value: string) =>
                  setEditedCharacters({ ...editedCharacters, [person.id]: { ...edits, [field]: value } });
                return (
                  <div key={person.id} className="space-y-2 rounded border border-zinc-200 bg-white p-3">
                    <div className="flex items-center gap-2">
                      <input
                        value={edits.name ?? person.name}
                        onChange={(e) => update("name", e.target.value)}
                        className="flex-1 rounded border border-transparent px-1 font-medium hover:border-zinc-200"
                        disabled={!canEdit}
                      />
                      <span className="text-xs text-zinc-500">{person.role}</span>
                      <StatusBadge status={person.status} />
                    </div>
                    <textarea
                      value={edits.description ?? person.description}
                      onChange={(e) => update("description", e.target.value)}
                      rows={2}
                      className="w-full rounded border border-zinc-200 p-1 text-sm"
                    />
                    <textarea
                      value={edits.planned_arc ?? person.planned_arc}
                      onChange={(e) => update("planned_arc", e.target.value)}
                      rows={2}
                      className="w-full rounded border border-zinc-200 p-1 text-sm text-zinc-600"
                    />
                  </div>
                );
              })}
            </div>
          </Section>

          <Section title={`Acts and episode beats (${episodes.length})`}>
            <div className="space-y-3">
              {acts.map((act) => (
                <div key={act.number} className="rounded border border-zinc-200 bg-white">
                  <button
                    onClick={() => setOpenAct(openAct === act.number ? null : act.number)}
                    className="w-full p-3 text-left"
                  >
                    <p className="font-semibold">
                      Act {act.number}: {act.title}{" "}
                      <span className="font-normal text-zinc-500">(episodes {act.first_episode}-{act.last_episode})</span>
                    </p>
                    <p className="text-sm text-zinc-600">{act.goal}</p>
                    <p className="text-sm text-zinc-500">Turning point: {act.turning_point}</p>
                  </button>
                  {openAct === act.number && (
                    <ol className="divide-y divide-zinc-100 border-t border-zinc-100">
                      {episodes
                        .filter((e) => e.act_number === act.number)
                        .map((episode) => {
                          const isWritten = episode.status === "approved";
                          return (
                            <li key={episode.number} className="flex gap-3 p-2">
                              <span className="w-10 pt-1 text-right text-sm text-zinc-400">{episode.number}</span>
                              <textarea
                                value={editedBeats[episode.number] ?? episode.beat}
                                onChange={(e) => setEditedBeats({ ...editedBeats, [episode.number]: e.target.value })}
                                disabled={isWritten}
                                rows={2}
                                className="flex-1 rounded border border-zinc-200 p-1 text-sm disabled:bg-zinc-50 disabled:text-zinc-500"
                              />
                              <div className="w-24 pt-1"><StatusBadge status={episode.status} /></div>
                            </li>
                          );
                        })}
                    </ol>
                  )}
                </div>
              ))}
            </div>
          </Section>
        </>
      )}
    </div>
  );
}
