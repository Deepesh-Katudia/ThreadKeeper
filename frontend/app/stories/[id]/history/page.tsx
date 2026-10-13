"use client";

import { useCallback } from "react";

import { Card, ErrorBox, PaneBody, Section, Spinner, StatusBadge, StoryNav } from "@/components/ui";
import { api, Ripple, RippleChange } from "@/lib/api";
import { useLoader } from "@/lib/useLoader";
import { useStory } from "@/lib/useStory";

/** Every edit to approved history, what it changed, and what the human decided about the episodes after it. */
export default function HistoryPage() {
  const { storyId, overview } = useStory();
  const fetchRipples = useCallback(() => api.ripples(storyId), [storyId]);
  const { data: ripples, error } = useLoader(fetchRipples);

  const header = <StoryNav storyId={storyId} title={overview?.story.title ?? ""} />;
  if (!ripples) {
    return <>{header}<PaneBody>{error ? <ErrorBox message={error} /> : <Spinner label="Loading history…" />}</PaneBody></>;
  }

  return (
    <>
      {header}
      <PaneBody>
        <div className="mx-auto max-w-5xl">
          <Section title={`Edits to approved episodes · ${ripples.length}`}>
            {ripples.length === 0 ? (
              <p className="text-sm text-faint">No approved episode has been edited yet. Editing one starts a ripple review, recorded here.</p>
            ) : (
              <div className="space-y-2">{ripples.map((r) => <RippleRow key={r.id} ripple={r} />)}</div>
            )}
          </Section>
        </div>
      </PaneBody>
    </>
  );
}

function RippleRow({ ripple }: { ripple: Ripple }) {
  const when = ripple.created_at ? new Date(ripple.created_at).toLocaleString() : "";
  return (
    <Card>
      <details className="group">
        <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 px-4 py-3 text-sm">
          <span className="inline-block text-faint transition group-open:rotate-90">›</span>
          <span className="w-40 text-xs text-faint">{when}</span>
          <b>Episode {ripple.source_episode}</b>
          <span className="text-xs text-muted">v{ripple.from_version} → v{ripple.to_version}{ripple.is_restore ? " (restore)" : ""}</span>
          <StatusBadge status={ripple.status} />
          <span className="ml-auto text-xs text-faint">${ripple.cost_usd.toFixed(4)}</span>
        </summary>
        <div className="space-y-4 border-t border-line px-4 py-3 text-sm">
          {ripple.summary && <p className="break-words text-muted">{ripple.summary}</p>}
          {ripple.change && <ChangeList change={ripple.change} />}
          <ItemList ripple={ripple} />
          <BeatList ripple={ripple} />
        </div>
      </details>
    </Card>
  );
}

function ChangeList({ change }: { change: RippleChange }) {
  const lines = [
    ...change.retracted.map((f) => ({ tone: "text-red-300 line-through", text: `${f.subject}: ${f.statement}` })),
    ...change.added.map((f) => ({ tone: "text-emerald-300", text: `${f.subject}: ${f.statement}` })),
    ...change.removed_characters.map((c) => ({ tone: "text-red-300", text: `${c.name} removed from the episode` })),
    ...change.new_characters.map((name) => ({ tone: "text-emerald-300", text: `${name} now appears` })),
    ...change.status_changes.map((s) => ({ tone: "text-amber-300", text: `${s.name} → ${s.status}` })),
    ...change.threads.map((t) => ({ tone: "text-amber-300", text: `Thread "${t.title}" ${t.change}` })),
  ];
  return (
    <div>
      <p className="mb-1 text-[11px] tracking-wide text-faint uppercase">Memory diff</p>
      {lines.length === 0 ? <p className="text-faint">Only the wording changed.</p> : (
        <ul className="space-y-0.5">{lines.map((l, i) => <li key={i} className={`break-words ${l.tone}`}>{l.text}</li>)}</ul>
      )}
    </div>
  );
}

const OUTCOMES: Record<string, string> = { accept: "fix accepted", edit: "edited by hand", keep: "kept as is", rewrite: "rewrite requested" };

function ItemList({ ripple }: { ripple: Ripple }) {
  if (ripple.items.length === 0) return null;
  return (
    <div>
      <p className="mb-1 text-[11px] tracking-wide text-faint uppercase">Later episodes</p>
      <ul className="divide-y divide-line rounded-lg border border-line">
        {ripple.items.map((item) => (
          <li key={item.episode_number} className="grid gap-1 px-3 py-2 md:grid-cols-[4rem_8rem_1fr] md:gap-3">
            <span className="text-xs text-faint">ep {item.episode_number}</span>
            <span className="text-xs">{item.check_status}</span>
            <span className="break-words text-muted">
              {item.decision ? OUTCOMES[item.decision] : item.check_status === "unaffected" ? "no change needed" : "undecided"}
              {item.resulting_version ? ` · v${item.resulting_version}` : ""}
              {item.conflicts[0] ? ` · “${item.conflicts[0].quote}”: ${item.conflicts[0].reason}` : ""}
              {item.decision_note ? ` · ${item.decision_note}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function BeatList({ ripple }: { ripple: Ripple }) {
  const replan = ripple.replan;
  if (!replan) return null;
  const applied = replan.changes.filter((c) => replan.applied.includes(c.episode));
  return (
    <div>
      <p className="mb-1 text-[11px] tracking-wide text-faint uppercase">Beat changes applied · {applied.length} of {replan.changes.length} proposed</p>
      <ul className="divide-y divide-line rounded-lg border border-line">
        {applied.map((change) => (
          <li key={change.episode} className="grid gap-1 px-3 py-2 md:grid-cols-[3rem_1fr_1fr] md:gap-3">
            <span className="text-xs text-faint">ep {change.episode}</span>
            <span className="break-words text-faint line-through decoration-faint/50">{change.before}</span>
            <span className="break-words">{change.after}</span>
          </li>
        ))}
        {applied.length === 0 && <li className="px-3 py-2 text-faint">None.</li>}
      </ul>
    </div>
  );
}
