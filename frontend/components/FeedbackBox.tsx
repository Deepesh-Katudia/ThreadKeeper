"use client";

import { useState } from "react";

import { Button, ErrorBox } from "@/components/ui";
import { api, Job } from "@/lib/api";

const EXAMPLES = ["Slow down the romance.", "Kill off the landlord within the next few episodes.", "More humour in the dialogue."];

/** Story-wide feedback: becomes a standing instruction and re-plans the upcoming beats. */
export function FeedbackBox({
  storyId,
  isBusy,
  onSubmitted,
}: {
  storyId: number;
  isBusy: boolean;
  onSubmitted: (job: Job) => void;
}) {
  const [text, setText] = useState("");
  const [expiresAfter, setExpiresAfter] = useState(0);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    try {
      const { job } = await api.giveFeedback(storyId, text, expiresAfter);
      setText("");
      onSubmitted(job);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-2 rounded border border-violet-200 bg-violet-50 p-4">
      <h3 className="font-semibold">Steer the rest of the story</h3>
      <p className="text-sm text-zinc-600">
        Feedback here is saved as a standing instruction that every future episode sees, and the next 20 unwritten
        beats are re-planned around it. To fix only the episode in front of you, use Reject or Edit instead.
      </p>
      <ErrorBox message={error} />
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={EXAMPLES.join("  ·  ")}
        rows={2}
        className="w-full rounded border border-zinc-300 bg-white p-2 text-sm"
      />
      <div className="flex items-center gap-3">
        <label className="text-sm">
          Applies until episode{" "}
          <input
            type="number"
            min={0}
            value={expiresAfter}
            onChange={(e) => setExpiresAfter(Number(e.target.value))}
            className="w-20 rounded border border-zinc-300 px-1"
          />{" "}
          <span className="text-zinc-500">(0 = rest of the story)</span>
        </label>
        <Button onClick={submit} disabled={isBusy || text.trim().length < 3}>Give feedback &amp; re-plan</Button>
      </div>
    </div>
  );
}
