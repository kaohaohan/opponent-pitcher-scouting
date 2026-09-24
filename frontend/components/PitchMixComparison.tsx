import type { PitchComparisonRowData, PregameLiveComparisonData, SignalData } from "@/lib/types";
import { DataState } from "@/components/DataState";
import { SampleSizeBadge } from "@/components/SampleSizeBadge";

function formatPercent(value: number | null): string {
  // `0` is a real, meaningful "today's usage is zero" value — it must
  // render as "0%", never fall through to the same "—" placeholder used
  // for genuinely missing data. Only an explicit `null` is missing.
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

type SignalLevel = SignalData["level"];

function signalLevelMap(signals: SignalData[]): Map<string, SignalLevel> {
  const map = new Map<string, SignalLevel>();
  for (const signal of signals) {
    map.set(`${signal.pitchType}:${signal.metric}`, signal.level);
  }
  return map;
}

/**
 * The deterministic Today-vs-Baseline pitch mix table. Renders straight
 * from query data with no dependency on the AI note — this section stays
 * visible and correct even when a `ComparisonNote` generation fails.
 * Split into Usage and Velocity column groups, each ordered Today / Base /
 * Δ so the live figure always leads. Cells backing an active `Signal` are
 * tinted amber (watch) or red (alert) by matching pitch_type + metric —
 * the same pairing the backend used to produce that signal.
 */
export function PitchMixComparison({
  comparison,
}: {
  comparison: PregameLiveComparisonData | null;
}) {
  const signalLevels = comparison ? signalLevelMap(comparison.signals) : new Map<string, SignalLevel>();

  return (
    <section className="panel comparison-panel" aria-labelledby="comparison-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Backend-generated facts</p>
          <h2 id="comparison-title">Today vs. Baseline</h2>
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
            <table className="data-table comparison-table">
              <thead>
                <tr>
                  <th rowSpan={2}>Pitch</th>
                  <th colSpan={3} className="comparison-table__group">
                    Usage
                  </th>
                  <th colSpan={3} className="comparison-table__group comparison-table__group--velocity">
                    Velocity
                  </th>
                  <th rowSpan={2}>Sample</th>
                </tr>
                <tr>
                  <th>Today</th>
                  <th>Base</th>
                  <th>Δpp</th>
                  <th className="comparison-table__group--velocity">Today</th>
                  <th>Base</th>
                  <th>Δ mph</th>
                </tr>
              </thead>
              <tbody>
                {comparison.rows.map((row: PitchComparisonRowData) => {
                  const usageLevel = signalLevels.get(`${row.pitchType}:usage`);
                  const velocityLevel = signalLevels.get(`${row.pitchType}:velocity`);
                  return (
                    <tr key={row.pitchType} data-notable={row.isNotable}>
                      <td>
                        <span className="pitch-pill" data-tone={row.tone}>
                          {row.pitchName}
                        </span>
                      </td>
                      <td data-signal={usageLevel}>{formatPercent(row.liveUsagePct)}</td>
                      <td>{formatPercent(row.baselineUsagePct)}</td>
                      <td data-signal={usageLevel}>{formatDelta(row.usageDeltaPp, "pp")}</td>
                      <td data-signal={velocityLevel} className="comparison-table__group--velocity">
                        {formatVelocity(row.liveVelocity)}
                      </td>
                      <td>{formatVelocity(row.baselineVelocity)}</td>
                      <td data-signal={velocityLevel}>{formatDelta(row.velocityDelta, " mph")}</td>
                      <td>
                        <SampleSizeBadge status={row.status} sampleSize={row.liveSampleSize} compact />
                      </td>
                    </tr>
                  );
                })}
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
