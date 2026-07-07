export type Direction = "achat" | "vente" | "neutre";

export interface Signal {
  id: number;
  actif: string;
  regime: string;
  strategie: string;
  direction: Direction;
  entree: number;
  sl: number;
  tp1: number;
  tp2: number;
  invalidation: number;
  confiance: number;
  analyse: string;
  created_at: string;
}

export interface Trade {
  id: number;
  signal_id: number;
  actif: string;
  direction: Direction;
  statut: string;
  statut_label?: string;
  prix_actuel: number | null;
  pnl_estime: number | null;
  be_recommande: boolean;
  opened_at: string;
  closed_at?: string | null;
  signal?: Signal | null;
}

export interface DashboardAsset {
  actif: string;
  prix: number | null;
  rsi: number | null;
  adx: number | null;
  atr: number | null;
  regime: string | null;
  signal: Signal | null;
  trade_ouvert: Trade | null;
}

export interface DashboardData {
  actifs: DashboardAsset[];
  dernier_cycle: string | null;
  circuit_breaker: boolean;
}

export interface HistoryData {
  total_trades: number;
  taux_reussite: number | null;
  pnl_total_r: number;
  par_actif: Record<string, { total: number; gagnes: number; pnl_total: number }>;
  par_regime: Record<string, { total: number; gagnes: number; pnl_total: number }>;
  trades: Trade[];
}

export interface HealthData {
  status: string;
  mode: Record<string, string>;
  dernier_cycle: string | null;
  circuit_breaker: { actif: boolean; pertes_consecutives: number };
}
