"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { DataState } from "@/components/DataState";
import { PlayerWatch, type PitcherComparisonProps } from "@/components/PlayerWatch";
import {
  subjectFromParticipant,
  toComparisonNote,
  toPlayerWatchData,
  toPregameLiveComparison,
  type WatchSubject,
} from "@/lib/adapters";
import type { GameParticipantDto } from "@/lib/api";
import {
  useAlerts,
  useComparisonNote,
  useEvents,
  useGameParticipants,
  useLiveSync,
  usePregameLiveComparison,
  type ComparisonRequest,
} from "@/lib/queries";

type WatchRole = "batter" | "pitcher";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Player data could not be loaded.";
}

function unique(values: number[]): number[] {
  return [...new Set(values)];
}

function subjectKey(role: WatchRole, id: number): string {
  return `${role}:${id}`;
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
  const queryClient = useQueryClient();
  const [gameIdInput, setGameIdInput] = useState("");
  const [loadedGameId, setLoadedGameId] = useState<number | null>(null);
  const [activeGameId, setActiveGameId] = useState<string>();
  const [activeRole, setActiveRole] = useState<WatchRole>("batter");
  const [selectedBatterIds, setSelectedBatterIds] = useState<number[]>([]);
  const [selectedPitcherIds, setSelectedPitcherIds] = useState<number[]>([]);
  const [selectedSubject, setSelectedSubject] = useState<string>();
  const [monitoring, setMonitoring] = useState(false);
  const [syncMessage, setSyncMessage] = useState("Load a game to choose batters and pitchers.");
  const [baselineStartDate, setBaselineStartDate] = useState("");
  const [baselineEndDate, setBaselineEndDate] = useState("");
  const [noteRequest, setNoteRequest] = useState<ComparisonRequest | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const monitoringRef = useRef(false);
  const syncLiveMutation = useLiveSync();
  const participantsQuery = useGameParticipants(loadedGameId);
  const alertsQuery = useAlerts();

  const participants = participantsQuery.data?.participants ?? [];
  const subjects = useMemo(() => {
    const byKey = new Map<string, WatchSubject>();
    for (const participant of participants) {
      if (selectedBatterIds.includes(participant.player_id) && participant.roles.includes("batter")) {
        byKey.set(subjectKey("batter", participant.player_id), subjectFromParticipant(participant, "batter"));
      }
      if (selectedPitcherIds.includes(participant.player_id) && participant.roles.includes("pitcher")) {
        byKey.set(subjectKey("pitcher", participant.player_id), subjectFromParticipant(participant, "pitcher"));
      }
    }
    return [...byKey.entries()];
  }, [participants, selectedBatterIds, selectedPitcherIds]);

  useEffect(() => {
    if (!selectedSubject || !subjects.some(([key]) => key === selectedSubject)) {
      setSelectedSubject(subjects[0]?.[0]);
    }
  }, [selectedSubject, subjects]);

  const subject = subjects.find(([key]) => key === selectedSubject)?.[1];
  const eventsQuery = useEvents(
    undefined,
    200,
    Boolean(subject && activeGameId),
    activeGameId,
    subject?.role === "batter" ? subject.id : undefined,
    subject?.role === "pitcher" ? subject.id : undefined,
  );

  const comparisonRequest: ComparisonRequest | null =
    subject?.role === "pitcher" && activeGameId && baselineStartDate && baselineEndDate
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

  const runSync = async (
    gameId: number,
    batterIds: number[],
    pitcherIds: number[],
    keepMonitoring: boolean,
  ) => {
    try {
      const report = await syncLiveMutation.mutateAsync({
        game_id: gameId,
        batter_ids: batterIds,
        pitcher_ids: pitcherIds,
      });
      setActiveGameId(report.game_id);
      setSyncMessage(`${report.game_status ?? report.game_state ?? "Snapshot"}: ${report.stored} new, ${report.duplicates} duplicate${report.duplicates === 1 ? "" : "s"}.`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["players"] }),
        queryClient.invalidateQueries({ queryKey: ["events"] }),
        queryClient.invalidateQueries({ queryKey: ["alerts"] }),
      ]);
      if (keepMonitoring && monitoringRef.current && report.game_state !== "Final") {
        timerRef.current = setTimeout(() => void runSync(gameId, batterIds, pitcherIds, true), 20_000);
      } else if (report.game_state === "Final") {
        monitoringRef.current = false;
        setMonitoring(false);
        setSyncMessage("Final game snapshot synced; monitoring stopped.");
      }
    } catch (error) {
      setSyncMessage(errorMessage(error));
      if (keepMonitoring && monitoringRef.current) {
        timerRef.current = setTimeout(() => void runSync(gameId, batterIds, pitcherIds, true), 20_000);
      }
    }
  };

  useEffect(() => () => {
    monitoringRef.current = false;
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  const loadGame = () => {
    const gameId = Number(gameIdInput.trim());
    if (!Number.isInteger(gameId) || gameId <= 0) {
      setSyncMessage("Use a positive MLB game ID.");
      return;
    }
    setLoadedGameId(gameId);
    setActiveGameId(undefined);
    setSelectedBatterIds([]);
    setSelectedPitcherIds([]);
    setSelectedSubject(undefined);
    setSyncMessage("Loading game participants...");
  };

  const toggleSelection = (role: WatchRole, id: number) => {
    const update = (values: number[]) =>
      values.includes(id) ? values.filter((value) => value !== id) : [...values, id];
    if (role === "batter") setSelectedBatterIds(update);
    else setSelectedPitcherIds(update);
  };

  const toggleMonitoring = () => {
    if (monitoring) {
      monitoringRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
      setMonitoring(false);
      setSyncMessage("Monitoring stopped.");
      return;
    }
    if (loadedGameId === null || selectedBatterIds.length + selectedPitcherIds.length === 0) {
      setSyncMessage("Choose at least one batter or pitcher before monitoring.");
      return;
    }
    const batterIds = unique(selectedBatterIds);
    const pitcherIds = unique(selectedPitcherIds);
    monitoringRef.current = true;
    setMonitoring(true);
    setSyncMessage("Syncing MLB snapshot...");
    void runSync(loadedGameId, batterIds, pitcherIds, true);
  };

  const discoveryStatus = participantsQuery.isLoading ? (
    <DataState kind="loading">Loading game participants...</DataState>
  ) : participantsQuery.error ? (
    <DataState kind="error" onRetry={() => void participantsQuery.refetch()}>
      {errorMessage(participantsQuery.error)}
    </DataState>
  ) : loadedGameId !== null && participants.length === 0 ? (
    <DataState>No announced or observed participants are available yet.</DataState>
  ) : null;

  const controls = (
    <section className="panel live-controls" aria-labelledby="live-controls-title">
      <div className="panel-heading">
        <div><p className="section-kicker">MLB live feed</p><h2 id="live-controls-title">Monitor a game</h2></div>
        <span className={monitoring ? "live-control-status is-active" : "live-control-status"}>{monitoring ? "Monitoring" : "Stopped"}</span>
      </div>
      <div className="live-controls__grid">
        <label className="field-label">Game ID<input value={gameIdInput} onChange={(event) => setGameIdInput(event.target.value)} placeholder="776743" inputMode="numeric" disabled={monitoring} /></label>
        <button className="secondary-button" type="button" onClick={loadGame} disabled={monitoring || participantsQuery.isFetching}>Load game</button>
        <button className="primary-button" type="button" onClick={toggleMonitoring}>{monitoring ? "Stop monitoring" : "Start monitoring"}</button>
      </div>
      {participantsQuery.data ? (
        <div className="game-discovery-summary">
          <strong>{participantsQuery.data.teams.away.name} at {participantsQuery.data.teams.home.name}</strong>
          <span>{participantsQuery.data.game_status ?? participantsQuery.data.game_state ?? "Game loaded"}</span>
        </div>
      ) : null}
      <div className="role-tabs" role="tablist" aria-label="Watch role">
        {(["batter", "pitcher"] as const).map((role) => (
          <button key={role} type="button" className={activeRole === role ? "is-active" : ""} onClick={() => setActiveRole(role)}>
            {role === "batter" ? "Batters" : "Pitchers"}
          </button>
        ))}
      </div>
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
                  return (
                    <label className="participant-option" key={`${activeRole}-${participant.player_id}`}>
                      <input type="checkbox" checked={checked} disabled={monitoring} onChange={() => toggleSelection(activeRole, participant.player_id)} />
                      <span>{participant.name}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      ) : null}
      <p className="control-status">{syncMessage} Updates run about every 20 seconds while this page is open.</p>
    </section>
  );

  if (alertsQuery.isLoading || eventsQuery.isLoading) {
    return <>{controls}<DataState kind="loading">Loading recorded player data...</DataState></>;
  }
  const error = alertsQuery.error ?? eventsQuery.error;
  const hasCachedData = Boolean(alertsQuery.data || eventsQuery.data);
  if (error && !hasCachedData) {
    return <>{controls}<DataState kind="error" onRetry={() => void Promise.all([alertsQuery.refetch(), eventsQuery.refetch()])}>{errorMessage(error)}</DataState></>;
  }
  if (!subject) return <>{controls}<DataState>Choose a batter or pitcher to monitor.</DataState></>;

  const view = toPlayerWatchData(subject, eventsQuery.data ?? [], alertsQuery.data ?? [], subject.role);
  if (!view) return <>{controls}<DataState>No completed plate appearances are available for this selection.</DataState></>;

  return <>
    {controls}
    {subjects.length > 1 ? (
      <label className="player-selector">Detail subject<select value={selectedSubject} onChange={(event) => setSelectedSubject(event.target.value)}>{subjects.map(([key, item]) => <option key={key} value={key}>{item.name} · {item.role}</option>)}</select></label>
    ) : null}
    <PlayerWatch player={view} pitcherComparison={pitcherComparison} />
  </>;
}
