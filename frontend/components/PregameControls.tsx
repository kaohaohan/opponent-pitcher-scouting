"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { PitcherAvatar } from "@/components/PitcherAvatar";
import { usePitcherSearch } from "@/lib/queries";
import type { PitcherProfileData } from "@/lib/types";

export interface SelectedPitcher {
  id: number;
  name: string;
  team: string | null;
  throws: string | null;
}

export interface PregameControlsProps {
  pitcher: PitcherProfileData;
  isGenerating?: boolean;
  statusMessage?: string;
  initialPitcherId?: number;
  initialPitcherName?: string;
  initialPitcherTeam?: string | null;
  initialPitcherThrows?: string | null;
  onGenerate?: (request: {
    pitcherId: number;
    startDate: string;
    endDate: string;
    pitcherName?: string;
    pitcherTeam?: string | null;
    pitcherThrows?: string | null;
  }) => void;
}

export function PregameControls({
  pitcher,
  isGenerating = false,
  statusMessage,
  initialPitcherId,
  initialPitcherName,
  initialPitcherTeam,
  initialPitcherThrows,
  onGenerate,
}: PregameControlsProps) {
  const [selectedPitcher, setSelectedPitcher] = useState<SelectedPitcher | null>(
    initialPitcherId && initialPitcherName
      ? {
          id: initialPitcherId,
          name: initialPitcherName,
          team: initialPitcherTeam ?? null,
          throws: initialPitcherThrows ?? null,
        }
      : null,
  );
  const [searchTerm, setSearchTerm] = useState(initialPitcherName ?? "");
  const [debouncedTerm, setDebouncedTerm] = useState(searchTerm);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [showManualEntry, setShowManualEntry] = useState(false);
  const [manualId, setManualId] = useState(pitcher.id ? String(pitcher.id) : "");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  // A pitcher handed off from Player Watch (via URL params) arrives after
  // this component has already mounted, since the route doesn't remount.
  useEffect(() => {
    if (initialPitcherId && initialPitcherName) {
      setSelectedPitcher({
        id: initialPitcherId,
        name: initialPitcherName,
        team: initialPitcherTeam ?? null,
        throws: initialPitcherThrows ?? null,
      });
      setSearchTerm(initialPitcherName);
      setIsDropdownOpen(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPitcherId, initialPitcherName, initialPitcherTeam, initialPitcherThrows]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedTerm(searchTerm), 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  const searchQuery = usePitcherSearch(showManualEntry ? "" : debouncedTerm);
  const matches = searchQuery.data ?? [];

  function handleSearchChange(value: string) {
    setSearchTerm(value);
    setSelectedPitcher(null);
    setIsDropdownOpen(true);
  }

  function handleSelect(match: { id: number; name: string; team: string | null; throws: string | null }) {
    setSelectedPitcher({ id: match.id, name: match.name, team: match.team, throws: match.throws });
    setSearchTerm(match.name);
    setIsDropdownOpen(false);
    setValidationError(null);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!startDate || !endDate || startDate > endDate) {
      setValidationError("Choose a valid start and end date.");
      return;
    }

    if (showManualEntry) {
      const parsedPitcherId = Number(manualId);
      if (!Number.isInteger(parsedPitcherId) || parsedPitcherId <= 0) {
        setValidationError("Enter a valid pitcher ID.");
        return;
      }
      setValidationError(null);
      onGenerate?.({ pitcherId: parsedPitcherId, startDate, endDate });
      return;
    }

    if (!selectedPitcher) {
      setValidationError("Search for a pitcher and select one from the results.");
      return;
    }
    setValidationError(null);
    onGenerate?.({
      pitcherId: selectedPitcher.id,
      startDate,
      endDate,
      pitcherName: selectedPitcher.name,
      pitcherTeam: selectedPitcher.team,
      pitcherThrows: selectedPitcher.throws,
    });
  }

  return (
    <form className="pregame-controls" onSubmit={handleSubmit}>
      {showManualEntry ? (
        <label className="field-label">
          Pitcher ID
          <input
            inputMode="numeric"
            min="1"
            onChange={(event) => setManualId(event.target.value)}
            placeholder="e.g. 669302"
            type="number"
            value={manualId}
          />
        </label>
      ) : (
        <div className="field-label pitcher-search">
          Pitcher
          <input
            autoComplete="off"
            onChange={(event) => handleSearchChange(event.target.value)}
            onFocus={() => setIsDropdownOpen(true)}
            onBlur={() => setTimeout(() => setIsDropdownOpen(false), 150)}
            placeholder="Search by name, e.g. Cole"
            type="text"
            value={searchTerm}
          />
          {isDropdownOpen && debouncedTerm.trim().length >= 2 ? (
            <div className="pitcher-search__results" role="listbox">
              {searchQuery.isFetching ? (
                <p className="pitcher-search__status">Searching…</p>
              ) : searchQuery.error ? (
                <p className="pitcher-search__status">Pitcher search is unavailable right now.</p>
              ) : matches.length === 0 ? (
                <p className="pitcher-search__status">No matching MLB pitchers found.</p>
              ) : (
                matches.map((match) => (
                  <button
                    className="pitcher-search__option"
                    key={match.id}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => handleSelect(match)}
                    role="option"
                    type="button"
                  >
                    <PitcherAvatar name={match.name} playerId={match.id} size={28} />
                    <span className="pitcher-search__option-text">
                      <span>
                        {match.name}
                        {match.throws ? ` · ${match.throws}HP` : ""}
                      </span>
                      <small>
                        {match.team ?? "Team unknown"} · ID {match.id}
                      </small>
                    </span>
                  </button>
                ))
              )}
            </div>
          ) : null}
          {selectedPitcher ? (
            <p className="pitcher-search__selected">
              <PitcherAvatar name={selectedPitcher.name} playerId={selectedPitcher.id} size={24} />
              <span>
                Selected: {selectedPitcher.name}
                {selectedPitcher.team ? ` · ${selectedPitcher.team}` : ""}
                {selectedPitcher.throws ? ` · ${selectedPitcher.throws}HP` : ""} · ID {selectedPitcher.id}
              </span>
            </p>
          ) : null}
        </div>
      )}
      <button
        className="link-button"
        onClick={() => setShowManualEntry((value) => !value)}
        type="button"
      >
        {showManualEntry ? "Search by name instead" : "Enter pitcher ID manually"}
      </button>
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
      <p className="pregame-controls__hint">
        Pregame searches historical Statcast pitches in this date window. For a specific game outing, use{" "}
        <Link href="/player-watch">Player Watch</Link>.
      </p>
      <button className="primary-button" disabled={isGenerating} type="submit">
        <span aria-hidden="true" data-spinning={isGenerating}>
          ↻
        </span>
        {isGenerating ? "Generating…" : "Generate brief"}
      </button>
      <p className="control-status" aria-live="polite">
        {validationError ?? statusMessage ?? "Generate a brief for the selected pitcher and date window."}
      </p>
    </form>
  );
}
