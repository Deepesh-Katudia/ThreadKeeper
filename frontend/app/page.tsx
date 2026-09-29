"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, ErrorBox, Section, StatusBadge } from "@/components/ui";
import { api, setAccessKey } from "@/lib/api";
import { useLoader } from "@/lib/useLoader";

const EXAMPLE_PREMISE =
  "A delivery rider realizes every address on today's route belongs to someone who died in the same building.";

export default function HomePage() {
  const router = useRouter();
  const { data: stories, error, setError, reload: loadStories } = useLoader(api.listStories);
  const [premise, setPremise] = useState(EXAMPLE_PREMISE);
  const [totalEpisodes, setTotalEpisodes] = useState(200);
  const [accessKey, setKey] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  async function createStory() {
    setIsCreating(true);
    setError(null);
    try {
      const { story_id } = await api.createStory(premise, totalEpisodes);
      router.push(`/stories/${story_id}`);
    } catch (e) {
      setError((e as Error).message);
      setIsCreating(false);
    }
  }

  function saveKey() {
    setAccessKey(accessKey);
    setKey("");
    loadStories();
  }

  return (
    <div>
      <Section title="Access key">
        <div className="flex gap-2">
          <input
            type="password"
            value={accessKey}
            onChange={(e) => setKey(e.target.value)}
            placeholder="Passcode from the backend's ACCESS_KEY (remembered in this browser)"
            className="w-80 rounded border border-zinc-300 px-3 py-1.5 text-sm"
          />
          <Button variant="secondary" onClick={saveKey}>Save</Button>
        </div>
      </Section>

      <ErrorBox message={error} />

      <Section title="Start a new serial">
        <div className="space-y-3 rounded border border-zinc-200 bg-white p-4">
          <label className="block text-sm font-medium">One-line premise</label>
          <textarea
            value={premise}
            onChange={(e) => setPremise(e.target.value)}
            rows={3}
            className="w-full rounded border border-zinc-300 p-2 text-sm"
          />
          <div className="flex items-center gap-3">
            <label className="text-sm">Episodes</label>
            <input
              type="number"
              min={10}
              max={200}
              value={totalEpisodes}
              onChange={(e) => setTotalEpisodes(Number(e.target.value))}
              className="w-24 rounded border border-zinc-300 px-2 py-1 text-sm"
            />
            <Button onClick={createStory} disabled={isCreating || premise.trim().length < 10}>
              {isCreating ? "Starting..." : "Plan the arc"}
            </Button>
          </div>
          <p className="text-xs text-zinc-500">
            Planning takes a few minutes: the story bible first, then all acts&apos; episode beats in parallel.
          </p>
        </div>
      </Section>

      <Section title="Your serials">
        {!stories || stories.length === 0 ? (
          <p className="text-sm text-zinc-500">No stories yet.</p>
        ) : (
          <ul className="divide-y divide-zinc-200 rounded border border-zinc-200 bg-white">
            {stories.map((story) => (
              <li key={story.id}>
                <Link href={`/stories/${story.id}`} className="flex items-center justify-between p-3 hover:bg-zinc-50">
                  <div>
                    <p className="font-medium">{story.title || "(planning...)"}</p>
                    <p className="text-sm text-zinc-500">{story.premise}</p>
                  </div>
                  <div className="flex items-center gap-3 text-sm text-zinc-600">
                    {story.approved_episodes}/{story.total_episodes} written
                    <StatusBadge status={story.status} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
