#!/usr/bin/env python3
"""Minimal YouTube Data API v3 client. Standard library only, no install step.

Responses are cached on disk so repeated checks inside one session do not burn
quota. Search costs 100 quota units per call; everything else costs 1.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from ytconfig import CACHE_DIR, ConfigError, api_key

API_BASE = "https://www.googleapis.com/youtube/v3"
DEFAULT_TTL = 6 * 3600  # 6h: saturation moves in days, not minutes


class YouTubeError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# transport
# --------------------------------------------------------------------------- #


def _cache_path(endpoint: str, params: dict) -> "Any":
    payload = json.dumps([endpoint, sorted(params.items())], sort_keys=True)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{endpoint}_{digest}.json"


def _request(endpoint: str, params: dict, ttl: int = DEFAULT_TTL) -> dict:
    params = {k: v for k, v in params.items() if v is not None}
    cache_file = _cache_path(endpoint, params)
    if ttl > 0 and cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < ttl:
            return json.loads(cache_file.read_text(encoding="utf-8"))

    query = dict(params)
    query["key"] = api_key()
    url = f"{API_BASE}/{endpoint}?" + urllib.parse.urlencode(query)

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:600]
        if exc.code == 403 and "quotaExceeded" in detail:
            raise YouTubeError(
                "YouTube API daily quota exceeded. Fall back to screenshot input for "
                "supply/saturation data (the brief treats screenshots as a first-class source)."
            ) from exc
        raise YouTubeError(f"YouTube API {endpoint} failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise YouTubeError(f"Network error calling YouTube API: {exc.reason}") from exc

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(body), encoding="utf-8")
    return body


def _paged(endpoint: str, params: dict, limit: int, ttl: int = DEFAULT_TTL) -> list[dict]:
    items: list[dict] = []
    token = None
    while len(items) < limit:
        page = _request(
            endpoint,
            {**params, "maxResults": min(50, limit - len(items)), "pageToken": token},
            ttl=ttl,
        )
        items.extend(page.get("items", []))
        token = page.get("nextPageToken")
        if not token:
            break
    return items[:limit]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

_ISO_DURATION = re.compile(
    r"P(?:(?P<days>\d+)D)?T?(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"
)


def parse_duration(value: str) -> int:
    """ISO-8601 duration -> seconds. Returns 0 for live/unknown."""
    if not value:
        return 0
    match = _ISO_DURATION.fullmatch(value)
    if not match:
        return 0
    parts = {k: int(v) for k, v in match.groupdict(default="0").items()}
    return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def days_since(value: str) -> float:
    return (datetime.now(timezone.utc) - parse_ts(value)).total_seconds() / 86400


def rfc3339_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _chunks(items: list, size: int) -> Iterable[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #


def resolve_channel_id(ref: str) -> str:
    """Accept a channel ID, @handle, or channel URL and return the UC... ID."""
    ref = (ref or "").strip()
    if not ref:
        raise YouTubeError("Empty channel reference.")

    if ref.startswith("UC") and len(ref) == 24:
        return ref

    if "youtube.com" in ref:
        path = urllib.parse.urlparse(ref).path.strip("/")
        if path.startswith("channel/"):
            return path.split("/")[1]
        segment = path.split("/")[0]
        ref = segment if segment.startswith("@") else "@" + segment

    handle = ref if ref.startswith("@") else "@" + ref
    body = _request("channels", {"part": "id", "forHandle": handle}, ttl=30 * 86400)
    items = body.get("items") or []
    if items:
        return items[0]["id"]

    # Fall back to search — costs 100 quota units but beats failing outright.
    body = _request(
        "search",
        {"part": "snippet", "type": "channel", "q": handle.lstrip("@"), "maxResults": 1},
        ttl=30 * 86400,
    )
    items = body.get("items") or []
    if not items:
        raise YouTubeError(f"Could not resolve channel: {ref}")
    return items[0]["snippet"]["channelId"]


def channel_info(channel_ids: list[str]) -> dict[str, dict]:
    """channel_id -> {title, subscribers, uploads_playlist, video_count}."""
    out: dict[str, dict] = {}
    for chunk in _chunks(list(dict.fromkeys(channel_ids)), 50):
        body = _request(
            "channels",
            {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk)},
            ttl=7 * 86400,
        )
        for item in body.get("items", []):
            stats = item.get("statistics", {})
            out[item["id"]] = {
                "id": item["id"],
                "title": item["snippet"]["title"],
                "subscribers": int(stats.get("subscriberCount", 0) or 0),
                "hidden_subscribers": bool(stats.get("hiddenSubscriberCount", False)),
                "video_count": int(stats.get("videoCount", 0) or 0),
                "uploads_playlist": item["contentDetails"]["relatedPlaylists"]["uploads"],
            }
    return out


def video_details(video_ids: list[str]) -> list[dict]:
    """Normalised video records for a list of video IDs."""
    out: list[dict] = []
    for chunk in _chunks(list(dict.fromkeys(video_ids)), 50):
        body = _request(
            "videos",
            {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk)},
            ttl=DEFAULT_TTL,
        )
        for item in body.get("items", []):
            stats = item.get("statistics", {})
            published = item["snippet"]["publishedAt"]
            out.append(
                {
                    "id": item["id"],
                    "title": item["snippet"]["title"],
                    "channel_id": item["snippet"]["channelId"],
                    "channel_title": item["snippet"]["channelTitle"],
                    "published_at": published,
                    "age_days": round(days_since(published), 1),
                    "views": int(stats.get("viewCount", 0) or 0),
                    "likes": int(stats.get("likeCount", 0) or 0),
                    "comments": int(stats.get("commentCount", 0) or 0),
                    "duration_seconds": parse_duration(item["contentDetails"].get("duration", "")),
                    "url": f"https://youtube.com/watch?v={item['id']}",
                }
            )
    return out


def channel_uploads(channel_id: str, limit: int = 50) -> list[dict]:
    """Most recent uploads for a channel, newest first, with stats."""
    info = channel_info([channel_id]).get(channel_id)
    if not info:
        raise YouTubeError(f"Channel not found: {channel_id}")
    items = _paged(
        "playlistItems",
        {"part": "contentDetails", "playlistId": info["uploads_playlist"]},
        limit=limit,
        ttl=DEFAULT_TTL,
    )
    ids = [i["contentDetails"]["videoId"] for i in items]
    videos = video_details(ids)
    videos.sort(key=lambda v: v["published_at"], reverse=True)
    return videos


def search_videos(
    query: str,
    days: int | None = None,
    limit: int = 50,
    order: str = "relevance",
) -> list[dict]:
    """Live YouTube search -> normalised video records with stats."""
    params = {
        "part": "snippet",
        "type": "video",
        "q": query,
        "order": order,
        "publishedAfter": rfc3339_days_ago(days) if days else None,
    }
    items = _paged("search", params, limit=limit, ttl=DEFAULT_TTL)
    ids = [i["id"]["videoId"] for i in items if i.get("id", {}).get("videoId")]
    return video_details(ids)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Ad-hoc YouTube API probes.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("resolve", help="Resolve a channel reference to a UC... ID")
    p.add_argument("ref")

    p = sub.add_parser("uploads", help="List recent uploads for a channel")
    p.add_argument("ref")
    p.add_argument("--limit", type=int, default=10)

    p = sub.add_parser("search", help="Search YouTube")
    p.add_argument("query")
    p.add_argument("--days", type=int)
    p.add_argument("--limit", type=int, default=15)

    args = parser.parse_args()
    try:
        if args.cmd == "resolve":
            print(resolve_channel_id(args.ref))
        elif args.cmd == "uploads":
            print(json.dumps(channel_uploads(resolve_channel_id(args.ref), args.limit), indent=2))
        elif args.cmd == "search":
            print(json.dumps(search_videos(args.query, args.days, args.limit), indent=2))
    except (YouTubeError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
