import type { Direction } from "@/lib/types";

export function RegimeBadge({ regime }: { regime: string | null }) {
  const styles: Record<string, string> = {
    tendance: "bg-blue-500/15 text-blue-300 border-blue-500/40",
    range: "bg-slate-500/15 text-slate-300 border-slate-500/40",
    volatile: "bg-amber-500/15 text-amber-300 border-amber-500/40",
    transition: "bg-purple-500/15 text-purple-300 border-purple-500/40",
  };
  const label = regime ?? "inconnu";
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${styles[label] ?? styles.transition}`}>
      {label}
    </span>
  );
}

export function DirectionBadge({ direction }: { direction: Direction }) {
  const styles: Record<Direction, string> = {
    achat: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
    vente: "bg-rose-500/15 text-rose-300 border-rose-500/40",
    neutre: "bg-slate-500/15 text-slate-300 border-slate-500/40",
  };
  const icons: Record<Direction, string> = { achat: "▲", vente: "▼", neutre: "■" };
  return (
    <span className={`rounded border px-2 py-0.5 text-sm font-semibold uppercase ${styles[direction]}`}>
      {icons[direction]} {direction}
    </span>
  );
}

export function ConfidenceBadge({ value }: { value: number }) {
  const color =
    value >= 70 ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/40"
    : value >= 45 ? "bg-amber-500/15 text-amber-300 border-amber-500/40"
    : "bg-slate-500/15 text-slate-400 border-slate-500/40";
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${color}`}>
      confiance {value}%
    </span>
  );
}

export function StatusBadge({ statut }: { statut: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    en_cours: { label: "En cours", cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40" },
    tp1_touche: { label: "TP1 touché", cls: "bg-emerald-500/25 text-emerald-200 border-emerald-400/50" },
    tp2_touche: { label: "TP2 touché", cls: "bg-emerald-600/30 text-emerald-100 border-emerald-300/60" },
    be_recommande: { label: "BE recommandé", cls: "bg-orange-500/15 text-orange-300 border-orange-500/40" },
    sl_touche: { label: "SL touché", cls: "bg-rose-500/15 text-rose-300 border-rose-500/40" },
    invalide: { label: "Invalidé", cls: "bg-red-600/20 text-red-300 border-red-500/50" },
  };
  const item = map[statut] ?? { label: statut, cls: "bg-slate-500/15 text-slate-300 border-slate-500/40" };
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${item.cls}`}>
      {item.label}
    </span>
  );
}

/** Case à cocher visuelle (lecture seule) pour TP/SL touché ou non. */
export function CheckMark({ checked, label, danger = false }: { checked: boolean; label: string; danger?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs">
      <span
        className={`inline-flex h-4 w-4 items-center justify-center rounded border text-[10px] font-bold ${
          checked
            ? danger
              ? "border-rose-400 bg-rose-500/30 text-rose-200"
              : "border-emerald-400 bg-emerald-500/30 text-emerald-200"
            : "border-slate-600 bg-slate-800"
        }`}
      >
        {checked ? "✓" : ""}
      </span>
      <span className={checked ? "text-slate-200" : "text-slate-500"}>{label}</span>
    </span>
  );
}
