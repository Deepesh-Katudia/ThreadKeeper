"use client";

import { useCallback } from "react";

import { Cell, Table } from "@/components/Table";
import { Card, ErrorBox, PaneBody, Section, Spinner, StoryNav } from "@/components/ui";
import { api } from "@/lib/api";
import { useLoader } from "@/lib/useLoader";
import { useStory } from "@/lib/useStory";

const dollars = (value?: number) => (value === undefined ? "–" : `$${value.toFixed(value < 1 ? 4 : 2)}`);

export default function CostsPage() {
  const { storyId, overview } = useStory();
  const fetchCosts = useCallback(() => api.costs(storyId), [storyId]);
  const { data: costs, error } = useLoader(fetchCosts);

  const header = <StoryNav storyId={storyId} title={overview?.story.title ?? ""} />;
  if (!costs) {
    return <>{header}<PaneBody>{error ? <ErrorBox message={error} /> : <Spinner label="Loading costs…" />}</PaneBody></>;
  }

  const { projection } = costs;

  return (
    <>
      {header}
      <PaneBody>
        <div className="mx-auto max-w-5xl">
          <div className="mb-8 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Spent so far" value={dollars(costs.total_cost_usd)} />
            <Stat label="Arc planning" value={dollars(costs.planning_cost_usd)} />
            <Stat label="Average per episode" value={dollars(projection.average_cost_per_episode_usd)} />
            <Stat label="Cap per episode" value={dollars(costs.cost_cap_per_episode_usd)} />
          </div>

          <Section title="Projection for the full serial">
            <Card className="p-4 text-sm leading-relaxed">
              {projection.based_on_episodes === 0 ? (
                <span className="text-muted">Approve an episode to see a projection.</span>
              ) : (
                <span className="text-muted">
                  Based on {projection.based_on_episodes} approved episodes: about{" "}
                  <b className="text-fg">{dollars(projection.estimated_total_cost_usd)}</b> and{" "}
                  <b className="text-fg">{projection.estimated_total_hours} hours</b> of model time for all{" "}
                  {overview?.story.total_episodes} episodes (about {projection.average_seconds_per_episode}s each), not counting human review time.
                </span>
              )}
            </Card>
          </Section>

          <Section title="Per episode">
            <Table headers={["Ep", "Cost", "Calls", "Revisions", "Failed", "Tokens in / out", "Model time"]}>
              {costs.per_episode.map((row) => (
                <tr key={row.episode}>
                  <Cell>{row.episode}</Cell>
                  <Cell className={row.cost_usd > costs.cost_cap_per_episode_usd ? "text-red-400" : ""}>{dollars(row.cost_usd)}</Cell>
                  <Cell>{row.calls}</Cell>
                  <Cell>{row.revisions}</Cell>
                  <Cell>{row.failed_calls}</Cell>
                  <Cell className="whitespace-nowrap">{row.input_tokens.toLocaleString()} / {row.output_tokens.toLocaleString()}</Cell>
                  <Cell>{(row.latency_ms / 1000).toFixed(1)}s</Cell>
                </tr>
              ))}
            </Table>
          </Section>

          <Section title="Trace · latest model calls">
            <p className="mb-3 text-[11px] text-faint">Full traces with prompts and outputs are in LangSmith (project “threadkeeper”).</p>
            <Table headers={["Ep", "Step", "Model", "In", "Cached", "Out", "Cost", "Latency", "Result"]}>
              {[...costs.recent_calls].reverse().map((call) => (
                <tr key={call.id} className="text-xs">
                  <Cell>{call.episode_number || "–"}</Cell>
                  <Cell>{call.step}</Cell>
                  <Cell className="text-muted">{call.model}</Cell>
                  <Cell>{call.input_tokens}</Cell>
                  <Cell>{call.cache_read_tokens}</Cell>
                  <Cell>{call.output_tokens}</Cell>
                  <Cell>{dollars(call.cost_usd)}</Cell>
                  <Cell>{(call.latency_ms / 1000).toFixed(1)}s</Cell>
                  <Cell className={call.succeeded ? "text-emerald-400" : "min-w-48 text-red-400"}>{call.succeeded ? "ok" : call.error}</Cell>
                </tr>
              ))}
            </Table>
          </Section>
        </div>
      </PaneBody>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-4">
      <p className="text-[11px] tracking-wide text-faint uppercase">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight">{value}</p>
    </Card>
  );
}
