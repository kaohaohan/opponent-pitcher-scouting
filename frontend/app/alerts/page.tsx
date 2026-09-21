import type { Metadata } from "next";

import { AlertsPanel } from "@/components/AlertsPanel";
import { AppShell } from "@/components/AppShell";
import { alertsSummary, recentAlerts } from "@/data/mock-data";

export const metadata: Metadata = {
  title: "Alerts",
};

export default function AlertsPage() {
  return (
    <AppShell
      active="alerts"
      eyebrow="Monitoring / Rule outcomes"
      title="Alerts"
      description="Recent events that matched active player-watch rules."
      meta={
        <>
          <span className="data-window-label">Last updated</span>
          <strong>2 minutes ago</strong>
        </>
      }
    >
      <AlertsPanel alerts={recentAlerts} summary={alertsSummary} />
    </AppShell>
  );
}
