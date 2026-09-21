import type { Metadata } from "next";

import { AppShell } from "@/components/AppShell";
import { PlayerWatch } from "@/components/PlayerWatch";
import { playerWatch } from "@/data/mock-data";

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
          <span className="live-indicator">Live</span>
          <strong>1 active game</strong>
        </>
      }
    >
      <PlayerWatch player={playerWatch} />
    </AppShell>
  );
}
