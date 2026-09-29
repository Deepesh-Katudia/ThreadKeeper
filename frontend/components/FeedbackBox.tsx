"use client";

import { useState } from "react";

import { ReturnIcon } from "@/components/icons";
import { AutoTextarea, ErrorBox } from "@/components/ui";
import { api, Job } from "@/lib/api";

const PLACEHOLDER = "Steer the rest of the story… e.g. “Slow down the romance” or “Kill off the landlord soon”";

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

  const canSubmit = !isBusy && text.trim().length >= 3;

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
    <div className="rounded-xl border border-line bg-panel p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Story direction</h3>
        <label className="flex items-center gap-2 text-[11px] text-muted">
          Applies until episode
          <input
            type="number"
            min={0}
            value={expiresAfter}
            onChange={(e) => setExpiresAfter(Number(e.target.value))}
            className="w-16 rounded-md border border-line bg-field px-2 py-0.5 text-xs text-fg"
          />
          <span className="text-faint">(0 = forever)</span>
        </label>
      </div>
      <p className="mb-2 text-[11px] text-faint">
        Saved as a standing instruction that every future episode sees; the next 20 unwritten beats are re-planned around it.
      </p>
      <ErrorBox message={error} />
      <div className="mt-2 flex items-end gap-2 rounded-lg border border-line bg-field p-1.5">
        <AutoTextarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && canSubmit) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={PLACEHOLDER}
          className="border-0 bg-transparent focus:border-0"
        />
        <button onClick={submit} disabled={!canSubmit} title="Give feedback & re-plan (Enter)" className="mb-0.5 rounded-md p-2 text-muted hover:bg-subtle hover:text-fg disabled:opacity-40">
          <ReturnIcon />
        </button>
      </div>
    </div>
  );
}
