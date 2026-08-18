---
name: check
description: Validate a YouTube video idea before filming it — returns a verdict, a 0-100 score expressed as a predicted multiple of Krystian's channel median, hard evidence, the strongest argument against filming, and a packaging fix. Use whenever Krystian pastes a news item, screenshot, link, or backlog idea and is deciding whether to record it. Triggers on "should I film this", "check this idea", "is this worth a video", "/check", a dropped screenshot of an announcement or YouTube search results, or a link to a product launch or changelog.
---

# YouTube Checker

An adversarial, on-demand validator. It runs when Krystian is about to commit a day
of his life to filming something. Its job is to **try to kill the idea** and report
what survived.

**Language: the entire output is written in Polish** — evidence lines, verdict prose,
packaging fix, everything. Only identifiers stay in English: evidence JSON field
names, verdict labels (FILM NOW / DON'T FILM...), and the block headings of the
output format. This applies regardless of the input's language (screenshots and
news items will often be in English).

It is not a cron, not an idea generator, and it does not re-score the backlog.

## The one thing that makes this tool work

**Gather and write ALL evidence before any verdict exists.**

If the verdict is formed first, everything after it is rationalisation. That is the
default failure mode of an LLM asked to judge, and the ordering below is the defence
against it. Do not skip ahead. Do not "get a feel for it" and then collect numbers
that agree.

The score is not yours to choose. Evidence goes into `scripts/score.py`, the number
comes out, and you report it. If you disagree with the number, say so in prose —
do not edit the number.

---

## Step 0 — classify the mode

| Input | Mode |
|---|---|
| Screenshot of an announcement / news article / launch page / tweet | **A** |
| Link to a release, changelog, blog post, product launch | **A** |
| Pasted description of something that just came out | **A** |
| Notion backlog row URL, or a title matching a backlog row | **B** |
| Screenshot of YouTube search results | **B** (supply data is the input) |
| A general idea with no news hook | **B** |

If you cannot tell, ask **once**, then proceed. Never run both modes.

The modes do not share a rubric, and that is deliberate: a news item from 6 hours ago
has zero YouTube evidence. Scoring it with a demand-and-proof rubric would always lose
to a safe proven topic — which is exactly the bug this tool exists to avoid.

## Step 0.5 — Mode B only: THE INDEPENDENCE RULE

Read `references/independence.md` before touching Notion. Summary:

> When validating a backlog row you **must not read** `Viral Score`, `Proof Stats`,
> `Evidence`, `Score Trend` or `Urgency` before your own verdict is written.
> You may read only `Title`, `Summary`, `Target Keyword`.

If you see a score of 82 first, everything you write afterwards justifies 82. Two
systems that anchor on each other are one system with extra steps.

Fetch the daily system's score **after** the verdict is written, and append one
comparison line. Disagreement is a feature — surface it, never reconcile it silently.

---

## Step 1 — the channel median (always first)

```bash
python scripts/median.py
```

This is the denominator of the entire scale. Never hardcode it, never estimate it.
It is cached for 7 days; add `--refresh` to force recomputation. Its p25/p75 spread
also sizes the predicted band — a consistent channel gets a tighter interval.

If it fails (no API key, no channel configured), say so plainly and continue with
multiples only — do not invent a median.

## Step 2 — gather evidence

Run the checks **in order**. Every check must produce a **number or a concrete
finding**. `"unknown"` is an acceptable value; a vague adjective is not.

- **Mode A** → follow `references/mode-a.md`
- **Mode B** → follow `references/mode-b.md` — starts with **your own channel's
  history on the topic**, the heaviest input in the mode and the only one about
  Krystian's audience rather than someone else's.

Live supply data:

```bash
python scripts/supply.py mode-a --q "<topic>"     # who already published
python scripts/supply.py mode-b --q "<topic>"     # saturation + momentum + real demand
                                                  #   + own-channel history, in one run
python scripts/history.py --q "<topic>"           # own-channel history alone
```

If the API quota is gone or the topic queries badly, **a screenshot of YouTube search
results is a first-class substitute, not a downgrade** — one image carries titles,
thumbnails, view counts, ages and channels at once. Run
`python scripts/supply.py from-screenshot` for the exact fields to read off it.

Web search is fair game for Mode A (launch size, pricing/access, waitlist status).

## Step 3 — score it

Write the evidence to a JSON file, then:

```bash
python scripts/score.py --file /tmp/evidence.json --json
```

Field schemas are in `references/scoring.md`. The script applies the hard gates
itself — window closed, dead topic, 100K+ channel covered it *and won on it*,
cannibalising your own recent video, viewer cannot access the product, cannot ship
in time. **A tripped gate caps the score no matter how good everything else is.**
Report the gate verbatim when it fires. Two gates are conditional by design: your
own channel over-performing on the topic overrides the dead-topic gate, and a big
channel's *flop* on the topic does not close it.

## Step 4 — write the output

Use the exact format in `references/output-format.md`. Non-negotiable parts:

- **STRONGEST ARGUMENT AGAINST is mandatory on every run, at every score** — including
  a 95. If you cannot produce one, you have not researched enough. Go back to Step 2.
- **BETTER ALTERNATIVE loses by default.** You may only propose one when you can point
  to concrete numbers on which it beats the original. Otherwise the section reads
  exactly: *"Your idea beats anything I found — record it."* An agent asked to suggest
  something better always suggests something; this rule is the counterweight.
- **PACKAGING FIX is always present.** In this niche the same topic does 3K or 300K on
  packaging alone. This is the highest-value section of the output.

## Step 5 — log the prediction

```bash
python scripts/predlog.py add --from-result /tmp/result.json
```

A prediction written down before filming is the only mechanism that ever tells you
whether the 0-100 scale means anything. Do this on every run, including DON'T FILM
verdicts. Killed ideas are verified WITHOUT filming: ~30-60 days later,
`python scripts/predlog.py shadow --id <n> --q "<topic>"` checks whether anyone else
shipped the topic and beat their own median after the kill — the only way false
negatives ever become visible. `predlog.py calibrate` lists the kills still waiting
for their shadow check.

---

## Anti-rubber-stamp rules

- You **must** be able to output ⛔ DON'T FILM, and must do so whenever a hard gate trips.
- Sanity test: **if in the first 10 uses this tool never says "don't film this", the
  tool is broken — not lucky.** If you notice you are on a streak of green verdicts,
  that is a signal to check whether you are gathering evidence honestly, not a signal
  that the ideas are good.
- Never soften a gate because the idea is exciting. The gates encode decisions already
  made; re-litigating them at judgement time is how the tool becomes a rubber stamp.
- "I couldn't find competitors" is not evidence of an opening. Run the real-demand
  test before treating an empty search as good news.

## Out of scope

No cron. No idea generation. No re-scoring the backlog. No scripts, no thumbnail
generation (packaging *concepts* only). No dashboard.
