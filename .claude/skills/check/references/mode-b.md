# Mode B — existing idea / backlog row

**The question:** the idea looked good on paper — what would make it fail in practice?

Before you start: if this is a Notion backlog row, re-read `independence.md`. You may
read only `Title`, `Summary`, `Target Keyword` until your verdict exists.

Run the checks in this order.

---

## 1. Saturation right now

The backlog score was computed this morning at best, and saturation moves in days.
Re-check live:

```bash
python scripts/supply.py mode-b --q "<topic>"
```

- How many videos on this topic from the last 90 days are above ~20K views?
- Has any channel over 100K subs covered it in the last 30 days?

→ `videos_90d_over_20k`: integer
→ `big_channel_covered_30d`: true/false

**If a 100K+ channel covered it in the last 30 days, you lose the algorithm fight.
Say so plainly.** Hard gate, caps at 38.

Note the shape of the saturation curve: **zero competitors is not the best outcome.**
1-2 proven videos is the sweet spot — demand exists and there is still room. Zero
means unproven, and check 2 has to carry the entire idea.

## 2. Real gap vs dead topic

**The most important check in the entire tool.**

Has **any** video on this topic significantly beaten its own channel's median?

Not "got a lot of views" — a big channel's floor beats a small channel's ceiling, and
that tells you nothing about the topic. The question is whether the topic made a video
outperform *what that channel normally does*.

→ `best_overperformance_ratio`: best video's views ÷ that video's own channel median
→ `overperformance_sample_size`: how many videos you actually checked

`supply.py mode-b` computes this by pulling each candidate channel's median.

**If nothing has ever over-performed on this topic, "no competition" means NO DEMAND,
not an opening.** Ratio below 1.0 is a hard gate, caps at 35.

Most "nobody is covering this!" ideas die here. This is the one distinction the daily
system is structurally bad at, and the main reason this tool exists separately.

If the medians could not be computed, the script says so — do **not** let a failed
lookup masquerade as a dead topic. Get the number from a screenshot instead
(open the top channel, eyeball the median of its last ~10 uploads).

## 3. Executability

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

## 4. Packaging survival

Would the title and thumbnail survive in the sidebar **next to the competitors found
in check 1**? Look at their actual titles and thumbnails — that is the comparison set,
not an abstract standard.

→ `packaging_strength`: 0-10

| | |
|---|---|
| 0-3 | generic, indistinguishable from existing videos, no visual hook |
| 4-6 | fine but not distinctive; would be picked only by someone already searching |
| 7-8 | a clear angle competitors do not have; thumbnail concept is obvious |
| 9-10 | the packaging alone would make someone click over a bigger channel |

In this niche the same topic does 3K or 300K on packaging alone, so packaging is
**scored, not assumed**. Weight: 0.20 — the second-heaviest input.

## 5. Downside / decay

- What specifically makes this flop
- Is it evergreen or dead in two weeks
- Audience-mismatch risk (too advanced / too basic for the channel)

→ `decay`: `evergreen` | `months` | `weeks` | `dead_soon`
→ `audience_fit`: `core` | `adjacent` | `mismatch`

---

## Only after all five are written

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
  "videos_90d_over_20k": 4,
  "big_channel_covered_30d": false,
  "best_overperformance_ratio": 2.1,
  "overperformance_sample_size": 12,
  "hours_needed": 8,
  "access_blockers": "none",
  "packaging_strength": 7,
  "decay": "months",
  "audience_fit": "core"
}
```

Weights: real demand .30, saturation .22, packaging .20, executability .13,
decay .08, audience fit .07.
