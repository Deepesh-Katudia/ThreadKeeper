"use client";

import { useEffect, useState } from "react";

import { Button, ErrorBox, Spinner, StatusBadge } from "@/components/ui";
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
    api.episode(storyId, number).then(setEpisode).catch((e) => setError((e as Error).message));
  }, [storyId, number]);

  if (!episode) return error ? <ErrorBox message={error} /> : <Spinner label="Loading episode..." />;

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
  const saveEdit = () =>
    act(async () => {
      setEpisode(await api.editEpisode(storyId, number, draftText));
    });
  const reject = () => act(async () => (await api.rejectEpisode(storyId, number, reason)).job);
  const rewriteStale = () =>
    act(async () => (await api.rejectEpisode(storyId, number, episode.human_note || "Rewrite against the updated story.")).job);

  const report = episode.critic_report ?? {};
  const locked = isBusy || isSaving;

  return (
    <article className="rounded border border-zinc-200 bg-white p-5">
      <header className="mb-4">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-bold">
            Episode {episode.number}{episode.title ? `: ${episode.title}` : ""}
          </h2>
          <StatusBadge status={episode.status} />
        </div>
        <p className="mt-1 text-sm text-zinc-500">Beat: {episode.beat}</p>
        {episode.text && (
          <p className="mt-1 text-xs text-zinc-500">
            {episode.word_count} words · {episode.revision_count} revision{episode.revision_count === 1 ? "" : "s"} ·
            ${report.cost_usd?.toFixed(3) ?? "?"}
            {episode.was_edited_by_human ? " · edited by a human" : ""}
          </p>
        )}
      </header>

      <ErrorBox message={error} />

      {episode.status === "failed" && <ErrorBox message={`Writing failed: ${episode.error}`} />}
      {episode.status === "drafting" && <Spinner label="Being written..." />}
      {episode.status === "planned" && <p className="text-sm text-zinc-500">Not written yet.{episode.human_note && ` Note for the next draft: ${episode.human_note}`}</p>}
      {episode.status === "stale" && (
        <div className="mb-3 rounded border border-orange-300 bg-orange-50 p-3 text-sm">
          This draft was written before an earlier episode was changed, so it may contradict the story now.
          <div className="mt-2"><Button onClick={rewriteStale} disabled={locked}>Rewrite it</Button></div>
        </div>
      )}

      {mode === "edit" ? (
        <div className="space-y-2">
          {episode.status === "approved" && (
            <p className="rounded bg-amber-50 p-2 text-sm text-amber-900">
              This episode is already canon. Saving re-extracts its memory (facts, deaths, threads) and marks any
              later unapproved drafts as stale.
            </p>
          )}
          <textarea value={draftText} onChange={(e) => setDraftText(e.target.value)} rows={22} className="prose-episode w-full rounded border border-zinc-300 p-3" />
          <div className="flex gap-2">
            <Button onClick={saveEdit} disabled={locked}>{isSaving ? "Saving..." : "Save edit"}</Button>
            <Button variant="secondary" onClick={() => setMode("read")}>Cancel</Button>
          </div>
        </div>
      ) : (
        episode.text && <div className="prose-episode">{episode.text}</div>
      )}

      {mode === "reject" && (
        <div className="mt-4 space-y-2 rounded border border-red-200 bg-red-50 p-3">
          <p className="text-sm">What should the next draft do differently? (This note applies to this episode only.)</p>
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} className="w-full rounded border border-zinc-300 p-2 text-sm" />
          <div className="flex gap-2">
            <Button variant="danger" onClick={reject} disabled={locked || reason.trim().length < 3}>Reject &amp; rewrite</Button>
            <Button variant="secondary" onClick={() => setMode("read")}>Cancel</Button>
          </div>
        </div>
      )}

      {mode === "read" && (episode.status === "in_review" || episode.status === "approved") && (
        <div className="mt-5 flex gap-2 border-t border-zinc-100 pt-4">
          {episode.status === "in_review" && <Button onClick={approve} disabled={locked}>Approve</Button>}
          <Button variant="secondary" onClick={() => { setDraftText(episode.text); setMode("edit"); }} disabled={locked}>
            Edit text
          </Button>
          {episode.status === "in_review" && (
            <Button variant="danger" onClick={() => setMode("reject")} disabled={locked}>Reject…</Button>
          )}
        </div>
      )}

      {report.final && <CriticPanel episode={episode} />}
      {episode.status === "in_review" && <PendingMemory memory={episode.pending_memory} />}
      {report.context_sent && <ContextPanel sections={report.context_sent} />}
    </article>
  );
}

function CriticPanel({ episode }: { episode: Episode }) {
  const report = episode.critic_report;
  const final = report.final!;
  return (
    <details className="mt-5 rounded border border-zinc-200 p-3" open={!report.passed}>
      <summary className="cursor-pointer text-sm font-semibold">
        Critic: {report.passed ? "passed" : "flagged problems"} · hook {final.hook_score}/5
        {report.possible_repeats_of?.length ? ` · similar to ep ${report.possible_repeats_of.join(", ")}` : ""}
      </summary>
      <div className="mt-2 space-y-2 text-sm">
        {final.problems.length > 0 && (
          <ul className="list-disc pl-5">
            {final.problems.map((p, i) => <li key={i}><b>{p.kind}</b>: {p.detail}</li>)}
          </ul>
        )}
        <p className="text-zinc-600">Advice: {final.advice}</p>
        <p className="text-xs text-zinc-500">
          Attempts: {report.attempts?.map((a) => `${a.stage}${a.verdict ? ` (${a.verdict}, ${a.words}w)` : ` (${a.reason})`}`).join(" → ")}
        </p>
      </div>
    </details>
  );
}

function PendingMemory({ memory }: { memory: Record<string, unknown> }) {
  const facts = (memory.new_facts as { subject: string; statement: string }[]) ?? [];
  const changes = (memory.character_changes as { name: string; new_status: string }[]) ?? [];
  const opened = (memory.threads_opened as { title: string }[]) ?? [];
  const resolved = (memory.threads_resolved as string[]) ?? [];
  return (
    <details className="mt-3 rounded border border-zinc-200 p-3">
      <summary className="cursor-pointer text-sm font-semibold">What approving will add to story memory</summary>
      <div className="mt-2 space-y-1 text-sm">
        <p><b>Summary:</b> {String(memory.summary ?? "")}</p>
        {changes.map((c, i) => <p key={i}><b>Status change:</b> {c.name} → {c.new_status}</p>)}
        {facts.map((f, i) => <p key={i}><b>Fact:</b> {f.subject}: {f.statement}</p>)}
        {opened.map((t, i) => <p key={i}><b>New thread:</b> {t.title}</p>)}
        {resolved.map((t, i) => <p key={i}><b>Resolves:</b> {t}</p>)}
      </div>
    </details>
  );
}

function ContextPanel({ sections }: { sections: Record<string, string> }) {
  return (
    <details className="mt-3 rounded border border-zinc-200 p-3">
      <summary className="cursor-pointer text-sm font-semibold">What the writer saw (memory layers sent in the prompt)</summary>
      <div className="mt-2 space-y-3">
        {Object.entries(sections).map(([title, body]) => (
          <div key={title}>
            <p className="text-xs font-semibold uppercase text-zinc-500">{title}</p>
            <pre className="whitespace-pre-wrap text-xs text-zinc-700">{body}</pre>
          </div>
        ))}
      </div>
    </details>
  );
}
