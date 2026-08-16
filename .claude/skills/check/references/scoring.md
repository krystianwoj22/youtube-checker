# The 0-100 scale, the gates, and the evidence schemas

## Why the score is computed in code

The score is produced by `scripts/score.py`, not by the model. A model asked to produce
both a number and a justification will move the number to suit the justification. Here
the evidence goes in, the number comes out, and the model cannot negotiate with it.

If you think the number is wrong, say so in prose. Do not edit the number.

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
| Nothing on the topic has ever beaten its own channel median | 35 | B |
| A 100K+ channel covered it in the last 30 days | 38 | B |
| Requires an enterprise tier | 45 | B |

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

## Evidence schema — Mode B

```json
{
  "mode": "B",
  "topic": "string — one plain sentence",
  "videos_90d_over_20k": 4,
  "big_channel_covered_30d": false,
  "best_overperformance_ratio": 2.1,
  "overperformance_sample_size": 12,
  "hours_needed": 8,
  "access_blockers": "none | paid_tier | enterprise",
  "packaging_strength": 7,
  "decay": "evergreen | months | weeks | dead_soon",
  "audience_fit": "core | adjacent | mismatch"
}
```

Weights: real demand .30 · saturation .22 · packaging .20 · executability .13 ·
decay .08 · audience fit .07

Real demand is the heaviest input because it is the most important check in the tool.
Packaging is second-heaviest because in this niche the same topic does 3K or 300K on
packaging alone.

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
