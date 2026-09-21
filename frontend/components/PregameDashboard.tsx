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

interface PregameDashboardProps {
  pitcher: PitcherProfileData;
  pitches: PitchUsageData[];
  counts: CountBucketData[];
  brief: BriefSectionData[];
}

export function PregameDashboard({
  pitcher,
  pitches,
  counts,
  brief,
}: PregameDashboardProps) {
  return (
    <div className="pregame-grid">
      <section className="panel profile-panel" aria-labelledby="pitcher-profile-title">
        <div className="panel-heading">
          <div>
            <p className="section-kicker">Scouting window</p>
            <h2 id="pitcher-profile-title">Pitcher Profile</h2>
          </div>
          <span className="handedness">{pitcher.throws}HP</span>
        </div>

        <div className="pitcher-identity">
          <div className="pitcher-avatar" aria-hidden="true">
            {pitcher.name
              .split(" ")
              .map((part) => part[0])
              .join("")}
          </div>
          <div>
            <h3>{pitcher.name}</h3>
            <p>{pitcher.team}</p>
          </div>
        </div>

        <dl className="profile-stats">
          <div>
            <dt>Date range</dt>
            <dd>
              {pitcher.dateRangeShortLabel}
            </dd>
          </div>
          <div>
            <dt>Total pitches</dt>
            <dd>{pitcher.totalPitches.toLocaleString()}</dd>
          </div>
          <div>
            <dt>Avg velocity</dt>
            <dd>
              {pitcher.averageVelocity.toFixed(1)} <span>mph</span>
            </dd>
          </div>
          <div>
            <dt>Sample quality</dt>
            <dd>
              <SampleSizeBadge status={pitcher.overallStatus} />
            </dd>
          </div>
        </dl>

        <div className="panel-divider" />
        <PregameControls pitcher={pitcher} />
      </section>

      <div className="pregame-center">
        <PitchMix pitches={pitches} />
        <CountTendencies buckets={counts} />
      </div>

      <PregameBrief sections={brief} />
    </div>
  );
}
