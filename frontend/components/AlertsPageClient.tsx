"use client";

import { useState } from "react";

import { AlertsPanel, type RoleFilter } from "@/components/AlertsPanel";
import { DataState } from "@/components/DataState";
import { mergePitcherAlerts, toAlertData, toAlertsSummary, toPitchMixAlertData } from "@/lib/adapters";
import { useAlerts, useEvents, usePitchMixAlerts } from "@/lib/queries";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Alerts could not be loaded.";
}

export function AlertsPageClient() {
  const alertsQuery = useAlerts();
  const pitchMixAlertsQuery = usePitchMixAlerts();
  const eventsQuery = useEvents(undefined, 1000);
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("pitcher");

  if (alertsQuery.isLoading || pitchMixAlertsQuery.isLoading || eventsQuery.isLoading) {
    return <DataState kind="loading">Loading alert stream…</DataState>;
  }

  const error = alertsQuery.error ?? pitchMixAlertsQuery.error ?? eventsQuery.error;
  const hasCachedData = Boolean(alertsQuery.data || pitchMixAlertsQuery.data || eventsQuery.data);
  if (error && !hasCachedData) {
    return (
      <DataState kind="error" onRetry={() => void Promise.all([alertsQuery.refetch(), pitchMixAlertsQuery.refetch(), eventsQuery.refetch()])}>
        {errorMessage(error)}
      </DataState>
    );
  }

  const eventsById = new Map((eventsQuery.data ?? []).map((event) => [event.id, event]));
  const pitcherAlerts = (alertsQuery.data ?? [])
    .filter((alert) => alert.subject_role === "pitcher")
    .map((alert) => toAlertData(alert, eventsById));
  const mergedPitcherAlerts = mergePitcherAlerts(pitcherAlerts);
  const pitchMixAlerts = (pitchMixAlertsQuery.data ?? []).map(toPitchMixAlertData);
  const view =
    roleFilter === "pitcher"
      ? mergedPitcherAlerts
      : roleFilter === "pitch-mix"
        ? pitchMixAlerts
        : [...mergedPitcherAlerts, ...pitchMixAlerts].sort(
            (left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt),
          );

  return (
    <AlertsPanel
      alerts={view}
      summary={toAlertsSummary(view)}
      roleFilter={roleFilter}
      onRoleFilterChange={setRoleFilter}
    />
  );
}
