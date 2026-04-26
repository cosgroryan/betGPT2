import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function edgeColor(edge: number): string {
  if (edge >= 3) return "text-[#4edea3]";
  if (edge >= 0) return "text-[#f59e0b]";
  return "text-[#ef4444]";
}

export function edgeSign(edge: number): string {
  return edge >= 0 ? `+${edge.toFixed(1)}%` : `${edge.toFixed(1)}%`;
}

export function formatOdds(odds: number | null | undefined): string {
  if (!odds) return "—";
  return `$${odds.toFixed(2)}`;
}

export function formatProb(prob: number | null | undefined): string {
  if (prob == null) return "—";
  return `${prob.toFixed(1)}%`;
}

export function countdown(startTime: string): string {
  const diff = new Date(startTime).getTime() - Date.now();
  if (diff <= 0) return "LIVE";
  const m = Math.floor(diff / 60000);
  const s = Math.floor((diff % 60000) / 1000);
  if (m >= 60) return `${Math.floor(m / 60)}h ${m % 60}m`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function statusBadgeClass(status: string): string {
  switch (status?.toLowerCase()) {
    case "open": return "text-[#4edea3]";
    case "closed": return "text-[#f59e0b]";
    case "resulted":
    case "paying": return "text-[#bbcabf]";
    case "abandoned": return "text-[#ef4444]";
    default: return "text-[#bbcabf]";
  }
}
