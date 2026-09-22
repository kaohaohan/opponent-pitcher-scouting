import type { ComparisonNoteData, PlayerWatchData, PregameLiveComparisonData } from "@/lib/types";
import { ComparisonNote } from "@/components/ComparisonNote";
import { PitcherAvatar } from "@/components/PitcherAvatar";
import { PitchMixComparison } from "@/components/PitchMixComparison";

function formatMeasurement(value: number | null, unit: string) {
  return value === null ? "—" : `${value.toFixed(1)} ${unit}`;
}

export interface PitcherComparisonProps {
  comparison: PregameLiveComparisonData | null;
  note: ComparisonNoteData | null;
  noteLoading: boolean;
  noteError: string | null;
  onGenerateNote: () => void;
  startDate: string;
  endDate: string;
  onStartDateChange: (value: string) => void;
  onEndDateChange: (value: string) => void;
}

export function PlayerWatch({
  player,
  pitcherComparison,
}: {
  player: PlayerWatchData;
  // Only meaningful (and only rendered) when `player.role === "pitcher"`.
  pitcherComparison?: PitcherComparisonProps;
}) {
  const latest = player.latestPlateAppearance;
  const isPitcher = player.role === "pitcher";

  return (
    <div className="watch-layout">
      <section className="panel watch-hero">
        <div className="watch-hero__identity">
          {isPitcher ? (
            <PitcherAvatar name={player.name} playerId={player.playerId} size={50} />
          ) : (
            <div className="player-number" aria-hidden="true">{player.jerseyNumber}</div>
          )}
          <div>
            <p className="section-kicker">{isPitcher ? "Tracked pitcher" : "Tracked hitter"}</p>
            <h2>{player.name}</h2>
            <p>{player.team} · {player.opponent}</p>
          </div>
        </div>
        <div className="game-state">
          <span className="live-indicator">Live</span>
          {player.gameState}
        </div>
        <div className="today-line">
          <span>Today</span>
          <strong>{player.todayLine}</strong>
        </div>
      </section>

      <section className="panel latest-pa" aria-labelledby="latest-pa-title">
        <div className="panel-heading">
          <div>
            <p className="section-kicker">Most recent event</p>
            <h2 id="latest-pa-title">{isPitcher ? "Latest Plate Appearance Faced" : "Latest Plate Appearance"}</h2>
          </div>
          <span className="inning-label">{latest.inning}</span>
        </div>
        <div className="result-callout">
          <span className="result-callout__mark">{latest.resultCode}</span>
          <div>
            <strong>{isPitcher ? `${latest.result} allowed` : latest.result}</strong>
            <p>{latest.description}</p>
          </div>
        </div>
        <div className="measurement-grid">
          <div>
            <span>Exit velocity</span>
            <strong>{formatMeasurement(latest.exitVelocity, "mph")}</strong>
          </div>
          <div>
            <span>Pitch velocity</span>
            <strong>{formatMeasurement(latest.pitchVelocity, "mph")}</strong>
          </div>
          <div>
            <span>Pitch</span>
            <strong>{latest.pitchType}</strong>
          </div>
          <div>
            <span>{isPitcher ? "Batter" : "Pitcher"}</span>
            <strong>{isPitcher ? latest.batter : latest.pitcher}</strong>
          </div>
        </div>
      </section>

      <section className="panel triggered-rules" aria-labelledby="triggered-rules-title">
        <div className="panel-heading">
          <div>
            <p className="section-kicker">Watch engine</p>
            <h2 id="triggered-rules-title">Triggered Rules</h2>
          </div>
          <span className="panel-heading__meta">{player.triggeredRules.length} active</span>
        </div>
        <div className="rule-list">
          {player.triggeredRules.map((rule) => (
            <div className="rule-item" key={rule.rule}>
              <span className="rule-item__icon" aria-hidden="true">✓</span>
              <div>
                <strong>{rule.rule}</strong>
                <p>{rule.detail}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel recent-pa" aria-labelledby="recent-pa-title">
        <div className="panel-heading">
          <div>
            <p className="section-kicker">Game log</p>
            <h2 id="recent-pa-title">{isPitcher ? "Recent Plate Appearances Faced" : "Recent Plate Appearances"}</h2>
          </div>
          <span className="panel-heading__meta">Today</span>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Inning</th>
                <th>{isPitcher ? "Result allowed" : "Result"}</th>
                <th>{isPitcher ? "Batter" : "Pitcher"}</th>
                <th>Pitch</th>
                <th>Pitch velo</th>
                <th>Exit velo</th>
              </tr>
            </thead>
            <tbody>
              {player.recentPlateAppearances.map((appearance) => (
                <tr key={appearance.id}>
                  <td>{appearance.inning}</td>
                  <td><strong>{appearance.result}</strong></td>
                  <td>{isPitcher ? appearance.batter : appearance.pitcher}</td>
                  <td><span className="pitch-pill">{appearance.pitchType}</span></td>
                  <td>{formatMeasurement(appearance.pitchVelocity, "")}</td>
                  <td>{formatMeasurement(appearance.exitVelocity, "")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {isPitcher && pitcherComparison ? (
        <div className="comparison-section">
          <p className="section-kicker">Pre-game expectation vs. live game behavior</p>
          <form
            className="comparison-date-form"
            onSubmit={(event) => event.preventDefault()}
            aria-label="Pregame baseline date range"
          >
            <label className="field-label">
              Baseline start
              <input
                type="date"
                value={pitcherComparison.startDate}
                onChange={(event) => pitcherComparison.onStartDateChange(event.target.value)}
              />
            </label>
            <label className="field-label">
              Baseline end
              <input
                type="date"
                value={pitcherComparison.endDate}
                onChange={(event) => pitcherComparison.onEndDateChange(event.target.value)}
              />
            </label>
          </form>

          <PitchMixComparison comparison={pitcherComparison.comparison} />

          <ComparisonNote
            note={pitcherComparison.note}
            isLoading={pitcherComparison.noteLoading}
            error={pitcherComparison.noteError}
            onGenerate={pitcherComparison.onGenerateNote}
          />
        </div>
      ) : null}
    </div>
  );
}
