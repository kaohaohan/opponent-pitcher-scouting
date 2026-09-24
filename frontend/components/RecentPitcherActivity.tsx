import { DataState } from "@/components/DataState";
import type { PlateAppearanceData } from "@/lib/types";

function formatMeasurement(value: number | null, unit: string) {
  return value === null ? "—" : `${value.toFixed(1)} ${unit}`;
}

export interface RecentPitcherActivityProps {
  recentPlateAppearances: PlateAppearanceData[];
  triggeredRules: Array<{ rule: string; detail: string }>;
}

/**
 * The secondary, game-log half of the pitcher analysis view: every plate
 * appearance this pitcher has faced today, and any rule-engine alerts one
 * of them triggered. Extracted from the old `PlayerWatch` component — its
 * hero, latest-PA callout, and comparison sections are superseded by this
 * page's own header, `PitchMixComparison`, and `SignalsPanel`, so only the
 * rule-list and recent-PA table markup survives here.
 */
export function RecentPitcherActivity({
  recentPlateAppearances,
  triggeredRules,
}: RecentPitcherActivityProps) {
  return (
    <div className="pitcher-activity">
      <section className="panel triggered-rules" aria-labelledby="triggered-rules-title">
        <div className="panel-heading">
          <div>
            <p className="section-kicker">Watch engine</p>
            <h2 id="triggered-rules-title">PA Rule Alerts</h2>
          </div>
          <span className="panel-heading__meta">{triggeredRules.length} active</span>
        </div>
        {triggeredRules.length === 0 ? (
          <DataState>No rule alerts triggered for this pitcher today.</DataState>
        ) : (
          <div className="rule-list">
            {triggeredRules.map((rule) => (
              <div className="rule-item" key={rule.rule}>
                <span className="rule-item__icon" aria-hidden="true">
                  ✓
                </span>
                <div>
                  <strong>{rule.rule}</strong>
                  <p>{rule.detail}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel recent-pa" aria-labelledby="recent-pa-title">
        <div className="panel-heading">
          <div>
            <p className="section-kicker">Game log</p>
            <h2 id="recent-pa-title">Recent Plate Appearances Faced</h2>
          </div>
          <span className="panel-heading__meta">Today</span>
        </div>
        {recentPlateAppearances.length === 0 ? (
          <DataState>No completed plate appearances recorded yet today.</DataState>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Inning</th>
                  <th>Result allowed</th>
                  <th>Batter</th>
                  <th>Pitch</th>
                  <th>Pitch velo</th>
                  <th>Exit velo</th>
                </tr>
              </thead>
              <tbody>
                {recentPlateAppearances.map((appearance) => (
                  <tr key={appearance.id}>
                    <td>{appearance.inning}</td>
                    <td>
                      <strong>{appearance.result}</strong>
                    </td>
                    <td>{appearance.batter}</td>
                    <td>
                      <span className="pitch-pill">{appearance.pitchType}</span>
                    </td>
                    <td>{formatMeasurement(appearance.pitchVelocity, "")}</td>
                    <td>{formatMeasurement(appearance.exitVelocity, "")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
