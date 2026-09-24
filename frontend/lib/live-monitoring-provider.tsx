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
import Link from "next/link";

import { syncLive, type LiveSyncReport } from "@/lib/api";
import { useAlerts, usePitchMixAlerts } from "@/lib/queries";

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
  hasHydrated: boolean;
  canResume: boolean;
  monitoringStartedAt: number | null;
  /**
   * Load `gameId`, select only `pitcherId`, and start monitoring in one
   * step — the entry point the Pitcher Analysis view uses to auto-monitor
   * a live game, and to re-target when the user switches pitchers.
   * Overrides any monitoring already in progress for a different game or
   * pitcher.
   */
  watchPitcher: (gameId: number, pitcherId: number) => void;
  stopMonitoring: () => void;
  resumeMonitoring: () => void;
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
  const [requiresManualResume, setRequiresManualResume] = useState(false);
  const [monitoringStartedAt, setMonitoringStartedAt] = useState<number | null>(null);

  const monitoringRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generationRef = useRef(0);

  useEffect(() => {
    const restored = readStoredSession();
    if (restored?.gameId) {
      setGameId(restored.gameId);
      setSelectedPitcherIds(restored.selectedPitcherIds);
      setRequiresManualResume(true);
      setSyncMessage("Selections restored. Resume monitoring when ready.");
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
      generationRef.current += 1;
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );

  const runSync = useCallback(
    async (targetGameId: number, pitcherIds: number[], generation: number) => {
      if (generation !== generationRef.current) return;
      setIsSyncing(true);
      try {
        const report: LiveSyncReport = await syncLive({
          game_id: targetGameId,
          pitcher_ids: pitcherIds,
        });
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["players"] }),
          queryClient.invalidateQueries({ queryKey: ["events"] }),
          queryClient.invalidateQueries({ queryKey: ["alerts"] }),
          queryClient.invalidateQueries({ queryKey: ["pitch-mix-alerts"] }),
          queryClient.invalidateQueries({ queryKey: ["pregame-live-comparison"] }),
        ]);
        if (generation !== generationRef.current) return;
        setSyncedGameId(report.game_id);
        setLastGameState(report.game_state);
        setLastGameStatus(report.game_status);
        setLastSyncTimestamp(new Date().toISOString());
        setLastSyncError(null);
        setSyncMessage(
          `${report.game_status ?? report.game_state ?? "Snapshot"}: ${report.stored} new, ${report.duplicates} duplicate${report.duplicates === 1 ? "" : "s"}.`,
        );
        if (report.game_state === "Final") {
          monitoringRef.current = false;
          setIsMonitoring(false);
          setRequiresManualResume(false);
          setSyncMessage("Final game snapshot synced; monitoring stopped.");
        } else if (monitoringRef.current) {
          timerRef.current = setTimeout(
            () => void runSync(targetGameId, pitcherIds, generation),
            SYNC_INTERVAL_MS,
          );
        }
      } catch (error) {
        if (generation !== generationRef.current) return;
        const message = errorMessage(error);
        setLastSyncError(message);
        setSyncMessage(message);
        if (monitoringRef.current) {
          timerRef.current = setTimeout(
            () => void runSync(targetGameId, pitcherIds, generation),
            SYNC_INTERVAL_MS,
          );
        }
      } finally {
        if (generation === generationRef.current || !monitoringRef.current) setIsSyncing(false);
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
      const sameTarget = gameId === targetGameId && selectedPitcherIds[0] === pitcherId;
      if (sameTarget && isMonitoring) return;
      if (sameTarget && requiresManualResume) return;
      if (timerRef.current) clearTimeout(timerRef.current);
      const generation = ++generationRef.current;
      setGameId(targetGameId);
      setSelectedPitcherIds([pitcherId]);
      setRequiresManualResume(false);
      setSyncedGameId(null);
      setLastGameState(null);
      setLastGameStatus(null);
      setLastSyncError(null);
      setSyncMessage("Syncing MLB snapshot...");
      monitoringRef.current = true;
      setIsMonitoring(true);
      setMonitoringStartedAt(Date.now());
      void runSync(targetGameId, [pitcherId], generation);
    },
    [gameId, isMonitoring, requiresManualResume, runSync, selectedPitcherIds],
  );

  const stopMonitoring = useCallback(() => {
    monitoringRef.current = false;
    generationRef.current += 1;
    if (timerRef.current) clearTimeout(timerRef.current);
    setIsMonitoring(false);
    setRequiresManualResume(gameId !== null && selectedPitcherIds.length > 0);
    setSyncMessage("Monitoring stopped.");
  }, [gameId, selectedPitcherIds]);

  const resumeMonitoring = useCallback(() => {
    const pitcherId = selectedPitcherIds[0];
    if (gameId === null || pitcherId === undefined || lastGameState === "Final") return;
    if (timerRef.current) clearTimeout(timerRef.current);
    const generation = ++generationRef.current;
    setRequiresManualResume(false);
    setLastSyncError(null);
    setSyncMessage("Resuming live sync...");
    monitoringRef.current = true;
    setIsMonitoring(true);
    setMonitoringStartedAt(Date.now());
    void runSync(gameId, [pitcherId], generation);
  }, [gameId, lastGameState, runSync, selectedPitcherIds]);

  const canResume =
    hasHydrated &&
    requiresManualResume &&
    gameId !== null &&
    selectedPitcherIds.length > 0 &&
    lastGameState !== "Final";

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
      hasHydrated,
      canResume,
      monitoringStartedAt,
      watchPitcher,
      stopMonitoring,
      resumeMonitoring,
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
      hasHydrated,
      canResume,
      monitoringStartedAt,
      watchPitcher,
      stopMonitoring,
      resumeMonitoring,
    ],
  );

  return (
    <LiveMonitoringContext.Provider value={value}>
      <LiveMonitoringAlertNotice />
      {children}
    </LiveMonitoringContext.Provider>
  );
}

function LiveMonitoringAlertNotice() {
  const monitoring = useLiveMonitoring();
  const alertsQuery = useAlerts();
  const pitchMixAlertsQuery = usePitchMixAlerts();
  const previousAlerts = useRef<
    Map<string, { message: string; level: string; timestamp: number }>
    | null
  >(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!alertsQuery.data || !pitchMixAlertsQuery.data) return;
    const current = new Map<string, { message: string; level: string; timestamp: number }>();
    for (const alert of alertsQuery.data) {
      if (alert.subject_role === "pitcher") {
        current.set(`event:${alert.id}`, {
          message: alert.message,
          level: "event",
          timestamp: Date.parse(alert.created_at),
        });
      }
    }
    for (const alert of pitchMixAlertsQuery.data) {
      current.set(
        `pitch-mix:${alert.id}`,
        {
          message: `${alert.pitch_name ?? alert.pitch_type} ${alert.metric} ${alert.level.toUpperCase()}`,
          level: alert.level,
          timestamp: Date.parse(alert.first_raised_at),
        },
      );
    }
    if (previousAlerts.current === null) {
      previousAlerts.current = current;
      const sessionStartedAt = monitoring.monitoringStartedAt;
      const newDuringSession = [...current.values()].find(
        (alert) =>
          monitoring.isMonitoring &&
          sessionStartedAt !== null &&
          alert.timestamp >= sessionStartedAt - 1_000,
      );
      if (newDuringSession) setNotice(newDuringSession.message);
      return;
    }
    const newMessages = [...current.entries()]
      .filter(([id, alert]) => {
        const previous = previousAlerts.current?.get(id);
        return previous === undefined || previous.level !== alert.level;
      })
      .map(([, alert]) => alert.message);
    previousAlerts.current = current;
    if (monitoring.isMonitoring && newMessages.length > 0) {
      setNotice(newMessages[0]);
    }
  }, [alertsQuery.data, monitoring.isMonitoring, monitoring.monitoringStartedAt, pitchMixAlertsQuery.data]);

  if (!notice) return null;
  return (
    <aside className="monitoring-notice" role="status">
      <span>New alert: {notice}</span>
      <Link href="/alerts">View alerts</Link>
      <button type="button" aria-label="Dismiss alert notice" onClick={() => setNotice(null)}>
        ×
      </button>
    </aside>
  );
}

export function useLiveMonitoring(): LiveMonitoringContextValue {
  const context = useContext(LiveMonitoringContext);
  if (!context) {
    throw new Error("useLiveMonitoring must be used within a LiveMonitoringProvider");
  }
  return context;
}
