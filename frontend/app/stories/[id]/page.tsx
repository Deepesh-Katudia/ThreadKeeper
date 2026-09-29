"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ChevronIcon } from "@/components/icons";
import { AutoTextarea, Button, Card, ErrorBox, PaneBody, Section, Spinner, StatusBadge, StoryNav, TextInput } from "@/components/ui";
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

  if (!overview) {
    return <PaneBody>{error ? <ErrorBox message={error} /> : <Spinner label="Loading…" />}</PaneBody>;
  }

  const { story, acts, episodes, characters } = overview;
  const canEdit = status === "arc_review" || status === "writing";
  const unsavedCount = Object.keys(editedBeats).length + Object.keys(editedCharacters).length;

  async function run(action: () => Promise<unknown>) {
    setIsSaving(true);
    setError(null);
    try {
      await action();
      reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setIsSaving(false);
    }
  }

  const saveChanges = () =>
    run(async () => {
      const beats = Object.entries(editedBeats).map(([number, beat]) => ({ number: Number(number), beat }));
      const people = Object.entries(editedCharacters).map(([id, changes]) => ({
        ...characters.find((c) => c.id === Number(id))!,
        ...changes,
      }));
      await api.editArc(storyId, beats, people);
      setEditedBeats({});
      setEditedCharacters({});
    });

  return (
    <>
      <StoryNav storyId={storyId} title={story.title} />
      <PaneBody>
        <div className="mx-auto max-w-4xl">
          <div className="mb-6 flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h2 className="text-2xl font-semibold tracking-tight break-words">{story.title || "Planning your serial…"}</h2>
              <p className="mt-2 text-sm leading-relaxed break-words text-muted">{story.logline || story.premise}</p>
            </div>
            <StatusBadge status={story.status} />
          </div>

          <ErrorBox message={error} />

          {isPlanning && <Spinner label="Planning the story bible and every episode beat. This takes a few minutes." />}

          {status === "planning_failed" && (
            <div className="space-y-3">
              <ErrorBox message={`Planning failed: ${overview.latest_job?.detail ?? "unknown error"}`} />
              <Button variant="primary" onClick={() => run(() => api.replanFromScratch(storyId))} disabled={isSaving}>Try again</Button>
            </div>
          )}

          {canEdit && (
            <>
              <div className="sticky top-0 z-10 -mx-1 mb-6 flex flex-wrap items-center gap-2 border-b border-line bg-bg/90 px-1 py-3 backdrop-blur">
                <Button onClick={saveChanges} disabled={isSaving || unsavedCount === 0}>
                  Save {unsavedCount || ""} change{unsavedCount === 1 ? "" : "s"}
                </Button>
                {status === "arc_review" ? (
                  <>
                    <Button variant="primary" onClick={() => run(() => api.approveArc(storyId))} disabled={isSaving || unsavedCount > 0}>
                      Approve arc &amp; start writing
                    </Button>
                    <Button variant="ghost" onClick={() => run(() => api.replanFromScratch(storyId))} disabled={isSaving}>
                      Throw away &amp; re-plan
                    </Button>
                  </>
                ) : (
                  <Link href={`/stories/${storyId}/episodes`} className="text-xs text-muted hover:text-fg">Go to episodes →</Link>
                )}
              </div>

              <Section title="Setting & style">
                <div className="grid gap-3 md:grid-cols-2">
                  <Card className="p-4"><p className="text-sm leading-relaxed break-words whitespace-pre-wrap">{story.setting}</p></Card>
                  <Card className="p-4"><p className="text-sm leading-relaxed break-words whitespace-pre-wrap">{story.style_guide}</p></Card>
                </div>
              </Section>

              <Section title={`Characters · ${characters.length}`}>
                <div className="grid gap-3 md:grid-cols-2">
                  {characters.map((person) => {
                    const edits = editedCharacters[person.id] ?? {};
                    const update = (field: keyof Character, value: string) =>
                      setEditedCharacters({ ...editedCharacters, [person.id]: { ...edits, [field]: value } });
                    return (
                      <Card key={person.id} className="space-y-2 p-3">
                        <div className="flex items-center gap-2">
                          <TextInput value={edits.name ?? person.name} onChange={(e) => update("name", e.target.value)} className="font-medium" />
                          <span className="text-[11px] whitespace-nowrap text-faint">{person.role}</span>
                        </div>
                        <AutoTextarea value={edits.description ?? person.description} onChange={(e) => update("description", e.target.value)} />
                        <AutoTextarea value={edits.planned_arc ?? person.planned_arc} onChange={(e) => update("planned_arc", e.target.value)} className="text-muted" />
                      </Card>
                    );
                  })}
                </div>
              </Section>

              <Section title={`Acts & beats · ${episodes.length} episodes`}>
                <div className="space-y-2">
                  {acts.map((act) => {
                    const isOpen = openAct === act.number;
                    return (
                      <Card key={act.number} className="overflow-hidden">
                        <button onClick={() => setOpenAct(isOpen ? null : act.number)} className="flex w-full items-start gap-3 p-4 text-left hover:bg-subtle/50">
                          <ChevronIcon className={`mt-0.5 h-4 w-4 shrink-0 text-muted transition ${isOpen ? "rotate-90" : ""}`} />
                          <span className="min-w-0">
                            <span className="block text-sm font-semibold break-words">
                              Act {act.number} · {act.title}{" "}
                              <span className="font-normal text-faint">ep {act.first_episode}–{act.last_episode}</span>
                            </span>
                            <span className="mt-1 block text-sm break-words text-muted">{act.goal}</span>
                            <span className="mt-1 block text-xs break-words text-faint">Turning point: {act.turning_point}</span>
                          </span>
                        </button>
                        {isOpen && (
                          <ol className="divide-y divide-line border-t border-line">
                            {episodes.filter((e) => e.act_number === act.number).map((episode) => (
                              <li key={episode.number} className="flex items-start gap-3 px-4 py-2">
                                <span className="w-8 shrink-0 pt-2 text-right text-xs text-faint">{episode.number}</span>
                                <AutoTextarea
                                  value={editedBeats[episode.number] ?? episode.beat}
                                  onChange={(e) => setEditedBeats({ ...editedBeats, [episode.number]: e.target.value })}
                                  disabled={episode.status === "approved"}
                                  className="disabled:opacity-60"
                                />
                                <span className="shrink-0 pt-2"><StatusBadge status={episode.status} /></span>
                              </li>
                            ))}
                          </ol>
                        )}
                      </Card>
                    );
                  })}
                </div>
              </Section>
            </>
          )}
        </div>
      </PaneBody>
    </>
  );
}
