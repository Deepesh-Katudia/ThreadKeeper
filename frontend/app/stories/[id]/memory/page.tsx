"use client";

import { useCallback, useState } from "react";

import { SearchIcon } from "@/components/icons";
import { Cell, Table } from "@/components/Table";
import { Button, Card, ErrorBox, PaneBody, Section, Spinner, StatusBadge, StoryNav } from "@/components/ui";
import { api } from "@/lib/api";
import { useLoader } from "@/lib/useLoader";
import { useStory } from "@/lib/useStory";

export default function MemoryPage() {
  const { storyId, overview } = useStory();
  const fetchMemory = useCallback(() => api.memory(storyId), [storyId]);
  const { data: memory, error, setError, reload } = useLoader(fetchMemory);
  const [factFilter, setFactFilter] = useState("");

  const header = <StoryNav storyId={storyId} title={overview?.story.title ?? ""} />;
  if (!memory) {
    return <>{header}<PaneBody>{error ? <ErrorBox message={error} /> : <Spinner label="Loading memory…" />}</PaneBody></>;
  }

  async function retire(directiveId: number) {
    try {
      await api.retireDirective(storyId, directiveId);
      reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const facts = memory.facts.filter((f) => `${f.subject} ${f.statement}`.toLowerCase().includes(factFilter.toLowerCase()));

  return (
    <>
      {header}
      <PaneBody>
        <div className="mx-auto max-w-5xl">
          <ErrorBox message={error} />

          <Section title="Standing instructions">
            {memory.directives.length === 0 ? (
              <p className="text-sm text-faint">None yet. Give story direction from the Episodes tab.</p>
            ) : (
              <div className="space-y-2">
                {memory.directives.map((d) => (
                  <Card key={d.id} className={`flex items-start justify-between gap-4 p-4 ${d.is_active ? "" : "opacity-50"}`}>
                    <div className="min-w-0">
                      <p className="text-sm font-medium break-words">{d.text}</p>
                      <p className="mt-1 text-[11px] text-faint">
                        Given after ep {d.given_after_episode} · {d.expires_after_episode ? `until ep ${d.expires_after_episode}` : "for the rest of the story"}
                        {d.is_active ? "" : " · retired"}
                      </p>
                      {d.replan_summary && <p className="mt-2 text-sm break-words text-muted">Re-plan: {d.replan_summary}</p>}
                    </div>
                    {d.is_active && <Button variant="ghost" onClick={() => retire(d.id)}>Retire</Button>}
                  </Card>
                ))}
              </div>
            )}
          </Section>

          <Section title={`Story so far · recap through episode ${memory.story_so_far_through}`}>
            <Card className="p-4">
              <p className="text-sm leading-relaxed break-words whitespace-pre-wrap text-muted">{memory.story_so_far || "Written every 10 episodes."}</p>
            </Card>
          </Section>

          <Section title={`Characters · ${memory.characters.length}`}>
            <Table headers={["Name", "Role", "Status", "First / last seen", "Description"]}>
              {memory.characters.map((c) => (
                <tr key={c.id}>
                  <Cell className="font-medium">{c.name}</Cell>
                  <Cell className="text-muted">{c.role}</Cell>
                  <Cell>
                    <StatusBadge status={c.status} />
                    {c.status_changed_in ? <span className="ml-1 text-[11px] text-faint">ep {c.status_changed_in}</span> : null}
                  </Cell>
                  <Cell className="whitespace-nowrap text-faint">{c.first_episode || "plan"} / {c.last_seen_episode || "–"}</Cell>
                  <Cell className="min-w-64 text-muted">{c.description}</Cell>
                </tr>
              ))}
            </Table>
          </Section>

          <Section title={`Threads · ${memory.threads.length}`}>
            <Table headers={["Thread", "Status", "Opens", "Pays off"]}>
              {memory.threads.map((t) => (
                <tr key={t.id}>
                  <Cell className="min-w-64"><p className="font-medium">{t.title}</p><p className="mt-0.5 text-muted">{t.description}</p></Cell>
                  <Cell><StatusBadge status={t.status} /></Cell>
                  <Cell className="text-faint">{t.opened_episode || "–"}</Cell>
                  <Cell className="whitespace-nowrap text-faint">{t.resolved_episode ? `ep ${t.resolved_episode} ✓` : t.payoff_episode ? `planned ep ${t.payoff_episode}` : "–"}</Cell>
                </tr>
              ))}
            </Table>
          </Section>

          <Section
            title={`Canon facts · ${memory.facts.length}`}
            aside={
              <label className="flex items-center gap-2 rounded-md border border-line px-2.5 py-1 text-sm">
                <SearchIcon className="h-3.5 w-3.5 text-faint" />
                <input value={factFilter} onChange={(e) => setFactFilter(e.target.value)} placeholder="Filter" className="w-40 bg-transparent text-sm placeholder:text-faint focus:outline-none" />
              </label>
            }
          >
            <Table headers={["Episode", "Subject", "Fact"]}>
              {facts.map((f) => (
                <tr key={f.id}>
                  <Cell className="text-faint">{f.source_episode}</Cell>
                  <Cell className="font-medium">{f.subject}</Cell>
                  <Cell className="text-muted">{f.statement}</Cell>
                </tr>
              ))}
            </Table>
          </Section>

          {memory.acts.some((a) => a.summary) && (
            <Section title="Act summaries">
              <div className="space-y-2">
                {memory.acts.filter((a) => a.summary).map((a) => (
                  <Card key={a.number} className="p-4 text-sm break-words">
                    <b>Act {a.number} · {a.title}.</b> <span className="text-muted">{a.summary}</span>
                  </Card>
                ))}
              </div>
            </Section>
          )}
        </div>
      </PaneBody>
    </>
  );
}
