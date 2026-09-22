import { CountTendencies } from "@/components/CountTendencies";
import { PitchMix } from "@/components/PitchMix";
import { PregameBrief } from "@/components/PregameBrief";
import { PregameControls } from "@/components/PregameControls";
import { SampleSizeBadge } from "@/components/SampleSizeBadge";
import type {
  BriefSectionData,
  CountBucketData,
  PitcherProfileData,
  PitchUsageData,
} from "@/lib/types";
import { DataState } from "@/components/DataState";

interface PregameDashboardProps {
  pitcher: PitcherProfileData;
  pitches: PitchUsageData[];
  counts: CountBucketData[];
  brief: BriefSectionData[];
  isLoading?: boolean;
  statusMessage?: string;
  error?: string;
  initialPitcherId?: number;
  initialPitcherName?: string;
  initialPitcherTeam?: string | null;
  onRetry?: () => void;
  onGenerate?: (request: {
    pitcherId: number;
    startDate: string;
    endDate: string;
    pitcherName?: string;
    pitcherTeam?: string | null;
  }) => void;
}

export function PregameDashboard({
  pitcher,
  pitches,
  counts,
  brief,
  isLoading = false,
  statusMessage,
  error,
  initialPitcherId,
  initialPitcherName,
  initialPitcherTeam,
  onRetry,
  onGenerate,
}: PregameDashboardProps) {
  const hasGeneratedProfile = pitcher.id !== null && pitcher.startDate !== "" && pitcher.endDate !== "";

  return (
    <div className="pregame-grid">
      <section className="panel profile-panel" aria-labelledby="pitcher-profile-title">
        <div className="panel-heading">
          <div>
            <p className="section-kicker">Scouting window</p>
            <h2 id="pitcher-profile-title">Pitcher Profile</h2>
          </div>
          <span className="handedness">{pitcher.throws === "—" ? "—" : `${pitcher.throws}HP`}</span>
        </div>

        <div className="pitcher-identity">
          <div>
            <h3>{pitcher.name}</h3>
            {pitcher.team === "—" ? null : <p>{pitcher.team}</p>}
          </div>
        </div>

        {hasGeneratedProfile ? (
          <dl className="profile-stats">
            <div>
              <dt>Date range</dt>
              <dd>{pitcher.dateRangeShortLabel}</dd>
            </div>
            <div>
              <dt>Total pitches</dt>
              <dd>{pitcher.totalPitches.toLocaleString()}</dd>
            </div>
            {pitcher.averageVelocity === null ? null : (
              <div>
                <dt>Avg velocity</dt>
                <dd>
                  {pitcher.averageVelocity.toFixed(1)}
                  <span> mph</span>
                </dd>
              </div>
            )}
            <div>
              <dt>Sample quality</dt>
              <dd>
                <SampleSizeBadge status={pitcher.overallStatus} />
              </dd>
            </div>
          </dl>
        ) : null}

        <div className="panel-divider" />
        <PregameControls
          initialPitcherId={initialPitcherId}
          initialPitcherName={initialPitcherName}
          initialPitcherTeam={initialPitcherTeam}
          isGenerating={isLoading}
          onGenerate={onGenerate}
          pitcher={pitcher}
          statusMessage={statusMessage}
        />
      </section>

      <div className="pregame-center">
        <PitchMix pitches={pitches} />
        <CountTendencies buckets={counts} />
      </div>

      <PregameBrief sections={brief} />
      {error ? <DataState kind="error" onRetry={onRetry}>{error}</DataState> : null}
    </div>
  );
}
