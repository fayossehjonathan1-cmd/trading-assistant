"use client";

import { useMemo, useState } from "react";
import { DirectionBadge, RegimeBadge, StatusBadge } from "@/components/Badges";
import { formatDate, formatPrice, useLiveData } from "@/lib/api";
import type { HistoryData } from "@/lib/types";

const CLOSED = new Set(["tp2_touche", "sl_touche", "invalide"]);

function StatCard({ label, value, tone = "text-slate-100" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${tone}`}>{value}</div>
    </div>
  );
}

export default function HistoryPage() {
  const { data, error, loading } = useLiveData<HistoryData>("/api/history", 15000);
  const [actif, setActif] = useState("tous");
  const [regime, setRegime] = useState("tous");

  const closedTrades = useMemo(
    () => (data?.trades ?? []).filter((t) => CLOSED.has(t.statut)),
    [data],
  );

  const filtered = useMemo(
    () =>
      closedTrades.filter(
        (t) =>
          (actif === "tous" || t.actif === actif) &&
          (regime === "tous" || t.signal?.regime === regime),
      ),
    [closedTrades, actif, regime],
  );

  const assets = useMemo(() => [...new Set(closedTrades.map((t) => t.actif))], [closedTrades]);
  const regimes = useMemo(
    () => [...new Set(closedTrades.map((t) => t.signal?.regime).filter(Boolean) as string[])],
    [closedTrades],
  );

  const wins = filtered.filter((t) => ["tp1_touche", "tp2_touche"].includes(t.statut)).length;
  const pnl = filtered.reduce((acc, t) => acc + (t.pnl_estime ?? 0), 0);

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-xl font-bold text-slate-100">Historique &amp; Journal</h1>
      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-300">
          Backend injoignable ({error}).
        </div>
      )}
      {loading && !data && <div className="py-16 text-center text-slate-500">Chargement…</div>}

      {data && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <StatCard label="Trades clôturés (filtre)" value={String(filtered.length)} />
            <StatCard
              label="Taux de réussite"
              value={filtered.length ? `${((wins / filtered.length) * 100).toFixed(1)}%` : "—"}
              tone={wins / Math.max(filtered.length, 1) >= 0.5 ? "text-emerald-300" : "text-rose-300"}
            />
            <StatCard
              label="P&L cumulé"
              value={`${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}R`}
              tone={pnl >= 0 ? "text-emerald-300" : "text-rose-300"}
            />
          </div>

          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-2 text-slate-400">
              Actif
              <select
                value={actif}
                onChange={(e) => setActif(e.target.value)}
                className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-200"
              >
                <option value="tous">tous</option>
                {assets.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-2 text-slate-400">
              Régime
              <select
                value={regime}
                onChange={(e) => setRegime(e.target.value)}
                className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-200"
              >
                <option value="tous">tous</option>
                {regimes.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </label>
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full bg-slate-950">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                  {["Actif", "Direction", "Régime", "Statut", "Entrée", "P&L", "Confiance", "Clôturé le"].map((h) => (
                    <th key={h} className="px-3 py-2 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((t) => (
                  <tr key={t.id} className="border-t border-slate-900 text-sm">
                    <td className="px-3 py-2 font-semibold text-slate-100">{t.actif}</td>
                    <td className="px-3 py-2"><DirectionBadge direction={t.direction} /></td>
                    <td className="px-3 py-2">{t.signal && <RegimeBadge regime={t.signal.regime} />}</td>
                    <td className="px-3 py-2"><StatusBadge statut={t.statut} /></td>
                    <td className="px-3 py-2 font-mono text-slate-300">{formatPrice(t.signal?.entree)}</td>
                    <td className={`px-3 py-2 font-mono font-semibold ${(t.pnl_estime ?? 0) >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
                      {(t.pnl_estime ?? 0) >= 0 ? "+" : ""}{(t.pnl_estime ?? 0).toFixed(2)}R
                    </td>
                    <td className="px-3 py-2 text-slate-400">{t.signal?.confiance}%</td>
                    <td className="px-3 py-2 text-xs text-slate-500">{formatDate(t.closed_at)}</td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-3 py-8 text-center text-sm text-slate-500">
                      Aucun trade clôturé pour ce filtre.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
