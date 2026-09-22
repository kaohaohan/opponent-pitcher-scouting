# Taiwanese Baseball Player Watch

An **event-monitoring system**, not a statistics dashboard. It follows selected
batters and pitchers, detects newly completed plate appearances, evaluates
role-specific watch rules against them, and records alerts.

The distinction matters for the design: nothing here aggregates or projects.
The interesting questions are "has this plate appearance already been seen?" and
"does it match a rule?" — which is why idempotent ingestion and a rule engine sit
at the centre, and the API is a thin read layer over what was ingested.

## Setup

Requires Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # or requirements.txt without the test deps
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Interactive API documentation is available at <http://127.0.0.1:8000/docs>.

The dashboard is a separate Next.js application. In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open <http://localhost:3000/pregame>. The current frontend phase uses
the FastAPI application through a same-origin Next.js rewrite. The browser calls
`/backend/api/...`; Next.js forwards those requests to `FASTAPI_BASE_URL`.
The rewrite defaults to `http://127.0.0.1:8000` for local development.

Run the tests:

```bash
pytest
```

Lint:

```bash
ruff check .
```

`pyproject.toml` configures a minimal rule set (`E`, `F`, `I`, `UP` — real bugs,
dead code, unsorted imports, outdated syntax). No docstring, naming, or
complexity rules, and no mypy; the gate is intentionally small.

### Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./watch.db` | SQLAlchemy URL |
| `REPLAY_FIXTURE_PATH` | `app/fixtures/hao_yu_lee_2025-08-14.json` | Default replay fixture |
| `FRONTEND_DIR` | `./frontend` | Static page directory |
| `GEMINI_API_KEY` | *(none)* | Required to call `POST /api/pregame/brief` or `POST .../comparison/note`; read from the environment only |
| `FASTAPI_BASE_URL` | `http://127.0.0.1:8000` | Server-only Next.js rewrite target for the dashboard |

## API

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/players` | Batter-oriented list of players we have seen plate appearances for |
| `GET` | `/api/events` | Stored plate appearances. Filters: `game_id`, legacy internal `player_id`, external `batter_id`, external `pitcher_id`, `limit` |
| `GET` | `/api/alerts` | Alerts, newest first. Filters: `rule_type`, `subject_role`, `limit` |
| `POST` | `/api/replay` | **Development/demo only.** Replays a fixture through the pipeline. Optional `fixture_path` |
| `GET` | `/api/live/games/{game_id}/participants` | Read-only MLB game participant discovery for batter/pitcher selection |
| `POST` | `/api/live/sync` | Fetches one MLB live snapshot and ingests completed PAs for selected `batter_ids` and/or `pitcher_ids`; legacy `watched_player_ids` still means batter IDs |
| `POST` | `/api/pregame/brief` | Fetches one pitcher's recent Statcast pitches, aggregates pitch usage, and returns an LLM-written brief plus the structured context it was built from. Body: `pitcher_id`, `start_date`, `end_date` |
| `GET` | `/api/live/games/{game_id}/pitchers/{pitcher_id}/comparison` | Deterministic pregame-vs-live pitch-mix comparison for one pitcher. Never calls Gemini — safe to poll. Query: `start_date`, `end_date` |
| `POST` | `/api/live/games/{game_id}/pitchers/{pitcher_id}/comparison/note` | On-demand Gemini explanation of that same comparison. Query: `start_date`, `end_date` (recomputes the comparison internally; no request body). A failure here never affects the GET route above |
| `GET` | `/health` | Liveness |

Interactive docs at `/docs`.

A replay returns a report rather than a bare 200, so the effect is visible:

```bash
curl -X POST http://127.0.0.1:8000/api/replay
{"source":"replay","events_read":6,"stored":5,"duplicates":0,
 "ignored_incomplete":1,"invalid":0,"alerts_created":3}

# Run it again — ingestion is idempotent.
{"source":"replay","events_read":6,"stored":0,"duplicates":5,
 "ignored_incomplete":1,"invalid":0,"alerts_created":0}
```

`source_error` is `null` on a clean run, and carries the failure when the source
itself broke part-way through (see **Failure handling** below).

## Architecture

```
LiveSource (MLB snapshot) --\
                             --> PlateAppearanceProcessor --> RuleEngine --> SQLite
ReplaySource (JSON fixture) -/
```

```
app/
├── main.py                  FastAPI app factory, static mount, table creation on startup
├── config.py                Env-var settings with defaults
├── db.py                    Engine, session factory, declarative base
├── migrations.py            Additive SQLite migrations for existing local DBs
├── models.py                ORM: Player, PlateAppearance, Alert
├── schemas.py               PlateAppearanceEvent (the normalized contract) + read models
├── repository.py            The only module that writes SQL; owns conflict handling
├── api/routes.py            Read endpoints + the replay trigger
├── sources/
│   ├── base.py              PlateAppearanceSource ABC — the source contract
│   ├── replay.py            Sequential replay from a JSON fixture
│   └── live.py              MLB live feed adapter + participant discovery
├── processing/processor.py  The six-step pipeline
├── rules/engine.py          Watch rules (pure functions) + RuleEngine
└── fixtures/                Mock historical game data
```

### The pipeline

`PlateAppearanceProcessor.process_event` runs, for each event:

1. Receive the event from a source.
2. **Ignore incomplete plate appearances** — an at-bat still in progress is not
   news yet.
3. Normalize and validate into a `PlateAppearanceEvent`.
4. **Insert idempotently.**
5. Evaluate watch rules for the matched role(s).
6. Persist the resulting alerts.

A plate appearance is still stored once, keyed by `(game_id, at_bat_index)`.
Alerts are separately unique on `(plate_appearance_id, subject_role, rule_type)`,
so a repeated sync creates no duplicate alerts, while a PA first stored for a
watched batter can later raise the missing pitcher alerts if that pitcher is
selected.

### Watch rules

| Rule | Condition |
| --- | --- |
| `extra_base_hit` | `result` in Double, Triple, Home Run |
| `hard_contact` | `exit_velocity >= 100` mph |
| `high_velocity_hit` | `pitch_velocity >= 95` mph **and** `result` is a hit |
| `pitcher_extra_base_hit_allowed` | Watched pitcher allowed a double, triple, or home run |
| `pitcher_high_exit_velocity_allowed` | Watched pitcher allowed `exit_velocity >= 100` mph |

Rules are pure functions from an event to an optional `RuleMatch`, so they are
tested without touching a database and can be reordered or extended by appending
to `RULES`.

## Design decisions

**Idempotency is enforced by the database, not by the application.**
`plate_appearances` carries `UNIQUE(game_id, at_bat_index)`, and inserts go
through `INSERT ... ON CONFLICT DO NOTHING RETURNING id`. A check-then-insert has
a race between the check and the insert, so the unique index arbitrates instead.
`RETURNING` also answers the caller's only question in a single round trip: a row
comes back when this insert created the plate appearance, and nothing comes back
when it already existed. That is exactly the signal step 5 needs — which is why
replaying a game twice creates no second round of alerts, rather than merely
avoiding duplicate rows.

**Missing measurements stay `NULL`.** `pitch_velocity`, `exit_velocity` and
`launch_angle` are nullable, and absent values are never coerced to `0`. A 0 mph
exit velocity would read as a rule-relevant fact rather than as an absence of
data — it would look like the softest contact ever measured. Rules that depend on
a measurement return no match when it is missing, and the normalizing validator
maps placeholder strings (`""`, `"N/A"`, `"-"`) to `None` rather than to a number.
The fixture and the test suite both cover this case deliberately.

**One normalized event contract, shared by every source.** A source's only job is
to yield mappings shaped like `PlateAppearanceEvent`; feed-specific concerns —
HTTP, polling, MLB's field names, unit conversions — stay behind
`PlateAppearanceSource`. Live events carry explicit batter and pitcher
identities plus transient matched roles. Legacy replay fields
(`external_player_id`, `player_name`, `team`, `pitcher`) are still accepted as
batter aliases.

Sources emit plain mappings rather than validated models on purpose: validation
belongs to the processor, so a malformed event cannot be silently dropped inside
a source, and every source is held to the same standard.

**`LiveSource` is one-shot by design.** The browser owns polling. Each sync
fetches one MLB snapshot, emits completed PAs for any watched batter or pitcher,
and then stops. Because idempotency is a database guarantee, a live source can
safely re-emit events it is unsure about instead of maintaining perfect
client-side state.

**Existing SQLite databases upgrade in place.** Startup still calls
`Base.metadata.create_all()` for fresh databases, then runs additive migrations.
The Phase 4 migration adds nullable pitcher linkage, backfills existing alerts
as `subject_role = 'batter'`, and creates the role-aware alert uniqueness index.
Historical pitcher IDs remain `NULL`; names are not backfilled by guessing.

### Failure handling

Failures are counted, logged and reported — never swallowed. There are three
distinct kinds, and they are deliberately not collapsed into one:

| Kind | Handling |
| --- | --- |
| Plate appearance not complete | `ignored_incomplete`. Expected, not a failure. |
| Event fails validation | `invalid`, logged as a warning with the game id and at-bat index. The rest of the source continues — one malformed event does not abort a replay. |
| The source itself fails | Logged with a traceback and returned as `source_error`. The drain stops. |

A source failing part-way through — a live feed losing its connection, a fixture
that is not valid JSON — **does not discard the events already ingested**. Each
event commits in its own transaction, so an upstream failure cannot roll back or
corrupt earlier plate appearances; the report still counts what was stored before
the failure. This matters most for live polling: MLB feed errors will happen
mid-game, and the next browser-driven sync must be able to resume rather than
lose the innings it already saw.

`NotImplementedError` is intentionally *not* caught. It means unimplemented code,
not an upstream outage, so source implementations still fail loudly when a
method is missing rather than quietly reporting a feed failure.

**The replay trigger is an HTTP endpoint rather than a script**, so the demo works
from the UI button with no second entry point to keep in sync. It is marked
development-only; it is safe to call repeatedly, but nothing about it is
authenticated.

### Known limitations

These are deliberate for an MVP skeleton:

* No authentication on any endpoint, including `POST /api/replay`.
* Players are created implicitly by ingestion; game participant discovery is
  read-only and there are no persisted watchlists.
* `ON CONFLICT` uses the SQLite dialect. Moving to Postgres means swapping that
  import in `repository.py` — the single place SQL is written.
* Result strings are the normalization vocabulary (`"Double"`, `"Home Run"`, …);
  a real feed adapter has to map into it.
* Ruff is configured, but there is no type-check gate (no mypy) and no CI
  workflow wired up to run either automatically; both run locally on request.
* `ReplaySource` reads its fixture in one go, so a truncated fixture yields zero
  events rather than a partial game. Mid-stream source failure is still handled and
  covered by tests — it is the shape a live feed will fail in.

Not implemented, and intentionally out of scope: authentication, AI, cloud
infrastructure, advanced analytics, WebSockets, notifications, projections.

## Phase 2: Pre-game Brief

A second, self-contained feature living entirely in `app/pregame/`: given one
pitcher and a date window, fetch their recent tracked pitches, calculate
pitch-usage statistics, and ask an LLM to describe those precomputed facts in
prose. Phase 1's event-monitoring pipeline is untouched — nothing in
`app/pregame/` reads from or writes to the `watch.db` tables.

**The backend calculates the baseball facts. The LLM communicates them.** The
LLM is never the source of truth for a statistic: every count, percentage,
and sample size it sees was computed before it was called.

```
StatcastPitchSource --> PitchRecord --> AggregationService --> SampleSizeGuard
                                              |                       |
                                    pitch_usage_by_type      pitch_usage_by_count
                                              \_______________________/
                                                        |
                                            PregameContextBuilder
                                                        |
                                                 GeminiProvider
                                                        |
                                              POST /api/pregame/brief
```

```
app/pregame/
├── schemas.py           PitchRecord (the normalized contract) + usage/context/API models
├── sample_size.py        MIN_SAMPLE_SIZE guard: sufficient vs insufficient_sample
├── aggregation.py         pitch_usage_by_type(), pitch_usage_by_count() — pure functions
├── context.py             PregameContextBuilder — assembles the structured PregameContext
├── sources/
│   ├── base.py             PitchDataSource ABC
│   └── statcast.py          Baseball Savant's public CSV endpoint (httpx + stdlib csv)
├── llm/
│   ├── base.py              LLMProvider ABC
│   └── gemini.py             GeminiProvider (google-genai)
└── api.py                  POST /api/pregame/brief
```

### The sample-size guard

`MIN_SAMPLE_SIZE = 20`, applied **per bucket**, not to the pitcher's overall
pitch count: a pitcher can have thousands of tracked pitches while one
rarely-thrown pitch type still has only a handful of observations. Each row
in `pitch_usage_by_type` carries its own type's count as its sample size;
each row in `pitch_usage_by_count` carries that count's total pitches as its
sample size (the denominator that makes its percentage meaningful or not).

Low-sample rows are **never dropped** from `PregameContext` — they stay
visible with `status: "insufficient_sample"` — and `PregameContextBuilder`
adds a plain-language note to `limitations` for each one. The Gemini system
instruction explicitly tells it to treat `insufficient_sample` rows and the
`limitations` list as caveats, never as tendencies.

### The LLM boundary

`GeminiProvider.generate_brief(context: PregameContext) -> str` is the entire
surface an LLM has: it receives the structured context and returns text. It
cannot query Statcast, cannot open a database session, and cannot compute or
invent a number that is not already in the context — there is no argument
through which it could. `LLMProvider` is an ABC so it is trivially swappable
in tests: `FakeLLMProvider` (in `tests/pregame/fakes.py`) records the exact
context object it was given and returns canned text, so tests assert on the
*shape* of what an LLM receives without ever calling one.

`GEMINI_API_KEY` is read from the environment only (`app/config.py`), with no
default. Its absence is not an import-time error — Phase 1 must not require a
Gemini key to start — but `GeminiProvider.generate_brief` raises
`GeminiConfigurationError` immediately if it is unset, and `POST
/api/pregame/brief` turns that into a `503`. A failed upstream Statcast or
Gemini call becomes a `502` with a clear message. Neither path retries; this
phase adds no resilience infrastructure.

### Known limitations

* Stateless by design: no brief is persisted, and repeating a request refetches
  and regenerates from scratch.
* One pitcher, one data source (Baseball Savant), one LLM provider (Gemini) —
  by scope, not by accident.
* `StatcastPitchSource` calls Baseball Savant synchronously in the request
  path; there is no caching, pagination, or retry.
* No authentication on `POST /api/pregame/brief`, consistent with Phase 1.
* Pitch-type and count-usage percentages round to one decimal place; no
  attempt is made to reconcile rounding across a breakdown.

Not implemented, and intentionally out of scope for this phase: series
adjustment detection, next-pitch prediction, ML models, hitter-vs-pitcher
matchup modeling, handedness splits, heatmaps, bat tracking, RAG, vector
databases, autonomous agents, WebSockets, multiple LLM providers, and an
OpenAI integration.

## Phase 4: MLB game monitoring

Player Watch starts from a game ID. The UI calls participant discovery, lets the
user choose batters and pitchers by name, and then synchronizes one MLB game
snapshot with:

```http
POST /api/live/sync
Content-Type: application/json

{"game_id": 776743, "batter_ids": [657557], "pitcher_ids": [542881]}
```

`game_id`, `batter_ids`, and `pitcher_ids` are positive integers. Both arrays
default to empty, but at least one selected player is required. The Phase 3
`watched_player_ids` field is still accepted and is normalized into
`batter_ids`. The response reports the MLB game state/status plus the same
ingestion counters as replay (`stored`, `duplicates`, `invalid`, and
`alerts_created`). A nonexistent game returns `404`; validation failures return
`422`; MLB timeouts, non-404 HTTP failures, invalid JSON, and unusable feed
schemas return `502`.

Participant discovery is read-only:

```http
GET /api/live/games/776743/participants
```

It returns game status, home/away teams, and deterministic participant rows with
MLB player ID, name, team, side, and roles (`batter`, `pitcher`, or both).

The live adapter fetches `https://statsapi.mlb.com/api/v1.1/game/{game_id}/feed/live`
once per request, traverses completed plays oldest-first, and emits a PA once
when either side is selected. MLB values map into the shared
`PlateAppearanceEvent` contract:

| Normalized field | MLB field |
| --- | --- |
| `batter_id`, `batter_name` | `matchup.batter.id`, `matchup.batter.fullName` |
| `pitcher_id`, `pitcher_name` | `matchup.pitcher.id`, `matchup.pitcher.fullName` |
| `batter_team`, `pitcher_team` | `gameData.teams.away/home.name` by `about.isTopInning` |
| `at_bat_index`, `inning`, `result`, `is_complete` | `about.atBatIndex`, `about.inning`, `result.event`, `about.isComplete` |
| pitch/Statcast fields | terminal `playEvents[]` item with `isPitch: true` |

Missing measurements remain `null`, never zero. Malformed individual watched
plays are allowed to reach the processor for validation; a play that cannot be
attributed to any watched batter or pitcher is skipped. Feed-level errors abort
that sync before ingestion. The existing SQLite unique key on
`(game_id, at_bat_index)` and role-aware alert uniqueness make repeated
synchronization safe and prevent duplicate alerts.

Polling belongs to the browser, not the backend. Player Watch performs an
immediate sync and schedules the next one 20 seconds after the prior request
completes, invalidating the existing players/events/alerts queries after each
successful sync. It stops on a final game, validation error, or 404, retries
transient `502` failures on the next interval, and stops when the page unmounts.
Monitoring is intentionally request-driven and is not an unattended worker;
watchlists are not persisted. Full-game rescanning is accepted for this MVP.

For a real smoke test, start the app with a fresh SQLite database, open Player
Watch, enter game `776743`, load the game, choose at least one batter or pitcher,
then start monitoring. Verify `/api/events?game_id=776743` and `/api/alerts`;
repeat the POST and confirm `stored` is zero, duplicate counts increase, and
database rows/alerts do not. The automated tests use the trimmed historical
snapshot in `tests/fixtures/mlb_live_feed_776743_20250814_230000.json` and never
contact MLB.
## Phase 5: Pregame vs. live comparison

A third, self-contained feature living in `app/comparison/`, connecting
Phase 2 (pregame Statcast baseline) and Phase 3/4 (live MLB feed) without
modifying either: for one watched pitcher in one game, compute how their
live pitch mix compares to their pregame baseline, then optionally ask
Gemini to narrate the comparison already computed.

**The backend calculates every number. Gemini only explains rows the
backend already flagged as notable.** Deliberately two endpoints, not
one: the numeric comparison never calls Gemini, so it stays a full `200`
even when the AI note is unavailable, times out, or replies with
something that doesn't parse.

```
StatcastPitchSource ---> PregameContextBuilder ---\
        (Phase 2, reused)                          \
                                                      --> build_comparison --> PregameLiveComparison
LiveSource.fetch_snapshot() -> live_metrics.py ------/         |                        |
        (Phase 3/4, one new                                    |                GeminiComparisonProvider
         public method)                                        |                        |
                                                                 |                 ComparisonNote
                                       GET  .../comparison  <----'
                                       POST .../comparison/note  <-- (Gemini, on-demand only)
```

```
app/comparison/
├── schemas.py            PregameLiveComparison(Row), ComparisonNote — the API contracts
├── sample_size.py         Live-specific thresholds (see below) — distinct from Phase 2's
├── live_metrics.py        compute_live_pitcher_metrics() — pure, reads a raw MLB feed snapshot
├── compare.py              build_comparison() — combines a PregameContext and LivePitcherMetrics
├── llm/
│   ├── base.py               ComparisonNoteProvider ABC (structured in, structured out)
│   └── gemini.py              GeminiComparisonProvider (google-genai, JSON response schema)
└── api.py                 GET .../comparison, POST .../comparison/note
```

No new database table and no pitch-level persistence: a single MLB feed
snapshot already carries every pitch a pitcher has thrown in the game so
far (`liveData.plays.allPlays[*].playEvents[*]`, not just each play's
terminal pitch), so `live_metrics.py` reads it straight from the same
fetch `LiveSource.fetch_snapshot()` already makes — a genuinely new
public method on `LiveSource`, mirroring its existing
`discover_participants()`. Pitches from an in-progress at-bat count
toward the live totals, not just completed plate appearances.

`avg_velocity_by_pitch_type()` is a small, additive addition to
`app/pregame/aggregation.py` (with a matching `avg_velocity` field on
`PitchTypeUsage`) — the only change to Phase 2, needed because Statcast's
`release_speed` was already fetched but never aggregated by pitch type.

**Pregame and live pitch types use different vocabularies, and both sides
have to agree before a row can be compared.** Baseball Savant's
`pitch_type` column is a short code (`FF`, `SL`, `CH`, ...); the MLB live
feed's `details.type` is usually a `{code, description}` pair, but a
trimmed feed can carry only the human-readable `description` (`"Slider"`).
`live_metrics.py` normalizes every live pitch to the same short-code
vocabulary — preferring `code` when present, falling back to a
`description -> code` lookup table otherwise — so a comparison row's key
lines up with its Statcast baseline instead of two differently-spelled
rows that never match.

### Sample-size rules

Live in-game samples are much smaller than the multi-game Statcast window
Phase 2 guards, so Phase 5 uses its own, smaller thresholds
(`app/comparison/sample_size.py`), not Phase 2's `MIN_SAMPLE_SIZE = 20`:

| Threshold | Value | Guards |
| --- | --- | --- |
| `MIN_LIVE_PITCHES_FOR_ANY_CLAIM` | 10 | The outing as a whole — below it, `overall_live_status` is insufficient and no row can be notable |
| `MIN_PITCH_TYPE_SAMPLE` | 5 | One pitch type's own row — below it, that row's `status` is insufficient regardless of the pitcher's overall count |
| `NOTABLE_USAGE_DELTA_PP` | 10.0 pp | A sufficient row's usage delta must clear this to set `is_notable` |
| `NOTABLE_VELOCITY_DELTA_MPH` | 1.5 mph | A sufficient row's velocity delta must clear this to set `is_notable` |

Every row always carries its raw `usage_delta_pp`/`velocity_delta` —
`is_notable` only gates whether Gemini may describe that delta as a
change, never whether the number itself is shown.

### The LLM boundary

`GeminiComparisonProvider.generate_note(comparison: PregameLiveComparison)
-> ComparisonNote` mirrors Phase 2's boundary discipline (structured
input, no database/source access) but with **structured output**: the
Gemini call is made with `response_mime_type="application/json"` and a
`response_schema=ComparisonNote`, and the reply is parsed with
`ComparisonNote.model_validate_json`. A reply that doesn't parse or
validate raises `GeminiMalformedResponseError` — a failure mode Phase 2's
free-text contract has no equivalent of. `GeminiConfigurationError`/
`GeminiRequestError` are reused directly from `app.pregame.llm.gemini`.
The call carries an explicit 15-second timeout
(`types.HttpOptions(timeout=15_000)`), which Phase 2's brief call does
not set.

### Failure behavior

| Condition | `GET .../comparison` | `POST .../comparison/note` |
| --- | --- | --- |
| No pregame baseline | `200`, `baseline_available: false`, live-only rows | `200`, note explains no baseline |
| Insufficient live sample | `200`, `overall_live_status: "insufficient_sample"` | `200`, cautious `sample_note` |
| `GEMINI_API_KEY` unset | unaffected (never calls Gemini) | `503` |
| Gemini request failure/timeout | unaffected | `502` |
| Gemini malformed response | unaffected | `502` |
| Baseball Savant down | `502` | `502` |
| MLB feed down | `502` | `502` |
| Unsupported pitcher / no data anywhere | `200`, both availability flags `false`, empty `rows` | `200`, note says nothing to compare |
| Game not found | `404` | `404` |

Automated tests never contact MLB, Baseball Savant, or Gemini —
`tests/comparison/fakes.py` provides `StubLiveSource`,
`FakeComparisonNoteProvider`, and `FakeGenAIClient` for the same
dependency-override/monkeypatch seams Phase 2's and Phase 3/4's tests
already use.

Not implemented, and intentionally out of scope for this phase: whiff/
called-strike rates, handedness splits, next-pitch prediction, cached or
persisted baselines, and any UI beyond a compact section on Pitcher Watch.
