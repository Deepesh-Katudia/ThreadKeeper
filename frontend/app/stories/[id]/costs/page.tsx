"use client";

import { useEffect, useState } from "react";

import { ErrorBox, Section, Spinner, StoryNav } from "@/components/ui";
import { api, Costs } from "@/lib/api";
import { useStory } from "@/lib/useStory";

const dollars = (value?: number) => (value === undefined ? "-" : `$${value.toFixed(value < 1 ? 4 : 2)}`);

export default function CostsPage() {
  const { storyId, overview } = useStory();
  const [costs, setCosts] = useState<Costs | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.costs(storyId).then(setCosts).catch((e) => setError((e as Error).message));
  }, [storyId]);

  if (!costs) return error ? <ErrorBox message={error} /> : <Spinner label="Loading costs..." />;

  const { projection } = costs;

  return (
    <div>
      <StoryNav storyId={storyId} title={overview?.story.title ?? ""} />

      <div className="mb-8 grid gap-3 md:grid-cols-4">
        <Stat label="Spent so far" value={dollars(costs.total_cost_usd)} />
        <Stat label="Arc planning" value={dollars(costs.planning_cost_usd)} />
        <Stat label="Average per episode" value={dollars(projection.average_cost_per_episode_usd)} />
        <Stat label="Cost cap per episode" value={dollars(costs.cost_cap_per_episode_usd)} />
      </div>

      <Section title="Projection for the full serial">
        {projection.based_on_episodes === 0 ? (
          <p className="text-sm text-zinc-500">Approve an episode to see a projection.</p>
        ) : (
          <p className="text-sm">
            Based on {projection.based_on_episodes} approved episodes: about{" "}
            <b>{dollars(projection.estimated_total_cost_usd)}</b> and{" "}
            <b>{projection.estimated_total_hours} hours</b> of model time for all {overview?.story.total_episodes} episodes
            (about {projection.average_seconds_per_episode}s each), not counting human review time.
          </p>
        )}
      </Section>

      <Section title="Per episode">
        <table className="w-full rounded border border-zinc-200 bg-white text-sm">
          <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500">
            <tr>
              <th className="p-2">Ep</th><th className="p-2">Cost</th><th className="p-2">Calls</th><th className="p-2">Revisions</th>
              <th className="p-2">Failed</th><th className="p-2">Tokens in / out</th><th className="p-2">Model time</th>
            </tr>
          </thead>
          <tbody>
            {costs.per_episode.map((row) => (
              <tr key={row.episode} className="border-t border-zinc-100">
                <td className="p-2">{row.episode}</td>
                <td className={`p-2 ${row.cost_usd > costs.cost_cap_per_episode_usd ? "text-red-600" : ""}`}>{dollars(row.cost_usd)}</td>
                <td className="p-2">{row.calls}</td>
                <td className="p-2">{row.revisions}</td>
                <td className="p-2">{row.failed_calls}</td>
                <td className="p-2">{row.input_tokens.toLocaleString()} / {row.output_tokens.toLocaleString()}</td>
                <td className="p-2">{(row.latency_ms / 1000).toFixed(1)}s</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="Trace: latest model calls">
        <p className="mb-2 text-xs text-zinc-500">Full traces with prompts and outputs are in LangSmith (project &quot;threadkeeper&quot;).</p>
        <table className="w-full rounded border border-zinc-200 bg-white text-xs">
          <thead className="bg-zinc-50 text-left uppercase text-zinc-500">
            <tr>
              <th className="p-2">Ep</th><th className="p-2">Step</th><th className="p-2">Model</th><th className="p-2">In</th>
              <th className="p-2">Cached</th><th className="p-2">Out</th><th className="p-2">Cost</th><th className="p-2">Latency</th><th className="p-2">Result</th>
            </tr>
          </thead>
          <tbody>
            {[...costs.recent_calls].reverse().map((call) => (
              <tr key={call.id} className="border-t border-zinc-100">
                <td className="p-2">{call.episode_number || "-"}</td>
                <td className="p-2">{call.step}</td>
                <td className="p-2">{call.model}</td>
                <td className="p-2">{call.input_tokens}</td>
                <td className="p-2">{call.cache_read_tokens}</td>
                <td className="p-2">{call.output_tokens}</td>
                <td className="p-2">{dollars(call.cost_usd)}</td>
                <td className="p-2">{(call.latency_ms / 1000).toFixed(1)}s</td>
                <td className={`p-2 ${call.succeeded ? "text-emerald-700" : "text-red-600"}`}>{call.succeeded ? "ok" : call.error.slice(0, 80)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-zinc-200 bg-white p-3">
      <p className="text-xs uppercase text-zinc-500">{label}</p>
      <p className="text-xl font-semibold">{value}</p>
    </div>
  );
}
