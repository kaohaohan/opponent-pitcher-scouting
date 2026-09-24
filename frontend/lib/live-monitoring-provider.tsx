"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";

import { syncLive, type LiveSyncReport } from "@/lib/api";

const STORAGE_KEY = "pw-live-monitoring-session-v1";
const SYNC_INTERVAL_MS = 20_000;

interface StoredSession {
  version: 1;
  gameId: number | null;
  selectedPitcherIds: number[];
}

function isIdArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every((item) => typeof item === "number" && Number.isFinite(item));
}

function readStoredSession(): StoredSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredSession> | null;
    if (!parsed || parsed.version !== 1) return null;
    const gameId =
      typeof parsed.gameId === "number" && Number.isInteger(parsed.gameId) && parsed.gameId > 0
        ? parsed.gameId
        : null;
    return {
      version: 1,
      gameId,
      selectedPitcherIds: isIdArray(parsed.selectedPitcherIds) ? parsed.selectedPitcherIds : [],
    };
  } catch {
    return null;
  }
}

function writeStoredSession(session: StoredSession) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Storage unavailable or full — session stays in-memory only for this tab.
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Live sync failed.";
}

interface LiveMonitoringContextValue {
  gameId: number | null;
  selectedPitcherIds: number[];
  isMonitoring: boolean;
  isSyncing: boolean;
  syncMessage: string;
  lastSyncTimestamp: string | null;
  lastSyncError: string | null;
  lastGameState: string | null;
  lastGameStatus: string | null;
  /** The backend-confirmed game id string, set once a sync has completed. */
  syncedGameId: string | null;
  /**
   * Load `gameId`, select only `pitcherId`, and start monitoring in one
   * step — the entry point the Pitcher Analysis view uses to auto-monitor
   * a live game, and to re-target when the user switches pitchers.
   * Overrides any monitoring already in progress for a different game or
   * pitcher.
   */
  watchPitcher: (gameId: number, pitcherId: number) => void;
  stopMonitoring: () => void;
}

const LiveMonitoringContext = createContext<LiveMonitoringContextValue | null>(null);

export function LiveMonitoringProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  // Initial state must match between server and client render (localStorage
  // isn't available during SSR), so restoration happens in an effect below
  // rather than in these initializers — otherwise React throws a hydration
  // mismatch on the first paint.
  const [gameId, setGameId] = useState<number | null>(null);
  const [selectedPitcherIds, setSelectedPitcherIds] = useState<number[]>([]);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState("Load a game to choose a pitcher.");
  const [lastSyncTimestamp, setLastSyncTimestamp] = useState<string | null>(null);
  const [lastSyncError, setLastSyncError] = useState<string | null>(null);
  const [lastGameState, setLastGameState] = useState<string | null>(null);
  const [lastGameStatus, setLastGameStatus] = useState<string | null>(null);
  const [syncedGameId, setSyncedGameId] = useState<string | null>(null);
  const [hasHydrated, setHasHydrated] = useState(false);

  const monitoringRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const restored = readStoredSession();
    if (restored?.gameId) {
      setGameId(restored.gameId);
      setSelectedPitcherIds(restored.selectedPitcherIds);
      setSyncMessage("Selections restored. Press Start monitoring to resume live sync.");
    }
    setHasHydrated(true);
  }, []);

  useEffect(() => {
    if (!hasHydrated) return;
    writeStoredSession({ version: 1, gameId, selectedPitcherIds });
  }, [hasHydrated, gameId, selectedPitcherIds]);

  useEffect(
    () => () => {
      monitoringRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );

  const runSync = useCallback(
    async (targetGameId: number, pitcherIds: number[]) => {
      setIsSyncing(true);
      try {
        const report: LiveSyncReport = await syncLive({
          game_id: targetGameId,
          pitcher_ids: pitcherIds,
        });
        setSyncedGameId(report.game_id);
        setLastGameState(report.game_state);
        setLastGameStatus(report.game_status);
        setLastSyncTimestamp(new Date().toISOString());
        setLastSyncError(null);
        setSyncMessage(
          `${report.game_status ?? report.game_state ?? "Snapshot"}: ${report.stored} new, ${report.duplicates} duplicate${report.duplicates === 1 ? "" : "s"}.`,
        );
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["players"] }),
          queryClient.invalidateQueries({ queryKey: ["events"] }),
          queryClient.invalidateQueries({ queryKey: ["alerts"] }),
          queryClient.invalidateQueries({ queryKey: ["pitch-mix-alerts"] }),
          queryClient.invalidateQueries({ queryKey: ["pregame-live-comparison"] }),
        ]);
        if (report.game_state === "Final") {
          monitoringRef.current = false;
          setIsMonitoring(false);
          setSyncMessage("Final game snapshot synced; monitoring stopped.");
        } else if (monitoringRef.current) {
          timerRef.current = setTimeout(
            () => void runSync(targetGameId, pitcherIds),
            SYNC_INTERVAL_MS,
          );
        }
      } catch (error) {
        const message = errorMessage(error);
        setLastSyncError(message);
        setSyncMessage(message);
        if (monitoringRef.current) {
          timerRef.current = setTimeout(
            () => void runSync(targetGameId, pitcherIds),
            SYNC_INTERVAL_MS,
          );
        }
      } finally {
        setIsSyncing(false);
      }
    },
    [queryClient],
  );

  // The only entry point into monitoring now that Player Watch goes
  // straight from game discovery to a single pitcher: load the game,
  // select just that pitcher, and start syncing — all in one call, using
  // explicit arguments rather than composing loadGame/togglePitcher/
  // startMonitoring, whose state updates wouldn't be visible to each
  // other until the next render. Safe to call again for a different
  // pitcher (or game) while already monitoring — it cancels the pending
  // sync timer and re-targets immediately.
  const watchPitcher = useCallback(
    (targetGameId: number, pitcherId: number) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      setGameId(targetGameId);
      setSelectedPitcherIds([pitcherId]);
      setSyncedGameId(null);
      setLastGameState(null);
      setLastGameStatus(null);
      setLastSyncError(null);
      setSyncMessage("Syncing MLB snapshot...");
      monitoringRef.current = true;
      setIsMonitoring(true);
      void runSync(targetGameId, [pitcherId]);
    },
    [runSync],
  );

  const stopMonitoring = useCallback(() => {
    monitoringRef.current = false;
    if (timerRef.current) clearTimeout(timerRef.current);
    setIsMonitoring(false);
    setSyncMessage("Monitoring stopped.");
  }, []);

  const value = useMemo<LiveMonitoringContextValue>(
    () => ({
      gameId,
      selectedPitcherIds,
      isMonitoring,
      isSyncing,
      syncMessage,
      lastSyncTimestamp,
      lastSyncError,
      lastGameState,
      lastGameStatus,
      syncedGameId,
      watchPitcher,
      stopMonitoring,
    }),
    [
      gameId,
      selectedPitcherIds,
      isMonitoring,
      isSyncing,
      syncMessage,
      lastSyncTimestamp,
      lastSyncError,
      lastGameState,
      lastGameStatus,
      syncedGameId,
      watchPitcher,
      stopMonitoring,
    ],
  );

  return <LiveMonitoringContext.Provider value={value}>{children}</LiveMonitoringContext.Provider>;
}

export function useLiveMonitoring(): LiveMonitoringContextValue {
  const context = useContext(LiveMonitoringContext);
  if (!context) {
    throw new Error("useLiveMonitoring must be used within a LiveMonitoringProvider");
  }
  return context;
}
