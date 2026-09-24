import type { Metadata } from "next";

import { AppShell } from "@/components/AppShell";
import { PitcherAnalysisClient } from "@/components/PitcherAnalysisClient";

export const metadata: Metadata = {
  title: "Pitcher Analysis",
};

interface PitcherAnalysisPageProps {
  params: Promise<{ gameId: string; pitcherId: string }>;
}

export default async function PitcherAnalysisPage({ params }: PitcherAnalysisPageProps) {
  const { gameId: gameIdParam, pitcherId: pitcherIdParam } = await params;
  const gameId = Number(gameIdParam);
  const pitcherId = Number(pitcherIdParam);
  const isValid =
    Number.isInteger(gameId) && gameId > 0 && Number.isInteger(pitcherId) && pitcherId > 0;

  return (
    <AppShell
      active="player-watch"
      eyebrow="Live pitcher monitoring"
      title="Pitcher Analysis"
      description="Today's outing vs. this pitcher's scouting baseline, with signals worth a second look."
    >
      {isValid ? (
        <PitcherAnalysisClient gameId={gameId} pitcherId={pitcherId} />
      ) : (
        <p className="control-status is-error">Invalid game or pitcher id in the URL.</p>
      )}
    </AppShell>
  );
}
