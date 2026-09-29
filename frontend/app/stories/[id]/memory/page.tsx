"use client";

import { useCallback, useState } from "react";

import { Button, ErrorBox, Section, Spinner, StatusBadge, StoryNav } from "@/components/ui";
import { api } from "@/lib/api";
import { useLoader } from "@/lib/useLoader";
import { useStory } from "@/lib/useStory";

export default function MemoryPage() {
  const { storyId, overview } = useStory();
  const fetchMemory = useCallback(() => api.memory(storyId), [storyId]);
  const { data: memory, error, setError, reload: load } = useLoader(fetchMemory);
  const [factFilter, setFactFilter] = useState("");

  if (!memory) return error ? <ErrorBox message={error} /> : <Spinner label="Loading memory..." />;

  async function retire(directiveId: number) {
    try {
      await api.retireDirective(storyId, directiveId);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const filteredFacts = memory.facts.filter((f) =>
    `${f.subject} ${f.statement}`.toLowerCase().includes(factFilter.toLowerCase()),
  );

  return (
    <div>
      <StoryNav storyId={storyId} title={overview?.story.title ?? ""} />
      <ErrorBox message={error} />

      <Section title="Standing instructions (human feedback)">
        {memory.directives.length === 0 ? (
          <p className="text-sm text-zinc-500">None yet. Give feedback from the Episodes tab.</p>
        ) : (
          <ul className="space-y-2">
            {memory.directives.map((d) => (
              <li key={d.id} className={`rounded border border-zinc-200 bg-white p-3 ${d.is_active ? "" : "opacity-50"}`}>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-medium">{d.text}</p>
                    <p className="text-xs text-zinc-500">
                      Given after ep {d.given_after_episode} ·{" "}
                      {d.expires_after_episode ? `until ep ${d.expires_after_episode}` : "for the rest of the story"}
                      {d.is_active ? "" : " · retired"}
                    </p>
                    {d.replan_summary && <p className="mt-1 text-sm text-zinc-600">Re-plan: {d.replan_summary}</p>}
                  </div>
                  {d.is_active && <Button variant="secondary" onClick={() => retire(d.id)}>Retire</Button>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title={`Story so far (recap through episode ${memory.story_so_far_through})`}>
        <p className="whitespace-pre-wrap rounded border border-zinc-200 bg-white p-3 text-sm">
          {memory.story_so_far || "Written every 10 episodes."}
        </p>
      </Section>

      <Section title={`Characters (${memory.characters.length})`}>
        <table className="w-full rounded border border-zinc-200 bg-white text-sm">
          <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500">
            <tr><th className="p-2">Name</th><th className="p-2">Role</th><th className="p-2">Status</th><th className="p-2">First / last seen</th><th className="p-2">Description</th></tr>
          </thead>
          <tbody>
            {memory.characters.map((c) => (
              <tr key={c.id} className="border-t border-zinc-100 align-top">
                <td className="p-2 font-medium">{c.name}</td>
                <td className="p-2">{c.role}</td>
                <td className="p-2"><StatusBadge status={c.status} />{c.status_changed_in ? <span className="ml-1 text-xs text-zinc-500">ep {c.status_changed_in}</span> : null}</td>
                <td className="p-2 text-zinc-500">{c.first_episode || "plan"} / {c.last_seen_episode || "-"}</td>
                <td className="p-2 text-zinc-600">{c.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title={`Threads (${memory.threads.length})`}>
        <table className="w-full rounded border border-zinc-200 bg-white text-sm">
          <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500">
            <tr><th className="p-2">Thread</th><th className="p-2">Status</th><th className="p-2">Opens</th><th className="p-2">Pays off</th></tr>
          </thead>
          <tbody>
            {memory.threads.map((t) => (
              <tr key={t.id} className="border-t border-zinc-100 align-top">
                <td className="p-2"><p className="font-medium">{t.title}</p><p className="text-zinc-600">{t.description}</p></td>
                <td className="p-2"><StatusBadge status={t.status} /></td>
                <td className="p-2">{t.opened_episode || "-"}</td>
                <td className="p-2">{t.resolved_episode ? `ep ${t.resolved_episode} ✓` : t.payoff_episode ? `planned ep ${t.payoff_episode}` : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section
        title={`Canon facts (${memory.facts.length})`}
        aside={<input value={factFilter} onChange={(e) => setFactFilter(e.target.value)} placeholder="Filter..." className="rounded border border-zinc-300 px-2 py-1 text-sm" />}
      >
        <ul className="divide-y divide-zinc-100 rounded border border-zinc-200 bg-white text-sm">
          {filteredFacts.map((f) => (
            <li key={f.id} className="flex gap-3 p-2">
              <span className="w-12 text-zinc-400">ep {f.source_episode}</span>
              <span className="w-40 font-medium">{f.subject}</span>
              <span className="flex-1 text-zinc-700">{f.statement}</span>
            </li>
          ))}
        </ul>
      </Section>

      {memory.acts.some((a) => a.summary) && (
        <Section title="Act summaries">
          {memory.acts.filter((a) => a.summary).map((a) => (
            <p key={a.number} className="mb-2 rounded border border-zinc-200 bg-white p-3 text-sm">
              <b>Act {a.number}: {a.title}.</b> {a.summary}
            </p>
          ))}
        </Section>
      )}
    </div>
  );
}
