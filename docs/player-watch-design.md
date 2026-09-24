# Player Watch: Engineering Design

Player Watch is a browser-driven live discovery and pitcher analysis flow. It
shows who is pitching in games happening now, then lets the user inspect that
pitcher's outing against a historical Statcast baseline. Its analysis is
descriptive: the application reports observed pitches and deterministic
signals, without predicting the next pitch or explaining why a change occurred.

## Product model: current pitcher and tracked pitcher

These are intentionally different identities with different jobs.

**Current pitcher** answers “Who is pitching right now?” Live Game Discovery
uses the MLB schedule with hydrated linescore for the game list. Its live game
cards read the current pitcher from the defensive side of that linescore. The
schedule refreshes every 30 seconds while it contains live games. The separate
game-summary endpoint reads the same field from the MLB live feed. When a
half-inning changes or a pitching substitution is reported by MLB, Live Now
follows the pitcher currently on the mound on the next refresh.

**Tracked pitcher** answers “How did this selected pitcher perform today versus
baseline?” Opening analysis pins the route and all comparison queries to that
pitcher's ID. A half-inning change, the opposing team taking the field, or a
reliever entering does not replace the analysis target. This keeps an earlier
pitcher's outing available for inspection after he leaves the mound.

While the game is live and the summary identifies a different current pitcher,
the analysis page displays a banner such as “Robbie Ray is no longer pitching.
Now pitching: David Morgan” and a **View current pitcher** link. The banner
informs the user; navigation happens only if the user selects the link.

> Live discovery follows the game's current pitcher, while analysis pages remain
> pinned to the user-selected pitcher to preserve comparison context.

Consequently, Player Watch home may show one pitcher while an already-open
analysis page shows another at the same moment. This is expected.

The route also works for upcoming and completed games. Upcoming rows link
probable pitchers to their baseline view; final games can be opened for a
full-game comparison. The baseline date range can be adjusted in the analysis
page.

## Analysis: Today vs. Baseline

The analysis combines two sources:

- **Today:** the MLB Stats API live feed's pitch events for the selected pitcher
  in this game.
- **Baseline:** pitcher-level historical pitch records fetched from Baseball
  Savant / Statcast for the chosen date window. By default the window ends the
  day before the game and starts roughly one year earlier.

Backend comparison code computes pitch-type usage, measured velocity, deltas,
sample sizes, availability, and WATCH / ALERT signals. The `GET .../comparison`
endpoint returns this deterministic result and is polled independently of the
AI note. Missing data remains distinct from a measured zero: a pitch type not
thrown today can have 0% usage, while unavailable pitch data remains null.

The comparison table keeps low-sample rows visible and labels their sample
status. It does not treat an absent measurement as zero. Signal thresholds are
product heuristics with sample-size gates, not statistical significance tests.
They have no p-values or confidence intervals and do not claim causality.

### Pitch Location

Location adds a third observational dimension beside usage and velocity:

> What is he throwing? How hard? Where is he attacking?

`GET /api/live/games/{game_id}/pitchers/{pitcher_id}/locations` reads the same
cached MLB live-feed snapshot used by other live views. It walks
`liveData.plays.allPlays`, selects plays whose `matchup.pitcher.id` is the
tracked pitcher, and considers pitch events (`isPitch`). It normalizes pitch
type from `details.type` and reads `pitchData.coordinates.pX` / `pZ` with
`pitchData.strikeZoneTop` / `strikeZoneBottom`. The response includes only
recognized pitch types in the pitch count; points are plotted only when all
coordinates and valid strike-zone bounds are available. The current play is
included, so pitches from an unfinished plate appearance can appear.

The browser renders a catcher-view strike zone divided into nine cells. Each
pitch's vertical coordinate is normalized to its measured zone before plotting
so pitchers and batters with different measured strike-zone heights can share
the same chart. Horizontal coordinates are mapped relative to the 17-inch
plate; distant points are compressed for readability. Pitch types use
different colors and the chart provides a legend and coordinate tooltips.
Locations are a descriptive view of observed pitches, not a causal account of
why placement changed. Location is not currently an input to WATCH / ALERT
generation.

The pitch-type selector filters only the points and plotted count in this
visualization. It does not filter Today vs. Baseline signals. For example,
selecting Slider in the location chart must not hide a Sinker Usage ALERT in
**Worth a glance**. Visual filtering is a local exploration control; global
signals are an attention mechanism and should not disappear because of a chart
filter.

## Worth a glance: global signals

**Worth a glance** is the attention layer for the tracked pitcher. It renders
all active backend-computed WATCH / ALERT signals for Usage and Velocity from
the current comparison. It is not a chart legend or a filtered view of the
selected pitch type. Location filters have no effect on it.

Signals prioritize changes that meet product-defined magnitude and sample-size
thresholds. WATCH is phrased as an early change to keep monitoring; ALERT is a
higher heuristic level. Neither level establishes statistical significance,
predicts an outcome, or identifies a cause.

## Gemini boundary

Gemini is optional narration, requested by the user through **Generate AI
Note**. Polling and the deterministic comparison endpoint do not call it. The
backend computes the pitch comparison and a separate deterministic
`OutcomeContext` from the same MLB live-feed snapshot. That context includes
completed plate appearances, home runs and extra-base hits allowed, hard-hit
contacts at the existing 100 mph rule threshold, measured exit-velocity count,
maximum exit velocity, and limitations for missing measurements. Gemini
receives this structured context alongside the comparison in the note request;
the regular comparison endpoint remains deterministic and independent of
Gemini.
Gemini cannot query MLB, Statcast, or the database, and has no write path to
those systems.

The model may narrate pitch changes only when present in the backend's
`signals` list. It does not calculate pitch metrics or outcome totals, determine
WATCH / ALERT status, parse raw MLB feed data, invent numeric values, predict
future results, or speculate about why an outcome occurred. Outcome Context is
descriptive evidence about results allowed so far, not a causal or predictive
model. Its structured response contains prose fields (`summary`,
`notable_changes`, and `sample_note`). A malformed response or Gemini failure
is reported by the note request and does not remove or block deterministic
comparison results. The comparison remains available when Gemini is unavailable
or unconfigured.

Successful notes are cached in process for 60 seconds, keyed by game, pitcher,
baseline window, and a digest of the computed comparison and outcome context.
The process lock is held during generation so simultaneous same-state requests in one
process share the result rather than both spending quota. Errors are not
cached. The cache is local to one backend process and is not a distributed
rate limit.

## Live monitoring, caches, and ingestion

The browser initiates live monitoring from the pitcher analysis page. It posts
the selected game and pitcher to `/api/live/sync` immediately, then repeats
every 20 seconds while the root-level provider is active. Route changes within
the same tab do not stop the loop. The global navigation shows monitoring
state, the tracked game/pitcher, last-sync time and any sync error; users can
stop or resume from there. Newly observed event or pitch-mix alerts produce an
in-app notice linking to Alerts, while the initial alert list is treated as
existing history. Selected game and pitcher IDs are saved in browser local
storage, but a reload does not resume automatically: the user can explicitly
resume the restored session. Monitoring stops when the game reaches Final, the
user stops it, or the tab closes. Browser throttling can delay sync while the
tab is in the background. The live schedule polls every 30 seconds while live
games are present. Game summary, comparison, locations, events, and alert queries use approximately
15-second polling while their view is active. Polling pauses in the background
for the query hooks that opt out of background refetching.

The backend's MLB live snapshot cache is in-process and keyed by game, with a
10-second fresh period and stale-while-revalidate behavior before its maximum
stale age. Schedule responses have a separate in-process cache. Statcast
baseline pitch records are cached for six hours by pitcher and date window.
Successful Gemini notes use the separate 60-second cache described above.
These caches are discarded on process restart and are not shared across
backend replicas.

Ingestion processes completed plate appearances for selected pitchers. The
database enforces uniqueness on `(game_id, at_bat_index)` and inserts with
conflict handling; rule evaluation runs only for newly inserted plate
appearances. Alert uniqueness also includes plate appearance, subject role, and
rule, so replaying a feed snapshot or fixture does not create duplicate event
or alert rows. Pitch-mix signal records are upserted by their game, pitcher,
metric, and pitch-type identity.

## Primary API paths

| Need | Endpoint | Behavior |
| --- | --- | --- |
| Discover games | `GET /api/live/games?date=YYYY-MM-DD` | Schedule, score/state, current pitcher for live games, and probable pitchers |
| Refresh game context | `GET /api/live/games/{game_id}/summary` | Current linescore and current pitcher from the cached live feed |
| Inspect participants | `GET /api/live/games/{game_id}/participants` | Read-only player and role discovery |
| Ingest a live snapshot | `POST /api/live/sync` | Idempotently process completed PAs for selected pitchers and update pitch-mix signals |
| Compare outing | `GET /api/live/games/{game_id}/pitchers/{pitcher_id}/comparison` | Deterministic Usage / Velocity table and WATCH / ALERT signals; no Gemini call |
| Plot locations | `GET /api/live/games/{game_id}/pitchers/{pitcher_id}/locations` | Today's valid, typed pitch-location points from the live snapshot |
| Generate note | `POST /api/live/games/{game_id}/pitchers/{pitcher_id}/comparison/note` | On-demand Gemini narration with a process-local cache |

## Current limitations

- Monitoring is browser-driven. Route navigation within the same tab preserves
  polling, but closing the tab stops it; there is no independent server-side
  worker. Background-tab throttling can delay polling.
- Browser storage restores the selected game and pitcher, not an active
  monitoring loop. A restored session requires an explicit Resume action.
- Caches are in-memory per process; restarts clear them and multiple replicas
  do not share them. Gemini's cooldown/cache therefore protects repeated
  same-state requests within one process only.
- Location is Today-only. Historical Statcast location overlays, location
  alerts, count/handedness splits, movement, and causal explanations are not
  implemented.
- A location pitch with an unrecognized type is excluded from the returned
  total; a recognized pitch lacking coordinates still counts but cannot be
  plotted.
- This is descriptive scouting support, not a prediction system or a
  statistical significance testing system.
- The deployment uses SQLite on one persistent volume and is intended for a
  low-traffic demo, not multi-replica concurrent writes.
- The product has no authentication. The Gemini note endpoint is public and
  its cache is not a general per-user or distributed rate limiter.
