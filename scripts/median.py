#!/usr/bin/env python3
"""Channel median view count — the denominator of the entire 0-100 scale.

Two things this deliberately does, per the build brief §7:

  * Uploads younger than `exclude_younger_than_days` are excluded from the median
    (they have not finished accumulating views) but are still returned as
    reference points.
  * Shorts are excluded via a minimum duration. A channel that posts Shorts
    otherwise has a median that describes its Shorts, not its videos.

Never hardcode the median anywhere. Call this.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import ytapi
from ytconfig import CACHE_DIR, ConfigError, load, own_channel_ref


def _cache_file(channel_id: str) -> Path:
    return CACHE_DIR / f"median_{channel_id}.json"


def compute_median(
    channel_ref: str,
    lookback_uploads: int = 30,
    exclude_younger_than_days: int = 30,
    min_duration_seconds: int = 90,
    cache_days: int = 7,
    refresh: bool = False,
) -> dict:
    channel_id = ytapi.resolve_channel_id(channel_ref)
    cache_file = _cache_file(channel_id)

    if not refresh and cache_file.exists():
        age_days = (time.time() - cache_file.stat().st_mtime) / 86400
        if age_days < cache_days:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            cached["from_cache"] = True
            cached["cache_age_days"] = round(age_days, 2)
            return cached

    # Over-fetch: some uploads get dropped as Shorts or as too young.
    uploads = ytapi.channel_uploads(channel_id, limit=min(lookback_uploads * 2, 100))
    info = ytapi.channel_info([channel_id]).get(channel_id, {})

    too_young = [v for v in uploads if v["age_days"] < exclude_younger_than_days]
    shorts = [v for v in uploads if v["duration_seconds"] and v["duration_seconds"] < min_duration_seconds]
    short_ids = {v["id"] for v in shorts}

    eligible = [
        v
        for v in uploads
        if v["age_days"] >= exclude_younger_than_days and v["id"] not in short_ids
    ][:lookback_uploads]

    if not eligible:
        raise ytapi.YouTubeError(
            f"No eligible uploads for {channel_id} after filtering "
            f"(age >= {exclude_younger_than_days}d, duration >= {min_duration_seconds}s). "
            "Loosen median.exclude_younger_than_days or median.min_duration_seconds."
        )

    views = sorted(v["views"] for v in eligible)
    median = statistics.median(views)

    result = {
        "channel_id": channel_id,
        "channel_title": info.get("title", ""),
        "subscribers": info.get("subscribers", 0),
        "median_views": int(median),
        "mean_views": int(statistics.fmean(views)),
        "sample_size": len(eligible),
        "p25_views": int(statistics.quantiles(views, n=4)[0]) if len(views) >= 4 else int(views[0]),
        "p75_views": int(statistics.quantiles(views, n=4)[2]) if len(views) >= 4 else int(views[-1]),
        "min_views": views[0],
        "max_views": views[-1],
        "filters": {
            "lookback_uploads": lookback_uploads,
            "exclude_younger_than_days": exclude_younger_than_days,
            "min_duration_seconds": min_duration_seconds,
            "excluded_too_young": len(too_young),
            "excluded_shorts": len(shorts),
        },
        "reference_recent_uploads": [
            {
                "title": v["title"],
                "views": v["views"],
                "age_days": v["age_days"],
                "note": "too young for the median, shown as a reference point",
            }
            for v in too_young[:5]
        ],
        "sample": [
            {"title": v["title"], "views": v["views"], "age_days": v["age_days"]}
            for v in eligible
        ],
        "computed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "from_cache": False,
    }

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def own_median(refresh: bool = False) -> dict:
    cfg = load()
    m = cfg["median"]
    return compute_median(
        own_channel_ref(cfg),
        lookback_uploads=m["lookback_uploads"],
        exclude_younger_than_days=m["exclude_younger_than_days"],
        min_duration_seconds=m["min_duration_seconds"],
        cache_days=m["cache_days"],
        refresh=refresh,
    )


def competitor_median(channel_id: str, refresh: bool = False) -> dict:
    """Median for someone else's channel — used for 'did this video beat its
    own channel's median', which is Mode B's most important check.

    Competitor medians use a looser filter: we want a fair denominator for
    *their* recent output, not a strict view of a channel we know well.
    """
    cfg = load()
    m = cfg["median"]
    return compute_median(
        channel_id,
        lookback_uploads=m["lookback_uploads"],
        exclude_younger_than_days=0,
        min_duration_seconds=m["min_duration_seconds"],
        cache_days=m["cache_days"],
        refresh=refresh,
    )


def _format_human(result: dict) -> str:
    f = result["filters"]
    lines = [
        f"{result['channel_title']} ({result['channel_id']})",
        f"  subscribers      {result['subscribers']:,}",
        f"  MEDIAN VIEWS     {result['median_views']:,}   <- denominator of the 0-100 scale",
        f"  mean             {result['mean_views']:,}",
        f"  p25 / p75        {result['p25_views']:,} / {result['p75_views']:,}",
        f"  range            {result['min_views']:,} - {result['max_views']:,}",
        f"  sample           {result['sample_size']} uploads",
        f"  excluded         {f['excluded_too_young']} too young (<{f['exclude_younger_than_days']}d), "
        f"{f['excluded_shorts']} shorts (<{f['min_duration_seconds']}s)",
        f"  computed         {result['computed_at']}"
        + (f"  (cached {result.get('cache_age_days', 0)}d ago)" if result.get("from_cache") else ""),
    ]
    if result["reference_recent_uploads"]:
        lines.append("  recent (excluded from median, reference only):")
        for v in result["reference_recent_uploads"]:
            lines.append(f"    {v['views']:>8,}  {v['age_days']:>5}d  {v['title'][:58]}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--channel", help="Channel ID, @handle or URL. Defaults to the configured own channel.")
    parser.add_argument("--competitor", action="store_true", help="Use competitor filters (no age exclusion).")
    parser.add_argument("--refresh", action="store_true", help="Ignore the cache and recompute.")
    parser.add_argument("--json", action="store_true", help="Emit raw JSON.")
    args = parser.parse_args()

    try:
        if args.channel and args.competitor:
            result = competitor_median(args.channel, refresh=args.refresh)
        elif args.channel:
            cfg = load()["median"]
            result = compute_median(
                args.channel,
                lookback_uploads=cfg["lookback_uploads"],
                exclude_younger_than_days=cfg["exclude_younger_than_days"],
                min_duration_seconds=cfg["min_duration_seconds"],
                cache_days=cfg["cache_days"],
                refresh=args.refresh,
            )
        else:
            result = own_median(refresh=args.refresh)
    except (ytapi.YouTubeError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(_format_human(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
