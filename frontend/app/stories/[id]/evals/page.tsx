"use client";

import { useCallback, useState } from "react";

import { Cell, Table } from "@/components/Table";
import { Button, Card, ErrorBox, PaneBody, Section, Spinner, StoryNav } from "@/components/ui";
import { api, EvaluationRun, EvaluatorKey, Job } from "@/lib/api";
import { useJob } from "@/lib/useJob";
import { useLoader } from "@/lib/useLoader";
import { useStory } from "@/lib/useStory";

const EVALUATORS: { key: EvaluatorKey; label: string; how: string }[] = [
  { key: "hook", label: "Hook", how: "LLM judge: does the ending make you need the next episode?" },
  { key: "consistency", label: "Consistency", how: "LLM judge: any contradiction with canon established earlier?" },
  { key: "follows_directives", label: "Follows your direction", how: "LLM judge: does it respect the standing instructions in force?" },
  { key: "no_repetition", label: "No repetition", how: "Code: is the summary a near-copy of an earlier one?" },
  { key: "word_count", label: "Length 400–700", how: "Code: word count inside the allowed range." },
];

export default function EvalsPage() {
  const { storyId, overview, reload: reloadStory } = useStory();
  const fetchEvaluations = useCallback(() => api.evaluations(storyId), [storyId]);
  const { data, error, setError, reload } = useLoader(fetchEvaluations);
  const [message, setMessage] = useState<string | null>(null);

  const { watch, isRunning } = useJob(
    useCallback(
      (finished: Job) => {
        setMessage(finished.status === "failed" ? `Evaluation failed: ${finished.detail}` : finished.detail);
        reload();
        reloadStory();
      },
      [reload, reloadStory],
    ),
    overview?.running_job?.kind === "evaluate" ? overview.running_job : null,
  );

  const header = <StoryNav storyId={storyId} title={overview?.story.title ?? ""} />;
  if (!data) {
    return <>{header}<PaneBody>{error ? <ErrorBox message={error} /> : <Spinner label="Loading evaluations…" />}</PaneBody></>;
  }

  async function runEvaluation() {
    setError(null);
    setMessage(null);
    try {
      watch((await api.runEvaluation(storyId)).job);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const latest = data.evaluations[0];
  // Only one background job per story: don't offer to start an evaluation while something else runs.
  const busy = isRunning || Boolean(overview?.running_job);

  return (
    <>
      {header}
      <PaneBody>
        <div className="mx-auto max-w-5xl">
          <Card className="mb-8 p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0 max-w-2xl">
                <h2 className="text-lg font-semibold">Evaluation in LangSmith</h2>
                <p className="mt-2 text-sm leading-relaxed text-muted">
                  Every episode&apos;s trace already carries the critic&apos;s scores and your decision (approve / edit / reject) as
                  LangSmith feedback. Running an evaluation adds a LangSmith experiment over all approved episodes, scored by{" "}
                  <span className="text-fg">{data.judge_model}</span>, a different model family from the writer.
                </p>
                <p className="mt-3 flex flex-wrap items-center gap-3 text-xs">
                  <span className={data.langsmith_enabled ? "text-emerald-400" : "text-amber-400"}>
                    ● {data.langsmith_enabled ? "LangSmith connected" : "LangSmith not configured"}
                  </span>
                  {data.project_url && (
                    <a href={data.project_url} target="_blank" rel="noreferrer" className="text-muted underline hover:text-fg">
                      Open traces in LangSmith ↗
                    </a>
                  )}
                </p>
              </div>
              <div className="flex flex-col items-end gap-2">
                <Button variant="primary" onClick={runEvaluation} disabled={busy || !data.langsmith_enabled || data.approved_episodes === 0}>
                  Run evaluation
                </Button>
                <span className="text-[11px] text-faint">
                  {data.approved_episodes} approved episodes · about ${data.estimated_cost_usd.toFixed(3)}
                </span>
              </div>
            </div>
            <div className="mt-3 space-y-2">
              <ErrorBox message={error} />
              {isRunning && <Spinner label="Scoring every approved episode in LangSmith…" />}
              {!isRunning && message && <p className="text-xs break-words text-muted">{message}</p>}
            </div>
          </Card>

          {latest ? <LatestRun run={latest} /> : (
            <p className="mb-8 text-sm text-faint">No evaluation has been run yet. Approve a few episodes, then press “Run evaluation”.</p>
          )}

          <Section title={`Critic vs human${data.critic_vs_human.agreement !== null ? ` · ${Math.round(data.critic_vs_human.agreement * 100)}% agreement` : ""}`}>
            <p className="mb-3 text-xs text-faint">
              Agreement = the critic passed an episode you approved unchanged, or flagged one you rejected or edited. Low agreement means the critic needs tuning.
            </p>
            {data.critic_vs_human.rows.length === 0 ? (
              <p className="text-sm text-faint">No episodes written yet.</p>
            ) : (
              <Table headers={["Ep", "Critic", "Hook", "Revisions", "You", "Agree"]}>
                {data.critic_vs_human.rows.map((row) => (
                  <tr key={row.episode}>
                    <Cell>{row.episode}</Cell>
                    <Cell className={row.critic_passed ? "text-emerald-400" : "text-red-400"}>{row.critic_passed ? "passed" : "flagged"}</Cell>
                    <Cell>{row.hook_score ?? "–"}/5</Cell>
                    <Cell>{row.revisions}</Cell>
                    <Cell className="text-muted">{row.human.replace("_", " ")}</Cell>
                    <Cell>{row.human.startsWith("in_review") ? "–" : row.agrees ? "✓" : "✗"}</Cell>
                  </tr>
                ))}
              </Table>
            )}
          </Section>

          {data.evaluations.length > 1 && (
            <Section title="Earlier runs">
              <Table headers={["When", "Episodes", ...EVALUATORS.map((e) => e.label), "Cost", ""]}>
                {data.evaluations.slice(1).map((run) => (
                  <tr key={run.id}>
                    <Cell className="whitespace-nowrap text-faint">{run.created_at ? new Date(run.created_at).toLocaleString() : "–"}</Cell>
                    <Cell>{run.episodes_scored}</Cell>
                    {EVALUATORS.map((e) => <Cell key={e.key}>{percent(run.scores[e.key])}</Cell>)}
                    <Cell>${run.cost_usd.toFixed(3)}</Cell>
                    <Cell>{run.experiment_url && <a href={run.experiment_url} target="_blank" rel="noreferrer" className="text-muted underline hover:text-fg">LangSmith ↗</a>}</Cell>
                  </tr>
                ))}
              </Table>
            </Section>
          )}
        </div>
      </PaneBody>
    </>
  );
}

function LatestRun({ run }: { run: EvaluationRun }) {
  return (
    <>
      <Section
        title={`Latest run · ${run.episodes_scored} episodes · $${run.cost_usd.toFixed(3)}`}
        aside={run.experiment_url && (
          <a href={run.experiment_url} target="_blank" rel="noreferrer" className="text-xs text-muted underline hover:text-fg">
            Open experiment in LangSmith ↗
          </a>
        )}
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {EVALUATORS.map((evaluator) => (
            <ScoreTile key={evaluator.key} label={evaluator.label} how={evaluator.how} score={run.scores[evaluator.key]} />
          ))}
        </div>
      </Section>

      <Section title="Per episode">
        <Table headers={["Ep", ...EVALUATORS.map((e) => e.label), "Judge's notes"]}>
          {run.per_episode.map((row) => (
            <tr key={row.episode}>
              <Cell>{row.episode}</Cell>
              {EVALUATORS.map((e) => <Cell key={e.key} className={tone(row[e.key])}>{percent(row[e.key])}</Cell>)}
              <Cell className="min-w-72 text-xs text-muted">
                {(["hook", "consistency", "follows_directives"] as EvaluatorKey[])
                  .filter((key) => row.comments[key])
                  .map((key) => <p key={key} className="mb-1"><span className="text-faint">{key.replace("_", " ")}: </span>{row.comments[key]}</p>)}
              </Cell>
            </tr>
          ))}
        </Table>
      </Section>
    </>
  );
}

function ScoreTile({ label, how, score }: { label: string; how: string; score: number | null | undefined }) {
  const value = typeof score === "number" ? score : null;
  return (
    <Card className="p-4">
      <p className="text-[11px] tracking-wide text-faint uppercase">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone(value)}`}>{percent(value)}</p>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-subtle">
        <div className={`h-full rounded-full bg-current ${tone(value)}`} style={{ width: `${Math.round((value ?? 0) * 100)}%` }} />
      </div>
      <p className="mt-2 text-[11px] leading-snug text-faint">{how}</p>
    </Card>
  );
}

function percent(score: number | null | undefined): string {
  return typeof score === "number" ? `${Math.round(score * 100)}%` : "–";
}

function tone(score: number | null | undefined): string {
  if (typeof score !== "number") return "text-faint";
  if (score >= 0.8) return "text-emerald-400";
  if (score >= 0.6) return "text-amber-400";
  return "text-red-400";
}
