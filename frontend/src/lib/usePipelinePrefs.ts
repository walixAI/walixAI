import { useEffect, useState } from "react";

export interface PipelinePrefs {
  view: "kanban" | "list";
  search: string;
  pipelineId: string | null;
  filters: {
    ownerName: string;
    amountMin: string;
    amountMax: string;
    closeBefore: string | null; // ISO date
    source: string;
    tag: string;
  };
}

const DEFAULT_PREFS: PipelinePrefs = {
  view: "kanban",
  search: "",
  pipelineId: null,
  filters: {
    ownerName: "all",
    amountMin: "",
    amountMax: "",
    closeBefore: null,
    source: "all",
    tag: "",
  },
};

const KEY = "walix.pipeline.prefs.v1";

function read(): PipelinePrefs {
  if (typeof window === "undefined") return DEFAULT_PREFS;
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw);
    return {
      ...DEFAULT_PREFS,
      ...parsed,
      filters: { ...DEFAULT_PREFS.filters, ...(parsed?.filters ?? {}) },
    };
  } catch {
    return DEFAULT_PREFS;
  }
}

export function usePipelinePrefs() {
  const [prefs, setPrefs] = useState<PipelinePrefs>(() => read());

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(prefs));
    } catch {
      /* storage full / disabled */
    }
  }, [prefs]);

  return [prefs, setPrefs] as const;
}
