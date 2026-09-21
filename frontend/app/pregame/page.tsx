import type { Metadata } from "next";

import { AppShell } from "@/components/AppShell";
import { PregamePageClient } from "@/components/PregamePageClient";

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
          <strong>Select below</strong>
        </>
      }
    >
      <PregamePageClient />
    </AppShell>
  );
}
