"use client";

import { useEffect, useRef, useState } from "react";

import { api, Job } from "./api";

const POLL_EVERY_MS = 2500;

/**
 * Polls a background job until it finishes, then calls onFinished once.
 * `jobFromServer` lets a page pick up a job that was already running before it loaded.
 */
export function useJob(onFinished: (job: Job) => void, jobFromServer: Job | null = null) {
  const [startedHere, setStartedHere] = useState<Job | null>(null);
  const [finishedIds, setFinishedIds] = useState<number[]>([]);
  const finishedRef = useRef(onFinished);

  useEffect(() => {
    finishedRef.current = onFinished;
  }, [onFinished]);

  const candidate = startedHere ?? jobFromServer;
  const job = candidate && !finishedIds.includes(candidate.id) ? candidate : null;
  const jobId = job?.status === "running" ? job.id : null;

  useEffect(() => {
    if (jobId === null) return;
    const timer = setInterval(async () => {
      try {
        const latest = await api.job(jobId);
        if (latest.status !== "running") {
          setFinishedIds((ids) => [...ids, latest.id]);
          setStartedHere(null);
          finishedRef.current(latest);
        }
      } catch {
        // A missed poll is fine; the next one will try again.
      }
    }, POLL_EVERY_MS);
    return () => clearInterval(timer);
  }, [jobId]);

  return { watch: setStartedHere, isRunning: jobId !== null };
}
