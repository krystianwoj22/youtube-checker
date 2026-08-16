---
description: Validate a YouTube video idea before filming — verdict, score, evidence, packaging fix
argument-hint: "[idea, link, or backlog title — or just drop a screenshot]"
---

Run the YouTube Checker on this input:

$ARGUMENTS

Use the `check` skill. Follow it exactly — in particular:

1. Classify the mode (A = fresh news/launch, B = existing idea/backlog row) before anything else.
2. Mode B: obey the independence rule. Only `Title`, `Summary`, `Target Keyword` until your verdict is written.
3. Gather and write **all** evidence before any verdict exists.
4. The score comes from `scripts/score.py`. Do not choose it yourself, do not adjust it.
5. STRONGEST ARGUMENT AGAINST is mandatory at every score.
6. BETTER ALTERNATIVE loses by default — omit it unless concrete numbers beat the original.
7. Log the prediction with `scripts/predlog.py` before you finish.

If no input was given above, ask what to check — do not guess.
