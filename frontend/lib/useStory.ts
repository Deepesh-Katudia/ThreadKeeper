"use client";

import { useParams } from "next/navigation";
import { useCallback } from "react";

import { api } from "./api";
import { useLoader } from "./useLoader";

/** Loads a story's overview and gives back a `reload` to call after any change. */
export function useStory() {
  const params = useParams<{ id: string }>();
  const storyId = Number(params.id);
  const fetchOverview = useCallback(() => api.overview(storyId), [storyId]);
  const { data: overview, error, setError, reload } = useLoader(fetchOverview);
  return { storyId, overview, error, setError, reload };
}
