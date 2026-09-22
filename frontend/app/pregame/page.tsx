import type { Metadata } from "next";
import { Suspense } from "react";

import { AppShell } from "@/components/AppShell";
import { PregamePageClient } from "@/components/PregamePageClient";

export const metadata: Metadata = {
  title: "Opponent Pitcher Scouting",
};

export default function PregamePage() {
  return (
    <AppShell
      active="pregame"
      eyebrow="Opponent scouting / Pitcher intelligence"
      title="Opponent Pitcher Scouting"
      description="Review an opposing pitcher's arsenal, velocity, count tendencies, and scouting notes before the game."
    >
      <Suspense fallback={null}>
        <PregamePageClient />
      </Suspense>
    </AppShell>
  );
}
