const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { next: { revalidate: 30 } });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

// ── Types ────────────────────────────────────────────────────────────

export interface MlPrediction {
  entrant_id: string;
  name: string;
  runner_number: number;
  barrier: number;
  jockey: string;
  trainer: string;
  tab_fixed_win: number | null;
  tab_implied_prob: number;   // already as %, e.g. 23.8
  model_prob: number;         // %, e.g. 28.5
  model_odds: number;
  value_edge: number;         // %, e.g. +4.7
  value_pct: number;
  is_value_bet: boolean;
  fluc_drift: number | null;
  is_market_mover: boolean;
  is_favourite: boolean;
  speedmap_label: string;
  speedmap_label_enc: number;
  shap_top_features: { feature: string; value: number; shap: number }[];
}

export interface Runner {
  entrant_id: string;
  name: string;
  runner_number: number;
  barrier: number;
  jockey: string;
  trainer: string;
  weight: unknown;
  age: number;
  sex: string;
  is_scratched: boolean;
  is_late_scratched: boolean;
  is_favourite: boolean;
  is_mover: boolean;
  silk_url: string | null;
  form_comment_short: string | null;
  last_twenty_starts: string | null;
  odds: { fixed_win: number | null; fixed_place: number | null; pool_win: number | null; pool_place: number | null };
  flucs_sparkline: (number | null)[];
  speedmap: { label: string; barrier_speed: number; finish_speed: number; settling_lengths: number } | null;
  form_indicators: { group: string; name: string; negative: boolean; priority: number }[];
  ml: MlPrediction | null;
}

export interface RaceDetail {
  race: {
    event_id: string;
    meeting_name: string;
    display_name: string;
    race_number: number;
    distance: number;
    class: string;
    track_condition: string;
    track_surface: string;
    track_direction: string;
    rail_position: string;
    weather: string;
    start_time: string;
    status: string;
    field_size: number;
    prize_money: Record<string, number> | null;
    group: string;
  };
  runners: Runner[];
  money_tracker: { entrants: { entrant_id: string; bet_percentage: number; hold_percentage: number }[] } | null;
  big_bets: unknown[];
  biggest_bet: unknown;
  model_available: boolean;
}

export interface MeetingRace {
  event_id: string;
  race_number: number;
  name: string;
  distance: number;
  status: string;
  start_time: string;
  track_condition: string;
  weather: string;
  country: string;
}

export interface Meeting {
  meeting_id: string;
  name: string;
  country: string;
  state: string;
  track_condition: string;
  races: MeetingRace[];
}

export interface ValueOpportunity {
  event_id: string;
  meeting: string;
  race_number: number;
  start_time: string;
  status: string;
  runner: string;
  entrant_id: string;
  barrier: number;
  jockey: string;
  ml_prob: number;
  ml_odds: number;
  tab_odds: number | null;
  tab_implied: number;
  value_edge: number;
  fluc_drift: number | null;
  is_mover: boolean;
}

export interface TrackerBet {
  id: number;
  event_id: string;
  race_label: string;
  runner: string;
  model_odds: number;
  tab_odds: number | null;
  value_edge: number;
  flagged_at: string | null;
  result_position: number | null;
  won: boolean | null;
  placed: boolean | null;
  pl: number | null;
}

// ── Fetch helpers ────────────────────────────────────────────────────

export const getMeetingsToday = () =>
  apiFetch<{ meetings: Meeting[]; date: string }>("/api/meetings/today");

export const getRaceDetail = (eventId: string) =>
  apiFetch<RaceDetail>(`/api/race/${eventId}`);

export const getRaceResults = (eventId: string) =>
  apiFetch<{ event_id: string; results: unknown[] }>(`/api/race/${eventId}/results`);

export const getValueToday = () =>
  apiFetch<{ opportunities: ValueOpportunity[]; count: number }>("/api/value/today");

export const getTrackerHistory = (limit = 50) =>
  apiFetch<{ bets: TrackerBet[]; summary: unknown }>(`/api/tracker/history?limit=${limit}`);
