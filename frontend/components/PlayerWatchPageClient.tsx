"use client";

import { GameDiscovery } from "@/components/GameDiscovery";

/**
 * Player Watch home page. The flow is now: pick a date, see what's live
 * right now, drill into a pitcher's live-vs-baseline analysis. See
 * `GameDiscovery` for the Live Now / Upcoming / Final / manual-entry
 * sections themselves.
 */
export function PlayerWatchPageClient() {
  return <GameDiscovery />;
}
