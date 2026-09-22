"use client";

import { useState } from "react";

import { AlertsPanel, type RoleFilter } from "@/components/AlertsPanel";
import { DataState } from "@/components/DataState";
import { toAlertData, toAlertsSummary } from "@/lib/adapters";
import { useAlerts, useEvents, usePlayers } from "@/lib/queries";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Alerts could not be loaded.";
}

export function AlertsPageClient() {
  const alertsQuery = useAlerts();
  const playersQuery = usePlayers();
  const eventsQuery = useEvents(undefined, 1000);
  // Pitcher-role alerts are the primary opponent-scouting signal; batter
  // alerts and the full stream remain one click away rather than deleted.
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("pitcher");

  if (alertsQuery.isLoading || playersQuery.isLoading || eventsQuery.isLoading) {
    return <DataState kind="loading">Loading alert stream…</DataState>;
  }

  const error = alertsQuery.error ?? playersQuery.error ?? eventsQuery.error;
  const hasCachedData = Boolean(alertsQuery.data || playersQuery.data || eventsQuery.data);
  if (error && !hasCachedData) {
    return (
      <DataState kind="error" onRetry={() => void Promise.all([alertsQuery.refetch(), playersQuery.refetch(), eventsQuery.refetch()])}>
        {errorMessage(error)}
      </DataState>
    );
  }

  const players = playersQuery.data ?? [];
  const alerts = alertsQuery.data ?? [];
  const filteredAlerts =
    roleFilter === "all" ? alerts : alerts.filter((alert) => alert.subject_role === roleFilter);
  const eventsById = new Map((eventsQuery.data ?? []).map((event) => [event.id, event]));
  const playersById = new Map(players.map((player) => [player.id, player]));
  const view = filteredAlerts.map((alert) => toAlertData(alert, playersById, eventsById));

  return (
    <AlertsPanel
      alerts={view}
      summary={toAlertsSummary(filteredAlerts, players)}
      roleFilter={roleFilter}
      onRoleFilterChange={setRoleFilter}
    />
  );
}
