#!/usr/bin/env python3
"""Own-channel topic history — the strongest predictor the first build ignored.

Every other input in Mode B describes SOMEONE ELSE'S audience. This one asks
the only question that is actually about Krystian's: when THIS channel already
made videos on this topic, what multiple of ITS OWN median did they do?

If three of your MCP videos did 0.6x your median, a competitor doing 2.4x on
their channel does not override that — their audience is not yours. Conversely,
a topic your channel over-performed on carries proof no competitor search can
provide. This feeds the heaviest-weighted sub-score in Mode B (own_history,
0.22) and the cannibalisation gate.

    python scripts/history.py --q "mcp server n8n"
    python scripts/history.py --q "claude api" --terms anthropic,assistant
"""

from __future__ import annotations

import argparse
import json
import re
import sys

import median as median_mod
import ytapi
from ytconfig import ConfigError, load, own_channel_ref

# Tokens like "the/and/how" match everything; tokens under 3 chars ("ai") match
# half the channel. Both make the history lookup meaninglessly broad.
STOPWORDS = {
    "the", "and", "for", "with", "how", "you", "your", "from", "this", "that",
    "what", "why", "not", "are", "can", "its", "use", "using", "into", "make",
    "build", "new", "best", "top", "full", "complete", "guide", "tutorial",
    "video", "youtube", "jak", "czy", "dla", "com", "www",
}


def query_tokens(query: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9]+", (query or "").lower())
        if len(t) >= 3 and t not in STOPWORDS
    }


def title_matches(title: str, tokens: set[str], min_hits: int) -> bool:
    if not tokens:
        return False
    text = (title or "").lower()
    hits = sum(1 for t in tokens if t in text)
    return hits >= min_hits


def own_topic_history(
    query: str,
    extra_terms: list[str] | None = None,
    lookback_uploads: int = 100,
    settled_age_days: int = 30,
) -> dict:
    """Match the query against the channel's own uploads and report each match
    as a multiple of the channel's own median.

    Ratios are only computed for uploads older than `settled_age_days` (views
    not settled yet), but younger matches still count for cannibalisation.
    """
    cfg = load()
    channel_id = ytapi.resolve_channel_id(own_channel_ref(cfg))
    own = median_mod.own_median()
    median_views = own["median_views"]

    tokens = query_tokens(query)
    for term in extra_terms or []:
        tokens |= query_tokens(term)
    if not tokens:
        raise ValueError(f"query {query!r} yields no usable topic tokens")
    # One shared word ("automation") on an automation channel matches half the
    # uploads. Require two token hits when the query is rich enough to allow it.
    min_hits = 2 if len(tokens) >= 3 else 1

    uploads = ytapi.channel_uploads(channel_id, limit=lookback_uploads)
    min_dur = cfg["median"]["min_duration_seconds"]
    matched = [
        v
        for v in uploads
        if title_matches(v["title"], tokens, min_hits)
        and (not v["duration_seconds"] or v["duration_seconds"] >= min_dur)
    ]

    settled = [v for v in matched if v["age_days"] >= settled_age_days]
    rated = sorted(
        (
            {
                "title": v["title"],
                "views": v["views"],
                "age_days": v["age_days"],
                "url": v["url"],
                "ratio_of_own_median": round(v["views"] / median_views, 2) if median_views else 0.0,
            }
            for v in settled
        ),
        key=lambda v: v["ratio_of_own_median"],
        reverse=True,
    )

    most_recent = min((v["age_days"] for v in matched), default=None)

    result = {
        "query": query,
        "tokens_used": sorted(tokens),
        "min_token_hits": min_hits,
        "uploads_scanned": len(uploads),
        "own_median": median_views,
        # --- fields that feed score.py Mode B ---
        "own_topic_videos": len(settled),
        "own_best_topic_ratio": rated[0]["ratio_of_own_median"] if rated else None,
        "own_recent_topic_video_days": most_recent,
        # --- supporting evidence ---
        "matches": rated[:10],
        "unsettled_matches": [
            {"title": v["title"], "views": v["views"], "age_days": v["age_days"]}
            for v in matched
            if v["age_days"] < settled_age_days
        ],
        "_field_note": (
            "own_topic_videos/own_best_topic_ratio feed the heaviest Mode B sub-score; "
            "own_recent_topic_video_days feeds the cannibalisation gate."
        ),
    }
    if not matched:
        result["_note"] = (
            "No prior upload matches this topic. That is neutral (untried), not negative — "
            "score.py treats it as 60/100 on own_history."
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--q", required=True, help="Topic query, same string used for supply.py")
    parser.add_argument("--terms", help="Comma-separated extra keywords to widen the title match")
    parser.add_argument("--lookback", type=int, default=100, help="How many own uploads to scan")
    args = parser.parse_args()

    extra = [t.strip() for t in (args.terms or "").split(",") if t.strip()]
    try:
        print(json.dumps(own_topic_history(args.q, extra, args.lookback), indent=2))
    except (ytapi.YouTubeError, ConfigError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "\nIf the lookup cannot run, pass own_topic_videos: null in the evidence "
            "(score.py treats it as neutral) — do not guess a ratio.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
