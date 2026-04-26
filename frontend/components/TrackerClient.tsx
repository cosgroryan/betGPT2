"use client";

import { type TrackerBet } from "@/lib/api";
import { edgeColor, edgeSign, formatOdds } from "@/lib/utils";

interface Summary {
  total: number;
  settled: number;
  total_pl: number;
  win_rate: number | null;
}

interface Props {
  data: { bets: TrackerBet[]; summary: Summary | null };
}

export default function TrackerClient({ data }: Props) {
  const { bets, summary } = data;
  const s = summary as Summary | null;

  const strikes = bets.filter((b) => b.won).length;
  const settled = bets.filter((b) => b.won !== null);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#2d3748] bg-[#0c0e11] flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-[#e2e2e6]">Session Summary</h2>
          <p className="text-[11px] text-[#86948a]">Today&apos;s Performance Terminal</p>
        </div>
        <div className="flex items-center gap-3">
          <button className="px-3 py-1 text-xs font-bold border border-[#86948a] text-[#86948a] hover:border-[#e2e2e6] hover:text-[#e2e2e6] transition-colors">
            EXPORT CSV
          </button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="flex gap-4 px-4 py-3 border-b border-[#2d3748]">
        <StatCard label="TOTAL RACES" value={String(s?.total ?? bets.length)} />
        <StatCard label="VALUE BETS" value={String(bets.length)} />
        <StatCard label="WINS" value={String(strikes)} color="text-[#4edea3]" />
        <StatCard label="PLACES" value={String(bets.filter((b) => b.placed && !b.won).length)} color="text-[#f59e0b]" />
        <StatCard
          label="STRIKE RATE"
          value={settled.length > 0 ? `${((strikes / settled.length) * 100).toFixed(1)}%` : "—"}
          color="text-[#4edea3]"
        />
        <StatCard
          label="P&L (FLAT $1)"
          value={s?.total_pl != null ? `${s.total_pl >= 0 ? "+" : ""}${s.total_pl.toFixed(2)}` : "—"}
          color={(s?.total_pl ?? 0) >= 0 ? "text-[#4edea3]" : "text-[#ef4444]"}
        />
      </div>

      {/* Bet history table */}
      <div className="flex-1 overflow-auto">
        <div className="px-4 py-2 flex items-center justify-between border-b border-[#2d3748]">
          <h3 className="text-[11px] font-bold tracking-wider text-[#86948a]">VALUE BET HISTORY</h3>
          <span className="text-[11px] font-mono text-[#86948a]">{bets.length} RECORDS FOUND</span>
        </div>
        <table className="tt-table w-full">
          <thead>
            <tr>
              <th>TIME</th>
              <th>RACE / MEETING</th>
              <th>RUNNER</th>
              <th>MODEL ODDS</th>
              <th>TAB ODDS</th>
              <th>VALUE EDGE</th>
              <th>RESULT</th>
              <th>P&L</th>
            </tr>
          </thead>
          <tbody>
            {bets.length === 0 && (
              <tr>
                <td colSpan={8} className="text-center py-12 text-[#86948a]">
                  No value bets recorded yet. Visit race pages to generate predictions.
                </td>
              </tr>
            )}
            {bets.map((bet) => (
              <tr key={bet.id}>
                <td className="font-mono text-[11px] text-[#86948a]">
                  {bet.flagged_at ? new Date(bet.flagged_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—"}
                </td>
                <td className="text-[12px] text-[#bbcabf]">{bet.race_label}</td>
                <td className="font-bold text-[#e2e2e6]">{bet.runner}</td>
                <td className="font-mono text-[#e2e2e6]">{formatOdds(bet.model_odds)}</td>
                <td className="font-mono text-[#e2e2e6]">{formatOdds(bet.tab_odds)}</td>
                <td className={`font-mono font-bold ${edgeColor(bet.value_edge)}`}>
                  {edgeSign(bet.value_edge)}
                </td>
                <td>
                  {bet.won === null ? (
                    <span className="text-[10px] font-bold text-[#f59e0b] border border-[#f59e0b] px-1">LIVE</span>
                  ) : bet.won ? (
                    <span className="text-[10px] font-bold text-[#4edea3] border border-[#4edea3] px-1">WIN</span>
                  ) : bet.placed ? (
                    <span className="text-[10px] font-bold text-[#bbcabf] border border-[#bbcabf] px-1">PLACE</span>
                  ) : (
                    <span className="text-[10px] font-bold text-[#ef4444] border border-[#ef4444] px-1">LOSS</span>
                  )}
                </td>
                <td
                  className={`font-mono font-bold ${
                    bet.pl == null ? "text-[#86948a]" : bet.pl >= 0 ? "text-[#4edea3]" : "text-[#ef4444]"
                  }`}
                >
                  {bet.pl == null ? "—" : `${bet.pl >= 0 ? "+" : ""}${bet.pl.toFixed(2)}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  color = "text-[#e2e2e6]",
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className="tt-panel px-3 py-2 min-w-[90px]">
      <p className="text-[10px] font-bold tracking-wider text-[#86948a] mb-1">{label}</p>
      <p className={`font-mono font-bold text-lg ${color}`}>{value}</p>
    </div>
  );
}
