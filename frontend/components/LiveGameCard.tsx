import Link from "next/link";

import { PitcherAvatar } from "@/components/PitcherAvatar";
import type { GameSummaryData } from "@/lib/types";

function analysisHref(gameId: string, pitcherId: number, name?: string): string {
  const base = `/player-watch/${gameId}/pitchers/${pitcherId}`;
  return name ? `${base}?name=${encodeURIComponent(name)}` : base;
}

/**
 * A large, top-of-page card for a game in progress: score, inning/outs
 * state, who's on the mound right now, and the primary CTA into that
 * pitcher's live analysis view. When the feed hasn't resolved a current
 * pitcher yet the CTA is disabled rather than linking somewhere wrong.
 */
export function LiveGameCard({ game }: { game: GameSummaryData }) {
  const pitcher = game.currentPitcher;
  const href = pitcher ? analysisHref(game.gameId, pitcher.id, pitcher.name) : null;

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
        <Link className="primary-button live-game-card__cta" href={href}>
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
