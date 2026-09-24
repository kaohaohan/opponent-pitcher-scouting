"use client";

import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";

import {
  generateComparisonNote,
  generatePregameBrief,
  getAlerts,
  getEvents,
  getGameParticipants,
  getGameSummary,
  getPlayers,
  getPregameLiveComparison,
  getSchedule,
  searchPitchers,
  syncLive,
  type GameSummaryDto,
  type LiveSyncRequest,
  type PregameBriefRequest,
} from "@/lib/api";

export function usePlayers() {
  return useQuery({
    queryKey: ["players"],
    queryFn: getPlayers,
    staleTime: 5 * 60 * 1000,
  });
}

export function useEvents(
  playerId?: number,
  limit = 200,
  enabled = true,
  gameId?: string,
  batterId?: number,
  pitcherId?: number,
) {
  return useQuery({
    queryKey: [
      "events",
      playerId ?? "all",
      gameId ?? "all",
      batterId ?? "all",
      pitcherId ?? "all",
      limit,
    ],
    queryFn: () => getEvents(playerId, limit, gameId, batterId, pitcherId),
    enabled: enabled && (playerId === undefined || playerId > 0),
    staleTime: 10 * 1000,
    refetchInterval: 15 * 1000,
    refetchIntervalInBackground: false,
    retry: 1,
  });
}

export function useSchedule(date: string) {
  return useQuery({
    queryKey: ["mlb-schedule", date],
    queryFn: () => getSchedule(date),
    staleTime: 30 * 1000,
    retry: 1,
    // Switching dates changes the query key; keep showing the previous
    // date's games while the new one loads instead of flashing back to a
    // loading state (see `isPlaceholderData` in `GameDiscovery`).
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      query.state.data?.some((game) => game.state === "live") ? 30 * 1000 : false,
    refetchIntervalInBackground: false,
  });
}

export function useGameSummary(gameId: number | null, options?: { live?: boolean }) {
  const live = options?.live ?? true;
  return useQuery({
    queryKey: ["live-game-summary", gameId ?? "idle"],
    queryFn: () => getGameSummary(gameId as number),
    enabled: gameId !== null && gameId > 0,
    staleTime: 10 * 1000,
    retry: 1,
    refetchInterval: (query) =>
      live && (query.state.data as GameSummaryDto | undefined)?.state === "live"
        ? 15 * 1000
        : false,
    refetchIntervalInBackground: false,
  });
}

export function useGameParticipants(gameId: number | null) {
  return useQuery({
    queryKey: ["live-game-participants", gameId ?? "idle"],
    queryFn: () => getGameParticipants(gameId as number),
    enabled: gameId !== null && gameId > 0,
    staleTime: 10 * 1000,
    retry: false,
  });
}

export function useLiveSync() {
  return useMutation({ mutationFn: (request: LiveSyncRequest) => syncLive(request) });
}

export function useAlerts(limit = 200) {
  return useQuery({
    queryKey: ["alerts", limit],
    queryFn: () => getAlerts(limit),
    staleTime: 10 * 1000,
    refetchInterval: 15 * 1000,
    refetchIntervalInBackground: false,
    retry: 1,
  });
}

// Only fires once the user has typed enough to narrow MLB's people search;
// the query key includes the search term so React Query caches per-term.
export function usePitcherSearch(query: string) {
  const trimmed = query.trim();
  return useQuery({
    queryKey: ["pitcher-search", trimmed],
    queryFn: () => searchPitchers(trimmed),
    enabled: trimmed.length >= 2,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

export function usePregameBrief(request: PregameBriefRequest | null) {
  return useQuery({
    queryKey: request
      ? ["pregame-brief", request.pitcher_id, request.start_date, request.end_date]
      : ["pregame-brief", "idle"],
    queryFn: () => generatePregameBrief(request as PregameBriefRequest),
    enabled: request !== null,
    staleTime: 30 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export interface ComparisonRequest {
  gameId: number;
  pitcherId: number;
  startDate: string;
  endDate: string;
}

// Never calls Gemini — cheap to poll alongside the existing live
// events/alerts queries while Pitcher Watch is open.
export function usePregameLiveComparison(request: ComparisonRequest | null) {
  return useQuery({
    queryKey: request
      ? ["pregame-live-comparison", request.gameId, request.pitcherId, request.startDate, request.endDate]
      : ["pregame-live-comparison", "idle"],
    queryFn: () =>
      getPregameLiveComparison(
        (request as ComparisonRequest).gameId,
        (request as ComparisonRequest).pitcherId,
        (request as ComparisonRequest).startDate,
        (request as ComparisonRequest).endDate,
      ),
    enabled: request !== null,
    staleTime: 10 * 1000,
    // Switching pitcher/game or editing the baseline window changes the
    // query key; keep showing the previous comparison while the new one
    // loads instead of flashing back to a loading state.
    placeholderData: keepPreviousData,
    refetchInterval: 15 * 1000,
    refetchIntervalInBackground: false,
    retry: 1,
  });
}

// On-demand only, like `usePregameBrief` — a fresh AI note isn't needed
// every 15s, and each generation is a real Gemini call.
export function useComparisonNote(request: ComparisonRequest | null) {
  return useQuery({
    queryKey: request
      ? ["comparison-note", request.gameId, request.pitcherId, request.startDate, request.endDate]
      : ["comparison-note", "idle"],
    queryFn: () =>
      generateComparisonNote(
        (request as ComparisonRequest).gameId,
        (request as ComparisonRequest).pitcherId,
        (request as ComparisonRequest).startDate,
        (request as ComparisonRequest).endDate,
      ),
    enabled: request !== null,
    staleTime: 30 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
    retry: false,
    refetchOnWindowFocus: false,
  });
}
