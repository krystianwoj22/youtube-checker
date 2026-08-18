# Mode A — fresh news / launch

**The question:** is there a first-mover window here, and can you get through it in time?

Demand data is **deliberately absent** from this rubric. On day zero it does not exist,
and pretending otherwise is what makes a fresh news item lose to a safe proven topic.
Mode A measures different things, not the same things with missing data.

The sub-score spreads are wide on purpose: a niche, non-demoable, contested launch
lands in ONLY IF territory **without** any gate firing. Passing the gates is not the
same as earning a green verdict.

Run the checks in this order. Each must yield a number or a concrete finding.

---

## 1. Launch size

Official release from a major player (Anthropic, OpenAI, Google, n8n, Make, Zapier)
vs a niche tool.

With a major player, **demand is a given** — the only question is who is first.

→ `launch_size`: `major` | `mid` | `niche`

Check the source. A community integration announced *about* Anthropic is not an
Anthropic release. A rebrand or a pricing tweak from a major player is not a launch.

## 2. Can the viewer touch it TODAY

**This is the single strongest predictor in Mode A.** A video about something the
viewer cannot run right after watching underperforms even when the news is huge.

Verify, do not assume:
- Is it publicly available right now, or announced-but-not-shipped?
- Waitlist? Gradual rollout? Region-locked?
- Does it work on a free or cheap plan, or only on a high tier?

→ `viewer_access`:
| value | meaning |
|---|---|
| `public_free` | anyone can use it today, free or trivially cheap |
| `public_paid` | available today on a plan the audience plausibly has |
| `limited` | gradual rollout, region-locked, or high paid tier — **caps the score at 60** |
| `waitlist` | announced, access queued — **caps at 39 (DON'T FILM)** |
| `enterprise` | enterprise/sales-contact only — **caps at 32 (DON'T FILM)** |

A waitlist or enterprise-only release caps the score hard. That is intended.

## 3. Is it demoable on screen

A build/demo beats talking-about-the-news by a wide margin. If there is nothing to
show, say so and let the score fall.

→ `demoable`: `yes` (you can build something on camera) | `partial` (UI walkthrough,
no real build) | `no` (talking head over a blog post)

## 4. Current supply

```bash
python scripts/supply.py mode-a --q "<topic>"
```

Count distinct channels that published on this in the last 7 days.

→ `channels_published_7d`: integer

**3+ channels already published = the window is closed, and the verdict is NO
regardless of how good the news is.** This is a hard gate. Do not argue with it in
the output; report it.

If search returns noise (the query is too generic), tighten the query to the product
name plus the feature name, and say in the evidence line what you searched for.

## 5. Time-to-publish vs window

Estimate honestly: research + build the demo + record + edit.

→ `hours_needed`: number
→ `hours_window_left`: number — hours until you expect 3+ channels to have covered it

If you need 3 days and the window is 48h, the score must be low no matter how strong
checks 1-4 are. `hours_needed > hours_window_left` caps the score at 45.

Estimating the window: for a major-player launch with obvious demo value, assume
24-48h. For a mid-tier tool, 3-7 days. If a big channel has already posted, the
window is measured in hours, not days.

---

## Evidence JSON

```json
{
  "mode": "A",
  "topic": "<one plain sentence — what the video actually is>",
  "launch_size": "major",
  "viewer_access": "public_free",
  "demoable": "yes",
  "channels_published_7d": 1,
  "hours_needed": 6,
  "hours_window_left": 36
}
```

Weighting is roughly **launch size × viewer accessibility × time remaining**
(access .28, launch size .22, supply .20, timing .18, demoable .12).
