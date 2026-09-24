"use client";

import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";

import { shiftDate } from "@/components/DateNav";
import { PitcherAvatar } from "@/components/PitcherAvatar";
import { getGameSummary, getPregameLiveComparison } from "@/lib/api";
import type { GameSummaryData } from "@/lib/types";

function analysisHref(gameId: string, pitcherId: number, name?: string | null, date?: string | null): string {
  const base = `/player-watch/${gameId}/pitchers/${pitcherId}`;
  const params = new URLSearchParams();
  if (name) params.set("name", name);
  if (date) params.set("date", date);
  const query = params.toString();
  return query ? `${base}?${query}` : base;
}

/**
 * A large, top-of-page card for a game in progress: score, inning/outs
 * state, who's on the mound right now, and the primary CTA into that
 * pitcher's live analysis view. When the feed hasn't resolved a current
 * pitcher yet the CTA is disabled rather than linking somewhere wrong.
 */
export function LiveGameCard({ game }: { game: GameSummaryData }) {
  const pitcher = game.currentPitcher;
  const href = pitcher ? analysisHref(game.gameId, pitcher.id, pitcher.name, game.gameDate) : null;
  const queryClient = useQueryClient();

  // On hover/focus of the CTA, warm the two queries the analysis page opens
  // with — same query keys and fetchers it uses, so a click right after
  // reuses this cache instead of refetching. Cheap to call repeatedly:
  // `prefetchQuery` is a no-op while a fresh entry already exists.
  const prefetchAnalysis = () => {
    if (!pitcher) return;
    const gameId = Number(game.gameId);
    const pitcherId = pitcher.id;
    const endDate = shiftDate(game.gameDate, -1);
    const startDate = shiftDate(endDate, -365);
    void queryClient.prefetchQuery({
      queryKey: ["live-game-summary", gameId],
      queryFn: () => getGameSummary(gameId),
      staleTime: 10 * 1000,
    });
    void queryClient.prefetchQuery({
      queryKey: ["pregame-live-comparison", gameId, pitcherId, startDate, endDate],
      queryFn: () => getPregameLiveComparison(gameId, pitcherId, startDate, endDate),
      staleTime: 10 * 1000,
    });
  };

  return (
    <article className="panel live-game-card">
      <div className="live-game-card__status">
        <span className="live-indicator">Live</span>
        <span className="live-game-card__state">{game.stateLabel}</span>
      </div>

      <div className="live-game-card__score">
        <span className="live-game-card__team">{game.awayTeam.name}</span>
        <span className="live-game-card__runs">
          {game.awayScore ?? 0} — {game.homeScore ?? 0}
        </span>
        <span className="live-game-card__team">{game.homeTeam.name}</span>
      </div>

      <div className="live-game-card__pitching">
        <p className="section-kicker">Pitching</p>
        {pitcher ? (
          <div className="live-game-card__pitcher">
            <PitcherAvatar name={pitcher.name} playerId={pitcher.id} size={40} />
            <strong>{pitcher.name}</strong>
          </div>
        ) : (
          <p className="live-game-card__pitcher-unknown">Current pitcher not yet available.</p>
        )}
      </div>

      {href ? (
        <Link
          className="primary-button live-game-card__cta"
          href={href}
          onMouseEnter={prefetchAnalysis}
          onFocus={prefetchAnalysis}
        >
          View live analysis
        </Link>
      ) : (
        <button className="primary-button live-game-card__cta" type="button" disabled>
          View live analysis
        </button>
      )}
    </article>
  );
}
