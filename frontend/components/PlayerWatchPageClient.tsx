"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { DataState } from "@/components/DataState";
import { PitcherAvatar } from "@/components/PitcherAvatar";
import { PlayerWatch, type PitcherComparisonProps } from "@/components/PlayerWatch";
import {
  subjectFromParticipant,
  toComparisonNote,
  toPlayerWatchData,
  toPregameLiveComparison,
  type WatchSubject,
} from "@/lib/adapters";
import type { GameParticipantDto } from "@/lib/api";
import { useLiveMonitoring } from "@/lib/live-monitoring-provider";
import {
  useAlerts,
  useComparisonNote,
  useEvents,
  useGameParticipants,
  usePregameLiveComparison,
  type ComparisonRequest,
} from "@/lib/queries";

type WatchRole = "batter" | "pitcher";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Player data could not be loaded.";
}

function subjectKey(role: WatchRole, id: number): string {
  return `${role}:${id}`;
}

function parseSubjectKey(key: string): { role: WatchRole; id: number } | null {
  const [role, idStr] = key.split(":");
  const id = Number(idStr);
  if ((role !== "batter" && role !== "pitcher") || !Number.isInteger(id)) return null;
  return { role, id };
}

function groupByTeam(participants: GameParticipantDto[], role: WatchRole) {
  const grouped = new Map<string, GameParticipantDto[]>();
  for (const participant of participants) {
    if (!participant.roles.includes(role)) continue;
    const key = `${participant.team_side}:${participant.team_name}`;
    grouped.set(key, [...(grouped.get(key) ?? []), participant]);
  }
  return [...grouped.entries()].map(([key, players]) => ({
    key,
    teamName: players[0]?.team_name ?? "Team",
    players: players.sort((left, right) => left.name.localeCompare(right.name)),
  }));
}

export function PlayerWatchPageClient() {
  const monitoring = useLiveMonitoring();
  const [gameIdInput, setGameIdInput] = useState(monitoring.gameId ? String(monitoring.gameId) : "");
  const [gameIdError, setGameIdError] = useState<string | null>(null);

  // The provider restores a persisted game id from localStorage after mount
  // (to avoid an SSR hydration mismatch), so pick it up here once it arrives.
  useEffect(() => {
    if (monitoring.gameId !== null) {
      setGameIdInput((current) => (current ? current : String(monitoring.gameId)));
    }
  }, [monitoring.gameId]);
  // Pitcher is the primary demo workflow (opponent-pitcher scouting); batter
  // selection remains available but is no longer the default tab.
  const [activeRole, setActiveRole] = useState<WatchRole>("pitcher");
  const [viewingSubjectKey, setViewingSubjectKey] = useState<string>();
  const [baselineStartDate, setBaselineStartDate] = useState("");
  const [baselineEndDate, setBaselineEndDate] = useState("");
  const [noteRequest, setNoteRequest] = useState<ComparisonRequest | null>(null);
  const participantsQuery = useGameParticipants(monitoring.gameId);
  const alertsQuery = useAlerts();

  const { selectedBatterIds, selectedPitcherIds } = monitoring;
  const activeGameId = monitoring.syncedGameId ?? undefined;

  const participants = participantsQuery.data?.participants ?? [];
  const subjects = useMemo(() => {
    // Pitchers are listed first so the default detail subject (subjects[0])
    // favors the opponent-pitcher scouting workflow when one is watched.
    const byKey = new Map<string, WatchSubject>();
    for (const participant of participants) {
      if (selectedPitcherIds.includes(participant.player_id) && participant.roles.includes("pitcher")) {
        byKey.set(subjectKey("pitcher", participant.player_id), subjectFromParticipant(participant, "pitcher"));
      }
    }
    for (const participant of participants) {
      if (selectedBatterIds.includes(participant.player_id) && participant.roles.includes("batter")) {
        byKey.set(subjectKey("batter", participant.player_id), subjectFromParticipant(participant, "batter"));
      }
    }
    return [...byKey.entries()];
  }, [participants, selectedBatterIds, selectedPitcherIds]);

  // Only supplies a default (the first watched pitcher) when there is no
  // viewing subject at all — it must not reset just because the current
  // subject happens to be unwatched, since viewing an unwatched pitcher is
  // an intentional, allowed state (see `viewSubject`).
  useEffect(() => {
    if (viewingSubjectKey === undefined && subjects.length > 0) {
      setViewingSubjectKey(subjects[0]?.[0]);
    }
  }, [viewingSubjectKey, subjects]);

  // Resolved against the game's participants (not just the watchlist) so a
  // pitcher can be viewed before being added to monitoring; also guarantees
  // identity is always derived fresh from the current game's roster.
  const subject = useMemo(() => {
    if (!viewingSubjectKey) return undefined;
    const parsed = parseSubjectKey(viewingSubjectKey);
    if (!parsed) return undefined;
    const participant = participants.find(
      (item) => item.player_id === parsed.id && item.roles.includes(parsed.role),
    );
    return participant ? subjectFromParticipant(participant, parsed.role) : undefined;
  }, [participants, viewingSubjectKey]);

  const isSubjectWatched = subject
    ? (subject.role === "batter" ? selectedBatterIds : selectedPitcherIds).includes(subject.id)
    : false;

  const eventsQuery = useEvents(
    undefined,
    200,
    Boolean(subject && activeGameId && isSubjectWatched),
    activeGameId,
    subject?.role === "batter" ? subject.id : undefined,
    subject?.role === "pitcher" ? subject.id : undefined,
  );

  const comparisonRequest: ComparisonRequest | null =
    subject?.role === "pitcher" && isSubjectWatched && activeGameId && baselineStartDate && baselineEndDate
      ? {
          gameId: Number(activeGameId),
          pitcherId: subject.id,
          startDate: baselineStartDate,
          endDate: baselineEndDate,
        }
      : null;
  const comparisonQuery = usePregameLiveComparison(comparisonRequest);
  const noteQuery = useComparisonNote(noteRequest);

  const onGenerateNote = () => {
    if (!comparisonRequest) return;
    if (noteRequest && JSON.stringify(noteRequest) === JSON.stringify(comparisonRequest)) {
      void noteQuery.refetch();
      return;
    }
    setNoteRequest(comparisonRequest);
  };

  const pitcherComparison: PitcherComparisonProps | undefined =
    subject?.role === "pitcher"
      ? {
          comparison: comparisonQuery.data ? toPregameLiveComparison(comparisonQuery.data) : null,
          note: noteQuery.data ? toComparisonNote(noteQuery.data) : null,
          noteLoading: noteQuery.isFetching,
          noteError: noteQuery.error ? errorMessage(noteQuery.error) : null,
          onGenerateNote,
          startDate: baselineStartDate,
          endDate: baselineEndDate,
          onStartDateChange: setBaselineStartDate,
          onEndDateChange: setBaselineEndDate,
        }
      : undefined;

  // A stale viewing subject must never survive a game change — this reset
  // is load-bearing (not just defense-in-depth) because the auto-pick effect
  // above intentionally no longer clears on "current subject is unwatched."
  useEffect(() => {
    setViewingSubjectKey(undefined);
  }, [monitoring.gameId]);

  const loadGame = () => {
    const gameId = Number(gameIdInput.trim());
    if (!Number.isInteger(gameId) || gameId <= 0) {
      setGameIdError("Use a positive MLB game ID.");
      return;
    }
    setGameIdError(null);
    monitoring.loadGame(gameId);
  };

  const toggleSelection = (role: WatchRole, id: number) => {
    const wasChecked = role === "batter" ? selectedBatterIds.includes(id) : selectedPitcherIds.includes(id);
    if (role === "batter") monitoring.toggleBatter(id);
    else monitoring.togglePitcher(id);
    if (wasChecked && viewingSubjectKey === subjectKey(role, id)) {
      setViewingSubjectKey(undefined);
    }
  };

  const viewSubject = (role: WatchRole, id: number) => {
    setViewingSubjectKey(subjectKey(role, id));
  };

  const watchlistSummary = (() => {
    const pitcherCount = selectedPitcherIds.length;
    const batterCount = selectedBatterIds.length;
    if (pitcherCount === 0 && batterCount === 0) return null;
    const parts = [
      pitcherCount > 0 ? `${pitcherCount} pitcher${pitcherCount === 1 ? "" : "s"}` : null,
      batterCount > 0 ? `${batterCount} batter${batterCount === 1 ? "" : "s"}` : null,
    ].filter(Boolean);
    return `Watching ${parts.join(" · ")}`;
  })();

  const discoveryStatus = participantsQuery.isLoading ? (
    <DataState kind="loading">Loading game participants...</DataState>
  ) : participantsQuery.error ? (
    <DataState kind="error" onRetry={() => void participantsQuery.refetch()}>
      {errorMessage(participantsQuery.error)}
    </DataState>
  ) : monitoring.gameId !== null && participants.length === 0 ? (
    <DataState>No announced or observed participants are available yet.</DataState>
  ) : null;

  const controls = (
    <section className="panel live-controls" aria-labelledby="live-controls-title">
      <div className="panel-heading">
        <div><p className="section-kicker">MLB live feed</p><h2 id="live-controls-title">Monitor a game</h2></div>
        <span className={monitoring.isMonitoring ? "live-control-status is-active" : "live-control-status"}>{monitoring.isMonitoring ? "Monitoring" : "Stopped"}</span>
      </div>
      <div className="live-controls__grid">
        <label className="field-label">Game ID<input value={gameIdInput} onChange={(event) => setGameIdInput(event.target.value)} placeholder="776743" inputMode="numeric" disabled={monitoring.isMonitoring} /></label>
        <button className="secondary-button" type="button" onClick={loadGame} disabled={monitoring.isMonitoring || participantsQuery.isFetching}>Load game</button>
        <button className="primary-button" type="button" onClick={monitoring.isMonitoring ? monitoring.stopMonitoring : monitoring.startMonitoring}>{monitoring.isMonitoring ? "Stop monitoring" : "Start monitoring"}</button>
      </div>
      {participantsQuery.data ? (
        <div className="game-discovery-summary">
          <strong>{participantsQuery.data.teams.away.name} at {participantsQuery.data.teams.home.name}</strong>
          <span>{participantsQuery.data.game_status ?? participantsQuery.data.game_state ?? "Game loaded"}</span>
        </div>
      ) : null}
      <div className="role-tabs" role="tablist" aria-label="Watch role">
        {(["pitcher", "batter"] as const).map((role) => (
          <button key={role} type="button" className={activeRole === role ? "is-active" : ""} onClick={() => setActiveRole(role)}>
            {role === "pitcher" ? "Pitchers" : "Batters"}
          </button>
        ))}
      </div>
      {watchlistSummary ? <p className="watchlist-summary">{watchlistSummary}</p> : null}
      {discoveryStatus}
      {participants.length > 0 ? (
        <div className="participant-groups">
          {groupByTeam(participants, activeRole).map((group) => (
            <div className="participant-group" key={group.key}>
              <h3>{group.teamName}</h3>
              <div className="participant-list">
                {group.players.map((participant) => {
                  const checked = activeRole === "batter"
                    ? selectedBatterIds.includes(participant.player_id)
                    : selectedPitcherIds.includes(participant.player_id);
                  const key = subjectKey(activeRole, participant.player_id);
                  const isViewing = key === viewingSubjectKey;
                  return (
                    <div
                      className={isViewing ? "participant-option is-active" : "participant-option"}
                      key={`${activeRole}-${participant.player_id}`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={monitoring.isMonitoring}
                        aria-label={`Watch ${participant.name}`}
                        onChange={() => toggleSelection(activeRole, participant.player_id)}
                      />
                      <button
                        type="button"
                        className="participant-option__name"
                        onClick={() => viewSubject(activeRole, participant.player_id)}
                      >
                        {participant.name}
                        {isViewing ? <span className="participant-option__badge">Viewing</span> : null}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      ) : null}
      {gameIdError ? <p className="control-status is-error">{gameIdError}</p> : null}
      <p className="control-status">
        {monitoring.syncMessage} Updates run about every 20 seconds while monitoring is active, even while you browse Alerts or Pregame.
      </p>
    </section>
  );

  if (alertsQuery.isLoading || eventsQuery.isLoading) {
    return <>{controls}<DataState kind="loading">Loading live pitcher data...</DataState></>;
  }
  const error = alertsQuery.error ?? eventsQuery.error;
  const hasCachedData = Boolean(alertsQuery.data || eventsQuery.data);
  if (error && !hasCachedData) {
    return <>{controls}<DataState kind="error" onRetry={() => void Promise.all([alertsQuery.refetch(), eventsQuery.refetch()])}>{errorMessage(error)}</DataState></>;
  }
  if (!subject) return <>{controls}<DataState>Choose a batter or pitcher to monitor.</DataState></>;

  const pregameHandoffHref =
    subject.role === "pitcher"
      ? `/pregame?pitcherId=${subject.id}&pitcherName=${encodeURIComponent(subject.name)}${
          subject.team ? `&pitcherTeam=${encodeURIComponent(subject.team)}` : ""
        }`
      : null;
  const pregameHandoffLink = pregameHandoffHref ? (
    <Link className="secondary-button" href={pregameHandoffHref}>
      Use {subject.name} in Pregame
    </Link>
  ) : null;
  const subjectSelector =
    subjects.length > 1 ? (
      <label className="player-selector">
        {subject?.role === "batter" ? "Viewing batter" : "Viewing pitcher"}
        <select value={viewingSubjectKey} onChange={(event) => setViewingSubjectKey(event.target.value)}>
          {subjects.map(([key, item]) => (
            <option key={key} value={key}>
              {item.name} · {item.role}
            </option>
          ))}
        </select>
      </label>
    ) : null;

  const view = toPlayerWatchData(subject, eventsQuery.data ?? [], alertsQuery.data ?? [], subject.role);
  if (!view) {
    // Before first pitch there's no event-derived PlayerWatchData (and so no
    // PlayerWatch hero) yet, but the pitcher is already known from game
    // participant discovery — show identity immediately instead of waiting
    // on synced events. A viewed-but-unwatched pitcher also lands here
    // (their events are never synced), with an explicit opt-in to monitor.
    const addToMonitoringButton = !isSubjectWatched ? (
      <button
        className="secondary-button"
        type="button"
        disabled={monitoring.isMonitoring}
        onClick={() => toggleSelection(subject.role, subject.id)}
      >
        Add to monitoring
      </button>
    ) : null;
    const viewingIdentity =
      subject.role === "pitcher" ? (
        <div className="selected-pitcher-identity">
          <PitcherAvatar name={subject.name} playerId={subject.id} size={44} />
          <div>
            <p className="section-kicker">Viewing pitcher</p>
            <strong>{subject.name}</strong>
            {subject.team ? <span>{subject.team}</span> : null}
          </div>
          {addToMonitoringButton}
        </div>
      ) : null;
    return (
      <>
        {controls}
        {subjectSelector}
        {viewingIdentity}
        {pregameHandoffLink}
        {subject.role === "batter" ? addToMonitoringButton : null}
        <DataState>
          {isSubjectWatched
            ? "No completed plate appearances are available for this selection."
            : "This player isn't being monitored yet. Add them to the watchlist to see live data."}
        </DataState>
      </>
    );
  }

  return <>
    {controls}
    {subjectSelector}
    {pregameHandoffLink}
    <PlayerWatch player={view} pitcherComparison={pitcherComparison} />
  </>;
}
