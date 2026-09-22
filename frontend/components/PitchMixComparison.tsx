import type { PregameLiveComparisonData } from "@/lib/types";
import { DataState } from "@/components/DataState";
import { SampleSizeBadge } from "@/components/SampleSizeBadge";

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)}%`;
}

function formatDelta(value: number | null, unit: string): string {
  if (value === null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}${unit}`;
}

function formatVelocity(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)} mph`;
}

/**
 * The deterministic pregame-vs-live pitch mix table. Renders straight
 * from query data with no dependency on the AI note — this section stays
 * visible and correct even when a `ComparisonNote` generation fails.
 */
export function PitchMixComparison({
  comparison,
}: {
  comparison: PregameLiveComparisonData | null;
}) {
  return (
    <section className="panel comparison-panel" aria-labelledby="comparison-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Backend-generated facts</p>
          <h2 id="comparison-title">Live vs. Pregame Pitch Mix</h2>
        </div>
        {comparison ? (
          <span className="panel-heading__meta">
            {comparison.liveTotalPitches} live pitch{comparison.liveTotalPitches === 1 ? "" : "es"}
            {comparison.baselineAvailable
              ? ` · ${comparison.baselineTotalPitches} baseline`
              : ""}
          </span>
        ) : null}
      </div>

      {!comparison || comparison.rows.length === 0 ? (
        <DataState>
          {comparison ? "No pitch data available yet for this pitcher." : "Loading comparison…"}
        </DataState>
      ) : (
        <>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Pitch</th>
                  <th>Pregame</th>
                  <th>Live</th>
                  <th>Usage Δ</th>
                  <th>Pregame velo</th>
                  <th>Live velo</th>
                  <th>Velo Δ</th>
                  <th>Sample</th>
                </tr>
              </thead>
              <tbody>
                {comparison.rows.map((row) => (
                  <tr key={row.pitchType} data-notable={row.isNotable}>
                    <td>
                      <span className="pitch-pill" data-tone={row.tone}>
                        {row.pitchName}
                      </span>
                    </td>
                    <td>{formatPercent(row.baselineUsagePct)}</td>
                    <td>{formatPercent(row.liveUsagePct)}</td>
                    <td>{formatDelta(row.usageDeltaPp, "pp")}</td>
                    <td>{formatVelocity(row.baselineVelocity)}</td>
                    <td>{formatVelocity(row.liveVelocity)}</td>
                    <td>{formatDelta(row.velocityDelta, " mph")}</td>
                    <td>
                      <SampleSizeBadge
                        status={row.status}
                        sampleSize={row.liveSampleSize}
                        compact
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {comparison.limitations.length > 0 ? (
            <ul className="brief-list brief-list--limitations comparison-limitations">
              {comparison.limitations.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </section>
  );
}
