"use client";

import { useState } from "react";
import { type RaceDetail, type Runner } from "@/lib/api";
import { edgeColor, edgeSign, formatOdds, formatProb, countdown } from "@/lib/utils";
import { TrendingUp, FileText, ChevronUp, ChevronDown } from "lucide-react";

interface Props {
  data: RaceDetail;
}

type Tab = "value" | "form";

export default function RaceDetailClient({ data }: Props) {
  const [tab, setTab] = useState<Tab>("value");
  const { race, runners, money_tracker, biggest_bet, model_available } = data;

  const active = runners.filter((r) => !r.is_scratched && !r.is_late_scratched);
  const sorted =
    tab === "value"
      ? [...active].sort((a, b) => (b.ml?.value_edge ?? -99) - (a.ml?.value_edge ?? -99))
      : [...active].sort((a, b) => (a.runner_number ?? 0) - (b.runner_number ?? 0));

  const holdPct = (() => {
    const entries = money_tracker?.entrants ?? [];
    const total = entries.reduce((s, e) => s + (e.hold_percentage ?? 0), 0);
    return total > 0 ? total.toFixed(1) : null;
  })();

  return (
    <div className="flex h-full">
      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Race header */}
        <div className="px-4 py-3 border-b border-[#2d3748] bg-[#0c0e11]">
          <div className="flex items-center gap-3 mb-1">
            <span className="bg-[#4edea3] text-[#003824] text-xs font-bold px-2 py-0.5">
              R{race.race_number}
            </span>
            <h2 className="text-[15px] font-bold text-[#e2e2e6]">
              {race.display_name ?? race.meeting_name} — {race.class ?? ""}
            </h2>
            <span className="ml-auto font-mono text-[#4edea3] text-lg font-bold">
              {race.start_time ? countdown(race.start_time) : race.status}
            </span>
          </div>
          <div className="flex items-center gap-4 text-[12px] text-[#bbcabf] font-mono">
            <span>{race.distance}M</span>
            {race.track_condition && <span>⛅ {race.track_condition?.toUpperCase()}</span>}
            {race.weather && <span>{race.weather}</span>}
            {race.rail_position && <span>Rail: {race.rail_position}</span>}
            {!model_available && (
              <span className="text-[#f59e0b] font-bold">⚠ No model — train first</span>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[#2d3748] bg-[#0c0e11]">
          {(["value", "form"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-[11px] font-bold tracking-wider transition-colors ${
                tab === t
                  ? "text-[#4edea3] border-b-2 border-[#4edea3]"
                  : "text-[#86948a] hover:text-[#e2e2e6]"
              }`}
            >
              {t === "value" ? "VALUE ANALYSIS" : "FORM GUIDE"}
            </button>
          ))}
        </div>

        {/* Runner table */}
        <div className="flex-1 overflow-auto">
          <table className="tt-table w-full">
            <thead>
              <tr>
                <th className="w-8">#</th>
                <th className="w-8">BAR</th>
                <th>RUNNER</th>
                <th>JOCKEY / TRAINER</th>
                <th>WGT</th>
                {tab === "value" ? (
                  <>
                    <th>ML WIN%</th>
                    <th>TAB WIN</th>
                    <th>IMPLIED</th>
                    <th>VALUE</th>
                    <th>FLUCTUATION</th>
                  </>
                ) : (
                  <>
                    <th>FORM</th>
                    <th>LAST COMMENT</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {sorted.map((runner) => (
                <RunnerRow key={runner.entrant_id} runner={runner} tab={tab} />
              ))}
            </tbody>
          </table>
        </div>

        {/* Speedmap */}
        <SpeedMap runners={active} />
      </div>

      {/* Right panel */}
      <aside className="w-60 border-l border-[#2d3748] bg-[#0c0e11] overflow-auto shrink-0 flex flex-col">
        <p className="px-3 py-2 text-[10px] font-bold tracking-widest text-[#86948a] border-b border-[#2d3748]">
          MARKET FEED
        </p>

        {holdPct && (
          <div className="px-3 py-2 border-b border-[#2d3748]">
            <p className="text-[10px] text-[#86948a] font-bold tracking-wider mb-1">HOLD %</p>
            <p className="font-mono font-bold text-[#e2e2e6]">{holdPct}%</p>
          </div>
        )}

        {/* Money tracker bars */}
        {(money_tracker?.entrants ?? []).length > 0 && (
          <div className="px-3 py-2 border-b border-[#2d3748]">
            <p className="text-[10px] text-[#86948a] font-bold tracking-wider mb-2">BET VOLUME</p>
            {(money_tracker?.entrants ?? []).slice(0, 8).map((e) => {
              const runner = runners.find((r) => r.entrant_id === e.entrant_id);
              return (
                <div key={e.entrant_id} className="flex items-center gap-2 mb-1">
                  <span className="text-[11px] text-[#bbcabf] w-20 truncate">{runner?.name ?? "—"}</span>
                  <div className="flex-1 h-2 bg-[#1e2023]">
                    <div
                      className="h-2 bg-[#4edea3]"
                      style={{ width: `${Math.min(e.bet_percentage ?? 0, 100)}%` }}
                    />
                  </div>
                  <span className="font-mono text-[10px] text-[#86948a] w-8 text-right">
                    {(e.bet_percentage ?? 0).toFixed(0)}%
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {biggest_bet && (
          <div className="px-3 py-2">
            <p className="text-[10px] text-[#86948a] font-bold tracking-wider mb-1">BIGGEST BET</p>
            <p className="font-mono text-[#4edea3] font-bold text-lg">
              ${(biggest_bet as { stake?: number }).stake?.toLocaleString() ?? "—"}
            </p>
          </div>
        )}
      </aside>
    </div>
  );
}

function RunnerRow({ runner, tab }: { runner: Runner; tab: Tab }) {
  const ml = runner.ml;
  const weightStr =
    typeof runner.weight === "object" && runner.weight !== null
      ? (runner.weight as { total?: string }).total ?? "—"
      : String(runner.weight ?? "—");

  return (
    <tr className={runner.is_scratched || runner.is_late_scratched ? "opacity-30" : ""}>
      <td className="font-mono text-[#86948a] text-center">{runner.runner_number}</td>
      <td className="font-mono text-[#86948a] text-center">{runner.barrier}</td>
      <td>
        <div className="flex items-center gap-2">
          <span className="font-bold text-[#e2e2e6]">{runner.name}</span>
          {runner.is_favourite && (
            <span className="text-[9px] font-bold text-[#ffb95f] border border-[#ffb95f] px-1">FAV</span>
          )}
          {runner.is_mover && (
            <span className="text-[9px] font-bold text-[#4edea3] border border-[#4edea3] px-1">↑</span>
          )}
        </div>
      </td>
      <td className="text-[12px] text-[#bbcabf]">
        {runner.jockey}
        {runner.trainer && <span className="block text-[11px] text-[#86948a]">{runner.trainer}</span>}
      </td>
      <td className="font-mono text-[12px] text-[#bbcabf]">{weightStr}</td>

      {tab === "value" ? (
        <>
          <td className="font-mono font-bold text-[#4edea3]">
            {ml ? formatProb(ml.model_prob) : "—"}
          </td>
          <td className="font-mono text-[#e2e2e6]">
            {formatOdds(runner.odds.fixed_win)}
          </td>
          <td className="font-mono text-[#bbcabf]">
            {ml ? formatProb(ml.tab_implied_prob) : "—"}
          </td>
          <td className={`font-mono font-bold ${ml ? edgeColor(ml.value_edge) : "text-[#86948a]"}`}>
            {ml ? edgeSign(ml.value_edge) : "—"}
          </td>
          <td>
            <FlucsSparkline values={runner.flucs_sparkline} />
          </td>
        </>
      ) : (
        <>
          <td className="font-mono text-[12px] text-[#e2e2e6]">
            {runner.last_twenty_starts ?? "—"}
          </td>
          <td className="text-[12px] text-[#bbcabf] max-w-xs truncate">
            {runner.form_comment_short ?? "—"}
          </td>
        </>
      )}
    </tr>
  );
}

function FlucsSparkline({ values }: { values: (number | null)[] }) {
  const pts = values.filter(Boolean) as number[];
  if (pts.length < 2) return <span className="text-[#86948a] font-mono text-xs">—</span>;
  const trend = pts[pts.length - 1] < pts[0] ? "shortening" : "drifting";
  return (
    <span className={`font-mono text-xs ${trend === "shortening" ? "text-[#4edea3]" : "text-[#ef4444]"}`}>
      {trend === "shortening" ? "▼" : "▲"} {pts[0].toFixed(2)} → {pts[pts.length - 1].toFixed(2)}
    </span>
  );
}

const SPEEDMAP_ZONES = ["LEAD", "ON SPEED", "MIDFIELD", "BACK"] as const;

function SpeedMap({ runners }: { runners: Runner[] }) {
  const zones: Record<string, Runner[]> = {
    LEAD: [], "ON SPEED": [], MIDFIELD: [], BACK: [],
  };
  for (const r of runners) {
    const lbl = r.speedmap?.label?.toUpperCase() ?? "MIDFIELD";
    const key = lbl === "ON-SPEED" || lbl === "ON SPEED" ? "ON SPEED" : lbl;
    if (key in zones) zones[key].push(r);
    else zones["MIDFIELD"].push(r);
  }

  return (
    <div className="border-t border-[#2d3748] bg-[#0c0e11] px-4 py-3">
      <div className="flex justify-around">
        {SPEEDMAP_ZONES.map((zone) => (
          <div key={zone} className="text-center">
            <p className="text-[10px] font-bold tracking-wider text-[#86948a] mb-2">{zone}</p>
            <div className="flex flex-wrap justify-center gap-1">
              {zones[zone].map((r) => (
                <div
                  key={r.entrant_id}
                  title={r.name}
                  className="w-8 h-8 rounded-full border-2 border-[#4edea3] flex items-center justify-center font-mono text-xs font-bold text-[#e2e2e6] bg-[#1e2023]"
                >
                  {r.runner_number}
                </div>
              ))}
              {zones[zone].length === 0 && (
                <span className="text-[11px] text-[#86948a]">—</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
