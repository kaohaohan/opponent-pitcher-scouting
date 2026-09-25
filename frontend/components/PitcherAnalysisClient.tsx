"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ComparisonNote } from "@/components/ComparisonNote";
import { ContactPitches } from "@/components/ContactPitches";
import { DataState } from "@/components/DataState";
import { shiftDate, todayIso } from "@/components/DateNav";
import { PitchMixComparison } from "@/components/PitchMixComparison";
import { PitchLocations } from "@/components/PitchLocations";
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
  useContactPitches,
  useEvents,
  useGameSummary,
  usePregameLiveComparison,
  usePitchLocations,
  type ComparisonRequest,
} from "@/lib/queries";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "This could not be loaded.";
}

function analysisHref(
  gameId: number,
  pitcherId: number,
  name?: string | null,
  date?: string | null,
): string {
  const base = `/player-watch/${gameId}/pitchers/${pitcherId}`;
  const params = new URLSearchParams();
  if (name) params.set("name", name);
  if (date) params.set("date", date);
  const query = params.toString();
  return query ? `${base}?${query}` : base;
}

const DATE_PARAM_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

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
  const rawDateParam = searchParams.get("date");
  // The caller (Game Discovery / Live cards) already knows the game's date
  // from the schedule it just fetched, so it passes it along in the URL —
  // that lets the comparison query start with the right baseline window
  // immediately, in parallel with the summary query, instead of waiting for
  // the summary to resolve `gameDate` first.
  const dateParam = rawDateParam && DATE_PARAM_PATTERN.test(rawDateParam) ? rawDateParam : null;

  const { watchPitcher, hasHydrated } = useLiveMonitoring();

  const summaryQuery = useGameSummary(gameId);
  const summary = summaryQuery.data ? toGameSummary(summaryQuery.data) : null;
  const summaryFailed =
    summaryQuery.isError || (summaryQuery.data === undefined && summaryQuery.fetchStatus === "paused");

  // Default baseline window: the day before the game, back 365 days. Prefers
  // the `date` URL param (known immediately) over `summary.gameDate` (only
  // known once the summary query resolves) over today, so the comparison
  // query below fires with the correct window from the first render whenever
  // the caller supplied a date. A custom window the user sets in "Baseline
  // settings" below always wins over this default.
  const gameDate = dateParam ?? summary?.gameDate ?? todayIso();
  const defaultEndDate = shiftDate(gameDate, -1);
  const defaultStartDate = shiftDate(defaultEndDate, -365);
  const [customBaseline, setCustomBaseline] = useState<{ start: string; end: string } | null>(null);
  const startDate = customBaseline?.start ?? defaultStartDate;
  const endDate = customBaseline?.end ?? defaultEndDate;

  const comparisonRequest: ComparisonRequest = { gameId, pitcherId, startDate, endDate };
  const comparisonQuery = usePregameLiveComparison(comparisonRequest);
  const locationsQuery = usePitchLocations(gameId, pitcherId);
  const contactPitchesQuery = useContactPitches(gameId, pitcherId);
  const comparison = comparisonQuery.data ? toPregameLiveComparison(comparisonQuery.data) : null;
  // `placeholderData: keepPreviousData` (see `usePregameLiveComparison`)
  // keeps the previous pitcher/window's result on screen while a changed
  // key (switching pitcher, editing the baseline, a resolved `date` param)
  // refetches, rather than dropping back to a loading state. This is the
  // only visible sign that a fresher comparison is on its way.
  const comparisonUpdating = comparisonQuery.isFetching && comparisonQuery.isPlaceholderData;

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

  // Start/retarget only after stored session state has been restored. The
  // root provider owns the loop, so unmounting this route does not stop it.
  useEffect(() => {
    if (!hasHydrated || summary?.state !== "live") return;
    watchPitcher(gameId, pitcherId);
  }, [gameId, hasHydrated, pitcherId, summary?.state, watchPitcher]);

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

  // Player Watch discovery follows the game's current pitcher, but this page
  // stays pinned to the selected pitcher. When the mound changes, show the
  // live context without changing the comparison target under the user's feet.
  const currentPitcher = summary?.currentPitcher ?? null;
  const showSwitchBanner =
    summary?.state === "live" && currentPitcher !== null && currentPitcher.id !== pitcherId;
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
          <span>
            {pitcherName} is no longer pitching. Now pitching: {currentPitcher!.name}
          </span>
          <Link
            className="secondary-button"
            href={analysisHref(gameId, currentPitcher!.id, currentPitcher!.name, summary?.gameDate)}
          >
            View current pitcher
          </Link>
        </div>
      ) : showFinalTag ? (
        <div className="pitcher-final-tag">Game final — full-game comparison</div>
      ) : null}

      <PitchMixComparison comparison={comparison} isUpdating={comparisonUpdating} />

      <PitchLocations
        locations={locationsQuery.data ?? null}
        isLoading={locationsQuery.isLoading}
        error={locationsQuery.isError ? errorMessage(locationsQuery.error) : null}
        onRetry={() => void locationsQuery.refetch()}
      />

      <ContactPitches
        contactPitches={contactPitchesQuery.data ?? null}
        isLoading={contactPitchesQuery.isLoading}
        error={contactPitchesQuery.isError ? errorMessage(contactPitchesQuery.error) : null}
        onRetry={() => void contactPitchesQuery.refetch()}
      />

      <SignalsPanel comparison={comparison} isUpdating={comparisonUpdating} />

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
        Monitoring continues while you move between pages in this tab. Closing it stops monitoring.
      </p>
    </div>
  );
}
