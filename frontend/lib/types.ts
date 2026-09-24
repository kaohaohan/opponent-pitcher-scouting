export type SampleStatus = "sufficient" | "insufficient_sample";

export type NavSection = "pregame" | "player-watch" | "alerts";

export interface PitcherProfileData {
  id: number | null;
  name: string;
  throws: "L" | "R" | "—";
  team: string;
  startDate: string;
  endDate: string;
  dateRangeLabel: string;
  dateRangeShortLabel: string;
  totalPitches: number;
  averageVelocity: number | null;
  overallStatus: SampleStatus;
}

export interface PitchUsageData {
  pitchType: string;
  pitchName: string;
  percentage: number;
  sampleSize: number;
  status: SampleStatus;
  tone: "fastball" | "breaking" | "offspeed" | "other";
}

export interface CountBucketData {
  id: string;
  label: string;
  leverage: string;
  primaryPitch: string;
  percentage: number;
  sampleSize: number;
  status: SampleStatus;
  pitchDistribution: Array<{
    pitchType: string;
    percentage: number;
  }>;
  note: string;
}

export interface BriefSectionData {
  title: "Pitch Mix" | "Count Tendencies" | "Things to Watch" | "Data Limitations";
  text: string;
  kind: "analysis" | "limitation";
}

export interface PlateAppearanceData {
  id: string;
  inning: string;
  opponent: string;
  pitcher: string;
  batter: string;
  result: string;
  resultCode: string;
  pitchType: string;
  pitchVelocity: number | null;
  exitVelocity: number | null;
  description: string;
}

export interface PlayerWatchData {
  role: "batter" | "pitcher";
  playerId: number;
  name: string;
  jerseyNumber: string;
  team: string;
  opponent: string;
  gameState: string;
  todayLine: string;
  latestPlateAppearance: PlateAppearanceData;
  triggeredRules: Array<{
    rule: string;
    detail: string;
  }>;
  recentPlateAppearances: PlateAppearanceData[];
}

export interface AlertData {
  id: string;
  player: string;
  team: string;
  subjectRole: "batter" | "pitcher";
  event: string;
  detail: string;
  gameMoment: string;
  timestamp: string;
  rule:
    | "extra_base_hit"
    | "hard_contact"
    | "high_velocity_hit"
    | "pitcher_extra_base_hit_allowed"
    | "pitcher_high_exit_velocity_allowed";
  severity: "standard" | "high";
}

export interface AlertsSummaryData {
  today: number;
  highPriority: number;
  trackedPlayers: number;
}

export interface PitcherRefData {
  id: number;
  name: string;
}

export interface GameSummaryData {
  gameId: string;
  gameDate: string;
  startTime: string | null;
  status: string;
  state: "live" | "upcoming" | "final" | "other";
  awayTeam: { id: number | null; name: string };
  homeTeam: { id: number | null; name: string };
  awayScore: number | null;
  homeScore: number | null;
  inning: number | null;
  inningHalf: "top" | "bottom" | null;
  inningState: string | null;
  outs: number | null;
  currentPitcher: PitcherRefData | null;
  currentPitcherTeamSide: "away" | "home" | null;
  probablePitchers: {
    away: PitcherRefData | null;
    home: PitcherRefData | null;
  };
  pitchersUsed: {
    away: PitcherRefData[];
    home: PitcherRefData[];
  };
  //: e.g. "Top 5th · 1 Out", "Final", or a formatted start time — omits
  // parts that are null rather than rendering a placeholder for them.
  stateLabel: string;
}

export interface SignalData {
  level: "watch" | "alert";
  metric: "usage" | "velocity";
  pitchType: string;
  pitchName: string | null;
  baselineValue: number;
  todayValue: number;
  delta: number;
  sampleBasis: number;
}

export interface PitchComparisonRowData {
  pitchType: string;
  pitchName: string;
  tone: "fastball" | "breaking" | "offspeed" | "other";
  baselineUsagePct: number | null;
  baselineVelocity: number | null;
  baselineSampleSize: number;
  liveUsagePct: number | null;
  liveVelocity: number | null;
  liveSampleSize: number;
  usageDeltaPp: number | null;
  velocityDelta: number | null;
  status: SampleStatus;
  isNotable: boolean;
}

export interface PregameLiveComparisonData {
  gameId: string;
  pitcherId: number;
  pitcherName: string | null;
  baselineStartDate: string;
  baselineEndDate: string;
  baselineAvailable: boolean;
  baselineTotalPitches: number;
  liveAvailable: boolean;
  liveTotalPitches: number;
  overallLiveStatus: SampleStatus;
  rows: PitchComparisonRowData[];
  signals: SignalData[];
  limitations: string[];
}

export interface ComparisonNoteData {
  summary: string;
  notableChanges: Array<{ metric: string; description: string }>;
  sampleNote: string;
}
