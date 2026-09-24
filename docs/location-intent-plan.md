# Pitch Location vs. Intended Location: Investigation & Plan

Status: **proposal, not implemented.**

An analyst called several home runs "mistake pitches": pitches that ended up
where hitters like to attack. This document asks whether the product can say
anything like that, and how it could do so without claiming more than the data
supports.

> **Where a pitch ended up is not where the pitcher meant to throw it.**
> The product can measure where a pitch finished, how dangerous that spot
> usually is, and how unusual it is *for this pitcher in this situation*. No
> public data tells us where the catcher set up or what the pitcher was aiming
> at, so the product should never say a pitcher "missed his spot."

---

## 1. What Statcast / Savant tells us about location and execution

### Fields available per pitch

| Area | Statcast CSV columns | MLB live feed (`playEvents[]`) |
| --- | --- | --- |
| Where the pitch crossed the plate | `plate_x`, `plate_z` (ft, catcher's view) | `pitchData.coordinates.pX / pZ` |
| Strike-zone edges for that batter | `sz_top`, `sz_bot` | `pitchData.strikeZoneTop / Bottom` |
| Zone bucket | `zone` (1–9 inside the zone, 11–14 outside) | `pitchData.zone` |
| Pitch identity | `pitch_type`, `release_speed`, spin, `pfx_x/z`, release point, extension, `arm_angle` (2020+) | `details.type`, `startSpeed`, `breaks` |
| Situation | `balls`, `strikes`, `stand`, `p_throws`, outs, runners | `count`, `matchup.batSide`, … |
| Result of the pitch | `description` (called strike, swinging strike, foul, in play…), `events` | `details.description`, `play.result` |
| Batted ball | `launch_speed`, `launch_angle`, `hit_distance_sc`, `bb_type` | `hitData.launchSpeed / launchAngle` |
| Result value | `estimated_woba_using_speedangle` (xwOBA), `delta_run_exp` (run value of the pitch) | none, so it would have to be computed |
| Swing (2024+) | `bat_speed`, `swing_length` | partial |

Savant also publishes derived views such as **attack regions** (Heart /
Shadow / Chase / Waste) and run value by region. These are fixed boxes
around the rulebook zone, so they can be rebuilt from `plate_x`, `plate_z`,
`sz_top` and `sz_bot`.

### What this data can and cannot support

It **can** support:

- where the ball crossed the plate
- how much of the plate that spot covers (heart vs. edge)
- what happened on the pitch and on any ball put in play
- how that spot compares with where this pitcher usually throws this pitch
- how much damage that spot usually allows, for the league or for this pitcher

It **cannot** support:

- where the catcher set up his glove
- what location the pitcher and catcher called
- whether the pitcher "hit his spot"

To its credit, the current system is honest about this. It only ever shows
where pitches actually finished.

### A gap in the current code

The problem statement lists "historical pitch-location tendencies", but the
code does not have them yet:

- `app/pregame/sources/statcast.py → parse_csv_rows` only keeps pitch type,
  count and velocity. `PitchRecord` has no `plate_x`, `plate_z`, `sz_*`,
  `stand` or batted-ball fields.
- Locations appear only for today's outing, from the MLB live feed
  (`app/comparison/locations.py`).

So any comparison against the pitcher's own history first needs the
Statcast record to carry location. This is Phase 1 below.

---

## 2. Can intended location be observed or reliably derived?

**Observed: no public source.**

| Source | Records intent? | Public? |
| --- | --- | --- |
| Statcast / Savant CSV | No | Yes |
| MLB Stats API live feed | No | Yes |
| Hawk-Eye pose tracking (catcher body and glove) | Could be derived from it | No (teams only) |
| Video charting of the catcher's target (e.g. commercial data providers) | Yes, hand-charted | Paid or proprietary |
| Our own analyst tagging from broadcast video | Yes, but slow and inconsistent between taggers | Could be built |

Public "command" style metrics, such as location-quality scores in the
Location+ / Pitching+ family, score **how good the location was** given the
pitch and count. They do **not** measure how close the pitch came to its
target. They answer "was this a good place to throw it?", not "did he hit
his spot?"

**Derived: only under assumptions, each with a known way to fail.**

| Method | Idea | Failure mode |
| --- | --- | --- |
| A. Damage region | Pitches in the Heart region, or in a zone cell with high run value, count as "hittable" | Some heart pitches are intentional. With a 3-0 count, a fastball down the middle is often the plan. |
| B. Deviation from the pitcher's usual pattern | Compare against where this pitcher throws this pitch in this count to hitters on this side. Measure how far outside that cloud the pitch landed. | It mixes up missing the target with choosing a different target (a pitch up to set up the next pitch, pitching around a hitter, a backdoor pitch). Pitchers with a wide spread look "wild". |
| C. Mixture / latent-target models | Treat each pitch type × count as a small set of targets plus scatter, and assign each pitch to its likeliest target | Research-grade. The fitted targets cannot be checked without real target data, and small samples per pitcher make them unstable. |
| D. Human annotation | An analyst tags the catcher's target from video | The only real source of intent. It is expensive, covers few pitches and is subjective, so it must carry its provenance. |

**Recommendation:** ship **A and B as descriptive facts**, with vocabulary
that makes no claim about intent. Treat C as research that is not on the
roadmap. Keep a **field in the schema for D** so intent can be added later
without breaking anything. Build no D UI now.

---

## 3. What the product should say

Replace "mistake pitch" and "missed target" with three separate observable
facts, each computed deterministically:

1. **Plate region**: *Heart / Shadow / Chase / Waste*. This is geometry only.
   It can be computed for every pitch from today's live feed.
2. **Location risk**: how much damage that region or cell allows for this
   pitch type and batter side, using league or pitcher history. Example: *"a
   region where his four-seamer has allowed a .520 xwOBA vs. LHH (n = 64)"*.
3. **Location atypicality**: how unusual the spot is compared with this
   pitcher's own history for the same pitch type, batter side and count
   group. Example: *"further toward the middle than 90% of his sliders to RHH
   when ahead in the count"*.

A home run can then be described as, for example: *"Heart-region four-seamer
in a 1-1 count; this spot is atypical for him (outside his usual 1-1
four-seam area vs. LHH); 108 mph EV."* That is a set of facts that a scout can
read as "probably a mistake". The system does not state it.

Allowed and banned wording, enforced in the Gemini prompt and checked in tests:

| Allowed | Banned |
| --- | --- |
| "caught the heart of the zone", "middle-middle" | "missed his spot / target", "mistake pitch" |
| "outside his usual location for this pitch and count" | "meant to", "intended", "tried to", "wanted to" |
| "a region that has been damaging for this pitch" | "lost command", "couldn't locate" (these state a cause) |

This follows existing rules. The comparison prompt already bans guessing
*why* something happened (`app/comparison/llm/gemini.py`), and Design
Decision D says the product is descriptive.

---

## 4. System design

### 4.1 Data (Phase 1): carry location into historical records

- `PitchRecord` (`app/pregame/schemas.py`): add nullable `plate_x`,
  `plate_z`, `sz_top`, `sz_bot`, `stand`, `zone`, `description`, `events`,
  `launch_speed`, `launch_angle`, `estimated_woba_using_speedangle` and
  `delta_run_exp`. Follow the existing rule: missing values become `None`,
  never `0`. Reuse `_blank_is_missing`.
- `parse_csv_rows`: map the new columns. Add fixture rows to
  `tests/pregame/fixtures/statcast_sample.json`, including blank location and
  blank `sz_*`.
- The 6-hour Statcast cache is unchanged; each cached row just gets wider.
  Check the memory impact on the Railway instance. A season of pitches for one
  pitcher is about 3k rows, which is small.

### 4.2 Pure analysis module: `app/location/`

It follows the same style as `app/pregame/aggregation.py`: pure functions,
no I/O, no LLM.

```
app/location/
├── regions.py      classify_region(plate_x, plate_z, sz_top, sz_bot) -> Region | None
├── profile.py      build_location_profile(records, pitch_type, stand, count_group) -> LocationProfile
├── atypicality.py  score_atypicality(pitch, profile) -> AtypicalityResult
├── risk.py         region_risk(records, pitch_type, stand) -> {Region: RiskCell}
└── schemas.py
```

Key decisions:

- **Regions.** Normalize the vertical position against the pitch's own
  `sz_top`/`sz_bot`, the same way the frontend's `plotY` does. Use a fixed
  17-inch plate plus the ball radius horizontally. Put all boundary constants
  in one place, with a note on where they came from. Phase 0 checks them
  against Savant's attack-region definition.
- **Count groups.** Use *ahead / even / behind / two-strike / 3-ball*, not
  all 12 counts, to keep samples usable. 3-ball counts stay separate
  because pitchers often aim at the heart on purpose there.
- **Profile fallback order** when a bucket is too small: (type, stand,
  count group) → (type, stand) → (type). The result must say **which level
  was used** and its `sample_size`. It never falls back silently, following
  the existing `SampleStatus` convention.
- **Atypicality metric.** Start with the empirical percentile of the pitch's
  distance from the profile's median location, scaled per axis by robust
  spread. A Mahalanobis-style distance on a small sample is easier to
  explain and to test than a KDE. Output: `percentile` (0–100), `is_atypical`
  (for example ≥ 90th percentile) and a `direction` ("toward middle", "up",
  "arm-side", …). *Toward middle* is what matters most for "mistake" cases.
- **Sample-size gate.** Add a new threshold in `app/pregame/sample_size.py`,
  for example ≥ 40 pitches in the bucket used. Below that, return
  `is_atypical: None` (unknown), not `False`.
- **Risk.** Phase 3 starts with the pitcher's own xwOBA on contact and run
  value per region, with the region's `n`. League priors or shrinkage are a
  later improvement. Only report risk when `n` clears the gate.

### 4.3 Schemas and the "intent" slot

```python
class PitchLocationFact(BaseModel):
    pitch_type: str
    count: str                   # "1-1"
    count_group: CountGroup
    stand: Literal["L", "R"] | None
    region: Region | None        # None when location/zone is unmeasured
    atypicality: AtypicalityResult | None
    region_risk: RiskCell | None
    # Intent is NOT inferred. The field is kept so annotated data can be added later.
    intended_location: IntendedLocation | None = None
    intent_source: Literal["none", "annotated"] = "none"
```

`DamagePitchFact` adds outcome data (event, EV, LA) for the final pitch of
home runs, extra-base hits and hard-hit plate appearances. Every payload also
carries a constant limitation string: *"Intended location is not available
in public data; location facts describe where pitches finished, not
command."*

### 4.4 API

- Extend `GET .../pitchers/{id}/locations` with `region` on each point and an
  optional `damage` block. The existing shape does not change; only fields are
  added.
- Add `GET .../pitchers/{id}/damage-pitches`. It returns a
  `DamagePitchFact[]` for today's outing and needs the Statcast baseline for
  atypicality and risk. If the baseline is unavailable it still returns the
  region facts, the same way `baseline_available: false` works today.
- Pregame (later): a per-pitch-type location profile summary, e.g. "four-seam
  vs. LHH: mostly up and arm-side". This matches the existing brief style.

### 4.5 LLM boundary

- Add `damage_pitches: list[DamagePitchFact]` to `ComparisonNoteInput`.
- Add the vocabulary rules from §3 to the system prompt.
- Add a **deterministic post-check** on Gemini output: a regex over the note
  for banned phrases. On a hit, return 502 with a reason, or run one
  regeneration. Test it in `tests/comparison/test_llm_boundary.py` with a fake
  provider that returns a banned phrase.

### 4.6 Frontend

- `PitchLocations.tsx`: optional Heart/Shadow overlay, and damage pitches
  drawn with a ring and a tooltip containing the facts from §3.
- Optional overlay of the historical profile (median and spread for the
  selected pitch type and batter side). The live-only filter stays a visual
  filter only, per Design Decision G.
- A short explainer ("Location ≠ intent") next to the panel.

---

## 5. Phased plan

| Phase | Scope | Exit criteria |
| --- | --- | --- |
| **0. Research spike** (offline script, not shipped) | Pull 1–2 seasons for ~20 pitchers. Check that the Savant columns exist and how often values are missing. Rebuild attack regions and match Savant. Measure whether "atypical, toward middle" adds damage signal *beyond* region (for example, xwOBA on Heart pitches, atypical vs. typical). Also check whether the 2026 zone rules change the meaning of `sz_top`/`sz_bot`. | A short write-up. If atypicality adds nothing beyond region, **drop Phase 2** and ship regions and risk only. |
| **1. Data** | Wider `PitchRecord` and parser, plus tests | All existing tests pass; new fixture tests for blank and missing values |
| **2. Regions + damage pitches (live only)** | `regions.py`, per-point `region`, `damage-pitches` without baseline, frontend ring and tooltip | Can be computed with no Statcast; unit tests at region boundaries |
| **3. Profile + atypicality + risk** | `profile.py`, `atypicality.py`, `risk.py`, sample-size gates, fallback reporting | Deterministic tests with synthetic clouds; `None` below the gate |
| **4. LLM** | Prompt rules, input extension, banned-phrase post-check | Boundary tests pass; the note cites only supplied facts |
| **5. (Deferred) Annotation** | Analyst tags the catcher's target from video → `intent_source="annotated"` | Needs a separate product decision |

Phases 1–2 are low risk and deliver value on their own. Phase 3 depends on
the Phase 0 result.

---

## 6. Risks

- **Intentional heart pitches.** 3-ball counts, a fastball in with a big
  lead, or a get-me-over breaking ball. Mitigation: count groups, plus
  wording that never implies an error.
- **Intentional waste or chase pitches that get hit.** These look atypical
  in the "away" direction, not toward the middle. Only *toward middle*
  should be surfaced as damage-relevant.
- **`sz_top`/`sz_bot` noise.** These are estimated per pitch from the
  batter's stance. Region boundaries have a few inches of uncertainty, so
  borderline pitches should say "edge" rather than pick a side confidently.
- **Pitch-type misclassification** between the live feed and Statcast (a
  known issue in `live_metrics._normalize_pitch_type`) puts a pitch in the
  wrong profile. Reuse the existing normalization.
- **Small samples.** Relievers and new pitch types. Gates and explicit
  `None` handle this.
- **Over-reading.** A few damage pitches in one game are anecdotes. The UI
  should list them as individual events, never as a rate or trend.

## 7. Open questions for the product owner

1. Is Phase 0 worth doing before any UI, or should Phases 1–2 ship first
   because they need no research?
2. Should location risk use the **pitcher's** history, the **league**, or
   (later) the **batter's** damage zones? The batter's zones fit "areas
   hitters like to attack" best but need batter-side Statcast pulls.
3. Is analyst annotation of intent (Phase 5) something you would actually
   use, or should it stay out of scope for good?
