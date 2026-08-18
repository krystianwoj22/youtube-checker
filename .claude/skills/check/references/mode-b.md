# Mode B — existing idea / backlog row

**The question:** the idea looked good on paper — what would make it fail in practice?

Before you start: if this is a Notion backlog row, re-read `independence.md`. You may
read only `Title`, `Summary`, `Target Keyword` until your verdict exists.

Run the checks in this order.

---

## 1. Your own channel's history on this topic — FIRST

**The only check that is about Krystian's audience.** Every other number in this mode
describes someone else's.

```bash
python scripts/history.py --q "<topic>"        # or read it off supply.py mode-b output
```

- How many prior uploads on this topic, and what multiple of **your own median** did
  the best one do?
- How recently did you last publish on it?

→ `own_topic_videos`: integer (0 = untried, which is neutral; `null` = lookup failed)
→ `own_best_topic_ratio`: best own video's views ÷ your median
→ `own_recent_topic_video_days`: age of your most recent video on the topic

This is the heaviest-weighted input (0.22). If three of your MCP videos did 0.6× your
median, a competitor doing 2.4× on their channel does not override that — their
audience is not yours. Conversely `own_best_topic_ratio >= 1.2` **overrides the
dead-topic gate**: your audience already proved the demand.

**Cannibalisation is a hard gate:** your own video on the topic under 60 days old caps
the score at 45. A second video splits your own audience unless the angle is genuinely
different — and if it is, that angle is the topic, so re-run the check on it.

## 2. Saturation right now

The backlog score was computed this morning at best, and saturation moves in days.
Re-check live:

```bash
python scripts/supply.py mode-b --q "<topic>"
```

- How many videos on this topic from the last 90 days are above ~20K views —
  **counting only videos whose title actually matches the topic**? supply.py filters
  this for you (`videos_90d_over_20k`; the unfiltered count is reported alongside).
  If `title_match_ratio` is low, the query is too broad — tighten it before believing
  the number.
- Has any channel over 100K subs covered it in the last 30 days — **and did their
  video beat their own median?**

→ `videos_90d_over_20k`: integer (title-matched)
→ `big_channel_covered_30d`: true/false
→ `big_channel_overperformed_30d`: true/false

**The gate is the second field, not the first.** A 100K+ channel that covered the
topic *and won on it* means you lose the algorithm fight — hard gate, caps at 38.
A 100K+ channel that covered it and **underperformed its own median** is contested
ground, not a closed door: say so, and study why their packaging missed — that is
free intel for yours.

Note the shape of the saturation curve: **zero competitors is not the best outcome.**
1-2 proven videos is the sweet spot — demand exists and there is still room. Zero
means unproven, and check 3 has to carry the entire idea.

## 3. Real gap vs dead topic

Has **any** video on this topic significantly beaten its own channel's median?

Not "got a lot of views" — a big channel's floor beats a small channel's ceiling, and
that tells you nothing about the topic. The question is whether the topic made a video
outperform *what that channel normally does*.

→ `best_overperformance_ratio`: best video's views ÷ that video's own channel median
→ `best_overperformance_age_days`: how old that winner is
→ `overperformance_sample_size`: how many videos you actually checked

`supply.py mode-b` computes this by pulling each candidate channel's median.

**If nothing has ever over-performed on this topic — including your own uploads —
"no competition" means NO DEMAND, not an opening.** Ratio below 1.0 is a hard gate,
caps at 35, unless your own channel over-performed on it (check 1).

A winner older than ~60 days is **stale evidence** — the demand sub-score is capped
automatically. A topic that peaked last quarter is not a topic peaking now.

If the medians could not be computed, the script says so — do **not** let a failed
lookup masquerade as a dead topic. Get the number from a screenshot instead
(open the top channel, eyeball the median of its last ~10 uploads).

## 4. Momentum

Is the topic producing winners **right now**, or did it already burn out? supply.py
computes this from the timing of the >20K videos: clustered in the last 30 days =
accelerating; all older than a month = fading.

→ `topic_momentum`: `accelerating` | `steady` | `fading` | `unknown`

From a screenshot: look at the upload dates on the winning videos. If the screenshot
cannot tell you, pass `unknown` — never guess `accelerating`.

## 5. Executability

Can Krystian actually build the demo? The daily agent has no idea what he can build;
this tool must.

- How many hours, realistically — research + build + record + edit
- What tools and accounts does it need
- Does it require a paid tier he does not have

→ `hours_needed`: number
→ `access_blockers`: `none` | `paid_tier` | `enterprise`

An idea requiring a paid enterprise tier or 3 days of setup **is a different idea than
it looks on paper**. Check `config/config.json` → `execution.paid_tools` for what he
already has.

## 6. Packaging survival — answer the five checks, don't emit a vibe

Would the title and thumbnail survive in the sidebar **next to the competitors found
in check 2**? Look at their actual titles and thumbnails — that is the comparison set,
not an abstract standard. Answer each check with a yes/no you could defend:

→ `packaging_checks`:

| check | passes when |
|---|---|
| `differentiated_angle` | the working title has an angle none of the found competitor titles has |
| `thumbnail_stands_out` | the thumbnail concept is visibly different from the top 5 found |
| `verifiable_promise` | the title's promise can be proven on screen in the first 15 seconds |
| `curiosity_gap` | the title opens a question the thumbnail does not answer |
| `title_specific` | there is a number, named tool, or concrete outcome in the title |

Five booleans with reasons are harder to inflate than one 0-10 gut number. The legacy
`packaging_strength` (0-10) is still accepted when the competitor set could not be
seen at all. Weight: 0.18 — in this niche the same topic does 3K or 300K on packaging
alone.

## 7. Audience fit

→ `audience_fit`: `core` | `adjacent` | `mismatch`

---

## Only after all seven are written

Fetch the daily system's `Viral Score` and append the comparison line:

```
daily system: 82 · checker: 61 · disagreement is on saturation
```

Name the axis you disagree on. Never reconcile the two numbers.

---

## Evidence JSON

```json
{
  "mode": "B",
  "topic": "<one plain sentence — what the video actually is>",
  "own_topic_videos": 2,
  "own_best_topic_ratio": 1.6,
  "own_recent_topic_video_days": null,
  "videos_90d_over_20k": 4,
  "big_channel_covered_30d": false,
  "big_channel_overperformed_30d": false,
  "best_overperformance_ratio": 2.1,
  "best_overperformance_age_days": 21,
  "overperformance_sample_size": 12,
  "topic_momentum": "steady",
  "hours_needed": 8,
  "access_blockers": "none",
  "packaging_checks": {
    "differentiated_angle": true,
    "thumbnail_stands_out": false,
    "verifiable_promise": true,
    "curiosity_gap": true,
    "title_specific": true
  },
  "audience_fit": "core"
}
```

Weights: own history .22, real demand .20, packaging .18, saturation .15,
executability .10, momentum .09, audience fit .06.
