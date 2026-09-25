export interface PlayerDto {
  id: number;
  external_player_id: string;
  name: string;
  team: string;
}

export interface PlateAppearanceDto {
  id: number;
  game_id: string;
  player_id: number;
  batter_player_id: number;
  pitcher_player_id: number | null;
  batter_id: string;
  batter_name: string;
  batter_team: string;
  pitcher_id: string | null;
  pitcher_name: string;
  pitcher_team: string | null;
  at_bat_index: number;
  inning: number;
  result: string;
  pitcher: string;
  pitch_type: string | null;
  pitch_velocity: number | null;
  exit_velocity: number | null;
  launch_angle: number | null;
  is_complete: boolean;
}

export interface LiveSyncRequest {
  game_id: number;
  watched_player_ids?: number[];
  batter_ids?: number[];
  pitcher_ids?: number[];
}

export interface LiveSyncReport {
  source: "live";
  game_id: string;
  game_state: string | null;
  game_status: string | null;
  events_read: number;
  stored: number;
  duplicates: number;
  ignored_incomplete: number;
  invalid: number;
  alerts_created: number;
  source_error: string | null;
}

export interface AlertDto {
  id: number;
  plate_appearance_id: number;
  subject_role: "batter" | "pitcher";
  rule_type: string;
  message: string;
  created_at: string;
}

export interface PitchMixAlertDto {
  id: number;
  game_id: string;
  pitcher_id: number;
  pitcher_name: string;
  team_name: string | null;
  metric: "usage" | "velocity";
  pitch_type: string;
  pitch_name: string | null;
  level: "watch" | "alert";
  baseline_value: number;
  today_value: number;
  delta: number;
  sample_basis: number;
  raised_at_pitches: number;
  active: boolean;
  first_raised_at: string;
  updated_at: string;
}

export interface TeamDto {
  id: number | null;
  name: string;
}

export interface PitchingLineDto {
  order: number;
  innings_pitched: string | null;
  pitches: number | null;
  hits: number | null;
  runs: number | null;
  earned_runs: number | null;
  walks: number | null;
  strikeouts: number | null;
}

export interface GameParticipantDto {
  player_id: number;
  name: string;
  team_id: number | null;
  team_name: string;
  team_side: "away" | "home";
  roles: Array<"batter" | "pitcher">;
  /** Set only for pitchers who actually appeared in this game. */
  pitching_line?: PitchingLineDto | null;
}

export interface GameParticipantsDto {
  game_id: string;
  game_state: string | null;
  game_status: string | null;
  teams: {
    away: TeamDto;
    home: TeamDto;
  };
  participants: GameParticipantDto[];
}

export type SampleStatusDto = "sufficient" | "insufficient_sample";

export interface PitchTypeUsageDto {
  pitch_type: string;
  count: number;
  percentage: number;
  sample_size: number;
  status: SampleStatusDto;
}

export interface PitchCountUsageDto {
  balls: number;
  strikes: number;
  pitch_type: string;
  count: number;
  percentage: number;
  sample_size: number;
  status: SampleStatusDto;
}

export interface PregameContextDto {
  pitcher_id: number;
  start_date: string;
  end_date: string;
  total_pitches: number;
  pitch_usage_by_type: PitchTypeUsageDto[];
  pitch_usage_by_count: PitchCountUsageDto[];
  overall_status: SampleStatusDto;
  limitations: string[];
}

export interface PregameBriefResponseDto {
  context: PregameContextDto;
  brief: string;
}

export interface PregameBriefRequest {
  pitcher_id: number;
  start_date: string;
  end_date: string;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/backend${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  const body = (await response.json().catch(() => null)) as
    | { detail?: string }
    | T
    | null;

  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body && typeof body.detail === "string"
        ? body.detail
        : `Request failed with status ${response.status}.`;
    throw new ApiError(detail, response.status);
  }

  return body as T;
}

export function getPlayers(): Promise<PlayerDto[]> {
  return fetchJson<PlayerDto[]>("/api/players");
}

export function getEvents(
  playerId?: number,
  limit = 200,
  gameId?: string,
  batterId?: number,
  pitcherId?: number,
): Promise<PlateAppearanceDto[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (playerId !== undefined) params.set("player_id", String(playerId));
  if (gameId) params.set("game_id", gameId);
  if (batterId !== undefined) params.set("batter_id", String(batterId));
  if (pitcherId !== undefined) params.set("pitcher_id", String(pitcherId));
  return fetchJson<PlateAppearanceDto[]>(`/api/events?${params.toString()}`);
}

export function getGameParticipants(gameId: number): Promise<GameParticipantsDto> {
  return fetchJson<GameParticipantsDto>(`/api/live/games/${gameId}/participants`);
}

export interface PitcherRefDto {
  id: number;
  name: string;
}

export interface GameSummaryDto {
  game_id: string;
  game_date: string;
  start_time: string | null;
  status: string;
  state: "live" | "upcoming" | "final" | "other";
  away_team: TeamDto;
  home_team: TeamDto;
  away_score: number | null;
  home_score: number | null;
  inning: number | null;
  inning_half: "top" | "bottom" | null;
  inning_state: string | null;
  outs: number | null;
  current_pitcher: PitcherRefDto | null;
  current_pitcher_team_side: "away" | "home" | null;
  probable_pitchers: {
    away: PitcherRefDto | null;
    home: PitcherRefDto | null;
  };
  // Each team's pitchers in order of appearance; last = current/most recent.
  // Only the single-game summary fills this; the schedule sends empty lists.
  pitchers_used: {
    away: PitcherRefDto[];
    home: PitcherRefDto[];
  };
}

export function getSchedule(date: string): Promise<GameSummaryDto[]> {
  const params = new URLSearchParams({ date });
  return fetchJson<GameSummaryDto[]>(`/api/live/games?${params.toString()}`);
}

export function getGameSummary(gameId: number): Promise<GameSummaryDto> {
  return fetchJson<GameSummaryDto>(`/api/live/games/${gameId}/summary`);
}

export function syncLive(request: LiveSyncRequest): Promise<LiveSyncReport> {
  return fetchJson<LiveSyncReport>("/api/live/sync", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getAlerts(limit = 200): Promise<AlertDto[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return fetchJson<AlertDto[]>(`/api/alerts?${params.toString()}`);
}

export function getPitchMixAlerts(limit = 200): Promise<PitchMixAlertDto[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return fetchJson<PitchMixAlertDto[]>(`/api/pitch-mix-alerts?${params.toString()}`);
}

export function generatePregameBrief(
  request: PregameBriefRequest,
): Promise<PregameBriefResponseDto> {
  return fetchJson<PregameBriefResponseDto>("/api/pregame/brief", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export interface PitcherSearchResultDto {
  id: number;
  name: string;
  team: string | null;
  throws: string | null;
}

export function searchPitchers(query: string): Promise<PitcherSearchResultDto[]> {
  const params = new URLSearchParams({ query });
  return fetchJson<PitcherSearchResultDto[]>(`/api/pregame/pitchers/search?${params.toString()}`);
}

export interface PregameLiveComparisonRowDto {
  pitch_type: string;
  baseline_usage_pct: number | null;
  baseline_velocity: number | null;
  baseline_sample_size: number;
  live_usage_pct: number | null;
  live_velocity: number | null;
  live_sample_size: number;
  usage_delta_pp: number | null;
  velocity_delta: number | null;
  status: SampleStatusDto;
  is_notable: boolean;
}

export interface SignalDto {
  level: "watch" | "alert";
  metric: "usage" | "velocity";
  pitch_type: string;
  pitch_name: string | null;
  baseline_value: number;
  today_value: number;
  delta: number;
  sample_basis: number;
}

export interface PregameLiveComparisonDto {
  game_id: string;
  pitcher_id: number;
  pitcher_name: string | null;
  baseline_start_date: string;
  baseline_end_date: string;
  baseline_available: boolean;
  baseline_total_pitches: number;
  live_available: boolean;
  live_total_pitches: number;
  overall_live_status: SampleStatusDto;
  rows: PregameLiveComparisonRowDto[];
  signals: SignalDto[];
  limitations: string[];
}

export interface PitchLocationDto {
  pitch_type: string;
  plate_x: number;
  plate_z: number;
  sz_top: number;
  sz_bot: number;
}

export interface PitchLocationsDto {
  total_pitches: number;
  points: PitchLocationDto[];
}

export function getPitchLocations(gameId: number, pitcherId: number): Promise<PitchLocationsDto> {
  return fetchJson<PitchLocationsDto>(`/api/live/games/${gameId}/pitchers/${pitcherId}/locations`);
}

export interface ContactPitchDto {
  at_bat_index: number | null;
  inning: number | null;
  batter_name: string | null;
  reasons: Array<"home_run" | "high_ev_contact">;
  outcome: string | null;
  pitch_type: string | null;
  pitch_velocity_mph: number | null;
  balls: number | null;
  strikes: number | null;
  batter_side: "L" | "R" | null;
  plate_x: number | null;
  plate_z: number | null;
  sz_top: number | null;
  sz_bot: number | null;
  region: "heart" | "shadow" | "chase" | "waste" | null;
  exit_velocity_mph: number | null;
  launch_angle_deg: number | null;
}

export interface ContactPitchesDto {
  high_ev_threshold_mph: number;
  pitches: ContactPitchDto[];
}

export function getContactPitches(gameId: number, pitcherId: number): Promise<ContactPitchesDto> {
  return fetchJson<ContactPitchesDto>(
    `/api/live/games/${gameId}/pitchers/${pitcherId}/contact-pitches`,
  );
}

export interface NotableChangeDto {
  metric: string;
  description: string;
}

export interface ComparisonNoteDto {
  summary: string;
  notable_changes: NotableChangeDto[];
  sample_note: string;
}

export function getPregameLiveComparison(
  gameId: number,
  pitcherId: number,
  startDate: string,
  endDate: string,
): Promise<PregameLiveComparisonDto> {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate });
  return fetchJson<PregameLiveComparisonDto>(
    `/api/live/games/${gameId}/pitchers/${pitcherId}/comparison?${params.toString()}`,
  );
}

export function generateComparisonNote(
  gameId: number,
  pitcherId: number,
  startDate: string,
  endDate: string,
): Promise<ComparisonNoteDto> {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate });
  return fetchJson<ComparisonNoteDto>(
    `/api/live/games/${gameId}/pitchers/${pitcherId}/comparison/note?${params.toString()}`,
    { method: "POST" },
  );
}
