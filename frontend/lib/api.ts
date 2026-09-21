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

export interface AlertDto {
  id: number;
  plate_appearance_id: number;
  rule_type: string;
  message: string;
  created_at: string;
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

export function getEvents(playerId?: number, limit = 200): Promise<PlateAppearanceDto[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (playerId !== undefined) params.set("player_id", String(playerId));
  return fetchJson<PlateAppearanceDto[]>(`/api/events?${params.toString()}`);
}

export function getAlerts(limit = 200): Promise<AlertDto[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return fetchJson<AlertDto[]>(`/api/alerts?${params.toString()}`);
}

export function generatePregameBrief(
  request: PregameBriefRequest,
): Promise<PregameBriefResponseDto> {
  return fetchJson<PregameBriefResponseDto>("/api/pregame/brief", {
    method: "POST",
    body: JSON.stringify(request),
  });
}
