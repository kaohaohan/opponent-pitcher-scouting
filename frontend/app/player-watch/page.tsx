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
      eyebrow="Live monitoring / Taiwanese hitters"
      title="Player Watch"
      description="Follow the latest completed plate appearances and watch-rule outcomes."
      meta={
        <>
          <span className="data-window-label">Source</span>
          <strong>Recorded API data</strong>
        </>
      }
    >
      <PlayerWatchPageClient />
    </AppShell>
  );
}
