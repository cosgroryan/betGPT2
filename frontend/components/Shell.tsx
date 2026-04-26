"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { LayoutDashboard, TrendingUp, Trophy, BookOpen } from "lucide-react";

const NAV = [
  { label: "DASHBOARD", href: "/", icon: LayoutDashboard },
  { label: "VALUE TRACKER", href: "/tracker", icon: TrendingUp },
];

const SIDEBAR = [
  { label: "Thoroughbred", href: "/", active: true },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();

  return (
    <div className="flex flex-col h-full">
      {/* Top nav */}
      <header className="flex items-center justify-between px-4 h-10 border-b border-[#2d3748] bg-[#0c0e11] shrink-0">
        <div className="flex items-center gap-6">
          <span className="text-[#4edea3] font-bold tracking-widest text-sm font-mono">
            VAL-TRACK TERMINAL
          </span>
          <nav className="flex gap-1">
            {NAV.map(({ label, href }) => (
              <Link
                key={href}
                href={href}
                className={cn(
                  "px-3 py-1 text-xs font-bold tracking-wider transition-colors",
                  path === href
                    ? "text-[#4edea3] border-b-2 border-[#4edea3]"
                    : "text-[#bbcabf] hover:text-[#e2e2e6]"
                )}
              >
                {label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3 text-[#86948a] text-xs font-mono">
          <span>● LIVE NOW</span>
        </div>
      </header>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="w-40 shrink-0 border-r border-[#2d3748] bg-[#0c0e11] flex flex-col pt-4">
          <p className="px-4 text-[10px] font-bold tracking-widest text-[#86948a] mb-2">RACE CENTER</p>
          <p className="px-4 text-[10px] text-[#86948a] mb-3">LIVE MEETINGS</p>
          {SIDEBAR.map(({ label, href }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2 px-4 py-2 text-[13px] transition-colors",
                "hover:bg-[#1e2023]",
                path === href ? "text-[#4edea3] bg-[#1e2023]" : "text-[#e2e2e6]"
              )}
            >
              <Trophy size={13} />
              {label}
            </Link>
          ))}
          <div className="mt-auto mb-4 px-4 flex flex-col gap-2">
            <Link href="/tracker" className="flex items-center gap-2 text-[12px] text-[#86948a] hover:text-[#e2e2e6]">
              <BookOpen size={12} /> Settings
            </Link>
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 overflow-auto bg-[#111316]">
          {children}
        </main>
      </div>
    </div>
  );
}
