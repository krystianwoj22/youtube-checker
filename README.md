# YouTube Checker

An on-demand video-idea validator. You paste an idea — a fresh news item, a screenshot,
a link, or a row from the Idea Backlog — and it returns a verdict on whether the video
is worth recording, a 0-100 score, hard evidence, the strongest argument against it,
and a packaging fix.

It runs when you are about to commit a day of your life to filming something.

It is **not** a cron. It is **not** an idea generator. It does **not** re-score the backlog.

---

## Setup

```bash
cp config/config.example.json config/config.json   # channel + competitors
cp .env.example .env                               # then put the API key in .env
python scripts/doctor.py                           # verify it can run
```

The API key lives in `.env` and nowhere else — `.env` is gitignored, `config.json`
is not a place for secrets. An exported `YOUTUBE_API_KEY` overrides the file if you
prefer shell profiles.

`doctor.py` tells you exactly what is missing. Nothing to install — standard library only.

## Use

Drop a screenshot, paste a link, or type an idea:

```
/check https://www.anthropic.com/news/some-launch
/check Notion backlog: "Build an MCP server in n8n"
/check                      ← then drop a screenshot
```

The `check` skill handles the rest. Behind it:

```bash
python scripts/median.py                          # the denominator of the whole scale
python scripts/history.py --q "topic"             # YOUR channel's history on the topic
python scripts/supply.py mode-a --q "topic"       # who already published
python scripts/supply.py mode-b --q "topic"       # saturation + momentum + real demand
                                                  #   + own history, in one run
python scripts/score.py --file evidence.json      # verdict, gates, predicted views
python scripts/predlog.py add --from-result r.json
python scripts/predlog.py shadow --id 3 --q "..." # verify a killed idea without filming
python scripts/predlog.py calibrate               # was the scale right?
```

---

## How it works

### Two modes, two rubrics

| Input | Mode | Question |
|---|---|---|
| News, launch, changelog, announcement screenshot | **A** | Is there a first-mover window, and can you get through it in time? |
| Backlog row, general idea, YouTube search screenshot | **B** | It looked good on paper — what would make it fail in practice? |

The modes cannot share a rubric. A news item from 6 hours ago has zero YouTube
evidence — no competitor videos, no search volume, no channel history. Scoring it with
a demand-and-proof rubric guarantees it loses to a safe proven topic, which is exactly
the bug this tool exists to avoid. Mode A measures *different things*, not the same
things with missing data.

### The score is a prediction, not a rating

> The score expresses the **predicted multiple of your own channel median**.

| Score | Meaning | Verdict |
|---|---|---|
| 85-100 | Likely 3×+ median | 🔴 **FILM NOW** |
| 70-84 | Likely 1.5-3× median | 🟢 **FILM** |
| 55-69 | Around median | 🟡 **SAFE FILLER** |
| 40-54 | Below median | ⚪ **ONLY IF** |
| 0-39 | Well below median | ⛔ **DON'T FILM** |

Abstract points cannot be wrong, so they teach you nothing. A multiple can be checked
at +30d — which is the entire point of the prediction log. The median is computed at
runtime from your last ~30 uploads; it is never hardcoded. The predicted band is a
50% interval sized to **your channel's own upload-to-upload volatility** (p25/p75) —
a consistent channel gets a tight band, a spiky one gets an honest wide one.

`python scripts/score.py --table` prints the full curve.

### The score is computed in code, not by the model

A model asked to produce both a number and a justification will move the number to suit
the justification. So evidence goes into `score.py`, the number comes out, and the model
reports it without negotiating.

### Hard gates

A gate caps the score regardless of everything else. This is what makes ⛔ DON'T FILM
reachable:

| Gate | Cap | Mode |
|---|---|---|
| 3+ channels published in the last 7 days | 35 | A |
| Waitlist / enterprise-only (viewer cannot touch it) | 39 / 32 | A |
| Cannot ship before the window closes | 45 | A |
| Nothing ever beat its own channel median — including your own uploads | 35 | B |
| A 100K+ channel covered it in the last 30 days **and beat its own median** | 38 | B |
| Your own video on the topic is under 60 days old (cannibalisation) | 45 | B |

The dead-topic gate is the one the daily system is structurally bad at: **if nothing has
ever over-performed on a topic, "no competition" means no demand, not an opening.** Most
"nobody is covering this!" ideas die there. Two gates are conditional by design: your
own channel over-performing on the topic overrides the dead-topic gate (your audience
already proved demand), and a big channel that covered the topic but **flopped against
its own median** does not close it — that is contested ground and free packaging intel.

Relatedly, the saturation curve is not monotonic — **zero competitors scores worse than
two.** Two proven videos means demand exists and there is room; zero means unproven.

### Your own channel is the heaviest input

The first build scored ideas entirely on other people's audiences. Mode B now starts
with `history.py`: how did **your** videos on this topic do against **your** median?
That signal carries weight 0.22 — the heaviest in the mode — because three of your
videos doing 0.6× your median is not overridden by a competitor doing 2.4× on theirs.
Topic momentum (are the winners clustered in the last 30 days, or is the topic
burning out?) and staleness caps on old overperformance evidence keep the demand
numbers current rather than quarterly.

### Independence from the daily system

When validating a backlog row, the Checker may read only `Title`, `Summary`,
`Target Keyword` — never `Viral Score`, `Proof Stats`, `Evidence`, `Score Trend` or
`Urgency` — until its own verdict is written.

If it sees a score of 82 first, everything it writes afterwards justifies 82. Two
systems that anchor on each other are one system with extra steps.

After the verdict exists it appends one comparison line
(`daily system: 82 · checker: 61 · disagreement is on saturation`).
**Disagreement is a feature — surfaced, never reconciled silently.**

### Anti-rubber-stamp

- STRONGEST ARGUMENT AGAINST is mandatory on every run, at every score, including a 95.
- BETTER ALTERNATIVE **loses by default** — proposed only when concrete numbers beat the
  original, otherwise the section reads *"Your idea beats anything I found — record it."*
  (An agent asked to suggest something better always suggests something.)
- **Sanity test: if in the first 10 uses it never says "don't film this", the tool is
  broken — not lucky.**

### Prediction log

Every run appends one line to `data/predictions.csv` before filming. Fill in actuals at
+7d and +30d:

```bash
python scripts/predlog.py fill --id 3 --video-id dQw4w9WgXcQ
python scripts/predlog.py calibrate
```

`calibrate` reports the **log error** (how far actuals land from the predicted centre,
as a multiplicative factor) split by mode — a metric that converges around ~20 entries
and cannot be gamed by widening the band; band hit-rate is reported as secondary only.

Killed ideas get verified too — **without filming them**:

```bash
python scripts/predlog.py shadow --id 3 --q "topic"
```

If someone else shipped the topic after the kill and beat their own channel's median,
the kill was probably wrong — and that is recordable with zero filming. This is the
only mechanism that ever surfaces false negatives, which is exactly where a validator
that mostly says "no" hides its mistakes. `calibrate` nags about kills still waiting
for their shadow check. No dashboard.

---

## Layout

```
.claude/skills/check/     the operating procedure (SKILL.md + references/)
.claude/commands/check.md the /check slash command
scripts/median.py         channel + competitor medians  (the scale's denominator)
scripts/history.py        YOUR channel's history on a topic (the heaviest Mode B input)
scripts/supply.py         live saturation + momentum + the real-demand test
scripts/score.py          the 0-100 scale, the gates, the verdict
scripts/predlog.py        prediction log + calibration + shadow checks on killed ideas
scripts/doctor.py         setup check
config/config.json        channel, competitors, thresholds  (gitignored)
data/predictions.csv      the log
tests/                    53 tests, mostly locking the gates in place
```

```bash
python -m unittest discover tests -v
```

## Out of scope

No cron, no idea generation, no backlog re-scoring, no script or thumbnail generation
(packaging *concepts* only), no dashboard.
