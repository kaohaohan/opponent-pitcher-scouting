"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ComparisonNote } from "@/components/ComparisonNote";
import { DataState } from "@/components/DataState";
import { shiftDate, todayIso } from "@/components/DateNav";
import { PitchMixComparison } from "@/components/PitchMixComparison";
import { PitcherAvatar } from "@/components/PitcherAvatar";
import { RecentPitcherActivity } from "@/components/RecentPitcherActivity";
import { SignalsPanel } from "@/components/SignalsPanel";
import {
  toComparisonNote,
  toGameSummary,
  toPlayerWatchData,
  toPregameLiveComparison,
} from "@/lib/adapters";
import { useLiveMonitoring } from "@/lib/live-monitoring-provider";
import {
  useAlerts,
  useComparisonNote,
  useEvents,
  useGameSummary,
  usePregameLiveComparison,
  type ComparisonRequest,
} from "@/lib/queries";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "This could not be loaded.";
}

function analysisHref(gameId: number, pitcherId: number, name?: string | null): string {
  const base = `/player-watch/${gameId}/pitchers/${pitcherId}`;
  return name ? `${base}?name=${encodeURIComponent(name)}` : base;
}

function sameRequest(a: ComparisonRequest | null, b: ComparisonRequest): boolean {
  return (
    a !== null &&
    a.gameId === b.gameId &&
    a.pitcherId === b.pitcherId &&
    a.startDate === b.startDate &&
    a.endDate === b.endDate
  );
}

export interface PitcherAnalysisClientProps {
  gameId: number;
  pitcherId: number;
}

/**
 * The Pitcher Analysis view: a single pitcher's live outing vs. their
 * scouting baseline, the signals worth a glance, an on-demand AI note, and
 * today's plate-appearance log. Reached from Game Discovery's Live/
 * Upcoming/Final rows or the manual game entry — see `GameDiscovery.tsx`.
 */
export function PitcherAnalysisClient({ gameId, pitcherId }: PitcherAnalysisClientProps) {
  const searchParams = useSearchParams();
  const nameParam = searchParams.get("name");

  const { watchPitcher, stopMonitoring } = useLiveMonitoring();

  const summaryQuery = useGameSummary(gameId);
  const summary = summaryQuery.data ? toGameSummary(summaryQuery.data) : null;
  const summaryFailed =
    summaryQuery.isError || (summaryQuery.data === undefined && summaryQuery.fetchStatus === "paused");

  // Default baseline window: the day before the game, back 365 days.
  // Falls back to today until the game's own date has loaded, then
  // recomputes — harmless since the comparison result is cached per
  // (pitcher, window) on the backend. A custom window the user sets in
  // "Baseline settings" below always wins over this default.
  const gameDate = summary?.gameDate ?? todayIso();
  const defaultEndDate = shiftDate(gameDate, -1);
  const defaultStartDate = shiftDate(defaultEndDate, -365);
  const [customBaseline, setCustomBaseline] = useState<{ start: string; end: string } | null>(null);
  const startDate = customBaseline?.start ?? defaultStartDate;
  const endDate = customBaseline?.end ?? defaultEndDate;

  const comparisonRequest: ComparisonRequest = { gameId, pitcherId, startDate, endDate };
  const comparisonQuery = usePregameLiveComparison(comparisonRequest);
  const comparison = comparisonQuery.data ? toPregameLiveComparison(comparisonQuery.data) : null;

  // The scouting note is strictly on-demand: `noteRequest` only ever
  // changes inside `handleGenerateNote`, never as a side effect of the
  // baseline window or the 15s comparison poll, so nothing here can
  // trigger a Gemini call on its own.
  const [noteRequest, setNoteRequest] = useState<ComparisonRequest | null>(null);
  const [noteGeneratedAtPitches, setNoteGeneratedAtPitches] = useState<number | null>(null);
  const noteQuery = useComparisonNote(noteRequest);
  const note = noteQuery.data ? toComparisonNote(noteQuery.data) : null;

  const handleGenerateNote = () => {
    setNoteGeneratedAtPitches(comparison?.liveTotalPitches ?? 0);
    if (sameRequest(noteRequest, comparisonRequest)) {
      // Same window as last time — `useComparisonNote` would otherwise
      // just hand back its cached result, so force a fresh Gemini call.
      void noteQuery.refetch();
    } else {
      setNoteRequest(comparisonRequest);
    }
  };

  // Auto-monitor only while the game is live, and re-target whenever the
  // pitcher (or game) this view is looking at changes — e.g. via the
  // "Now pitching" switch banner below. Monitoring stops when this view
  // unmounts (see the footer note); the provider itself also stops it
  // once the game goes Final.
  useEffect(() => {
    if (summary?.state !== "live") return undefined;
    watchPitcher(gameId, pitcherId);
    return () => stopMonitoring();
  }, [gameId, pitcherId, summary?.state, watchPitcher, stopMonitoring]);

  const eventsQuery = useEvents(undefined, 200, true, String(gameId), undefined, pitcherId);
  const alertsQuery = useAlerts(200);
  const pitcherName = comparison?.pitcherName ?? nameParam ?? `Pitcher ${pitcherId}`;
  const playerWatch = useMemo(() => {
    if (!eventsQuery.data) return null;
    return toPlayerWatchData(
      { id: pitcherId, name: pitcherName, team: "—", role: "pitcher" },
      eventsQuery.data,
      alertsQuery.data ?? [],
      "pitcher",
    );
  }, [eventsQuery.data, alertsQuery.data, pitcherId, pitcherName]);

  // Compare against this pitcher's OWN team, not whoever is on the mound:
  // every half-inning the other team's pitcher takes the mound, which is not
  // a pitching change. The viewed pitcher's side is whichever team's
  // appearance list includes him; that list's last entry is his team's
  // current pitcher. Before he has appeared (side unknown) there's nothing
  // to report.
  const ownSide = summary
    ? (["away", "home"] as const).find((side) =>
        summary.pitchersUsed[side].some((pitcher) => pitcher.id === pitcherId),
      )
    : undefined;
  const ownTeamPitchers = ownSide ? summary!.pitchersUsed[ownSide] : [];
  const replacementPitcher = ownTeamPitchers[ownTeamPitchers.length - 1] ?? null;
  const showSwitchBanner =
    summary?.state === "live" && replacementPitcher !== null && replacementPitcher.id !== pitcherId;
  const currentPitcher = replacementPitcher;
  const showFinalTag = summary?.state === "final";

  return (
    <div className="pitcher-analysis">
      <Link className="pitcher-analysis__back" href="/player-watch">
        ← Back to Player Watch
      </Link>

      <section className="panel pitcher-analysis-header">
        <div className="pitcher-analysis-header__identity">
          <PitcherAvatar loading="eager" name={pitcherName} playerId={pitcherId} size={50} />
          <div>
            <p className="section-kicker">Tracked pitcher</p>
            <h1>{pitcherName}</h1>
            {summary ? (
              <p>
                {summary.awayTeam.name} @ {summary.homeTeam.name}
              </p>
            ) : null}
          </div>
        </div>
        <div className="pitcher-analysis-header__state">
          {summary?.state === "live" ? <span className="live-indicator">Live</span> : null}
          <span>{summary?.stateLabel ?? "Loading…"}</span>
        </div>
        <div className="pitcher-analysis-header__pitches">
          <span>Pitches</span>
          <strong>{comparison ? comparison.liveTotalPitches : "—"}</strong>
        </div>
      </section>

      {summaryFailed ? (
        <DataState kind="error" onRetry={() => void summaryQuery.refetch()}>
          {errorMessage(summaryQuery.error)}
        </DataState>
      ) : null}

      {showSwitchBanner ? (
        <div className="pitcher-switch-banner">
          <span>Replaced — now pitching: {currentPitcher!.name}</span>
          <Link
            className="secondary-button"
            href={analysisHref(gameId, currentPitcher!.id, currentPitcher!.name)}
          >
            Switch to {currentPitcher!.name}
          </Link>
        </div>
      ) : showFinalTag ? (
        <div className="pitcher-final-tag">Game final — full-game comparison</div>
      ) : null}

      <PitchMixComparison comparison={comparison} />

      <SignalsPanel comparison={comparison} />

      <ComparisonNote
        note={note}
        isLoading={noteQuery.isFetching}
        error={noteQuery.error ? errorMessage(noteQuery.error) : null}
        onGenerate={handleGenerateNote}
        generatedAtPitches={noteGeneratedAtPitches}
        currentLivePitches={comparison?.liveTotalPitches ?? 0}
      />

      <details className="baseline-settings">
        <summary>Baseline settings</summary>
        <form
          className="comparison-date-form"
          onSubmit={(event) => event.preventDefault()}
          aria-label="Baseline date range"
        >
          <label className="field-label">
            Baseline start
            <input
              type="date"
              value={startDate}
              onChange={(event) => setCustomBaseline({ start: event.target.value, end: endDate })}
            />
          </label>
          <label className="field-label">
            Baseline end
            <input
              type="date"
              value={endDate}
              onChange={(event) => setCustomBaseline({ start: startDate, end: event.target.value })}
            />
          </label>
          {customBaseline ? (
            <button
              className="secondary-button"
              type="button"
              onClick={() => setCustomBaseline(null)}
            >
              Reset to default
            </button>
          ) : null}
        </form>
      </details>

      {eventsQuery.isLoading ? (
        <DataState kind="loading">Loading today&apos;s plate appearances…</DataState>
      ) : eventsQuery.isError ? (
        <DataState kind="error" onRetry={() => void eventsQuery.refetch()}>
          {errorMessage(eventsQuery.error)}
        </DataState>
      ) : (
        <RecentPitcherActivity
          recentPlateAppearances={playerWatch?.recentPlateAppearances ?? []}
          triggeredRules={playerWatch?.triggeredRules ?? []}
        />
      )}

      <p className="pitcher-analysis__footer">
        Monitoring runs in this browser tab — closing it stops monitoring.
      </p>
    </div>
  );
}
