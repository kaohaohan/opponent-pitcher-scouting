# Taiwanese Baseball Player Watch

An **event-monitoring system**, not a statistics dashboard. It follows selected
Taiwanese hitters, detects newly completed plate appearances, evaluates watch
rules against them, and records alerts.

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

Run the app:

```bash
uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000/> — a one-page UI with a **Run historical
replay** button and tables for players, alerts and plate appearances.

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
| `GEMINI_API_KEY` | *(none)* | Required to call `POST /api/pregame/brief`; read from the environment only |

## API

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/players` | Players we have seen plate appearances for |
| `GET` | `/api/events` | Stored plate appearances. Filters: `game_id`, `player_id`, `limit` |
| `GET` | `/api/alerts` | Alerts, newest first. Filters: `rule_type`, `limit` |
| `POST` | `/api/replay` | **Development/demo only.** Replays a fixture through the pipeline. Optional `fixture_path` |
| `POST` | `/api/pregame/brief` | Fetches one pitcher's recent Statcast pitches, aggregates pitch usage, and returns an LLM-written brief plus the structured context it was built from. Body: `pitcher_id`, `start_date`, `end_date` |
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
LiveSource (interface only) --\
                               --> PlateAppearanceProcessor --> RuleEngine --> SQLite
ReplaySource (JSON fixture) --/
```

```
app/
├── main.py                  FastAPI app factory, static mount, table creation on startup
├── config.py                Env-var settings with defaults
├── db.py                    Engine, session factory, declarative base
├── models.py                ORM: Player, PlateAppearance, Alert
├── schemas.py               PlateAppearanceEvent (the normalized contract) + read models
├── repository.py            The only module that writes SQL; owns conflict handling
├── api/routes.py            Read endpoints + the replay trigger
├── sources/
│   ├── base.py              PlateAppearanceSource ABC — the source contract
│   ├── replay.py            Sequential replay from a JSON fixture
│   └── live.py              Live feed interface; raises NotImplementedError
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
5. Evaluate the watch rules — *only for an event that was actually new*.
6. Persist the resulting alerts.

### Watch rules

| Rule | Condition |
| --- | --- |
| `extra_base_hit` | `result` in Double, Triple, Home Run |
| `hard_contact` | `exit_velocity >= 100` mph |
| `high_velocity_hit` | `pitch_velocity >= 95` mph **and** `result` is a hit |

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
`PlateAppearanceSource`. Adding a real MLB feed therefore means writing one
`events()` method. The processor, the rules and the schema do not change.

Sources emit plain mappings rather than validated models on purpose: validation
belongs to the processor, so a malformed event cannot be silently dropped inside
a source, and every source is held to the same standard.

**`LiveSource` is an interface, not a stub with fake behavior.** It pins down the
shape of the eventual integration (poll a game, watch a set of players, emit
normalized events) and raises `NotImplementedError`. Because idempotency is a
database guarantee, a live source can safely re-emit events it is unsure about
instead of maintaining perfect client-side state — a useful property for a
polling feed that may see the same at-bat several times.

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
the failure. This matters most for the source that does not exist yet: a polling
live feed will fail mid-game routinely, and it must be able to resume rather than
lose the innings it already saw.

`NotImplementedError` is intentionally *not* caught. It means unimplemented code,
not an upstream outage, so `process_source(LiveSource(...))` raises rather than
quietly reporting a feed failure.

**The replay trigger is an HTTP endpoint rather than a script**, so the demo works
from the UI button with no second entry point to keep in sync. It is marked
development-only; it is safe to call repeatedly, but nothing about it is
authenticated.

### Known limitations

These are deliberate for an MVP skeleton:

* `Base.metadata.create_all()` on startup instead of migrations.
* No authentication on any endpoint, including `POST /api/replay`.
* Players are created implicitly by ingestion; there is no watch-list management
  endpoint yet, so "selected hitters" are whichever players appear in a source.
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
