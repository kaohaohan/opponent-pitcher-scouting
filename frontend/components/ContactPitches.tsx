import { DataState } from "@/components/DataState";
import { displayName } from "@/components/PitchLocations";
import type { ContactPitchDto, ContactPitchesDto } from "@/lib/api";

const REGION_LABELS: Record<NonNullable<ContactPitchDto["region"]>, string> = {
  heart: "Heart",
  shadow: "Shadow",
  chase: "Chase",
  waste: "Waste",
};

function orDash(value: string | number | null): string {
  return value === null ? "—" : String(value);
}

function formatVelocity(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)} mph`;
}

function formatCount(balls: number | null, strikes: number | null): string {
  if (balls === null || strikes === null) return "—";
  return `${balls}-${strikes}`;
}

function formatRegion(region: ContactPitchDto["region"]): string {
  return region === null ? "—" : REGION_LABELS[region];
}

function formatLaunchAngle(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)}°`;
}

function formatThreshold(threshold: number): string {
  return Number.isInteger(threshold) ? String(threshold) : threshold.toFixed(1);
}

export function ContactPitches({
  contactPitches,
  isLoading,
  error,
  onRetry,
}: {
  contactPitches: ContactPitchesDto | null;
  isLoading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  const pitches = contactPitches?.pitches ?? [];
  const threshold = contactPitches ? formatThreshold(contactPitches.high_ev_threshold_mph) : null;

  return (
    <section className="panel contact-pitches" aria-labelledby="contact-pitches-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Today&apos;s pitches</p>
          <h2 id="contact-pitches-title">Contact Pitches</h2>
        </div>
        {contactPitches ? (
          <span className="panel-heading__meta">
            {pitches.length} card{pitches.length === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>
      {error ? (
        <DataState kind="error" onRetry={onRetry}>{error}</DataState>
      ) : isLoading && !contactPitches ? (
        <DataState kind="loading">Loading contact pitches…</DataState>
      ) : pitches.length === 0 ? (
        <DataState>
          No home runs or {threshold ?? "100"}+ mph contact allowed yet.
        </DataState>
      ) : (
        <>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Inning</th>
                  <th>Batter</th>
                  <th>Outcome</th>
                  <th>Pitch</th>
                  <th>Velocity</th>
                  <th>Count</th>
                  <th>Side</th>
                  <th>Region</th>
                  <th>Exit velo</th>
                  <th>Launch angle</th>
                </tr>
              </thead>
              <tbody>
                {pitches.map((pitch, index) => (
                  <tr key={pitch.at_bat_index ?? index}>
                    <td>{orDash(pitch.inning)}</td>
                    <td>{orDash(pitch.batter_name)}</td>
                    <td>
                      <strong>{orDash(pitch.outcome)}</strong>
                    </td>
                    <td>
                      {pitch.pitch_type ? (
                        <span className="pitch-pill">{displayName(pitch.pitch_type)}</span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>{formatVelocity(pitch.pitch_velocity_mph)}</td>
                    <td>{formatCount(pitch.balls, pitch.strikes)}</td>
                    <td>{orDash(pitch.batter_side)}</td>
                    <td>{formatRegion(pitch.region)}</td>
                    <td>{formatVelocity(pitch.exit_velocity_mph)}</td>
                    <td>{formatLaunchAngle(pitch.launch_angle_deg)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="pitch-locations__view">
            Location shows where the pitch finished, not where it was aimed.
          </p>
        </>
      )}
    </section>
  );
}
