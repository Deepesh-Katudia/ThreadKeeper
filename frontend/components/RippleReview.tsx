"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { PatchEdits, QuoteInContext, TextDiff } from "@/components/TextDiff";
import { AutoTextarea, Button, Card, ErrorBox, Section, Spinner, StatusBadge } from "@/components/ui";
import { api, Job, MemoryDiff, Ripple, RippleChange, RippleDecisionKind, RippleItem } from "@/lib/api";
import { useLoader } from "@/lib/useLoader";

type Run = (action: () => Promise<Job | null | void>) => Promise<void>;

/** The three human gates of a ripple: confirm memory, decide later episodes, approve new beats. */
export function RippleReview({ storyId, rippleId, isBusy, onChanged }: {
  storyId: number;
  rippleId: number;
  isBusy: boolean;
  onChanged: (job?: Job | null) => void;
}) {
  const fetchRipple = useCallback(() => api.ripple(storyId, rippleId), [storyId, rippleId]);
  const { data: ripple, error, setError } = useLoader(fetchRipple);
  const [isSaving, setIsSaving] = useState(false);

  if (!ripple) return error ? <ErrorBox message={error} /> : <Spinner label="Loading the ripple…" />;

  const run: Run = async (action) => {
    setIsSaving(true);
    setError(null);
    try {
      onChanged((await action()) ?? null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setIsSaving(false);
    }
  };
  const locked = isBusy || isSaving;

  return (
    <article className="mx-auto max-w-4xl space-y-4">
      <header>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-faint">Ripple review</span>
          <StatusBadge status={ripple.status} />
          <span className="text-[11px] text-faint">${ripple.cost_usd.toFixed(4)} so far</span>
        </div>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight">
          Episode {ripple.source_episode} {ripple.is_restore ? "restored" : "changed"} · v{ripple.from_version} → v{ripple.to_version}
        </h2>
      </header>
      <ErrorBox message={error} />
      {ripple.status === "confirm_memory" && <MemoryGate storyId={storyId} ripple={ripple} locked={locked} run={run} />}
      {ripple.status === "scanning" && (
        <Spinner label="Checking later episodes. Those with no sign of the change are cleared without a model call…" />
      )}
      {ripple.status === "reviewing" && <EpisodesGate storyId={storyId} ripple={ripple} locked={locked} run={run} />}
      {ripple.status === "replan_review" && <ReplanGate storyId={storyId} ripple={ripple} locked={locked} run={run} />}
      {(ripple.status === "closed" || ripple.status === "cancelled") && (
        <Card className="p-4 text-sm text-muted">{ripple.summary || "This ripple is finished."}</Card>
      )}
    </article>
  );
}

// --- Gate 1 ---------------------------------------------------------------------------

interface DiffRow {
  key: string;
  kind: string;
  text: string;
  tone: "removed" | "added" | "changed";
  drop: (diff: MemoryDiff) => MemoryDiff;
}

function MemoryGate({ storyId, ripple, locked, run }: { storyId: number; ripple: Ripple; locked: boolean; run: Run }) {
  const [dropped, setDropped] = useState<string[]>([]);
  const diff = ripple.diff!;
  const rows = diffRows(diff, ripple.change!);
  const toggle = (key: string) => setDropped((d) => (d.includes(key) ? d.filter((k) => k !== key) : [...d, key]));

  const confirm = () => run(async () => {
    const edited = dropped.length ? rows.filter((r) => dropped.includes(r.key)).reduce((d, r) => r.drop(d), diff) : null;
    return (await api.confirmMemory(storyId, ripple.id, edited)).job;
  });
  const cancel = () => run(async () => void (await api.cancelRipple(storyId, ripple.id)));

  return (
    <Section title="Step 1 of 3 · what changes in story memory">
      <p className="mb-3 text-sm text-muted">
        Nothing has changed yet. {ripple.is_restore ? "This restores an earlier version exactly, without a model call." : "Remove anything the extractor got wrong, then confirm."}
      </p>
      <Card className="divide-y divide-line">
        <p className="p-3 text-sm break-words"><span className="text-faint">New summary · </span>{diff.summary}</p>
        {rows.length === 0 && <p className="p-3 text-sm text-faint">No facts, characters or threads change; only the wording.</p>}
        {rows.map((row) => {
          const isDropped = dropped.includes(row.key);
          return (
            <div key={row.key} className={`flex items-start gap-3 p-3 text-sm ${isDropped ? "opacity-40" : ""}`}>
              <span className="w-32 shrink-0 text-[11px] tracking-wide text-faint uppercase">{row.kind}</span>
              <span className={`min-w-0 flex-1 break-words ${ROW_TONES[row.tone]}`}>{row.text}</span>
              <Button variant="ghost" onClick={() => toggle(row.key)} disabled={locked}>{isDropped ? "Keep" : "Remove"}</Button>
            </div>
          );
        })}
      </Card>
      <div className="mt-3 flex gap-2">
        <Button variant="primary" onClick={confirm} disabled={locked}>Confirm and check later episodes</Button>
        <Button variant="ghost" onClick={cancel} disabled={locked}>Cancel the edit</Button>
      </div>
    </Section>
  );
}

const ROW_TONES = { removed: "text-red-300 line-through decoration-red-400/60", added: "text-emerald-300", changed: "text-amber-300" };

function diffRows(diff: MemoryDiff, change: RippleChange): DiffRow[] {
  const rows: DiffRow[] = [];
  change.retracted.forEach((f) => rows.push({
    key: `retract-${f.id}`, kind: "Fact retracted", text: `${f.subject}: ${f.statement}`, tone: "removed",
    drop: (d) => ({ ...d, retract_fact_ids: d.retract_fact_ids.filter((id) => id !== f.id) }),
  }));
  diff.new_facts.forEach((f, i) => rows.push({
    key: `fact-${i}`, kind: "Fact added", text: `${f.subject}: ${f.statement}`, tone: "added",
    drop: (d) => ({ ...d, new_facts: d.new_facts.filter((x) => x !== f) }),
  }));
  change.removed_characters.forEach((c) => rows.push({
    key: `uncast-${c.id}`, kind: "Character removed", text: c.name, tone: "removed",
    drop: (d) => ({ ...d, remove_character_ids: d.remove_character_ids.filter((id) => id !== c.id) }),
  }));
  diff.new_characters.forEach((c) => rows.push({
    key: `cast-${c.name}`, kind: "New character", text: `${c.name} (${c.role})`, tone: "added",
    drop: (d) => ({ ...d, new_characters: d.new_characters.filter((x) => x !== c) }),
  }));
  diff.character_changes.forEach((c, i) => rows.push({
    key: `status-${i}`, kind: "Status", text: `${c.name} → ${c.new_status}`, tone: "changed",
    drop: (d) => ({ ...d, character_changes: d.character_changes.filter((x) => x !== c) }),
  }));
  change.threads.forEach((t, i) => rows.push(threadRow(t, i)));
  return rows;
}

const THREAD_FIELDS = { removed: "remove_thread_ids", resolved: "resolve_thread_ids", reopened: "reopen_thread_ids" } as const;

function threadRow(t: RippleChange["threads"][number], index: number): DiffRow {
  const base = { key: `thread-${index}`, kind: `Thread ${t.change}`, text: t.title };
  if (t.change === "opened") {
    return { ...base, tone: "added", drop: (d) => ({ ...d, threads_opened: d.threads_opened.filter((x) => x.title !== t.title) }) };
  }
  const field = THREAD_FIELDS[t.change];
  return {
    ...base, tone: t.change === "removed" ? "removed" : "changed",
    drop: (d) => ({ ...d, [field]: d[field].filter((id) => id !== t.id) }),
  };
}

// --- Gate 2 ---------------------------------------------------------------------------

function EpisodesGate({ storyId, ripple, locked, run }: { storyId: number; ripple: Ripple; locked: boolean; run: Run }) {
  const flagged = ripple.items.filter((i) => i.check_status !== "unaffected" || i.decision);
  const unaffected = ripple.items.filter((i) => i.check_status === "unaffected" && !i.decision);
  const nextUp = ripple.items.find((i) => !i.decision && i.check_status !== "unaffected")?.episode_number;
  const hasMinorFixes = ripple.items.some((i) => !i.decision && i.check_status === "minor" && i.proposal?.kind === "patch");

  return (
    <Section
      title="Step 2 of 3 · later episodes, in order"
      aside={hasMinorFixes && (
        <Button onClick={() => run(async () => (await api.acceptMinor(storyId, ripple.id)).job)} disabled={locked}>
          Accept all minor fixes
        </Button>
      )}
    >
      {ripple.summary && <p className="mb-3 rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-300">{ripple.summary}</p>}
      {unaffected.length > 0 && (
        <p className="mb-3 text-xs text-emerald-400">
          🟢 Checked and unaffected: episode{unaffected.length === 1 ? "" : "s"} {unaffected.map((i) => i.episode_number).join(", ")}
        </p>
      )}
      <div className="space-y-3">
        {flagged.map((item) => (
          <ItemCard
            key={item.episode_number}
            storyId={storyId}
            rippleId={ripple.id}
            item={item}
            isNext={item.episode_number === nextUp}
            locked={locked}
            run={run}
          />
        ))}
      </div>
    </Section>
  );
}

const CHECK_LABELS: Record<string, string> = {
  major: "🔴 needs review", recheck: "🔴 re-check after an earlier fix", minor: "🟡 minor · fix suggested",
  pending: "⏳ not checked (cost cap or interrupted)", unaffected: "🟢 unaffected",
};

function ItemCard({ storyId, rippleId, item, isNext, locked, run }: {
  storyId: number; rippleId: number; item: RippleItem; isNext: boolean; locked: boolean; run: Run;
}) {
  const [text, setText] = useState<string | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const number = item.episode_number;
  useEffect(() => {
    api.episode(storyId, number).then((e) => setText(e.text)).catch(() => setText(""));
  }, [storyId, number]);

  const decide = (decision: RippleDecisionKind, newText?: string) =>
    run(async () => (await api.decideItem(storyId, rippleId, number, decision, newText)).job);
  const proposal = item.proposal;
  const canAct = isNext && !locked && !item.decision;

  return (
    <Card className={`p-4 ${isNext ? "border-line-strong" : ""}`}>
      <div className="flex flex-wrap items-center gap-2">
        <b className="text-sm">Episode {number}</b>
        <span className="text-[11px] text-muted">{CHECK_LABELS[item.check_status]}</span>
        {item.decision && <StatusBadge status={`decided: ${item.decision}`} />}
      </div>
      {item.signals.reasons.length > 0 && (
        <p className="mt-1 text-[11px] break-words text-faint">Why it was checked: {item.signals.reasons.join("; ")}</p>
      )}
      {item.conflicts.map((c, i) => (
        <div key={i} className="mt-3 text-sm leading-relaxed break-words">
          {text !== null && <QuoteInContext text={text} quote={c.quote} />}
          <p className="mt-1 text-xs text-amber-300">{c.reason}</p>
        </div>
      ))}
      {!item.decision && <Proposal item={item} text={text} />}
      {draft !== null ? (
        <div className="mt-3 space-y-2">
          <AutoTextarea value={draft} onChange={(e) => setDraft(e.target.value)} className="prose-episode p-4" />
          <div className="flex gap-2">
            <Button variant="primary" onClick={() => decide("edit", draft)} disabled={!canAct || !draft.trim()}>Save my version</Button>
            <Button variant="ghost" onClick={() => setDraft(null)}>Cancel</Button>
          </div>
        </div>
      ) : (
        !item.decision && (
          <div className="mt-3 flex flex-wrap gap-2">
            {proposal?.text && <Button variant="primary" onClick={() => decide("accept")} disabled={!canAct}>Accept fix</Button>}
            <Button onClick={() => setDraft(proposal?.text || text || "")} disabled={!canAct}>Edit myself</Button>
            <Button onClick={() => decide("keep")} disabled={!canAct}>Keep as is</Button>
            <Button variant="ghost" onClick={() => decide("rewrite")} disabled={!canAct}>Rewrite</Button>
            {!isNext && <span className="self-center text-[11px] text-faint">Decide the earlier episodes first.</span>}
          </div>
        )
      )}
      {item.decision && item.decision_note && <p className="mt-2 text-xs text-faint">{item.decision_note}</p>}
    </Card>
  );
}

function Proposal({ item, text }: { item: RippleItem; text: string | null }) {
  const proposal = item.proposal;
  if (!proposal) {
    return item.check_status === "pending"
      ? <Note>Not checked: the ripple reached its cost cap. Keep it, edit it yourself, or ask for a rewrite.</Note>
      : null;
  }
  if (proposal.kind === "patch") {
    return <div className="mt-3 space-y-2"><Note>Proposed fix: {proposal.note}</Note><PatchEdits edits={proposal.edits} /></div>;
  }
  if (!proposal.text) return <Note>{proposal.note} Edit it yourself, keep it, or ask for a full rewrite.</Note>;
  return (
    <div className="mt-3 space-y-2">
      <Note>A full rewrite against the corrected canon. Changes from the current text:</Note>
      <Card className="max-h-96 overflow-y-auto p-3">{text !== null && <TextDiff before={text} after={proposal.text} />}</Card>
    </div>
  );
}

function Note({ children }: { children: ReactNode }) {
  return <p className="mt-3 text-xs break-words text-muted">{children}</p>;
}

// --- Gate 3 ---------------------------------------------------------------------------

function ReplanGate({ storyId, ripple, locked, run }: { storyId: number; ripple: Ripple; locked: boolean; run: Run }) {
  const changes = ripple.replan?.changes ?? [];
  const [kept, setKept] = useState<number[]>(changes.map((c) => c.episode));
  const toggle = (n: number) => setKept((k) => (k.includes(n) ? k.filter((x) => x !== n) : [...k, n]));
  const approve = () => run(async () => void (await api.approveReplan(storyId, ripple.id, kept)));

  return (
    <Section title="Step 3 of 3 · upcoming beats">
      <p className="mb-3 text-sm break-words text-muted">{ripple.replan?.what_changed}</p>
      {changes.length === 0 ? (
        <p className="mb-3 text-sm text-faint">No upcoming beats need to change.</p>
      ) : (
        <ul className="mb-3 divide-y divide-line rounded-lg border border-line text-sm">
          {changes.map((change) => (
            <li key={change.episode} className="grid gap-1 px-3 py-2 md:grid-cols-[4.5rem_1fr_1fr] md:gap-3">
              <label className="flex items-center gap-2 text-xs text-faint">
                <input type="checkbox" checked={kept.includes(change.episode)} onChange={() => toggle(change.episode)} className="accent-current" />
                ep {change.episode}
              </label>
              <span className="break-words text-faint line-through decoration-faint/50">{change.before}</span>
              <span className="break-words">{change.after}</span>
            </li>
          ))}
        </ul>
      )}
      <Button variant="primary" onClick={approve} disabled={locked}>
        {changes.length ? `Approve ${kept.length} beat change${kept.length === 1 ? "" : "s"} and finish` : "Finish"}
      </Button>
    </Section>
  );
}
