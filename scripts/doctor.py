#!/usr/bin/env python3
"""Check that the Checker can actually run. Run this first, and after any config change.

    python scripts/doctor.py
"""

from __future__ import annotations

import sys

from ytconfig import CONFIG_PATH, EXAMPLE_PATH, ROOT, ConfigError, api_key, load, prediction_log_path

OK, WARN, FAIL = "  ok  ", " warn ", " FAIL "


def main() -> int:
    failures = 0
    warnings = 0

    def report(status: str, label: str, detail: str = "") -> None:
        print(f"[{status}] {label}" + (f"\n         {detail}" if detail else ""))

    print(f"YouTube Checker — setup check\n{'=' * 62}")

    # 1. config file
    if CONFIG_PATH.exists():
        try:
            cfg = load()
            report(OK, "config/config.json found and parsed")
        except ConfigError as exc:
            report(FAIL, "config/config.json is broken", str(exc))
            return 1
    else:
        cfg = load()
        report(
            WARN,
            "config/config.json not found — using defaults",
            f"cp {EXAMPLE_PATH.relative_to(ROOT)} {CONFIG_PATH.relative_to(ROOT)}",
        )
        warnings += 1

    # 2. API key
    try:
        key = api_key()
        report(OK, f"YouTube Data API key found ({len(key)} chars)")
        have_key = True
    except ConfigError as exc:
        report(FAIL, "no YouTube Data API key", str(exc).split("\n")[0])
        failures += 1
        have_key = False

    # 3. channel configured
    channel_ref = cfg["channel"].get("id") or cfg["channel"].get("handle")
    if channel_ref:
        report(OK, f"channel configured: {channel_ref}")
    else:
        report(FAIL, "no channel configured", "set channel.id or channel.handle — this is the scale's denominator")
        failures += 1

    # 4. live median
    if have_key and channel_ref:
        try:
            import median as median_mod

            result = median_mod.own_median()
            report(
                OK,
                f"channel median: {result['median_views']:,} views "
                f"(n={result['sample_size']}, {result['channel_title']})",
                "predicted view ranges will be computed against this number",
            )
        except Exception as exc:
            report(FAIL, "could not compute channel median", str(exc)[:200])
            failures += 1
    else:
        report(WARN, "skipped channel median (needs API key + channel)")
        warnings += 1

    # 5. competitors
    competitors = cfg.get("competitor_channel_ids") or []
    if competitors:
        report(OK, f"{len(competitors)} competitor channel(s) configured")
    else:
        report(
            WARN,
            "no competitor_channel_ids configured",
            "not fatal — competitor medians resolve live from search results, "
            "but reusing COMPETITOR_CHANNEL_IDS from the Viral Content System is cheaper on quota",
        )
        warnings += 1

    # 6. prediction log
    log_path = prediction_log_path(cfg)
    if log_path.exists():
        rows = max(0, len(log_path.read_text(encoding="utf-8").strip().splitlines()) - 1)
        report(OK, f"prediction log: {log_path.relative_to(ROOT)} ({rows} entries)")
        if rows >= 15:
            print("         enough entries to run: python scripts/predlog.py calibrate")
    else:
        report(WARN, f"prediction log not created yet ({log_path.relative_to(ROOT)})", "it is created on first `predlog.py add`")
        warnings += 1

    # 7. scale sanity
    import score as score_mod

    assert score_mod.verdict_for(90)["label"] == "FILM NOW"
    assert score_mod.verdict_for(30)["label"] == "DON'T FILM"
    report(OK, "scale and verdict thresholds intact")

    print("=" * 62)
    if failures:
        print(f"{failures} failure(s), {warnings} warning(s) — the Checker cannot run fully yet.")
        return 1
    print(f"ready. {warnings} warning(s)." if warnings else "ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
