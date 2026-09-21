import type { Metadata } from "next";

import { AppShell } from "@/components/AppShell";
import { PregameDashboard } from "@/components/PregameDashboard";
import {
  countTendencies,
  pitcherProfile,
  pitchMix,
  pregameBrief,
} from "@/data/mock-data";

export const metadata: Metadata = {
  title: "Pregame",
};

export default function PregamePage() {
  return (
    <AppShell
      active="pregame"
      eyebrow="Game preparation / Pitcher intelligence"
      title="Pregame"
      description="Review pitch usage, count-specific patterns, and evidence-aware briefing notes."
      meta={
        <>
          <span className="data-window-label">Data window</span>
          <strong>{pitcherProfile.dateRangeLabel}</strong>
        </>
      }
    >
      <PregameDashboard
        brief={pregameBrief}
        counts={countTendencies}
        pitcher={pitcherProfile}
        pitches={pitchMix}
      />
    </AppShell>
  );
}
