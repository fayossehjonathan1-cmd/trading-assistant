# ⚡ Trading Assistant IA

Application complète d'assistant de trading pilotée par l'API Claude :
récupération continue des prix (XAUUSD, EURUSD, BTCUSD) et des actualités financières,
génération de signaux (achat/vente/neutre avec TP, SL, invalidation et raisonnement complet),
détection du régime de marché, suivi automatique des trades (TP/SL/Break-Even/invalidation),
notifications Telegram et dashboard temps réel.

## Architecture

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│  Backend Python (FastAPI)   │        │   Frontend Next.js 16        │
│  Render / Railway           │        │   Vercel                     │
│                             │        │                              │
│  APScheduler (cycle 5 min)  │  REST  │  /          Dashboard        │
│   ├─ Twelve Data (prix+ATR/ │◄───────│  /trades    Trades en cours  │
│   │   ADX/RSI calculés)     │        │  /history   Historique       │
│   ├─ Marketaux (news 4h)    │        │                              │
│   ├─ Détection de régime    │        │  Polling 10s + Supabase      │
│   ├─ API Claude (signal     │        │  Realtime (si configuré)     │
│   │   JSON structuré)       │        └──────────────┬───────────────┘
│   ├─ Suivi trades TP/SL/BE  │                       │ Realtime
│   └─ Telegram (notifs)      │        ┌──────────────▼───────────────┐
│                             │───────►│  Supabase (PostgreSQL + RLS) │
└─────────────────────────────┘ écrit  │  signals / trades / events   │
                                        └──────────────────────────────┘
```

- **Backend** : `backend/` — FastAPI + APScheduler. Chaque cycle : prix → indicateurs
  (RSI/ATR/ADX calculés localement, 1 seul crédit Twelve Data par actif) → régime
  (ADX > 25 tendance, < 20 range, ATR > 1.8× sa moyenne = volatile) → suivi des trades
  ouverts → nouveaux signaux via Claude (sortie JSON structurée garantie par
  `messages.parse` + Pydantic).
- **Frontend** : `frontend/` — Next.js 16 + Tailwind v4, 3 pages, rafraîchissement par
  polling + abonnement Supabase Realtime quand configuré.
- **Base** : `supabase/migrations/0001_init.sql` — tables `signals`, `trades`,
  `market_events`, RLS activé (lecture publique, écriture réservée à la clé
  `service_role`), Realtime activé sur les 3 tables.
- **Fiabilité** : retry sur toutes les API externes, aucun échec ne fait tomber le cycle,
  circuit breaker après 3 SL consécutifs (suspend les signaux + alerte Telegram,
  réactivation via `POST /api/circuit-breaker/reset`).

### Mode démo intégré

Sans aucune clé API, chaque service bascule automatiquement en mock (prix simulés,
news factices, signaux par règles, stockage en mémoire, notifications en logs).
L'application complète est donc testable immédiatement.

## 1. Clés API à créer (une seule fois)

| Variable | Où l'obtenir | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/settings/keys | Modèle par défaut : `claude-opus-4-8` (variable `CLAUDE_MODEL` pour changer — `claude-sonnet-5` ou `claude-haiku-4-5` réduisent le coût) |
| `TWELVEDATA_API_KEY` | https://twelvedata.com → Get API key (gratuit) | Plan gratuit : 800 crédits/jour. 3 actifs × cycle 5 min = 864/jour → mettre `ANALYSIS_INTERVAL_MINUTES=10` pour rester gratuit |
| `MARKETAUX_API_TOKEN` | https://www.marketaux.com → Sign up (gratuit) | Sentiment financier des 4 dernières heures |
| `TELEGRAM_BOT_TOKEN` | Telegram → chercher **@BotFather** → `/newbot` | |
| `TELEGRAM_CHAT_ID` | Telegram → chercher **@userinfobot** → il renvoie votre id | Envoyez d'abord un message à votre bot |
| `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` | https://supabase.com/dashboard → New project → Project Settings → API | `service_role` = backend uniquement, jamais côté client |
| `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` | même page Supabase (clé **anon public**) | Frontend (Realtime), optionnel |

## 2. Lancer en local

### Base de données (une fois)
Dans Supabase → SQL Editor → coller et exécuter `supabase/migrations/0001_init.sql`.
(Étape optionnelle : sans Supabase le backend stocke en mémoire.)

### Backend
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env               # puis remplir les clés (ou laisser vide = mode démo)
python -m uvicorn app.main:app --port 8000
```
Tests : `python -m pytest tests`

### Frontend
```powershell
cd frontend
npm install
copy .env.local.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```
Ouvrir http://localhost:3000

## 3. Déploiement

### Backend → Render (gratuit)
Le fichier `render.yaml` est fourni. Deux options :

**Option A — Blueprint** : pousser le repo sur GitHub, puis sur https://dashboard.render.com
→ *New* → *Blueprint* → sélectionner le repo. Renseigner les variables d'environnement
marquées `sync: false`.

**Option B — CLI** :
```bash
npm install -g @render-tools/cli   # ou utiliser le dashboard
render login
render blueprint launch
```

Alternative Railway :
```bash
npm install -g @railway/cli
railway login
cd backend
railway init
railway variables set ANTHROPIC_API_KEY=... TWELVEDATA_API_KEY=... MARKETAUX_API_TOKEN=... TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=...
railway up
```
Commande de démarrage : `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### Frontend → Vercel
```bash
npm install -g vercel
cd frontend
vercel login
vercel --prod
```
Dans le dashboard Vercel (ou via `vercel env add`) définir :
- `NEXT_PUBLIC_API_URL` = URL du backend Render (ex: `https://trading-assistant-api.onrender.com`)
- `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` (optionnel, active le Realtime)

Puis mettre `CORS_ORIGINS=https://votre-app.vercel.app` sur le backend.

## 4. API backend

| Endpoint | Description |
|---|---|
| `GET /health` | État + mode de chaque service + circuit breaker |
| `GET /api/dashboard` | Prix, indicateurs, régime, dernier signal et trade ouvert par actif |
| `GET /api/signals?actif=&limit=` | Historique des signaux |
| `GET /api/trades?statut=open\|all` | Trades avec signal associé |
| `GET /api/history` | Stats (taux de réussite, P&L en R, par actif / régime) |
| `GET /api/events` | Journal des événements marché |
| `POST /api/cycle/run` | Déclenche un cycle manuellement |
| `POST /api/circuit-breaker/reset` | Réactive la génération de signaux |

## Logique de trading implémentée (validée par backtest)

**Stratégie** : cassure de canal Donchian(10) sur bougies 1 h, uniquement en régime
tendance (ADX > 25), stop 2×ATR, TP1 ≥ 1,5R / TP2 ≥ 3R, sortie 50 % à TP1 puis stop au
break-even. Cette configuration est issue d'un backtest sur 6 mois de bougies réelles
(157 000+ bougies, `backend/backtest.py` + `sweep.py`/`sweep2.py`/`sweep3.py`) avec
validation in-sample/out-of-sample : **+29,3R sur 6 mois, positive sur les 3 actifs et
sur les deux périodes (PF hors échantillon 1,27)**. Les stratégies de retour à la
moyenne (RSI) testées n'ont montré aucun edge et ont été retirées.

- **Signal** : Claude reçoit prix + RSI/ATR/ADX + canal Donchian + 10 dernières bougies +
  régime détecté + news avec sentiment, et doit rendre un JSON validé (direction, entrée,
  SL, TP1, TP2, invalidation, confiance 0-100, analyse en français). Il n'est consulté
  qu'en régime tendance (`TRADE_REGIMES`) et n'ouvre que sur cassure confirmée. Un trade
  n'est ouvert que si direction ≠ neutre et confiance ≥ 40.
- **Suivi (chaque cycle)** : SL touché > TP2 > invalidation structurelle > invalidation
  par changement de régime radical (passage en volatile) > TP1 > **Break-Even recommandé
  dès que le gain atteint 1R**. Chaque transition = mise à jour BDD + événement + Telegram.
- **Cooldown** : 60 min minimum entre deux signaux sur le même actif, et jamais de nouveau
  signal tant qu'un trade est ouvert sur l'actif.

⚠️ Un backtest positif sur 6 mois (≈260 trades) ne garantit pas la rentabilité future.
Le journal Supabase (page Historique) constitue le forward test en conditions réelles —
suivez-le plusieurs semaines avant tout engagement de capital réel.

> ⚠️ Outil d'aide à la décision — aucune exécution d'ordres réels. Ce n'est pas un conseil
> en investissement.
