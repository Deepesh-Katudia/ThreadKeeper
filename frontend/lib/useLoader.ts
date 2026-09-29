"use client";

import { useCallback, useEffect, useState } from "react";

/** Fetches data when the component mounts; call `reload()` to fetch again after a change. */
export function useLoader<T>(fetcher: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let isCurrent = true;
    fetcher()
      .then((result) => {
        if (!isCurrent) return;
        setData(result);
        setError(null);
      })
      .catch((e: Error) => {
        if (isCurrent) setError(e.message);
      });
    return () => {
      isCurrent = false;
    };
  }, [fetcher, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  return { data, error, setError, reload };
}
