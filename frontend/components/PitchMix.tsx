import { SampleSizeBadge } from "@/components/SampleSizeBadge";
import { DataState } from "@/components/DataState";
import type { PitchUsageData } from "@/lib/types";

export function PitchMix({ pitches }: { pitches: PitchUsageData[] }) {
  return (
    <section className="panel pitch-mix-panel" aria-labelledby="pitch-mix-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Backend-generated facts</p>
          <h2 id="pitch-mix-title">Pitch Mix</h2>
        </div>
        <span className="panel-heading__meta">Tracked pitches</span>
      </div>

      {pitches.length === 0 ? (
        <DataState>Generate a brief to load pitch usage.</DataState>
      ) : (
        <div className="pitch-list">
          {pitches.map((pitch) => (
            <div className="pitch-row" key={pitch.pitchType}>
              <div className="pitch-row__identity">
                <span className="pitch-code" data-tone={pitch.tone}>
                  {pitch.pitchType}
                </span>
                <span>
                  <strong>{pitch.pitchName}</strong>
                  <small>{pitch.sampleSize.toLocaleString()} pitches</small>
                </span>
              </div>
              <div className="pitch-row__visual">
                <div className="bar-track" aria-hidden="true">
                  <span
                    className="bar-fill"
                    data-tone={pitch.tone}
                    style={{ width: `${pitch.percentage}%` }}
                  />
                </div>
                <strong className="pitch-percentage">{pitch.percentage}%</strong>
              </div>
              <SampleSizeBadge status={pitch.status} compact />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
