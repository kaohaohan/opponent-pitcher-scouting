"use client";

import { DataState } from "@/components/DataState";
import { PlayerWatch } from "@/components/PlayerWatch";
import { toPlayerWatchData } from "@/lib/adapters";
import { useAlerts, useEvents, usePlayers } from "@/lib/queries";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Player data could not be loaded.";
}

export function PlayerWatchPageClient() {
  const playersQuery = usePlayers();
  const player = playersQuery.data?.[0];
  const eventsQuery = useEvents(player?.id, 200, Boolean(player));
  const alertsQuery = useAlerts();

  if (playersQuery.isLoading || eventsQuery.isLoading || alertsQuery.isLoading) {
    return <DataState kind="loading">Loading recorded player data…</DataState>;
  }

  const error = playersQuery.error ?? eventsQuery.error ?? alertsQuery.error;
  const hasCachedData = Boolean(playersQuery.data || eventsQuery.data || alertsQuery.data);
  if (error && !hasCachedData) {
    return (
      <DataState kind="error" onRetry={() => void Promise.all([playersQuery.refetch(), eventsQuery.refetch(), alertsQuery.refetch()])}>
        {errorMessage(error)}
      </DataState>
    );
  }

  if (!player) {
    return <DataState>No tracked players have been recorded yet.</DataState>;
  }

  const view = toPlayerWatchData(player, eventsQuery.data ?? [], alertsQuery.data ?? []);
  if (!view) {
    return <DataState>No completed plate appearances are available for this player.</DataState>;
  }

  return <PlayerWatch player={view} />;
}
