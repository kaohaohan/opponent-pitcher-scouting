"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { DataState } from "@/components/DataState";
import { PlayerWatch } from "@/components/PlayerWatch";
import { toPlayerWatchData } from "@/lib/adapters";
import { useAlerts, useEvents, useLiveSync, usePlayers } from "@/lib/queries";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Player data could not be loaded.";
}

export function PlayerWatchPageClient() {
  const queryClient = useQueryClient();
  const playersQuery = usePlayers();
  const [gameIdInput, setGameIdInput] = useState("");
  const [watchedIdsInput, setWatchedIdsInput] = useState("");
  const [selectedPlayerId, setSelectedPlayerId] = useState<number>();
  const [activeGameId, setActiveGameId] = useState<string>();
  const [monitoring, setMonitoring] = useState(false);
  const [syncMessage, setSyncMessage] = useState("Enter an MLB game ID and player IDs to monitor.");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const monitoringRef = useRef(false);
  const syncLiveMutation = useLiveSync();
  const player = playersQuery.data?.find((item) => item.id === selectedPlayerId) ?? playersQuery.data?.[0];
  const eventsQuery = useEvents(player?.id, 200, Boolean(player), activeGameId);
  const alertsQuery = useAlerts();

  const runSync = async (gameId: number, watchedPlayerIds: number[], keepMonitoring: boolean) => {
    try {
      const report = await syncLiveMutation.mutateAsync({ game_id: gameId, watched_player_ids: watchedPlayerIds });
      setActiveGameId(report.game_id);
      setSyncMessage(`${report.game_status ?? report.game_state ?? "Snapshot"}: ${report.stored} new, ${report.duplicates} duplicate${report.duplicates === 1 ? "" : "s"}.`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["players"] }),
        queryClient.invalidateQueries({ queryKey: ["events"] }),
        queryClient.invalidateQueries({ queryKey: ["alerts"] }),
      ]);
      if (keepMonitoring && monitoringRef.current && report.game_state !== "Final") {
        timerRef.current = setTimeout(() => void runSync(gameId, watchedPlayerIds, true), 20_000);
      } else if (report.game_state === "Final") {
        monitoringRef.current = false;
        setMonitoring(false);
        setSyncMessage("Final game snapshot synced; monitoring stopped.");
      }
    } catch (error) {
      setSyncMessage(errorMessage(error));
      if (keepMonitoring && monitoringRef.current) {
        timerRef.current = setTimeout(() => void runSync(gameId, watchedPlayerIds, true), 20_000);
      }
    }
  };

  useEffect(() => () => {
    monitoringRef.current = false;
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  const toggleMonitoring = () => {
    if (monitoring) {
      monitoringRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
      setMonitoring(false);
      setSyncMessage("Monitoring stopped.");
      return;
    }
    const gameId = Number(gameIdInput.trim());
    const watchedTokens = watchedIdsInput.split(",").map((value) => value.trim()).filter((value) => value.length > 0);
    const watchedPlayerIds = watchedTokens.map((value) => Number(value));
    if (!Number.isInteger(gameId) || gameId <= 0 || watchedPlayerIds.length === 0 || watchedPlayerIds.some((id) => !Number.isInteger(id) || id <= 0)) {
      setSyncMessage("Use a positive MLB game ID and one or more positive player IDs.");
      return;
    }
    monitoringRef.current = true;
    setMonitoring(true);
    setSyncMessage("Syncing MLB snapshot…");
    void runSync(gameId, [...new Set(watchedPlayerIds)], true);
  };

  const controls = (
    <section className="panel live-controls" aria-labelledby="live-controls-title">
      <div className="panel-heading">
        <div><p className="section-kicker">MLB live feed</p><h2 id="live-controls-title">Monitor a game</h2></div>
        <span className={monitoring ? "live-control-status is-active" : "live-control-status"}>{monitoring ? "Monitoring" : "Stopped"}</span>
      </div>
      <div className="live-controls__grid">
        <label className="field-label">Game ID<input value={gameIdInput} onChange={(event) => setGameIdInput(event.target.value)} placeholder="776743" inputMode="numeric" /></label>
        <label className="field-label">MLB player IDs<input value={watchedIdsInput} onChange={(event) => setWatchedIdsInput(event.target.value)} placeholder="657557, 607208" inputMode="numeric" /></label>
        <button className="primary-button" type="button" onClick={toggleMonitoring}>{monitoring ? "Stop monitoring" : "Start monitoring"}</button>
      </div>
      <p className="control-status">{syncMessage} Updates run about every 20 seconds while this page is open.</p>
    </section>
  );

  if (playersQuery.isLoading || eventsQuery.isLoading || alertsQuery.isLoading) {
    return <>{controls}<DataState kind="loading">Loading recorded player data…</DataState></>;
  }
  const error = playersQuery.error ?? eventsQuery.error ?? alertsQuery.error;
  const hasCachedData = Boolean(playersQuery.data || eventsQuery.data || alertsQuery.data);
  if (error && !hasCachedData) {
    return <>{controls}<DataState kind="error" onRetry={() => void Promise.all([playersQuery.refetch(), eventsQuery.refetch(), alertsQuery.refetch()])}>{errorMessage(error)}</DataState></>;
  }
  if (!player) return <>{controls}<DataState>No tracked players have been recorded yet.</DataState></>;

  const view = toPlayerWatchData(player, eventsQuery.data ?? [], alertsQuery.data ?? []);
  if (!view) return <>{controls}<DataState>No completed plate appearances are available for this player.</DataState></>;

  return <>
    {controls}
    <label className="player-selector">Stored player<select value={player.id} onChange={(event) => setSelectedPlayerId(Number(event.target.value))}>{playersQuery.data?.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.team}</option>)}</select></label>
    <PlayerWatch player={view} />
  </>;
}
