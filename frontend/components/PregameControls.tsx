"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import type { PitcherProfileData } from "@/lib/types";

interface PregameControlsProps {
  pitcher: PitcherProfileData;
}

type GenerationState = "idle" | "generating" | "ready";

export function PregameControls({ pitcher }: PregameControlsProps) {
  const [startDate, setStartDate] = useState(pitcher.startDate);
  const [endDate, setEndDate] = useState(pitcher.endDate);
  const [generationState, setGenerationState] = useState<GenerationState>("idle");
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setGenerationState("generating");
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setGenerationState("ready"), 650);
  }

  return (
    <form className="pregame-controls" onSubmit={handleSubmit}>
      <label className="field-label">
        Pitcher
        <select defaultValue={pitcher.id}>
          <option value={pitcher.id}>{pitcher.name}</option>
        </select>
      </label>
      <div className="date-fields">
        <label className="field-label">
          Start date
          <input
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
          />
        </label>
        <label className="field-label">
          End date
          <input
            type="date"
            value={endDate}
            min={startDate}
            onChange={(event) => setEndDate(event.target.value)}
          />
        </label>
      </div>
      <button className="primary-button" disabled={generationState === "generating"} type="submit">
        <span aria-hidden="true">↻</span>
        {generationState === "generating" ? "Generating…" : "Generate brief"}
      </button>
      <p className="control-status" aria-live="polite">
        {generationState === "ready"
          ? "Mock brief refreshed for the selected window."
          : "Uses prepared mock data in this frontend phase."}
      </p>
    </form>
  );
}
