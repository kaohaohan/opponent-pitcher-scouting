"use client";

import { useState } from "react";

import { DataState } from "@/components/DataState";
import type { ScheduleGameDto } from "@/lib/api";
import { useSchedule } from "@/lib/queries";

function todayIso(): string {
  const now = new Date();
  const offsetMs = now.getTimezoneOffset() * 60 * 1000;
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10);
}

function shiftDate(date: string, days: number): string {
  const [year, month, day] = date.split("-").map(Number);
  const next = new Date(Date.UTC(year, month - 1, day + days));
  return next.toISOString().slice(0, 10);
}

function formatStartTime(startTime: string | null): string | null {
  if (!startTime) return null;
  const parsed = new Date(startTime);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(parsed);
}

function statusLabel(status: string): "Scheduled" | "Live" | "Final" | string {
  const normalized = status.toLowerCase();
  if (normalized.includes("final")) return "Final";
  if (normalized === "scheduled" || normalized === "pre-game" || normalized === "preview") {
    return "Scheduled";
  }
  if (normalized.includes("progress") || normalized.includes("live") || normalized.includes("delay")) {
    return "Live";
  }
  return status;
}

function gameSummary(game: ScheduleGameDto): string {
  const label = statusLabel(game.status);
  if (label === "Final" && game.away_score !== null && game.home_score !== null) {
    return `Final · ${game.away_team.name} ${game.away_score} – ${game.home_team.name} ${game.home_score}`;
  }
  if (label === "Live") {
    const score =
      game.away_score !== null && game.home_score !== null
        ? ` · ${game.away_team.name} ${game.away_score} – ${game.home_team.name} ${game.home_score}`
        : "";
    return `Live${score}`;
  }
  const time = formatStartTime(game.start_time);
  return time ? `Scheduled · ${time}` : "Scheduled";
}

interface GamePickerProps {
  selectedGameId: number | null;
  isMonitoring: boolean;
  onSelectGame: (gameId: number) => void;
}

export function GamePicker({ selectedGameId, isMonitoring, onSelectGame }: GamePickerProps) {
  const [date, setDate] = useState(todayIso);
  const [blockedMessage, setBlockedMessage] = useState<string | null>(null);
  const scheduleQuery = useSchedule(date);
  const games = scheduleQuery.data ?? [];
  // TanStack Query "pauses" a retrying fetch instead of settling into an error
  // when it believes the client is offline, which would otherwise render as a
  // false "no games" empty state rather than a failure the user can retry.
  const scheduleFailed =
    scheduleQuery.isError || (scheduleQuery.data === undefined && scheduleQuery.fetchStatus === "paused");

  const changeDate = (nextDate: string) => {
    setDate(nextDate);
    setBlockedMessage(null);
  };

  const handleSelect = (gameId: number) => {
    if (isMonitoring) {
      setBlockedMessage("Stop monitoring to change games.");
      return;
    }
    setBlockedMessage(null);
    onSelectGame(gameId);
  };

  return (
    <section className="game-picker" aria-labelledby="game-picker-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Choose a game</p>
          <h2 id="game-picker-title">MLB schedule</h2>
        </div>
      </div>
      <div className="game-picker__date-controls">
        <button type="button" className="secondary-button" onClick={() => changeDate(shiftDate(date, -1))}>
          ← Previous day
        </button>
        <input
          type="date"
          value={date}
          onChange={(event) => event.target.value && changeDate(event.target.value)}
          aria-label="Choose a date"
        />
        <button type="button" className="secondary-button" onClick={() => changeDate(todayIso())}>
          Today
        </button>
        <button type="button" className="secondary-button" onClick={() => changeDate(shiftDate(date, 1))}>
          Next day →
        </button>
      </div>

      {scheduleQuery.isLoading ? (
        <DataState kind="loading">Loading MLB schedule...</DataState>
      ) : scheduleFailed ? (
        <DataState kind="error" onRetry={() => void scheduleQuery.refetch()}>
          Could not load the MLB schedule. You can still enter a Game ID manually.
        </DataState>
      ) : games.length === 0 ? (
        <DataState>No MLB games scheduled for this date.</DataState>
      ) : (
        <div className="game-picker__list">
          {games.map((game) => {
            const gameId = Number(game.game_id);
            const isSelected = selectedGameId === gameId;
            return (
              <button
                key={game.game_id}
                type="button"
                className={isSelected ? "game-picker__row is-active" : "game-picker__row"}
                onClick={() => handleSelect(gameId)}
                aria-pressed={isSelected}
              >
                <span className="game-picker__matchup">
                  {game.away_team.name} @ {game.home_team.name}
                </span>
                <span className="game-picker__meta">{gameSummary(game)}</span>
              </button>
            );
          })}
        </div>
      )}
      {blockedMessage ? <p className="control-status is-error">{blockedMessage}</p> : null}
    </section>
  );
}
