import { DataState } from "@/components/DataState";
import type { PregameLiveComparisonData, SignalData } from "@/lib/types";

function formatUsagePercent(value: number): string {
  return `${Math.round(value)}%`;
}

function formatUsageDelta(delta: number): string {
  const rounded = Math.round(delta);
  return `${rounded > 0 ? "+" : ""}${rounded}pp`;
}

function formatVelocityDelta(delta: number): string {
  return `Δ ${delta > 0 ? "+" : ""}${delta.toFixed(1)} mph`;
}

function signalValuesLine(signal: SignalData): string {
  if (signal.metric === "usage") {
    const baseline = formatUsagePercent(signal.baselineValue);
    const today = signal.todayValue === 0 ? "not thrown yet today" : `${formatUsagePercent(signal.todayValue)} today`;
    return `${baseline} baseline → ${today}`;
  }
  return `${signal.baselineValue.toFixed(1)} → ${signal.todayValue.toFixed(1)} mph`;
}

function signalDeltaLine(signal: SignalData): string {
  return signal.metric === "usage" ? formatUsageDelta(signal.delta) : formatVelocityDelta(signal.delta);
}

function SignalCard({ signal }: { signal: SignalData }) {
  return (
    <article className="signal-card" data-level={signal.level}>
      <div className="signal-card__meta">
        <span className="signal-card__level" data-level={signal.level}>
          {signal.level.toUpperCase()}
        </span>
        <span className="signal-card__basis">
          {signal.sampleBasis} pitch{signal.sampleBasis === 1 ? "" : "es"}
        </span>
      </div>
      <h3 className="signal-card__title">
        {signal.pitchName ?? signal.pitchType} {signal.metric}
      </h3>
      <p className="signal-card__values">{signalValuesLine(signal)}</p>
      <p className="signal-card__delta">{signalDeltaLine(signal)}</p>
      {signal.level === "watch" ? (
        <p className="signal-card__note">Early signal — continue monitoring</p>
      ) : null}
    </article>
  );
}

/**
 * The signals half of Today vs Baseline: every usage/velocity gap that
 * cleared a product heuristic (see `app.comparison.signals` on the
 * backend), rendered as attention cards rather than buried in the table.
 * Purely a view over already-computed `comparison.signals` — no
 * thresholds or gating logic live here.
 */
export function SignalsPanel({ comparison }: { comparison: PregameLiveComparisonData | null }) {
  return (
    <section className="panel signals-panel" aria-labelledby="signals-panel-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Worth a glance</p>
          <h2 id="signals-panel-title">Signals</h2>
        </div>
        {comparison ? (
          <span className="panel-heading__meta">{comparison.signals.length} active</span>
        ) : null}
      </div>

      {!comparison ? (
        <DataState kind="loading">Loading signals…</DataState>
      ) : comparison.signals.length === 0 ? (
        <DataState>
          No notable changes yet — {comparison.liveTotalPitches} live pitch
          {comparison.liveTotalPitches === 1 ? "" : "es"} so far.
        </DataState>
      ) : (
        <div className="signal-card-grid">
          {comparison.signals.map((signal) => (
            <SignalCard key={`${signal.metric}-${signal.pitchType}`} signal={signal} />
          ))}
        </div>
      )}

      <p className="signals-panel__footer">Thresholds are monitoring heuristics, not statistical tests.</p>
    </section>
  );
}
