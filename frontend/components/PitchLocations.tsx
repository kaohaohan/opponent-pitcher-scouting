import { DataState } from "@/components/DataState";
import type { PitchLocationsDto } from "@/lib/api";
import { useState } from "react";

const PITCH_COLORS: Record<string, string> = {
  FF: "#63a9d8", SI: "#e3b65d", SL: "#e97668", CH: "#52c58a",
  CU: "#aa8ce0", FC: "#e59960", FS: "#6dcfc4", ST: "#ed80b4",
  KC: "#a6c86a", FA: "#8ca4ee", FT: "#e9ca79", FO: "#70b8a1",
  EP: "#d399db", KN: "#b9a98a", SC: "#d8a0a0", SV: "#90c3e0",
};

function colorForType(code: string): string {
  if (PITCH_COLORS[code]) return PITCH_COLORS[code];
  let hash = 0;
  for (const char of code) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return `hsl(${hash % 360} 68% 69%)`;
}

export function displayName(code: string): string {
  return ({ FF: "Four-seam", SI: "Sinker", SL: "Slider", CH: "Changeup", CU: "Curveball",
    FC: "Cutter", FS: "Splitter", ST: "Sweeper", KC: "Knuckle curve", FA: "Fastball",
    FT: "Two-seam", FO: "Forkball", EP: "Eephus", KN: "Knuckleball", SC: "Screwball",
    SV: "Slurve" } as Record<string, string>)[code] ?? code;
}

function plotX(plateX: number): number {
  const linear = 200 + plateX * (80 / (17 / 24));
  if (linear < 120) return 120 - 100 * Math.tanh((120 - linear) / 80);
  if (linear > 280) return 280 + 100 * Math.tanh((linear - 280) / 80);
  return linear;
}

function plotY(plateZ: number, bottom: number, top: number): number {
  const normalized = (plateZ - bottom) / (top - bottom);
  if (normalized < 0) return 310 + 100 * Math.tanh(-normalized);
  if (normalized > 1) return 90 - 100 * Math.tanh(normalized - 1);
  return 310 - normalized * 220;
}

export function PitchLocations({
  locations,
  isLoading,
  error,
  onRetry,
}: {
  locations: PitchLocationsDto | null;
  isLoading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  const [selectedType, setSelectedType] = useState("all");
  const points = locations?.points ?? [];
  const types = [...new Set(points.map((point) => point.pitch_type))].sort();
  const visiblePoints = selectedType === "all"
    ? points
    : points.filter((point) => point.pitch_type === selectedType);
  const plot = visiblePoints.map((point) => ({
    ...point,
    // pX increases to the catcher's right. A 17-inch plate is 1.417 feet wide.
    x: plotX(point.plate_x),
    // Each pitch gets its own measured zone before being placed on this shared zone.
    y: plotY(point.plate_z, point.sz_bot, point.sz_top),
  }));

  return (
    <section className="panel pitch-locations" aria-labelledby="pitch-locations-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Today&apos;s pitches</p>
          <h2 id="pitch-locations-title">Pitch locations</h2>
        </div>
        {locations ? <span className="panel-heading__meta">{visiblePoints.length} plotted / {locations.total_pitches} pitches</span> : null}
      </div>
      {error ? (
        <DataState kind="error" onRetry={onRetry}>{error}</DataState>
      ) : isLoading && !locations ? (
        <DataState kind="loading">Loading pitch locations…</DataState>
      ) : !locations || locations.total_pitches === 0 ? (
        <DataState>No pitches yet for this pitcher.</DataState>
      ) : points.length === 0 ? (
        <DataState>No usable pitch coordinates yet.</DataState>
      ) : (
        <div className="pitch-locations__content">
          <label className="pitch-locations__filter">
            Pitch type
            <select value={selectedType} onChange={(event) => setSelectedType(event.target.value)}>
              <option value="all">All pitches</option>
              {types.map((type) => <option key={type} value={type}>{displayName(type)}</option>)}
            </select>
          </label>
          <svg
            className="pitch-locations__plot"
            viewBox="-20 -20 440 460"
            role="img"
            aria-label={`Catcher's view of ${visiblePoints.length} pitch locations in a normalized nine-zone strike zone`}
          >
            <rect x="120" y="90" width="160" height="220" className="pitch-locations__zone" />
            {[1, 2].map((division) => (
              <g key={division} className="pitch-locations__grid">
                <line x1={120 + division * 160 / 3} x2={120 + division * 160 / 3} y1="90" y2="310" />
                <line x1="120" x2="280" y1={90 + division * 220 / 3} y2={90 + division * 220 / 3} />
              </g>
            ))}
            {plot.map((point, index) => (
              <circle key={index} cx={point.x} cy={point.y} r="5" fill={colorForType(point.pitch_type)} className="pitch-locations__dot">
                <title>{`${displayName(point.pitch_type)}: ${point.plate_x.toFixed(2)} ft horizontal, ${point.plate_z.toFixed(2)} ft high`}</title>
              </circle>
            ))}
          </svg>
          <p className="pitch-locations__view">Catcher&apos;s view · each pitch normalized to its measured strike zone · distant locations compressed</p>
          <ul className="pitch-locations__legend" aria-label="Pitch type colors">
            {types.map((type) => <li key={type}><span style={{ backgroundColor: colorForType(type) }} />{displayName(type)}</li>)}
          </ul>
        </div>
      )}
    </section>
  );
}
