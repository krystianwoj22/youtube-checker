# The independence rule (non-negotiable)

There is a separate **YouTube Viral Content System** — a daily cron agent that
discovers ideas and maintains the ranked Notion backlog `Idea Backlog - Youtube`.

The Checker is a deliberately separate system with a deliberately different lens.

| | Viral Content System (daily) | YouTube Checker (this tool) |
|---|---|---|
| Job | Discovery — "where is the opening?" | Judgment — "should *I* film *this*?" |
| Trigger | Cron, daily | On demand, before filming |
| Lens | Opportunity | Execution + risk |
| Bias | Optimistic (it proposes) | Adversarial (it tries to kill) |
| Output | Ranked backlog | Verdict + falsifiable prediction |

---

## The rule

When validating a backlog row (Mode B), you **must not read** that row's:

- `Viral Score`
- `Proof Stats`
- `Evidence`
- `Score Trend`
- `Urgency`

...before you have produced your own verdict.

You may read **only**: `Title`, `Summary`, `Target Keyword`.

## Why

If you see a score of 82 first, everything you write afterwards is a justification of
82. Two systems that anchor on each other are one system with extra steps — and the
whole point of building this separately is to get a second, independent opinion.

This applies to anchoring in general, not just to the literal field names. If the row
body contains the daily system's reasoning, do not read it. If a Notion query returns
the forbidden fields anyway, **do not look at them** and note in the output that they
were returned but not used.

## How to fetch safely

Prefer a query that names only the allowed properties. If the MCP tool returns the
whole page regardless, read only the three allowed fields and stop.

When in doubt, ask Krystian for the title and summary directly rather than opening
the row — the pasted text carries no score to anchor on.

## After the verdict is written

Only once EVIDENCE, SCORE, VERDICT, STRONGEST ARGUMENT AGAINST and KILL CONDITION are
all on the page, fetch the daily system's score and append **one line**:

```
daily system: 82 · checker: 61 · disagreement is on saturation
```

Name the axis of disagreement. That is the whole value of the comparison.

**Disagreement is a feature — surface it, never reconcile it silently.** Do not adjust
your score toward the daily system's, and do not explain away the gap. If the two
systems disagree badly and often, that is information about one of them.

## Writing back

Default is **read-only**: verdicts go to chat, not onto the backlog row
(`config/config.json` → `notion.write_back: false`).

The Checker never re-scores the backlog. That is the daily system's job, and
duplicating it destroys the independence this tool exists for.

If `write_back` is enabled, write only to Checker-owned properties
(`Checker Score`, `Checker Verdict`, `Checker Date`) and never touch the daily
system's fields.
