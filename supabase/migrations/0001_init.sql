-- Trading Assistant IA — schéma initial
-- À exécuter dans le SQL Editor de Supabase ou via `supabase db push`

create table if not exists public.signals (
  id bigint generated always as identity primary key,
  actif text not null,
  regime text not null,
  strategie text not null,
  direction text not null check (direction in ('achat', 'vente', 'neutre')),
  entree numeric,
  sl numeric,
  tp1 numeric,
  tp2 numeric,
  invalidation numeric,
  confiance integer check (confiance between 0 and 100),
  "analyse" text,  -- guillemets requis: ANALYSE est un mot-clé réservé PostgreSQL
  created_at timestamptz not null default now()
);

create table if not exists public.trades (
  id bigint generated always as identity primary key,
  signal_id bigint not null references public.signals (id) on delete cascade,
  actif text not null,
  direction text not null,
  statut text not null default 'en_cours'
    check (statut in ('en_cours', 'tp1_touche', 'tp2_touche', 'sl_touche', 'invalide', 'be_recommande')),
  prix_actuel numeric,
  pnl_estime numeric,
  be_recommande boolean not null default false,
  opened_at timestamptz not null default now(),
  closed_at timestamptz
);

create table if not exists public.market_events (
  id bigint generated always as identity primary key,
  actif text,
  type text not null,
  impact text,
  details text,
  timestamp timestamptz not null default now()
);

create index if not exists idx_signals_actif_created on public.signals (actif, created_at desc);
create index if not exists idx_trades_statut on public.trades (statut);
create index if not exists idx_events_timestamp on public.market_events (timestamp desc);

-- Row Level Security: lecture publique (dashboard), écriture réservée au backend (service_role bypass RLS)
alter table public.signals enable row level security;
alter table public.trades enable row level security;
alter table public.market_events enable row level security;

create policy "lecture publique signals" on public.signals for select using (true);
create policy "lecture publique trades" on public.trades for select using (true);
create policy "lecture publique events" on public.market_events for select using (true);

-- Realtime pour la mise à jour live du dashboard
alter publication supabase_realtime add table public.signals;
alter publication supabase_realtime add table public.trades;
alter publication supabase_realtime add table public.market_events;
