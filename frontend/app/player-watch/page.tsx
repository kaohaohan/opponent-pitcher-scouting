import type { Metadata } from "next";

import { AppShell } from "@/components/AppShell";
import { PlayerWatchPageClient } from "@/components/PlayerWatchPageClient";

export const metadata: Metadata = {
  title: "Live Pitcher Watch",
};

export default function PlayerWatchPage() {
  return (
    <AppShell
      active="player-watch"
      eyebrow="Live pitcher monitoring"
      title="Live Pitcher Watch"
      description="Monitor how the opposing pitcher is attacking hitters and compare live behavior with the pregame scouting baseline."
      meta={
        <>
          <span className="data-window-label">Source</span>
          <strong>MLB live data</strong>
        </>
      }
    >
      <PlayerWatchPageClient />
    </AppShell>
  );
}
