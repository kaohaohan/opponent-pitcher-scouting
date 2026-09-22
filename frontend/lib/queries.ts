"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import {
  generatePregameBrief,
  getAlerts,
  getEvents,
  getGameParticipants,
  getPlayers,
  syncLive,
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
