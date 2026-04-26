"use client";

import { useState } from "react";
import Link from "next/link";
import { type ValueOpportunity, type Meeting } from "@/lib/api";
import { edgeColor, edgeSign, formatOdds, formatProb, countdown, statusBadgeClass } from "@/lib/utils";
import { TrendingUp, Filter } from "lucide-react";

interface Props {
  initialValue: { opportunities: ValueOpportunity[]; count: number };
  initialMeetings: { meetings: Meeting[]; date: string };
}

export default function DashboardClient({ initialValue, initialMeetings }: Props) {
  const [minEdge, setMinEdge] = useState(3);
  const opps = initialValue.opportunities.filter((o) => o.value_edge >= minEdge);

  return (
    <div className="flex h-full">
      {/* Main panel */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#2d3748] bg-[#0c0e11]">
          <div>
            <p className="text-[10px] font-bold tracking-widest text-[#86948a] mb-0.5">
              Machine Learning Model V4.2 active. Analyzing 128 indicators per runner.
            </p>
            <h1 className="text-lg font-bold text-[#e2e2e6]">Top Value Bets Today</h1>
          </div>
          <div className="flex items-center gap-4">
            <div className="tt-panel px-3 py-2 text-right">
              <p className="text-[10px] text-[#86948a] font-bold tracking-wider">TOTAL POOL</p>
              <p className="font-mono font-bold text-[#e2e2e6]">AU/NZ</p>
            </div>
            <div className="tt-panel px-3 py-2 text-right">
              <p className="text-[10px] text-[#86948a] font-bold tracking-wider">AVG VALUE</p>
              <p className={`font-mono font-bold ${opps.length > 0 ? "text-[#4edea3]" : "text-[#86948a]"}`}>
                {opps.length > 0
                  ? `+${(opps.reduce((a, o) => a + o.value_edge, 0) / opps.length).toFixed(1)}%`
                  : "—"}
              </p>
            </div>
          </div>
        </div>

        {/* Filter bar */}
        <div className="flex items-center gap-3 px-4 py-2 border-b border-[#2d3748] bg-[#111316]">
          <Filter size={13} className="text-[#86948a]" />
          <span className="text-[11px] font-bold tracking-wider text-[#86948a]">MIN EDGE</span>
          {[0, 3, 5, 8].map((v) => (
            <button
              key={v}
              onClick={() => setMinEdge(v)}
              className={`px-2 py-0.5 text-xs font-bold border transition-colors ${
                minEdge === v
                  ? "border-[#4edea3] text-[#4edea3] bg-[#4edea3]/10"
                  : "border-[#2d3748] text-[#86948a] hover:border-[#86948a]"
              }`}
            >
              {v === 0 ? "ALL" : `>${v}%`}
            </button>
          ))}
          <span className="ml-auto text-[11px] text-[#86948a] font-mono">
            {opps.length} OPPORTUNITIES
          </span>
        </div>

        {/* Value table */}
        <div className="flex-1 overflow-auto">
          <table className="tt-table w-full">
            <thead>
              <tr>
                <th className="w-10">RANK</th>
                <th>RUNNER</th>
                <th>RACE / MEETING</th>
                <th>ML PROB</th>
                <th>TAB ODDS</th>
                <th>IMPLIED PROB</th>
                <th>VALUE SCORE</th>
                <th>TREND</th>
              </tr>
            </thead>
            <tbody>
              {opps.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-center py-12 text-[#86948a]">
                    {initialValue.count === 0
                      ? "No data — start the API and backfill historical races first."
                      : "No value bets above the current edge threshold."}
                  </td>
                </tr>
              )}
              {opps.map((opp, i) => (
                <tr key={`${opp.event_id}-${opp.entrant_id}`} className="cursor-pointer">
                  <td className="font-mono text-[#86948a] text-center">{i + 1}</td>
                  <td>
                    <Link href={`/race/${opp.event_id}`} className="font-bold text-[#e2e2e6] hover:text-[#4edea3]">
                      {opp.runner}
                    </Link>
                    {opp.is_mover && (
                      <span className="ml-2 text-[9px] font-bold text-[#ffb95f] border border-[#ffb95f] px-1">
                        MOVER
                      </span>
                    )}
                  </td>
                  <td className="text-[#bbcabf] font-mono text-xs">
                    <Link href={`/race/${opp.event_id}`} className="hover:text-[#4edea3]">
                      R{opp.race_number} {opp.meeting}
                    </Link>
                  </td>
                  <td className="font-mono text-[#4edea3] font-bold">{formatProb(opp.ml_prob)}</td>
                  <td className="font-mono text-[#e2e2e6]">{formatOdds(opp.tab_odds)}</td>
                  <td className="font-mono text-[#bbcabf]">{formatProb(opp.tab_implied)}</td>
                  <td className={`font-mono font-bold ${edgeColor(opp.value_edge)}`}>
                    {edgeSign(opp.value_edge)}
                  </td>
                  <td>
                    {opp.fluc_drift != null && (
                      <span className={`font-mono text-xs ${opp.fluc_drift < 0 ? "text-[#4edea3]" : "text-[#ef4444]"}`}>
                        {opp.fluc_drift < 0 ? "▼" : "▲"} {Math.abs(opp.fluc_drift * 100).toFixed(0)}%
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Right panel — meetings list */}
      <aside className="w-56 border-l border-[#2d3748] bg-[#0c0e11] overflow-auto shrink-0">
        <p className="px-3 py-2 text-[10px] font-bold tracking-widest text-[#86948a] border-b border-[#2d3748]">
          MARKET MOVERS
        </p>
        {initialMeetings.meetings.map((m) => (
          <div key={m.meeting_id} className="border-b border-[#2d3748]">
            <p className="px-3 py-1.5 text-[11px] font-bold text-[#4edea3]">{m.name}</p>
            {m.races.slice(0, 4).map((r) => (
              <Link
                key={r.event_id}
                href={`/race/${r.event_id}`}
                className="flex items-center justify-between px-3 py-1 hover:bg-[#1e2023] transition-colors"
              >
                <span className="text-[12px] text-[#e2e2e6]">R{r.race_number}</span>
                <span className={`text-[10px] font-mono ${statusBadgeClass(r.status)}`}>
                  {r.status === "Open" ? countdown(r.start_time) : r.status}
                </span>
              </Link>
            ))}
          </div>
        ))}
        {initialMeetings.meetings.length === 0 && (
          <p className="px-3 py-4 text-[12px] text-[#86948a]">No meetings today</p>
        )}
      </aside>
    </div>
  );
}
