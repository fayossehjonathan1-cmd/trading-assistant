"use client";

import { CheckMark, DirectionBadge, RegimeBadge, StatusBadge } from "@/components/Badges";
import { formatDate, formatPrice, useLiveData } from "@/lib/api";
import type { Trade } from "@/lib/types";

const CLOSED = new Set(["tp2_touche", "sl_touche", "invalide"]);

function rowTone(statut: string): string {
  if (statut === "be_recommande") return "border-l-2 border-l-orange-400";
  if (statut === "invalide" || statut === "sl_touche") return "border-l-2 border-l-rose-500";
  if (CLOSED.has(statut)) return "border-l-2 border-l-emerald-500";
  return "border-l-2 border-l-emerald-400/50";
}

function TradeRow({ trade }: { trade: Trade }) {
  const s = trade.signal;
  const tp1Hit = ["tp1_touche", "tp2_touche"].includes(trade.statut);
  const tp2Hit = trade.statut === "tp2_touche";
  const slHit = trade.statut === "sl_touche";
  const pnl = trade.pnl_estime ?? 0;

  return (
    <tr className={`bg-slate-900/50 text-sm ${rowTone(trade.statut)}`}>
      <td className="px-3 py-2.5 font-semibold text-slate-100">{trade.actif}</td>
      <td className="px-3 py-2.5"><DirectionBadge direction={trade.direction} /></td>
      <td className="px-3 py-2.5"><StatusBadge statut={trade.statut} /></td>
      <td className="px-3 py-2.5">{s && <RegimeBadge regime={s.regime} />}</td>
      <td className="px-3 py-2.5 font-mono text-slate-300">{formatPrice(s?.entree)}</td>
      <td className="px-3 py-2.5 font-mono text-slate-300">{formatPrice(trade.prix_actuel)}</td>
      <td className={`px-3 py-2.5 font-mono font-semibold ${pnl >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
        {pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}R
      </td>
      <td className="px-3 py-2.5">
        <div className="flex flex-col gap-1">
          <CheckMark checked={tp1Hit} label={`TP1 ${formatPrice(s?.tp1)}`} />
          <CheckMark checked={tp2Hit} label={`TP2 ${formatPrice(s?.tp2)}`} />
          <CheckMark checked={slHit} label={`SL ${formatPrice(s?.sl)}`} danger />
        </div>
      </td>
      <td className="px-3 py-2.5 text-xs text-slate-500">
        {formatDate(trade.opened_at)}
        {trade.closed_at && <div>→ {formatDate(trade.closed_at)}</div>}
      </td>
    </tr>
  );
}

export default function TradesPage() {
  const { data, error, loading } = useLiveData<Trade[]>("/api/trades?statut=all", 10000);
  const open = (data ?? []).filter((t) => !CLOSED.has(t.statut));
  const closed = (data ?? []).filter((t) => CLOSED.has(t.statut));

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-xl font-bold text-slate-100">Trades en cours</h1>
      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-300">
          Backend injoignable ({error}).
        </div>
      )}
      {loading && !data && <div className="py-16 text-center text-slate-500">Chargement…</div>}

      {data && (
        <>
          <TradeTable trades={open} empty="Aucun trade ouvert actuellement." />
          <h2 className="mt-2 text-base font-semibold text-slate-300">Récemment clôturés</h2>
          <TradeTable trades={closed.slice(0, 15)} empty="Aucun trade clôturé." />
        </>
      )}
    </div>
  );
}

function TradeTable({ trades, empty }: { trades: Trade[]; empty: string }) {
  if (trades.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-800 p-6 text-center text-sm text-slate-500">
        {empty}
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800">
      <table className="w-full border-separate border-spacing-y-0.5 bg-slate-950 p-1">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
            {["Actif", "Direction", "Statut", "Régime", "Entrée", "Prix actuel", "P&L", "Niveaux", "Ouvert / clôturé"].map((h) => (
              <th key={h} className="px-3 py-2 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => <TradeRow key={t.id} trade={t} />)}
        </tbody>
      </table>
    </div>
  );
}
