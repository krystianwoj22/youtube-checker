#!/usr/bin/env python3
"""Live YouTube supply / saturation / demand evidence.

This is where the numbers in the EVIDENCE block come from. It produces exactly
the fields score.py needs, so the pipeline is:

    supply.py mode-b --q "topic"  ->  evidence fields  ->  score.py

Two commands matter:

  mode-a  — how many channels already published in the last N days.
            3+ and the window is closed (brief §3.4).

  mode-b  — saturation now, whether a 100K+ channel covered it recently AND
            whether that video actually worked for them, topic momentum
            (accelerating vs fading), the real-demand test (has ANY video on
            this topic beaten its OWN channel's median), and the own-channel
            history lookup (how KRYSTIAN'S videos on this topic performed).

If the API quota is gone or a topic is hard to query, a screenshot of YouTube
search results is a valid substitute — see `--from-screenshot` for the shape
the numbers should be handed back in.
"""

from __future__ import annotations

import argparse
import json
import sys

import history as history_mod
import median as median_mod
import ytapi
from ytconfig import ConfigError, load


def _fmt_video(v: dict, extra: dict | None = None) -> dict:
    out = {
        "title": v["title"],
        "channel": v["channel_title"],
        "channel_id": v["channel_id"],
        "views": v["views"],
        "age_days": v["age_days"],
        # Views alone cannot tell a 3-day rocket from an 85-day corpse.
        "views_per_day": int(round(v["views"] / max(v["age_days"], 1.0))),
        "url": v["url"],
    }
    if v.get("likes"):
        # Engagement is free in the same API response. Like/view separates a
        # video the algorithm pushed from one the audience actually rated.
        out["like_view_pct"] = round(100.0 * v["likes"] / max(v["views"], 1), 2)
    if extra:
        out.update(extra)
    return out


def mode_a_supply(query: str, days: int, limit: int = 50) -> dict:
    """Who has already published on this news item."""
    videos = ytapi.search_videos(query, days=days, limit=limit, order="date")
    fresh = [v for v in videos if v["age_days"] <= days]
    channels = {}
    for v in fresh:
        prev = channels.get(v["channel_id"])
        if prev is None or v["views"] > prev["views"]:
            channels[v["channel_id"]] = v

    ranked = sorted(fresh, key=lambda v: v["views"], reverse=True)
    truncated = len(videos) >= limit
    out = {
        "query": query,
        "window_days": days,
        "videos_found": len(fresh),
        "channels_published_7d": len(channels),
        "channels_published_7d_is_floor": truncated,
        "top_videos": [_fmt_video(v) for v in ranked[:10]],
        "_field_note": "channels_published_7d feeds score.py Mode A. >= 3 closes the window.",
    }
    if truncated:
        out["_truncation_note"] = (
            f"Search hit the {limit}-result limit, so the channel count is a FLOOR. "
            "Report it as a '+' figure. The window is closed regardless."
        )
    return out


def _momentum(over_threshold: list[dict], window: int) -> tuple[str, str]:
    """Are winning videos on this topic getting MORE frequent or less?

    Compares the per-30d rate of >=threshold videos in the last 30 days against
    the 60 days before. Raw views/day cannot be compared across ages (views are
    front-loaded), but 'how often does this topic currently produce a winner'
    can.
    """
    recent = sum(1 for v in over_threshold if v["age_days"] <= 30)
    older = sum(1 for v in over_threshold if 30 < v["age_days"] <= window)
    older_rate = older / max((min(window, 90) - 30) / 30.0, 1.0)  # per-30d
    detail = f"{recent} winner(s) in the last 30d vs {older_rate:.1f}/30d over the prior 60d"
    if recent + older < 3:
        return "unknown", detail + " — too few winners to call a trend"
    if recent >= 1.5 * max(older_rate, 0.67):
        return "accelerating", detail
    if recent <= 0.5 * older_rate:
        return "fading", detail
    return "steady", detail


def mode_b_supply(query: str, cfg: dict, limit: int = 50, max_median_lookups: int = 12) -> dict:
    """Saturation + momentum + the real-demand test + own-channel history."""
    sat = cfg["saturation"]
    window = sat["mode_b_window_days"]
    relevant = sat["mode_b_relevant_views"]
    big_subs = sat["big_channel_subscribers"]
    big_window = sat["big_channel_window_days"]

    videos = ytapi.search_videos(query, days=window, limit=limit, order="viewCount")
    videos = [v for v in videos if v["age_days"] <= window]

    # --- relevance: does the result set actually match the topic? ----------- #
    # YouTube search is semantic; a broad query returns hundreds of loosely
    # related videos and buries the topic under fake saturation.
    tokens = history_mod.query_tokens(query)
    matched = [v for v in videos if history_mod.title_matches(v["title"], tokens, min_hits=1)]
    title_match_ratio = round(len(matched) / len(videos), 2) if videos else 0.0

    over_threshold = [v for v in videos if v["views"] >= relevant]
    over_threshold_matched = [v for v in matched if v["views"] >= relevant]

    momentum, momentum_detail = _momentum(over_threshold_matched or over_threshold, window)

    # --- big-channel check ------------------------------------------------- #
    channel_ids = list(dict.fromkeys(v["channel_id"] for v in videos))
    channels = ytapi.channel_info(channel_ids) if channel_ids else {}
    big_recent = [
        v
        for v in videos
        if v["age_days"] <= big_window
        and channels.get(v["channel_id"], {}).get("subscribers", 0) >= big_subs
    ]
    big_recent.sort(key=lambda v: channels[v["channel_id"]]["subscribers"], reverse=True)

    # --- the real-demand test (brief §4.2) --------------------------------- #
    # For the strongest candidates, compare the video against its OWN channel's
    # median. Beating your own channel's median is what proves topic demand;
    # raw view count only proves the channel is big. Big-channel videos are
    # forced into the candidate set: the gate needs to know whether their video
    # WORKED for them, not merely that it exists.
    candidates = sorted(videos, key=lambda v: v["views"], reverse=True)[:max_median_lookups]
    for v in big_recent:
        if v not in candidates:
            candidates.append(v)
    overperformers = []
    ratio_by_video: dict[str, float] = {}
    failed_lookups = []
    for v in candidates:
        try:
            cm = median_mod.competitor_median(v["channel_id"])
        except Exception as exc:
            failed_lookups.append({"channel": v["channel_title"], "error": str(exc)[:120]})
            continue
        cm_views = cm["median_views"]
        if cm_views <= 0:
            continue
        ratio = v["views"] / cm_views
        ratio_by_video[v["id"]] = ratio
        overperformers.append(
            _fmt_video(
                v,
                {
                    "channel_median": cm_views,
                    "channel_subscribers": cm.get("subscribers", 0),
                    "overperformance_ratio": round(ratio, 2),
                },
            )
        )

    overperformers.sort(key=lambda v: v["overperformance_ratio"], reverse=True)
    best_ratio = overperformers[0]["overperformance_ratio"] if overperformers else 0.0
    best_age = overperformers[0]["age_days"] if overperformers else None

    # Did any big channel's video actually beat ITS OWN median? Only that
    # closes the door (score.py gate). A big-channel flop is contested ground.
    # A big video whose median lookup failed counts as won — conservative.
    big_over = any(
        ratio_by_video.get(v["id"]) is None or ratio_by_video[v["id"]] >= 1.0 for v in big_recent
    )

    # The search returns at most `limit` results, so a full page means the real
    # count is "at least this many", not "exactly this many". Saying 50 when the
    # truth is 400 is the kind of vague-number-wearing-precision the brief bans.
    truncated = len(videos) >= limit

    # --- own-channel history (the heaviest Mode B input) -------------------- #
    try:
        own = history_mod.own_topic_history(query)
        own_fields = {
            "own_topic_videos": own["own_topic_videos"],
            "own_best_topic_ratio": own["own_best_topic_ratio"],
            "own_recent_topic_video_days": own["own_recent_topic_video_days"],
            "own_matches": own["matches"][:5],
        }
    except Exception as exc:
        own_fields = {
            "own_topic_videos": None,
            "own_best_topic_ratio": None,
            "own_recent_topic_video_days": None,
            "_own_history_error": str(exc)[:160],
        }

    result = {
        "query": query,
        "window_days": window,
        "videos_found": len(videos),
        "results_truncated": truncated,
        "title_match_ratio": title_match_ratio,
        # --- fields that feed score.py ---
        "videos_90d_over_20k": len(over_threshold_matched),
        "videos_90d_over_20k_unfiltered": len(over_threshold),
        "videos_90d_over_20k_is_floor": truncated,
        "big_channel_covered_30d": bool(big_recent),
        "big_channel_overperformed_30d": bool(big_recent) and big_over,
        "topic_momentum": momentum,
        "best_overperformance_ratio": best_ratio,
        "best_overperformance_age_days": best_age,
        "overperformance_sample_size": len(overperformers),
        **own_fields,
        # --- supporting evidence ---
        "momentum_detail": momentum_detail,
        "relevant_views_threshold": relevant,
        "big_channels_recent": [
            _fmt_video(
                v,
                {
                    "subscribers": channels[v["channel_id"]]["subscribers"],
                    "beat_own_median": (
                        None if v["id"] not in ratio_by_video else ratio_by_video[v["id"]] >= 1.0
                    ),
                },
            )
            for v in big_recent[:5]
        ],
        "overperformers": overperformers[:8],
        "top_videos": [_fmt_video(v) for v in sorted(videos, key=lambda x: x["views"], reverse=True)[:10]],
        "failed_median_lookups": failed_lookups,
    }

    if title_match_ratio < 0.6 and videos:
        result["_relevance_note"] = (
            f"Only {title_match_ratio:.0%} of results match the query terms in the title. "
            "The saturation count uses the MATCHED subset (videos_90d_over_20k); the raw count is in "
            "videos_90d_over_20k_unfiltered. If even the matched set looks off-topic, tighten the "
            "query (product name + feature name) and re-run."
        )
    if big_recent and not big_over:
        result["_big_channel_note"] = (
            "A 100K+ channel covered this but UNDERPERFORMED its own median. The gate does not "
            "fire — contested ground, not a closed door. Study why their packaging missed."
        )
    if truncated:
        result["_truncation_note"] = (
            f"Search returned a full page ({limit}); videos_90d_over_20k={len(over_threshold_matched)} is a "
            f"FLOOR, not an exact count. Report it as '{len(over_threshold_matched)}+' in the EVIDENCE block. "
            "The topic is heavily covered — the saturation sub-score is already at its floor either way."
        )

    if not overperformers:
        result["_warning"] = (
            "No channel medians could be computed, so the real-demand test did not run. "
            "best_overperformance_ratio=0.0 will trip the DEAD TOPIC gate — do not accept that "
            "verdict without either fixing the lookups or supplying the number from a screenshot."
        )
    elif best_ratio < 1.0:
        result["_finding"] = (
            f"Nothing on this topic has beaten its own channel's median (best {best_ratio}x across "
            f"{len(overperformers)} videos). This is the dead-topic signal from brief §4.2."
        )
    return result


SCREENSHOT_TEMPLATE = {
    "_how_to_use": (
        "When the API is unavailable or the topic is hard to query, read these fields off a "
        "screenshot of YouTube search results and pass them straight to score.py. One screenshot "
        "carries titles, thumbnails, view counts, ages and channels at once — the brief treats "
        "that as real market data, not a downgrade."
    ),
    "mode_a": {
        "channels_published_7d": "count distinct channels with an upload on this topic in the last 7 days",
    },
    "mode_b": {
        "videos_90d_over_20k": "count videos under 90 days old with >= 20K views whose title is actually about the topic",
        "big_channel_covered_30d": "true if any channel over 100K subs posted on it in the last 30 days",
        "big_channel_overperformed_30d": (
            "true only if that big channel's video ALSO beat what that channel normally does "
            "(open the channel, compare against its recent uploads). A big-channel flop does not close the topic."
        ),
        "topic_momentum": (
            "accelerating | steady | fading | unknown — are the winning videos clustered in the last "
            "30 days (accelerating) or all older than a month (fading)?"
        ),
        "best_overperformance_ratio": (
            "for the best-performing video visible, divide its views by that channel's typical "
            "recent views (open the channel, eyeball the median of the last ~10 uploads). "
            "This one number decides the dead-topic gate — do not guess it optimistically."
        ),
        "own_topic_videos": (
            "search your OWN channel for the topic: how many prior videos? Plus own_best_topic_ratio "
            "(their best views / your median) and own_recent_topic_video_days. If you cannot check, pass null."
        ),
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("mode-a", help="Fresh-news supply: who already published")
    a.add_argument("--q", required=True, help="Search query")
    a.add_argument("--days", type=int, help="Window in days (default from config)")
    a.add_argument("--limit", type=int, default=50)

    b = sub.add_parser("mode-b", help="Saturation + momentum + real demand + own history")
    b.add_argument("--q", required=True, help="Search query")
    b.add_argument("--limit", type=int, default=50)
    b.add_argument("--medians", type=int, default=12, help="How many competitor medians to compute")

    sub.add_parser("from-screenshot", help="Print the fields to read off a search-results screenshot")

    args = parser.parse_args()
    cfg = load()

    try:
        if args.cmd == "mode-a":
            days = args.days or cfg["saturation"]["mode_a_window_days"]
            print(json.dumps(mode_a_supply(args.q, days, args.limit), indent=2))
        elif args.cmd == "mode-b":
            print(json.dumps(mode_b_supply(args.q, cfg, args.limit, args.medians), indent=2))
        else:
            print(json.dumps(SCREENSHOT_TEMPLATE, indent=2))
    except (ytapi.YouTubeError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "\nFallback: run `python scripts/supply.py from-screenshot` and read the numbers "
            "off a screenshot of YouTube search results instead.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
