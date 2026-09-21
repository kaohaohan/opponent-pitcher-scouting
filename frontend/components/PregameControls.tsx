"use client";

import { FormEvent, useState } from "react";

import type { PitcherProfileData } from "@/lib/types";

export interface PregameControlsProps {
  pitcher: PitcherProfileData;
  isGenerating?: boolean;
  statusMessage?: string;
  onGenerate?: (request: { pitcherId: number; startDate: string; endDate: string }) => void;
}

export function PregameControls({
  pitcher,
  isGenerating = false,
  statusMessage,
  onGenerate,
}: PregameControlsProps) {
  const [pitcherId, setPitcherId] = useState(pitcher.id ? String(pitcher.id) : "");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedPitcherId = Number(pitcherId);
    if (!Number.isInteger(parsedPitcherId) || parsedPitcherId <= 0) {
      setValidationError("Enter a valid pitcher ID.");
      return;
    }
    if (!startDate || !endDate || startDate > endDate) {
      setValidationError("Choose a valid start and end date.");
      return;
    }
    setValidationError(null);
    onGenerate?.({ pitcherId: parsedPitcherId, startDate, endDate });
  }

  return (
    <form className="pregame-controls" onSubmit={handleSubmit}>
      <label className="field-label">
        Pitcher
        <input
          inputMode="numeric"
          min="1"
          onChange={(event) => setPitcherId(event.target.value)}
          placeholder="e.g. 669302"
          type="number"
          value={pitcherId}
        />
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
      <button className="primary-button" disabled={isGenerating} type="submit">
        <span aria-hidden="true">↻</span>
        {isGenerating ? "Generating…" : "Generate brief"}
      </button>
      <p className="control-status" aria-live="polite">
        {validationError ?? statusMessage ?? "Generate a brief for the selected pitcher and date window."}
      </p>
    </form>
  );
}
