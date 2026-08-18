# The 0-100 scale, the gates, and the evidence schemas

## Why the score is computed in code

The score is produced by `scripts/score.py`, not by the model. A model asked to produce
both a number and a justification will move the number to suit the justification. Here
the evidence goes in, the number comes out, and the model cannot negotiate with it.

If you think the number is wrong, say so in prose. Do not edit the number.

The arithmetic being in code does not make the inputs honest. The judgement-heavy
inputs (packaging, hours, launch size) are still yours to fill — fill them against
evidence, and prefer the verifiable forms (e.g. `packaging_checks`) wherever one exists.

## What the number means

> The score expresses the **predicted multiple of Krystian's own channel median** for
> this video, not an abstract quality rating.

Abstract points cannot be wrong, so they teach you nothing. A multiple can be checked
at +30d, which is what makes the prediction log worth keeping.

| Score | Meaning | Verdict |
|---|---|---|
| 85-100 | Likely 3×+ median | 🔴 **FILM NOW** — drop other work |
| 70-84 | Likely 1.5-3× median | 🟢 **FILM** — take the next slot |
| 55-69 | Around median | 🟡 **SAFE FILLER** — fine for the calendar, not a priority |
| 40-54 | Below median | ⚪ **ONLY IF** — only with a strategic reason (course material, SEO for a course) |
| 0-39 | Well below median | ⛔ **DON'T FILM** |

Both modes use "multiple of your median", which is the only reason a single scale is
allowed across two different rubrics.

The median is computed at runtime by `scripts/median.py`. **Never hardcode it.**

### The predicted band is sized to the channel, not to a constant

When the channel median is available, the reported low-high band is a **50% interval
derived from the channel's own p25/p75 spread** (its real upload-to-upload volatility).
A consistent channel gets a tight band; a spiky one gets an honest wide one. Quote the
band, not the point score — the point score exists for the log, the band is the claim.

See the full curve: `python scripts/score.py --table`

---

## Hard gates

A gate **caps** the final score regardless of how strong everything else is. The tool
must be able to say ⛔ DON'T FILM, and these are what make that happen.

| Gate | Cap | Mode |
|---|---|---|
| 3+ channels published in the last 7 days (window closed) | 35 | A |
| Viewer access: waitlist | 39 | A |
| Viewer access: enterprise-only | 32 | A |
| Viewer access: limited rollout / high tier | 60 | A |
| `hours_needed > hours_window_left` (cannot ship in time) | 45 | A |
| Nothing has ever beaten its own channel median on the topic — **and neither has yours** | 35 | B |
| A 100K+ channel covered it in the last 30 days **and beat its own median doing it** | 38 | B |
| Your own channel published on the topic < 60 days ago (cannibalisation) | 45 | B |
| Requires an enterprise tier | 45 | B |

Two gates are **conditional by design**:

- **Dead topic** is overridden when *your own* channel over-performed on the topic
  (`own_best_topic_ratio >= 1.2`). Your audience proving demand outranks the absence
  of proof on someone else's audience.
- **Big channel** only fires when the big channel's video **beat its own median**.
  A 100K+ channel posting a flop on the topic is contested ground, not a closed door
  — and free packaging intel. `supply.py` reports both fields.

When a gate fires, quote its reason verbatim. The reader must know the score was
capped, not earned.

**Never soften a gate because the idea is exciting.** The gates encode decisions
already made; re-litigating them at judgement time is how the tool becomes a rubber
stamp.

---

## Evidence schema — Mode A

```json
{
  "mode": "A",
  "topic": "string — one plain sentence",
  "launch_size": "major | mid | niche",
  "viewer_access": "public_free | public_paid | limited | waitlist | enterprise",
  "demoable": "yes | partial | no",
  "channels_published_7d": 0,
  "hours_needed": 6,
  "hours_window_left": 36
}
```

Weights: viewer access .28 · launch size .22 · supply .20 · timing .18 · demoable .12

Viewer access carries the most weight because it is the single strongest predictor in
Mode A. Demand data is absent on purpose — on day zero it does not exist.

The sub-score spreads are wide on purpose: a niche, non-demoable, contested launch
lands in ONLY IF territory **without** a gate firing. Green is not the ungated default.

## Evidence schema — Mode B

```json
{
  "mode": "B",
  "topic": "string — one plain sentence",

  "own_topic_videos": 2,
  "own_best_topic_ratio": 1.6,
  "own_recent_topic_video_days": null,

  "videos_90d_over_20k": 4,
  "big_channel_covered_30d": false,
  "big_channel_overperformed_30d": false,
  "best_overperformance_ratio": 2.1,
  "best_overperformance_age_days": 21,
  "overperformance_sample_size": 12,
  "topic_momentum": "accelerating | steady | fading | unknown",

  "hours_needed": 8,
  "access_blockers": "none | paid_tier | enterprise",
  "packaging_checks": {
    "differentiated_angle": true,
    "thumbnail_stands_out": true,
    "verifiable_promise": true,
    "curiosity_gap": false,
    "title_specific": true
  },
  "audience_fit": "core | adjacent | mismatch"
}
```

`supply.py mode-b` produces every field in the middle block **and** the own-history
block in one run. `history.py --q "<topic>"` produces the own-history block alone.
`packaging_strength` (0-10) is accepted where `packaging_checks` cannot be filled;
legacy `decay` is accepted where momentum cannot be computed.

Weights: **own history .22** · real demand .20 · packaging .18 · saturation .15 ·
executability .10 · momentum .09 · audience fit .06

Own history is the heaviest input because it is the only one about **Krystian's
audience** — every other Mode B input describes someone else's. Three of your videos
doing 0.6× your median is not overridden by a competitor doing 2.4× on theirs.
`own_topic_videos: 0` is neutral (untried ≠ bad); `null` means the lookup could not
run — never guess the ratio.

Overperformance evidence older than ~60 days is **stale** and the demand sub-score is
capped — a topic that peaked last quarter is not a topic peaking now. Momentum measures
exactly that: are the winning videos clustered in the last 30 days, or all older?

### The saturation curve is not monotonic

| videos over 20K in 90d | sub-score |
|---|---|
| 0 | 55 — unproven, not an opening |
| 1-2 | 85 — demand proven, room left |
| 3-5 | 70 |
| 6-10 | 50 |
| 11-20 | 32 |
| 20+ | 18 |

Zero competitors scores *worse* than two. That is deliberate: an empty search means
the topic is unproven, and the real-demand check has to carry the whole idea alone.

Use the **title-matched** count (`videos_90d_over_20k` from supply.py is already
matched; the raw count is `videos_90d_over_20k_unfiltered`). If the match ratio is
low, the query is too broad — tighten it before believing the saturation number.

---

## Running it

```bash
# from evidence file
python scripts/score.py --file /tmp/evidence.json --json

# quick check without a median lookup
echo '{"mode":"A",...}' | python scripts/score.py --no-median

# see the whole scale
python scripts/score.py --table
```

Missing a required field is an error, not a default. Every check must produce a
concrete finding before a score exists.
