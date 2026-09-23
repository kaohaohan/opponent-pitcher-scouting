"use client";

import { useState } from "react";

import { DataState } from "@/components/DataState";
import { SampleSizeBadge } from "@/components/SampleSizeBadge";
import type { CountBucketData } from "@/lib/types";

export function CountTendencies({
  buckets,
  isLoading = false,
}: {
  buckets: CountBucketData[];
  isLoading?: boolean;
}) {
  const [selectedId, setSelectedId] = useState(buckets[0]?.id ?? "");
  const selected = buckets.find((bucket) => bucket.id === selectedId) ?? buckets[0];

  if (isLoading || !selected) {
    return (
      <section className="panel count-panel" aria-labelledby="count-tendencies-title">
        <div className="panel-heading">
          <div>
            <p className="section-kicker">Backend-generated facts</p>
            <h2 id="count-tendencies-title">Count Tendencies</h2>
          </div>
          <span className="panel-heading__meta">Select count</span>
        </div>
        {isLoading ? (
          <DataState kind="loading">Computing count-specific tendencies…</DataState>
        ) : (
          <DataState>Generate a brief to load count-specific tendencies.</DataState>
        )}
      </section>
    );
  }

  return (
    <section className="panel count-panel" aria-labelledby="count-tendencies-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Backend-generated facts</p>
          <h2 id="count-tendencies-title">Count Tendencies</h2>
        </div>
        <span className="panel-heading__meta">Select count</span>
      </div>

      <div className="count-selector" role="list" aria-label="Count buckets">
        {buckets.map((bucket) => (
          <button
            aria-pressed={selectedId === bucket.id}
            className="count-tile"
            data-selected={selectedId === bucket.id}
            data-status={bucket.status}
            key={bucket.id}
            onClick={() => setSelectedId(bucket.id)}
            type="button"
          >
            <span className="count-tile__count">{bucket.label}</span>
            <span className="count-tile__pitch">
              {bucket.primaryPitch} <strong>{bucket.percentage}%</strong>
            </span>
            <span className="count-tile__sample">n={bucket.sampleSize}</span>
            {bucket.status === "insufficient_sample" ? (
              <span className="count-tile__warning">Small sample</span>
            ) : null}
          </button>
        ))}
      </div>

      <div className="count-detail" data-status={selected.status}>
        <div className="count-detail__header">
          <div>
            <span className="detail-label">Selected bucket</span>
            <h3>
              {selected.label} <span>{selected.leverage}</span>
            </h3>
          </div>
          <SampleSizeBadge status={selected.status} sampleSize={selected.sampleSize} />
        </div>

        {selected.status === "insufficient_sample" ? (
          <div className="sample-warning" role="note">
            <span aria-hidden="true">!</span>
            Small-sample warning: do not treat this bucket as a stable tendency.
          </div>
        ) : null}

        <div className="distribution-list">
          {selected.pitchDistribution.map((pitch) => (
            <div className="distribution-row" key={pitch.pitchType}>
              <span>{pitch.pitchType}</span>
              <div className="distribution-track" aria-hidden="true">
                <span style={{ width: `${pitch.percentage}%` }} />
              </div>
              <strong>{pitch.percentage}%</strong>
            </div>
          ))}
        </div>
        <p className="count-detail__note">{selected.note}</p>
      </div>
    </section>
  );
}
