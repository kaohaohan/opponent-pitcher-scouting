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
      eyebrow="Opponent scouting / Pitcher alerts"
      title="Alerts"
      description="Real-time alerts for how the opposing pitcher is performing against hitters."
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
