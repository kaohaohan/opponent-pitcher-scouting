# Opponent Pitcher Scouting

[![CI](https://github.com/kaohaohan/taiwanese-baseball-watch/actions/workflows/ci.yml/badge.svg)](https://github.com/kaohaohan/taiwanese-baseball-watch/actions/workflows/ci.yml)
[![Live Demo](https://img.shields.io/badge/Live%20Demo-taiwanese--baseball--watch.vercel.app-2ea44f)](https://taiwanese-baseball-watch.vercel.app)

> **How is this pitcher different today from what we expected?**

A live opponent-pitcher monitoring tool that compares current pitch behavior
against the pitcher's historical Statcast baseline and automatically surfaces
meaningful changes — deterministic stats first, Gemini for narration only.

![Pitcher Analysis — today vs. baseline with WATCH/ALERT signals](docs/images/live-pitcher-watch.png)

**[Try the live demo →](https://taiwanese-baseball-watch.vercel.app)**
Open **Player Watch**, pick a live game's current pitcher, and see today vs.
his baseline — or open any completed game from the Final list.

<details>
<summary>Live Now discovery screenshot</summary>

![Player Watch — Live Now cards with score, inning/outs, and current pitcher](docs/images/player-watch-live-now.png)

Player Watch's landing view: every game live right now, one click from its pitcher's analysis.

</details>

<details>
<summary>Pregame scouting brief screenshot</summary>

![Opponent Pitcher Scouting — pregame brief](docs/images/pregame-scouting.png)

The pregame brief for a probable starter: pitch mix, velocity, and count tendencies from the same Statcast baseline.

</details>

## Core workflow

```
Live games (score · inning · outs · who's pitching)
  → pick the current pitcher
  → Today vs. Baseline  (usage + velocity, per pitch type)
  → WATCH / ALERT signals  (deterministic, sample-size aware)
  → on-demand Gemini scouting note  (narrates signals only)
```

Player Watch opens on the games in progress right now. Each live card shows
the score, inning, outs, and current pitcher; one click opens that pitcher's
analysis: today's pitch usage and velocity next to his Statcast baseline
(default: the 365 days before the game), with backend-computed WATCH / ALERT
signals for changes worth a look. Live discovery follows the game's current
pitcher, while analysis pages remain pinned to the selected pitcher to preserve
comparison context; if the mound changes, the analysis page shows the current
pitcher with a one-click handoff. Monitoring starts automatically while the
game is live. Upcoming games list probable starters (baseline-only view),
completed games open as a full-game comparison, and a manual game-ID entry
remains under *Advanced*.

Before first pitch, the **Pregame** page builds the same baseline into a
pitch-mix, velocity, and count-tendency scouting brief.

<details>
<summary><strong>Architecture</strong> (click to expand diagram)</summary>

```mermaid
flowchart TB
    classDef user fill:#E1F5FE,stroke:#0277BD,stroke-width:2px;
    classDef system fill:#FFF3E0,stroke:#EF6C00,stroke-width:2px;
    classDef logic fill:#F3E5F5,stroke:#7B1FA2,stroke-width:2px;
    classDef data fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px;
    classDef ext fill:#FAFAFA,stroke:#616161,stroke-width:2px,stroke-dasharray: 5 5;

    Staff(("Hitter /<br/>Hitting Staff")):::user

    subgraph App ["Opponent Pitcher Scouting — application boundary"]
        FE["Frontend<br/>Next.js · React · TypeScript"]:::system
        API["Backend API<br/>FastAPI"]:::system

        subgraph Pregame ["① Pregame scouting"]
            AGG["Deterministic aggregation<br/>pitch mix · velocity · count tendencies"]:::logic
            PSS["Sample-size safeguards<br/>per bucket"]:::logic
            BASE["Pregame pitcher baseline"]:::logic
        end

        subgraph Live ["② Live monitoring"]
            PROC["Live event processing<br/>+ deterministic alert rules"]:::logic
            CMP["Live-vs-pregame comparison<br/>+ live sample-size thresholds"]:::logic
        end

        DB[("SQLite<br/>plate appearances · alerts")]:::data
    end

    SAVANT["Baseball Savant / Statcast<br/>historical pitch-level data"]:::ext
    MLB["MLB Stats API<br/>schedule · participants · live game feed"]:::ext
    GEMINI["Google Gemini<br/>interpretation only"]:::ext

    Staff --> FE
    FE <-->|"REST / JSON"| API

    API -->|"① fetch recent pitches"| SAVANT
    SAVANT -->|"pitch-level rows"| AGG
    AGG --> PSS --> BASE

    API -->|"② schedule · participants · live feed"| MLB
    MLB -->|"completed plate appearances"| PROC
    PROC -->|"idempotent insert"| DB
    DB -->|"events · alerts"| API
    MLB -->|"pitches thrown so far"| CMP
    BASE -->|"baseline"| CMP
    CMP -->|"deltas + WATCH/ALERT signals"| API

    BASE -.->|"Structured facts for interpretation"| GEMINI
    CMP -.->|"Structured facts for interpretation"| GEMINI
    GEMINI -.->|"narrative text only"| API
```

**Gemini does not compute the core baseball statistics or determine
deterministic alerts.** The backend computes the facts first (pitch usage,
velocity, sample sizes, pregame-vs-live deltas) and only then sends a
structured summary to Gemini for interpretation. Gemini never reads from the
MLB Stats API, Statcast, or SQLite, and never writes to them. Deterministic
statistics, comparisons, and alerting remain available independently of
Gemini.

</details>

<details>
<summary><strong>Engineering highlights</strong></summary>

- DB-backed idempotent ingestion — `UNIQUE(game_id, at_bat_index)` with
  `INSERT ... ON CONFLICT DO NOTHING RETURNING id`, so replaying or
  re-polling a game creates no duplicate rows or alerts
- Deterministic aggregation kept strictly separate from LLM interpretation —
  the comparison and pregame-brief endpoints compute every number before an
  LLM ever sees the request
- Two-level WATCH / ALERT signals — usage changes gated on total pitches
  thrown, velocity changes gated on that pitch type's own count
- True zero vs. missing kept distinct — a pitch not thrown yet today is `0%`
  (a real signal), while no data at all is `null`, never coerced to zero
- Shared 10s in-process live-feed snapshot cache (per-game lock) so sync,
  comparison, and game-summary polling collapse to one MLB request; 6h
  Statcast baseline cache
- Defensive MLB/Statcast parsing — UTF-8 BOM handling, pitchouts and
  intentional balls excluded from the pitch mix
- Pitcher-focused monitoring, event alerts, and persisted pitch-mix signals
- Live vs. pregame pitch-mix comparison, reconciling Statcast's short pitch
  codes against the MLB live feed's inconsistent naming
- Frontend live-monitoring session persists across route navigation
- Live game discovery (hydrated schedule linescore) with pitcher-change
  detection; "today" follows MLB's US Eastern calendar
- Explicit failure-state handling — source errors, partial ingestion, and
  LLM failures are reported, never silently swallowed
- Testable external-service boundaries — MLB, Statcast, and Gemini are all
  behind small interfaces with fakes used throughout the test suite

</details>

## Tech stack

**Frontend:** Next.js · React · TypeScript · TanStack Query

**Backend:** FastAPI · Python · SQLAlchemy · SQLite

**Data / integrations:** MLB Stats API · Baseball Savant / Statcast · Gemini API

<details>
<summary><strong>Local setup</strong> (run it yourself)</summary>


Requires Python 3.12 and Node 22.

```bash
# backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # or requirements.txt without the test deps

export GEMINI_API_KEY=your-key-here   # optional locally; required for the
                                       # scouting brief and AI comparison notes

uvicorn app.main:app --reload
```

Interactive API docs: <http://127.0.0.1:8000/docs>.

```bash
# frontend, in another terminal
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000> (redirects to `/pregame`). The dashboard talks
to FastAPI through a same-origin Next.js rewrite (`/backend/api/...` →
`FASTAPI_BASE_URL`, defaulting to `http://127.0.0.1:8000`).

## Deployment

The live demo runs on Vercel + Railway, deployed from `main`:

```
Browser → Vercel (Next.js, root: frontend/)
            │ /backend/:path* rewrite → FASTAPI_BASE_URL
            ▼
          Railway (FastAPI, uvicorn, 1 replica)
            ├─ MLB Stats API
            ├─ Baseball Savant / Statcast
            ├─ Gemini API (backend-only key)
            ▼
          Railway Volume /data → SQLite (watch.db)
```

**Backend (Railway)** — start command, and required env vars:

```
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | `sqlite:////data/watch.db` |
| `GEMINI_API_KEY` | (secret, backend-only) |
| `RAILPACK_PYTHON_VERSION` | `3.12` |

A persistent volume is mounted at `/data` so the SQLite file survives
redeploys. Single replica only — SQLite doesn't support concurrent writers
across instances.

**Frontend (Vercel)** — root directory `frontend`, production branch `main`,
one env var:

| Variable | Value |
| --- | --- |
| `FASTAPI_BASE_URL` | the Railway backend's public URL |

No `NEXT_PUBLIC_*` variable is used, and the Gemini key is never set on
Vercel — the browser only ever calls the same-origin `/backend/*` rewrite, so
the Railway URL and the Gemini key both stay server-side.

**Portfolio/demo limitation:** SQLite on a single Railway volume is
appropriate for this low-traffic demo, not multi-instance production scale.
A production deployment would move persistence to PostgreSQL and run the
backend on a platform with a managed database, as noted in Design decision B
below.

</details>

<details>
<summary><strong>Design decisions</strong></summary>

**A. Deterministic stats are separate from Gemini.** Every statistic, delta,
and sample-size flag is computed by plain Python before any LLM call, so the
numeric endpoints are correct and available even when Gemini is slow, down,
or misconfigured.

**B. SQLite is appropriate for the current portfolio/demo scope.** The
current workload is local and single-process, so SQLite keeps setup simple
while still providing database-backed constraints and idempotency. A
multi-worker production deployment would move persistence to a production
database such as PostgreSQL.

**C. Live sync is currently client-driven.** A root-level browser provider
continues syncing while the user navigates among app routes in the same tab.
The global status provides Stop/Resume controls and in-app new-alert notices;
after a reload, the stored selection requires an explicit Resume. Closing the
tab stops monitoring, and background browser throttling can delay sync. A
production multi-user version would move ingestion to a server-side
worker/scheduled process independent of browser lifecycle. That worker is not
implemented here.

**D. The product is descriptive/scouting-oriented, not predictive.** It
reports what a pitcher has actually thrown and how tonight compares to his
baseline — it does not forecast the next pitch or project outcomes.

**E. Signals are product heuristics, not statistical tests.** WATCH / ALERT
thresholds decide what is worth a user's glance; they carry no p-value,
confidence interval, or causal claim. A handful of live pitches isn't a
reliable signal, so every signal is gated on sample size, and low-sample rows
stay visible but flagged instead of being dropped or silently trusted.

**F. Gemini narrates, on demand.** The scouting note only cites
backend-computed signals, frames WATCH-level changes as early, never
speculates about causes, and is generated only when the user asks — polling
never calls Gemini. Gemini generation is protected by a short in-process
cooldown/cache for the same game, pitcher, baseline window, and live
comparison state; deterministic analysis remains available independently of
the LLM.

**G. Location filters are visual only.** Pitch-location filters affect the
strike-zone visualization only; global scouting signals remain unfiltered to
avoid hiding relevant usage or velocity changes.

</details>

## Testing

Local verification, all currently passing:

- 211 backend tests (`pytest -q`)
- `ruff check .`
- Frontend TypeScript check (`npm run typecheck`)
- Frontend production build (`npm run build`)

CI runs the same checks on every push and pull request via
[`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Known limitations

- SQLite (on a single Railway volume in the live demo) is appropriate for
  local/demo use, not multi-worker production writes
- Client-driven live polling stops when no client session is active
- No authentication
- Statcast baselines and live-feed snapshots are cached in-process only (lost
  on restart, not shared across replicas)
- No live-game UI tests; live behavior is verified manually against real games
- Scouting outputs are descriptive, not predictive
- Gemini interpretation can fail independently; deterministic numeric output
  remains available regardless

---

<details>
<summary><strong>Reference</strong> — API surface, watch rules, per-phase design writeups (for engineers who want to dig further)</summary>

### API

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/players` | Stored player list, retained for the event API |
| `GET` | `/api/events` | Stored plate appearances. Filters: `game_id`, `batter_id`, `pitcher_id`, `limit` |
| `GET` | `/api/alerts` | Alerts, newest first. Filters: `rule_type`, `subject_role`, `limit` |
| `GET` | `/api/pitch-mix-alerts` | Persisted pitcher usage/velocity signals. Filters: `game_id`, `pitcher_id`, `active`, `limit` |
| `POST` | `/api/replay` | Development/demo only. Replays a fixture through the pipeline |
| `GET` | `/api/live/games?date=YYYY-MM-DD` | Game summaries for a date: score, state, inning, outs, current pitcher (live only), probable pitchers |
| `GET` | `/api/live/games/{game_id}/summary` | One game's summary from its live feed (header + pitcher-change detection) |
| `GET` | `/api/live/games/{game_id}/participants` | Read-only MLB game participant discovery |
| `POST` | `/api/live/sync` | Fetches one MLB live snapshot and ingests completed PAs for selected pitchers; the role-aware backend input remains compatible with `batter_ids` |
| `GET` | `/api/pregame/pitchers/search?query=...` | Pitcher name search / MLBAM discovery |
| `POST` | `/api/pregame/brief` | Statcast pitch-usage aggregation + Gemini-written scouting brief. Body: `pitcher_id`, `start_date`, `end_date` |
| `GET` | `/api/live/games/{game_id}/pitchers/{pitcher_id}/comparison` | Deterministic baseline-vs-today comparison plus WATCH/ALERT `signals`. Never calls Gemini |
| `POST` | `/api/live/games/{game_id}/pitchers/{pitcher_id}/comparison/note` | On-demand Gemini explanation of that same comparison; repeated requests for the same state reuse a short in-process cache |
| `GET` | `/health` | Liveness |

Interactive docs at `/docs`.

### Watch rules

| Rule | Condition |
| --- | --- |
| `extra_base_hit` | `result` in Double, Triple, Home Run |
| `hard_contact` | `exit_velocity >= 100` mph |
| `high_velocity_hit` | `pitch_velocity >= 95` mph **and** `result` is a hit |
| `pitcher_extra_base_hit_allowed` | Watched pitcher allowed a double, triple, or home run |
| `pitcher_high_exit_velocity_allowed` | Watched pitcher allowed `exit_velocity >= 100` mph |

### Signal rules (live comparison)

Product heuristics, not statistical tests (`app/comparison/sample_size.py`).

| Metric | Sample gate | WATCH | ALERT |
| --- | --- | --- | --- |
| Usage | baseline ≥ 100 total pitches; today ≥ 10 total (WATCH) / ≥ 30 (ALERT) | \|Δ\| ≥ 8 pp | \|Δ\| ≥ 10 pp |
| Velocity | baseline ≥ 20 of that pitch type; today ≥ 3 of that type (WATCH) / ≥ 8 (ALERT) | \|Δ\| ≥ 1.0 mph | \|Δ\| ≥ 1.5 mph |

A usage of `0%` today (pitch not thrown yet) is a valid input; `null` (no
data) never produces a signal. Each pitch type and metric reports only its
highest level.

Pregame Statcast aggregation uses its own, larger threshold
(`MIN_SAMPLE_SIZE = 20`, applied per bucket) since it draws from a
multi-game window rather than a single live outing.

### Failure handling

Failures are counted, logged, and reported — never swallowed:

| Kind | Handling |
| --- | --- |
| Plate appearance not complete | `ignored_incomplete` — expected, not a failure |
| Event fails validation | `invalid`, logged with game id and at-bat index; the rest of the source continues |
| The source itself fails | Logged with a traceback, returned as `source_error`; that drain stops, but events already ingested are not rolled back |

| Condition | `GET .../comparison` | `POST .../comparison/note` |
| --- | --- | --- |
| No pregame baseline | `200`, `baseline_available: false` | `200`, note explains no baseline |
| Insufficient live sample | `200`, `insufficient_sample` | `200`, cautious note |
| `GEMINI_API_KEY` unset | unaffected | `503` |
| Gemini request failure/timeout | unaffected | `502` |
| Baseball Savant / MLB feed down | `502` | `502` |
| Game not found | `404` | `404` |

### Code layout

```
app/
├── main.py, config.py, db.py, migrations.py, models.py, schemas.py
├── repository.py       the only module that writes SQL; owns conflict handling
├── api/routes.py        REST endpoints for replay, live monitoring, pregame, and comparison
├── sources/              LiveSource (MLB, snapshot cache), ReplaySource, ScheduleSource, game summaries
├── processing/           PlateAppearanceProcessor pipeline
├── rules/                watch rules (pure functions) + RuleEngine
├── pregame/              Statcast baseline + Gemini scouting brief
└── comparison/           baseline-vs-today comparison, WATCH/ALERT signals, Gemini narration

frontend/
├── app/                  pregame, player-watch (+ [gameId]/pitchers/[pitcherId]), alerts routes
├── components/           GameDiscovery, LiveGameCard, PitcherAnalysisClient, SignalsPanel, ...
└── lib/                   api client, TanStack Query hooks, live-monitoring provider
```

`app/pregame/`, `app/comparison/`, and the event-monitoring pipeline remain
intentionally separated. Pregame builds the historical Statcast baseline
without touching `watch.db`, while comparison combines that baseline with the
current MLB live-feed snapshot without modifying either source.

</details>
