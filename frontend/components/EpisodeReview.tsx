"use client";

import { useEffect, useState, type ReactNode } from "react";

import { AutoTextarea, Button, Card, ErrorBox, Spinner, StatusBadge } from "@/components/ui";
import { api, Episode, Job } from "@/lib/api";

type Mode = "read" | "edit" | "reject";

/** One episode with the human controls: approve, edit, reject with a note. */
export function EpisodeReview({
  storyId,
  number,
  isBusy,
  onChanged,
}: {
  storyId: number;
  number: number;
  isBusy: boolean;
  onChanged: (job?: Job | null) => void;
}) {
  const [episode, setEpisode] = useState<Episode | null>(null);
  const [mode, setMode] = useState<Mode>("read");
  const [draftText, setDraftText] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    api.episode(storyId, number).then(setEpisode).catch((e: Error) => setError(e.message));
  }, [storyId, number]);

  if (!episode) return error ? <ErrorBox message={error} /> : <Spinner label="Loading episode…" />;

  async function act(action: () => Promise<Job | null | void>) {
    setIsSaving(true);
    setError(null);
    try {
      const job = await action();
      setMode("read");
      onChanged(job ?? null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setIsSaving(false);
    }
  }

  const approve = () => act(async () => void (await api.approveEpisode(storyId, number)));
  const saveEdit = () => act(async () => { setEpisode(await api.editEpisode(storyId, number, draftText)); });
  const reject = () => act(async () => (await api.rejectEpisode(storyId, number, reason)).job);
  const rewriteStale = () =>
    act(async () => (await api.rejectEpisode(storyId, number, episode.human_note || "Rewrite against the updated story.")).job);

  const report = episode.critic_report ?? {};
  const locked = isBusy || isSaving;

  return (
    <article className="mx-auto max-w-3xl">
      <header className="mb-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-faint">Episode {episode.number}</span>
          <StatusBadge status={episode.status} />
          {episode.was_edited_by_human && <span className="text-[11px] text-violet-400">edited by a human</span>}
        </div>
        {episode.title && <h2 className="mt-2 text-2xl font-semibold tracking-tight break-words">{episode.title}</h2>}
        <p className="mt-2 text-sm break-words text-muted"><span className="text-faint">Beat · </span>{episode.beat}</p>
        {episode.text && (
          <p className="mt-2 text-[11px] text-faint">
            {episode.word_count} words · {episode.revision_count} revision{episode.revision_count === 1 ? "" : "s"} · ${report.cost_usd?.toFixed(3) ?? "?"}
          </p>
        )}
      </header>

      <div className="space-y-3">
        <ErrorBox message={error} />
        {episode.status === "failed" && <ErrorBox message={`Writing failed: ${episode.error}`} />}
        {episode.status === "drafting" && <Spinner label="Being written…" />}
        {episode.status === "planned" && (
          <p className="text-sm break-words text-muted">
            Not written yet.{episode.human_note && ` Note for the next draft: ${episode.human_note}`}
          </p>
        )}
        {episode.status === "stale" && (
          <Card className="border-orange-500/30 p-3 text-sm">
            <p className="break-words">This draft was written before an earlier episode changed, so it may contradict the story now.</p>
            <div className="mt-2"><Button variant="primary" onClick={rewriteStale} disabled={locked}>Rewrite it</Button></div>
          </Card>
        )}
      </div>

      {mode === "edit" ? (
        <div className="mt-4 space-y-3">
          {episode.status === "approved" && (
            <p className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-xs break-words text-amber-300">
              This episode is already canon. Saving rebuilds its memory (facts, deaths, threads) and marks later unapproved drafts stale.
            </p>
          )}
          <AutoTextarea value={draftText} onChange={(e) => setDraftText(e.target.value)} className="prose-episode p-4" />
          <div className="flex gap-2">
            <Button variant="primary" onClick={saveEdit} disabled={locked}>{isSaving ? "Saving…" : "Save edit"}</Button>
            <Button variant="ghost" onClick={() => setMode("read")}>Cancel</Button>
          </div>
        </div>
      ) : (
        episode.text && <div className="prose-episode mt-4">{episode.text}</div>
      )}

      {mode === "reject" && (
        <Card className="mt-5 space-y-2 border-red-500/30 p-3">
          <p className="text-xs text-muted">What should the next draft do differently? This note applies to this episode only.</p>
          <AutoTextarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} placeholder="e.g. Less rain, more dialogue with Ray." />
          <div className="flex gap-2">
            <Button variant="danger" onClick={reject} disabled={locked || reason.trim().length < 3}>Reject &amp; rewrite</Button>
            <Button variant="ghost" onClick={() => setMode("read")}>Cancel</Button>
          </div>
        </Card>
      )}

      {mode === "read" && (episode.status === "in_review" || episode.status === "approved") && (
        <div className="mt-6 flex flex-wrap gap-2 border-t border-line pt-4">
          {episode.status === "in_review" && <Button variant="primary" onClick={approve} disabled={locked}>Approve</Button>}
          <Button onClick={() => { setDraftText(episode.text); setMode("edit"); }} disabled={locked}>Edit text</Button>
          {episode.status === "in_review" && <Button variant="danger" onClick={() => setMode("reject")} disabled={locked}>Reject…</Button>}
        </div>
      )}

      <div className="mt-6 space-y-2">
        {report.final && <CriticPanel episode={episode} />}
        {episode.status === "in_review" && <PendingMemory memory={episode.pending_memory} />}
        {report.context_sent && <ContextPanel sections={report.context_sent} />}
      </div>
    </article>
  );
}

function Disclosure({ title, open, children }: { title: ReactNode; open?: boolean; children: ReactNode }) {
  return (
    <details className="group rounded-lg border border-line bg-panel" open={open}>
      <summary className="cursor-pointer list-none px-3 py-2.5 text-xs font-medium break-words text-muted hover:text-fg">
        <span className="mr-1 inline-block transition group-open:rotate-90">›</span> {title}
      </summary>
      <div className="border-t border-line px-3 py-3 text-sm">{children}</div>
    </details>
  );
}

function CriticPanel({ episode }: { episode: Episode }) {
  const report = episode.critic_report;
  const final = report.final!;
  const repeats = report.possible_repeats_of?.length ? ` · similar to ep ${report.possible_repeats_of.join(", ")}` : "";
  return (
    <Disclosure title={`Critic: ${report.passed ? "passed" : "flagged problems"} · hook ${final.hook_score}/5${repeats}`} open={!report.passed}>
      <div className="space-y-2">
        {final.problems.length > 0 && (
          <ul className="list-disc space-y-1 pl-5">
            {final.problems.map((p, i) => <li key={i} className="break-words"><b>{p.kind}</b>: {p.detail}</li>)}
          </ul>
        )}
        <p className="break-words text-muted">Advice: {final.advice}</p>
        <p className="text-[11px] break-words text-faint">
          Attempts: {report.attempts?.map((a) => `${a.stage}${a.verdict ? ` (${a.verdict}, ${a.words}w)` : ` (${a.reason})`}`).join(" → ")}
        </p>
      </div>
    </Disclosure>
  );
}

function PendingMemory({ memory }: { memory: Record<string, unknown> }) {
  const facts = (memory.new_facts as { subject: string; statement: string }[]) ?? [];
  const changes = (memory.character_changes as { name: string; new_status: string }[]) ?? [];
  const opened = (memory.threads_opened as { title: string }[]) ?? [];
  const resolved = (memory.threads_resolved as string[]) ?? [];
  return (
    <Disclosure title="What approving adds to story memory">
      <div className="space-y-1.5 break-words">
        <p><span className="text-faint">Summary · </span>{String(memory.summary ?? "")}</p>
        {changes.map((c, i) => <p key={i}><span className="text-faint">Status · </span>{c.name} → {c.new_status}</p>)}
        {facts.map((f, i) => <p key={i}><span className="text-faint">Fact · </span>{f.subject}: {f.statement}</p>)}
        {opened.map((t, i) => <p key={i}><span className="text-faint">New thread · </span>{t.title}</p>)}
        {resolved.map((t, i) => <p key={i}><span className="text-faint">Resolves · </span>{t}</p>)}
      </div>
    </Disclosure>
  );
}

function ContextPanel({ sections }: { sections: Record<string, string> }) {
  return (
    <Disclosure title="What the writer saw (memory layers in the prompt)">
      <div className="space-y-4">
        {Object.entries(sections).map(([title, body]) => (
          <div key={title}>
            <p className="mb-1 text-[11px] tracking-wide text-faint uppercase">{title}</p>
            <pre className="font-sans text-xs leading-relaxed break-words whitespace-pre-wrap text-muted">{body}</pre>
          </div>
        ))}
      </div>
    </Disclosure>
  );
}
