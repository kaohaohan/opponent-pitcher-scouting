import type { Metadata } from "next";

import { AppShell } from "@/components/AppShell";
import { PlayerWatchPageClient } from "@/components/PlayerWatchPageClient";

export const metadata: Metadata = {
  title: "Player Watch",
};

export default function PlayerWatchPage() {
  return (
    <AppShell
      active="player-watch"
      eyebrow="Live game discovery"
      title="Player Watch"
      description="See what's live right now, then drill into a pitcher to compare today's outing with their scouting baseline."
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
