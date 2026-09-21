import type { Metadata } from "next";

import { AppShell } from "@/components/AppShell";
import { AlertsPageClient } from "@/components/AlertsPageClient";

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
          <strong>Auto-refreshing</strong>
        </>
      }
    >
      <AlertsPageClient />
    </AppShell>
  );
}
