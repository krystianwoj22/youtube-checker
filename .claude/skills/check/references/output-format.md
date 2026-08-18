# Output format (fixed, every run)

Order matters and is part of the design: **evidence is gathered and written before any
verdict exists.** Do not reorder these blocks, do not omit one because it seems obvious.

```
MODE: A (fresh news) | B (existing idea)
TOPIC: <one plain sentence — what the video actually is>

── EVIDENCE ─────────────────────────────
<one line per check from Mode A or Mode B, each with a NUMBER or a concrete finding.
 "unknown" is an acceptable value; a vague adjective is not.>

── VERDICT ──────────────────────────────
SCORE: <0–100>  →  predicted <X–Y>× your median (~<n>–<m> views)
VERDICT: <🔴 FILM NOW | 🟢 FILM | 🟡 SAFE FILLER | ⚪ ONLY IF | ⛔ DON'T FILM>

STRONGEST ARGUMENT AGAINST: <the best case for NOT filming this — required even
for a 95. If you cannot produce one, you have not researched enough.>

KILL CONDITION: <"if you find X before filming, drop it">

── PACKAGING FIX ────────────────────────
<always present. 2–3 title variants + one thumbnail concept.>

── BETTER ALTERNATIVE ───────────────────
<CONDITIONAL — see the rule below.>

── PREDICTION RECORD ────────────────────
<date> | <topic> | mode <A/B> | predicted <score> = <X–Y>× median | actual 7d: __ | actual 30d: __
```

Mode B adds one line after VERDICT, and only after everything above it is written:

```
daily system: 82 · checker: 61 · disagreement is on saturation
```

---

## EVIDENCE

One line per check, in the order the mode reference lists them. Every line carries a
number or a concrete finding.

Good:
```
Own history:     2 prior videos — best did 1.6× YOUR median (MCP intro, 14K views); last one 190d ago
Supply (7d):     2 channels published — Matt Wolfe (41K views, 3d), AI Foundations (9K, 1d)
Real demand:     best video 2.4× its own channel median, 18d old (n=11 checked)
Momentum:        accelerating — 3 winners in the last 30d vs 0.5/30d before
Big channel:     covered 12d ago by NetworkChuck — but 0.7× his median (flop; gate does not fire)
Executability:   ~6h — n8n Cloud Starter (have it) + Anthropic API key (have it)
Packaging:       4/5 checks pass — no curiosity gap yet in the working title
```

Bad — these are opinions wearing a number's clothes:
```
Supply:          fairly saturated
Real demand:     looks promising
Executability:   should be doable
```

Say `unknown` when it is unknown, and say why. `unknown` is honest; "moderate" is not.

## SCORE and VERDICT

Both come from `scripts/score.py`. Do not recompute, round, or adjust them. If a hard
gate fired, quote the gate's reason verbatim in the EVIDENCE block or immediately
under VERDICT — the reader needs to know the score was capped, not earned.

The score means **predicted multiple of Krystian's own channel median**, not abstract
quality. Always show the view range alongside it, because that is the falsifiable part.

## STRONGEST ARGUMENT AGAINST

**Mandatory on every run, at every score, including 95.**

It must be the *strongest* case, not a token caveat. "It might not do as well as hoped"
is not an argument. Name the specific mechanism by which this video underperforms:
who else is better positioned, which part of the audience will bounce, what the viewer
cannot do after watching.

If you cannot produce one, you have not researched enough — go back and gather more
evidence before writing the output.

## KILL CONDITION

A specific, checkable thing that would flip the decision, phrased as an instruction:

> "If a channel over 200K posts on this before you record, drop it."
> "If the free tier turns out to be capped at 5 runs/day, drop it — the demo dies."

Not: "if it becomes saturated" (uncheckable, no threshold).

## PACKAGING FIX

Always present, at every score. 2-3 title variants plus one thumbnail concept.

Most ideas fail on packaging, not on topic — in this niche the same topic does 3K or
300K on packaging alone. **This is the highest-value section of the output.**

Write titles that would survive next to the specific competitor titles found during
the saturation check, and say what each variant is doing differently (curiosity gap,
specificity, contrast, outcome).

## BETTER ALTERNATIVE — the trap

An agent asked to "suggest something better" **always** suggests something, including
when the original idea was good. So:

- A better alternative may only be proposed when you can point to **concrete numbers**
  on which it beats the original.
- Otherwise this section reads, exactly:

  > **Your idea beats anything I found — record it.**

- **The alternative loses by default.** Absence of a suggestion is the normal outcome,
  not a failure to be helpful.

## PREDICTION RECORD

Log it with `scripts/predlog.py` on every run, including DON'T FILM verdicts. The line
in the output and the CSV row should match.
