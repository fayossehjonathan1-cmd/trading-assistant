"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLiveData } from "@/lib/api";
import type { HealthData } from "@/lib/types";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/trades", label: "Trades en cours" },
  { href: "/history", label: "Historique" },
];

export default function Nav() {
  const pathname = usePathname();
  const { data: health } = useLiveData<HealthData>("/health", 30000);
  const demo = health ? Object.values(health.mode).some((m) => m === "mock" || m === "memoire") : false;

  return (
    <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <div className="flex items-center gap-6">
          <span className="text-lg font-bold text-slate-100">
            ⚡ Trading Assistant <span className="text-sky-400">IA</span>
          </span>
          <nav className="flex gap-1">
            {LINKS.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                  pathname === l.href
                    ? "bg-sky-500/15 text-sky-300"
                    : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                }`}
              >
                {l.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {health?.circuit_breaker.actif && (
            <span className="rounded-full border border-rose-500/40 bg-rose-500/15 px-2.5 py-1 font-semibold text-rose-300">
              ⛔ circuit breaker
            </span>
          )}
          {demo && (
            <span className="rounded-full border border-amber-500/40 bg-amber-500/15 px-2.5 py-1 font-semibold text-amber-300">
              mode démo
            </span>
          )}
          <span className={`h-2 w-2 rounded-full ${health ? "bg-emerald-400" : "bg-rose-500"}`} title={health ? "Backend connecté" : "Backend hors ligne"} />
        </div>
      </div>
    </header>
  );
}
