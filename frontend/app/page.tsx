"use client";

import { ConfidenceBadge, DirectionBadge, RegimeBadge, StatusBadge } from "@/components/Badges";
import { formatDate, formatPrice, useLiveData } from "@/lib/api";
import type { DashboardAsset, DashboardData } from "@/lib/types";

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-900 px-2 py-1.5 text-center">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="text-sm font-semibold text-slate-200">{value}</div>
    </div>
  );
}

function Level({ label, value, tone }: { label: string; value: number | null | undefined; tone: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-slate-500">{label}</span>
      <span className={`font-mono font-semibold ${tone}`}>{formatPrice(value)}</span>
    </div>
  );
}

function AssetCard({ asset }: { asset: DashboardAsset }) {
  const s = asset.signal;
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-100">{asset.actif}</h2>
          <div className="font-mono text-2xl font-bold text-sky-300">{formatPrice(asset.prix)}</div>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <RegimeBadge regime={asset.regime} />
          {asset.trade_ouvert && <StatusBadge statut={asset.trade_ouvert.statut} />}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Metric label="RSI 14" value={asset.rsi != null ? String(asset.rsi) : "—"} />
        <Metric label="ADX 14" value={asset.adx != null ? String(asset.adx) : "—"} />
        <Metric label="ATR 14" value={formatPrice(asset.atr)} />
      </div>

      {s ? (
        <div className="flex flex-col gap-2 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
          <div className="flex items-center justify-between">
            <DirectionBadge direction={s.direction} />
            <ConfidenceBadge value={s.confiance} />
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            <Level label="Entrée" value={s.entree} tone="text-slate-200" />
            <Level label="SL" value={s.sl} tone="text-rose-300" />
            <Level label="TP1" value={s.tp1} tone="text-emerald-300" />
            <Level label="TP2" value={s.tp2} tone="text-emerald-200" />
          </div>
          <div className="text-xs text-slate-500">
            Stratégie : <span className="text-slate-300">{s.strategie}</span> · {formatDate(s.created_at)}
          </div>
          <details className="text-xs text-slate-400">
            <summary className="cursor-pointer select-none text-sky-400 hover:text-sky-300">
              Voir l&apos;analyse complète
            </summary>
            <p className="mt-2 whitespace-pre-wrap leading-relaxed">{s.analyse}</p>
          </details>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-slate-800 p-3 text-center text-sm text-slate-500">
          Aucun signal pour le moment
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const { data, error, loading } = useLiveData<DashboardData>("/api/dashboard", 10000);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-100">Dashboard</h1>
        <span className="text-xs text-slate-500">
          Dernier cycle : {formatDate(data?.dernier_cycle)} · rafraîchissement auto
        </span>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-300">
          Backend injoignable ({error}). Vérifiez que l&apos;API tourne.
        </div>
      )}

      {loading && !data ? (
        <div className="py-16 text-center text-slate-500">Chargement des données de marché…</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          {data?.actifs.map((a) => <AssetCard key={a.actif} asset={a} />)}
        </div>
      )}
    </div>
  );
}
