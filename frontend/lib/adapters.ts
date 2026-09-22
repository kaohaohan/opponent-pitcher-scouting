import type {
  AlertDto,
  GameParticipantDto,
  PlateAppearanceDto,
  PlayerDto,
  PregameBriefResponseDto,
  PregameContextDto,
  PitchCountUsageDto,
  PitchTypeUsageDto,
} from "@/lib/api";
import type {
  AlertData,
  AlertsSummaryData,
  BriefSectionData,
  CountBucketData,
  PitcherProfileData,
  PitchUsageData,
  PlayerWatchData,
  PlateAppearanceData,
} from "@/lib/types";

const pitchNames: Record<string, string> = {
  CH: "Changeup",
  CU: "Curveball",
  FC: "Cutter",
  FF: "Four-seam",
  FS: "Splitter",
  KC: "Knuckle curve",
  SI: "Sinker",
  SL: "Slider",
  ST: "Sweeper",
  SV: "Slurve",
  FA: "Fastball",
};

const resultCodes: Record<string, string> = {
  "Caught Stealing": "CS",
  Double: "2B",
  Flyout: "F",
  Groundout: "GO",
  "Home Run": "HR",
  Lineout: "LO",
  Sacrifice: "SAC",
  Single: "1B",
  Strikeout: "K",
  Walk: "BB",
};

function pitchName(pitchType: string): string {
  return pitchNames[pitchType.toUpperCase()] ?? pitchType;
}

function pitchTone(pitchType: string): PitchUsageData["tone"] {
  const code = pitchType.toUpperCase();
  if (["CH", "FS", "FO", "SC"].includes(code)) return "offspeed";
  if (["CU", "KC", "SL", "ST", "SV"].includes(code)) return "breaking";
  if (["FA", "FC", "FF", "SI", "FT", "FO"].includes(code)) return "fastball";
  return "other";
}

function formatDate(value: string, includeYear: boolean): string {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    ...(includeYear ? { year: "numeric" } : {}),
  }).format(date);
}

function formatDateRange(startDate: string, endDate: string, short = false): string {
  const start = formatDate(startDate, !short);
  const end = formatDate(endDate, !short);
  return start === "—" || end === "—" ? "—" : `${start} — ${end}`;
}

function toPitchUsage(row: PitchTypeUsageDto): PitchUsageData {
  return {
    pitchType: row.pitch_type,
    pitchName: pitchName(row.pitch_type),
    percentage: row.percentage,
    sampleSize: row.sample_size,
    status: row.status,
    tone: pitchTone(row.pitch_type),
  };
}

const countLeverage: Record<string, string> = {
  "0-0": "First pitch",
  "0-1": "Hitter behind",
  "0-2": "Pitcher ahead",
  "1-0": "Hitter ahead",
  "1-1": "Neutral",
  "1-2": "Pitcher ahead",
  "2-0": "Hitter ahead",
  "2-1": "Hitter ahead",
  "2-2": "Put-away",
  "3-0": "Hitter ahead",
  "3-1": "Hitter ahead",
  "3-2": "Full count",
};

function countBucketKey(row: PitchCountUsageDto): string {
  return `${row.balls}-${row.strikes}`;
}

function toCountBucket(rows: PitchCountUsageDto[]): CountBucketData {
  const first = rows[0];
  const sorted = [...rows].sort((left, right) => right.count - left.count);
  const key = countBucketKey(first);
  const primary = sorted[0];

  return {
    id: key,
    label: `${first.balls}–${first.strikes}`,
    leverage: countLeverage[key] ?? "Count tendency",
    primaryPitch: primary.pitch_type,
    percentage: primary.percentage,
    sampleSize: first.sample_size,
    status: first.status,
    pitchDistribution: sorted.map((row) => ({
      pitchType: row.pitch_type,
      percentage: row.percentage,
    })),
    note:
      first.status === "insufficient_sample"
        ? `Only ${first.sample_size} tracked pitches reached this count. Treat the displayed mix as descriptive, not predictive.`
        : `${pitchName(primary.pitch_type)} leads this count's observed pitch mix.`,
  };
}

function toBriefSections(response: PregameBriefResponseDto): BriefSectionData[] {
  const sections: BriefSectionData[] = [];
  if (response.brief.trim()) {
    sections.push({
      title: "Things to Watch",
      kind: "analysis",
      text: response.brief.trim(),
    });
  }
  if (response.context.limitations.length > 0) {
    sections.push({
      title: "Data Limitations",
      kind: "limitation",
      text: response.context.limitations.join(" "),
    });
  }
  return sections;
}

function toPitcherProfile(context: PregameContextDto): PitcherProfileData {
  return {
    id: context.pitcher_id,
    name: `Pitcher ID ${context.pitcher_id}`,
    throws: "—",
    team: "—",
    startDate: context.start_date,
    endDate: context.end_date,
    dateRangeLabel: formatDateRange(context.start_date, context.end_date),
    dateRangeShortLabel: formatDateRange(context.start_date, context.end_date, true),
    totalPitches: context.total_pitches,
    averageVelocity: null,
    overallStatus: context.overall_status,
  };
}

export function emptyPregameViewModel(): {
  pitcher: PitcherProfileData;
  pitches: PitchUsageData[];
  counts: CountBucketData[];
  brief: BriefSectionData[];
} {
  return {
    pitcher: {
      id: null,
      name: "Choose a pitcher",
      throws: "—",
      team: "—",
      startDate: "",
      endDate: "",
      dateRangeLabel: "—",
      dateRangeShortLabel: "—",
      totalPitches: 0,
      averageVelocity: null,
      overallStatus: "insufficient_sample",
    },
    pitches: [],
    counts: [],
    brief: [],
  };
}

export function toPregameViewModel(response: PregameBriefResponseDto) {
  const byCount = new Map<string, PitchCountUsageDto[]>();
  for (const row of response.context.pitch_usage_by_count) {
    const key = countBucketKey(row);
    byCount.set(key, [...(byCount.get(key) ?? []), row]);
  }

  return {
    pitcher: toPitcherProfile(response.context),
    pitches: response.context.pitch_usage_by_type.map(toPitchUsage),
    counts: [...byCount.values()].map(toCountBucket),
    brief: toBriefSections(response),
  };
}

export interface WatchSubject {
  id: number;
  name: string;
  team: string;
  role: "batter" | "pitcher";
}

export function subjectFromParticipant(
  participant: GameParticipantDto,
  role: "batter" | "pitcher",
): WatchSubject {
  return {
    id: participant.player_id,
    name: participant.name,
    team: participant.team_name,
    role,
  };
}

function toPlateAppearance(
  event: PlateAppearanceDto,
  role: "batter" | "pitcher" = "batter",
): PlateAppearanceData {
  const pitch = event.pitch_type ?? "—";
  const opponent = role === "pitcher" ? event.batter_name : event.pitcher_name;
  const description =
    role === "pitcher"
      ? `${event.result} allowed to ${event.batter_name}.`
      : `${event.result} against ${event.pitcher_name}.`;
  return {
    id: String(event.id),
    inning: `Inning ${event.inning}`,
    opponent,
    pitcher: event.pitcher_name,
    batter: event.batter_name,
    result: event.result,
    resultCode: resultCodes[event.result] ?? event.result.slice(0, 3).toUpperCase(),
    pitchType: pitch,
    pitchVelocity: event.pitch_velocity,
    exitVelocity: event.exit_velocity,
    description,
  };
}

export function toPlayerWatchData(
  player: PlayerDto | WatchSubject,
  events: PlateAppearanceDto[],
  alerts: AlertDto[],
  role: "batter" | "pitcher" = "batter",
): PlayerWatchData | null {
  const completedEvents = events.filter((event) => event.is_complete);
  if (completedEvents.length === 0) return null;

  const sortedEvents = [...completedEvents].sort((left, right) => right.id - left.id);
  const latest = sortedEvents[0];
  const recentAlerts = alerts.filter((alert) =>
    alert.subject_role === role &&
    sortedEvents.some((event) => event.id === alert.plate_appearance_id),
  );
  const triggeredRules = recentAlerts
    .filter((alert) => alert.plate_appearance_id === latest.id)
    .map((alert) => ({
      rule: alert.rule_type.replaceAll("_", " "),
      detail: alert.message,
    }));

  return {
    role,
    name: player.name,
    jerseyNumber: "—",
    team: player.team,
    opponent: "—",
    gameState: `Latest recorded event · ${latest.game_id}`,
    todayLine: "—",
    latestPlateAppearance: toPlateAppearance(latest, role),
    triggeredRules,
    recentPlateAppearances: sortedEvents.map((event) => toPlateAppearance(event, role)),
  };
}

const validRules = new Set<AlertData["rule"]>([
  "extra_base_hit",
  "hard_contact",
  "high_velocity_hit",
  "pitcher_extra_base_hit_allowed",
  "pitcher_high_exit_velocity_allowed",
]);

function toAlertRule(ruleType: string): AlertData["rule"] {
  return validRules.has(ruleType as AlertData["rule"])
    ? (ruleType as AlertData["rule"])
    : "hard_contact";
}

function relativeTime(value: string): string {
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "—";
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (elapsedSeconds < 60) return "just now";
  if (elapsedSeconds < 3600) return `${Math.floor(elapsedSeconds / 60)}m ago`;
  if (elapsedSeconds < 86400) return `${Math.floor(elapsedSeconds / 3600)}h ago`;
  return `${Math.floor(elapsedSeconds / 86400)}d ago`;
}

function isToday(value: string): boolean {
  const date = new Date(value);
  const today = new Date();
  return (
    date.getFullYear() === today.getFullYear() &&
    date.getMonth() === today.getMonth() &&
    date.getDate() === today.getDate()
  );
}

export function toAlertData(
  alert: AlertDto,
  playersById: Map<number, PlayerDto>,
  eventsById: Map<number, PlateAppearanceDto>,
): AlertData {
  const event = eventsById.get(alert.plate_appearance_id);
  const player = event ? playersById.get(event.player_id) : undefined;
  const rule = toAlertRule(alert.rule_type);
  const subject =
    alert.subject_role === "pitcher"
      ? {
          name: event?.pitcher_name ?? "Unknown pitcher",
          team: event?.pitcher_team ?? "—",
        }
      : {
          name: player?.name ?? event?.batter_name ?? "Unknown player",
          team: player?.team ?? event?.batter_team ?? "—",
        };

  return {
    id: String(alert.id),
    player: subject.name,
    team: subject.team,
    subjectRole: alert.subject_role,
    event: event?.result ?? "Rule matched",
    detail: alert.message,
    gameMoment: event ? `Inning ${event.inning}` : "Recorded alert",
    timestamp: relativeTime(alert.created_at),
    rule,
    severity:
      rule === "extra_base_hit" ||
      rule === "hard_contact" ||
      rule === "pitcher_extra_base_hit_allowed" ||
      rule === "pitcher_high_exit_velocity_allowed"
        ? "high"
        : "standard",
  };
}

export function toAlertsSummary(
  alerts: AlertDto[],
  players: PlayerDto[],
): AlertsSummaryData {
  return {
    today: alerts.filter((alert) => isToday(alert.created_at)).length,
    highPriority: alerts.filter(
      (alert) =>
        alert.rule_type === "extra_base_hit" ||
        alert.rule_type === "hard_contact" ||
        alert.rule_type === "pitcher_extra_base_hit_allowed" ||
        alert.rule_type === "pitcher_high_exit_velocity_allowed",
    ).length,
    trackedPlayers: players.length,
  };
}
