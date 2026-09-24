"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { DataState } from "@/components/DataState";
import { DateNav, todayIso } from "@/components/DateNav";
import { LiveGameCard } from "@/components/LiveGameCard";
import { toGameSummary } from "@/lib/adapters";
import type { GameParticipantDto } from "@/lib/api";
import { useGameParticipants, useSchedule } from "@/lib/queries";
import type { GameSummaryData, PitcherRefData } from "@/lib/types";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The MLB schedule could not be loaded.";
}

function analysisHref(gameId: string, pitcherId: number, name?: string): string {
  const base = `/player-watch/${gameId}/pitchers/${pitcherId}`;
  return name ? `${base}?name=${encodeURIComponent(name)}` : base;
}

function formatStartTime(startTime: string | null): string | null {
  if (!startTime) return null;
  const parsed = new Date(startTime);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(parsed);
}

function ProbablePitcherLink({
  gameId,
  pitcher,
}: {
  gameId: string;
  pitcher: PitcherRefData | null;
}) {
  if (!pitcher) {
    return <span className="probable-pitcher probable-pitcher--tbd">TBD</span>;
  }
  return (
    <Link className="probable-pitcher" href={analysisHref(gameId, pitcher.id, pitcher.name)}>
      {pitcher.name}
    </Link>
  );
}

function UpcomingRow({ game }: { game: GameSummaryData }) {
  const time = formatStartTime(game.startTime) ?? "TBD";
  return (
    <div className="upcoming-row">
      <span className="upcoming-row__time">{time}</span>
      <span className="upcoming-row__matchup">
        {game.awayTeam.name} @ {game.homeTeam.name}
      </span>
      <div className="upcoming-row__pitchers">
        <ProbablePitcherLink gameId={game.gameId} pitcher={game.probablePitchers.away} />
        <span className="upcoming-row__vs" aria-hidden="true">vs</span>
        <ProbablePitcherLink gameId={game.gameId} pitcher={game.probablePitchers.home} />
      </div>
    </div>
  );
}

function FinalRow({ game }: { game: GameSummaryData }) {
  const scoreLabel =
    game.awayScore !== null && game.homeScore !== null
      ? `${game.awayTeam.name} ${game.awayScore} — ${game.homeTeam.name} ${game.homeScore}`
      : `${game.awayTeam.name} @ ${game.homeTeam.name} · ${game.status}`;
  const hasProbables = game.probablePitchers.away !== null || game.probablePitchers.home !== null;
  return (
    <div className="final-row">
      <span className="final-row__score">{scoreLabel}</span>
      {hasProbables ? (
        <div className="final-row__pitchers">
          <ProbablePitcherLink gameId={game.gameId} pitcher={game.probablePitchers.away} />
          <span className="upcoming-row__vs" aria-hidden="true">vs</span>
          <ProbablePitcherLink gameId={game.gameId} pitcher={game.probablePitchers.home} />
        </div>
      ) : null}
    </div>
  );
}

function LiveNowSection({ games }: { games: GameSummaryData[] }) {
  return (
    <section className="panel game-discovery-section" aria-labelledby="live-now-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Right now</p>
          <h2 id="live-now-title">Live Now</h2>
        </div>
      </div>
      {games.length === 0 ? (
        <DataState>No live games right now.</DataState>
      ) : (
        <div className="live-game-grid">
          {games.map((game) => (
            <LiveGameCard key={game.gameId} game={game} />
          ))}
        </div>
      )}
    </section>
  );
}

function UpcomingSection({ games }: { games: GameSummaryData[] }) {
  return (
    <section className="panel game-discovery-section" aria-labelledby="upcoming-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Later today</p>
          <h2 id="upcoming-title">Upcoming</h2>
        </div>
      </div>
      {games.length === 0 ? (
        <DataState>No upcoming games for this date.</DataState>
      ) : (
        <div className="upcoming-list">
          {games.map((game) => (
            <UpcomingRow key={game.gameId} game={game} />
          ))}
        </div>
      )}
    </section>
  );
}

function FinalSection({ games }: { games: GameSummaryData[] }) {
  const finals = games.filter((game) => game.state === "final");
  const others = games.filter((game) => game.state === "other");
  if (finals.length === 0 && others.length === 0) return null;

  return (
    <section className="panel game-discovery-section">
      <details className="game-discovery-final">
        <summary className="game-discovery-final__summary">
          <span className="section-kicker">Wrapped up</span>
          <span className="game-discovery-final__title">Final ({finals.length})</span>
        </summary>
        <div className="game-discovery-final__body">
          {finals.length > 0 ? (
            <div className="final-list">
              {finals.map((game) => (
                <FinalRow key={game.gameId} game={game} />
              ))}
            </div>
          ) : (
            <DataState>No final games for this date.</DataState>
          )}
          {others.length > 0 ? (
            <div className="game-discovery-other">
              <p className="section-kicker">Other</p>
              {others.map((game) => (
                <p key={game.gameId} className="game-discovery-other__row">
                  {game.awayTeam.name} @ {game.homeTeam.name} · {game.status}
                </p>
              ))}
            </div>
          ) : null}
        </div>
      </details>
    </section>
  );
}

interface PitcherGroup {
  key: string;
  teamName: string;
  players: GameParticipantDto[];
}

function groupPitchersByTeam(participants: GameParticipantDto[]): PitcherGroup[] {
  const grouped = new Map<string, GameParticipantDto[]>();
  for (const participant of participants) {
    if (!participant.roles.includes("pitcher")) continue;
    const key = `${participant.team_side}:${participant.team_name}`;
    grouped.set(key, [...(grouped.get(key) ?? []), participant]);
  }
  return [...grouped.entries()].map(([key, players]) => ({
    key,
    teamName: players[0]?.team_name ?? "Team",
    players: players.sort((left, right) => left.name.localeCompare(right.name)),
  }));
}

function ManualGameEntry() {
  const [gameIdInput, setGameIdInput] = useState("");
  const [loadedGameId, setLoadedGameId] = useState<number | null>(null);
  const [inputError, setInputError] = useState<string | null>(null);
  const participantsQuery = useGameParticipants(loadedGameId);

  const participants = participantsQuery.data?.participants ?? [];
  const pitcherGroups = useMemo(() => groupPitchersByTeam(participants), [participants]);

  const handleLoad = () => {
    const gameId = Number(gameIdInput.trim());
    if (!Number.isInteger(gameId) || gameId <= 0) {
      setInputError("Use a positive MLB game ID.");
      return;
    }
    setInputError(null);
    setLoadedGameId(gameId);
  };

  return (
    <details className="manual-game-entry">
      <summary>Advanced: Enter game ID manually</summary>
      <div className="manual-game-entry__body">
        <div className="live-controls__grid">
          <label className="field-label">
            Game ID
            <input
              value={gameIdInput}
              onChange={(event) => setGameIdInput(event.target.value)}
              placeholder="776743"
              inputMode="numeric"
            />
          </label>
          <button
            className="secondary-button"
            type="button"
            onClick={handleLoad}
            disabled={participantsQuery.isFetching}
          >
            Load game
          </button>
        </div>
        {inputError ? <p className="control-status is-error">{inputError}</p> : null}
        {loadedGameId !== null ? (
          participantsQuery.isLoading ? (
            <DataState kind="loading">Loading game participants...</DataState>
          ) : participantsQuery.error ? (
            <DataState kind="error" onRetry={() => void participantsQuery.refetch()}>
              {errorMessage(participantsQuery.error)}
            </DataState>
          ) : pitcherGroups.length === 0 ? (
            <DataState>No pitchers found for this game yet.</DataState>
          ) : (
            <div className="participant-groups">
              {pitcherGroups.map((group) => (
                <div className="participant-group" key={group.key}>
                  <h3>{group.teamName}</h3>
                  <div className="participant-list">
                    {group.players.map((pitcher) => (
                      <Link
                        key={pitcher.player_id}
                        className="manual-game-entry__pitcher"
                        href={analysisHref(String(loadedGameId), pitcher.player_id, pitcher.name)}
                      >
                        {pitcher.name}
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )
        ) : null}
      </div>
    </details>
  );
}

/**
 * The Player Watch home page: pick a date, then drill from "what's
 * happening right now" down to a single pitcher's live-vs-baseline
 * analysis. Replaces the old flow of picking a game, checking off
 * participants, and pressing Start monitoring.
 */
export function GameDiscovery() {
  const [date, setDate] = useState(todayIso);
  const scheduleQuery = useSchedule(date);

  const games = useMemo(() => (scheduleQuery.data ?? []).map(toGameSummary), [scheduleQuery.data]);
  const liveGames = useMemo(() => games.filter((game) => game.state === "live"), [games]);
  const upcomingGames = useMemo(() => games.filter((game) => game.state === "upcoming"), [games]);
  const finalAndOtherGames = useMemo(
    () => games.filter((game) => game.state === "final" || game.state === "other"),
    [games],
  );

  // TanStack Query "pauses" a retrying fetch instead of settling into an
  // error when it believes the client is offline, which would otherwise
  // render as a false "no games" empty state rather than a failure the user
  // can retry.
  const scheduleFailed =
    scheduleQuery.isError || (scheduleQuery.data === undefined && scheduleQuery.fetchStatus === "paused");

  return (
    <div className="game-discovery">
      <section className="panel game-discovery-section" aria-labelledby="game-discovery-date-title">
        <div className="panel-heading">
          <div>
            <p className="section-kicker">Choose a date</p>
            <h2 id="game-discovery-date-title">MLB schedule</h2>
          </div>
        </div>
        <DateNav date={date} onChange={setDate} />
      </section>

      {scheduleQuery.isLoading ? (
        <DataState kind="loading">Loading MLB schedule...</DataState>
      ) : scheduleFailed ? (
        <DataState kind="error" onRetry={() => void scheduleQuery.refetch()}>
          {errorMessage(scheduleQuery.error)}
        </DataState>
      ) : games.length === 0 ? (
        <DataState>No MLB games scheduled for this date.</DataState>
      ) : (
        <>
          <LiveNowSection games={liveGames} />
          <UpcomingSection games={upcomingGames} />
          <FinalSection games={finalAndOtherGames} />
        </>
      )}

      <ManualGameEntry />
    </div>
  );
}
