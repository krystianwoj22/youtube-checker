#!/usr/bin/env python3
"""The 0-100 scale, the hard gates, and the verdict.

The score is NOT an abstract quality rating. Per the build brief §5 it expresses
the predicted multiple of Krystian's own channel median. That makes it
falsifiable: at +30d you can check whether the video actually landed in the
predicted band. Abstract points cannot be wrong, so they teach you nothing.

Scoring is done here, in code, rather than by the model, for one reason: a model
asked to produce both a number and a justification will move the number to suit
the justification. Here the evidence goes in, the number comes out, and the
model cannot negotiate with it.

Usage:
    python scripts/score.py --file evidence.json
    echo '{...}' | python scripts/score.py
"""

from __future__ import annotations

import argparse
import json
import math
import sys

# --------------------------------------------------------------------------- #
# score <-> multiple-of-median curve  (brief §5)
# --------------------------------------------------------------------------- #

# Anchors are read straight off the verdict table: 85 -> 3x, 70 -> 1.5x,
# 55 -> ~median, 40 -> 0.5x. Interpolation is linear in log(multiple), so the
# curve is smooth and invertible.
ANCHORS = [(0, 0.08), (40, 0.50), (55, 0.90), (70, 1.50), (85, 3.00), (100, 6.00)]

# Fallback half-width of the predicted band, in score points, used only when the
# channel's own dispersion is unavailable. When median.py stats are present the
# band is derived from the channel's real p25/p75 spread instead — an interval
# matched to how volatile THIS channel actually is, not an arbitrary constant.
BAND_POINTS = 8

# sigma = ln(p75/p25)/1.349 for a lognormal view distribution. Clamped so a
# freak sample can't produce an absurd band.
SIGMA_MIN, SIGMA_MAX = 0.35, 1.20

VERDICTS = [
    (85, "FILM NOW", "\U0001f534", "drop other work"),
    (70, "FILM", "\U0001f7e2", "take the next slot"),
    (55, "SAFE FILLER", "\U0001f7e1", "fine for the calendar, not a priority"),
    (40, "ONLY IF", "⚪", "only with a strategic reason (course material, SEO for a course)"),
    (0, "DON'T FILM", "⛔", ""),
]


def score_to_multiple(score: float) -> float:
    score = max(0.0, min(100.0, float(score)))
    for (s0, m0), (s1, m1) in zip(ANCHORS, ANCHORS[1:]):
        if score <= s1:
            if s1 == s0:
                return m1
            t = (score - s0) / (s1 - s0)
            return math.exp(math.log(m0) + t * (math.log(m1) - math.log(m0)))
    return ANCHORS[-1][1]


def multiple_to_score(multiple: float) -> float:
    """Inverse of score_to_multiple — used by the calibration report."""
    multiple = max(ANCHORS[0][1], min(ANCHORS[-1][1], float(multiple)))
    for (s0, m0), (s1, m1) in zip(ANCHORS, ANCHORS[1:]):
        if multiple <= m1:
            if m1 == m0:
                return s1
            t = (math.log(multiple) - math.log(m0)) / (math.log(m1) - math.log(m0))
            return s0 + t * (s1 - s0)
    return ANCHORS[-1][0]


def multiple_band(score: float) -> tuple[float, float]:
    """Fallback band: +/- BAND_POINTS score points."""
    lo = score_to_multiple(max(0, score - BAND_POINTS))
    hi = score_to_multiple(min(100, score + BAND_POINTS))
    return round(lo, 2), round(hi, 2)


def sigma_from_stats(median_stats: dict) -> float | None:
    """Channel view-dispersion sigma from median.py output (p25/p75)."""
    p25 = median_stats.get("p25_views") or 0
    p75 = median_stats.get("p75_views") or 0
    if p25 <= 0 or p75 <= p25:
        return None
    sigma = math.log(p75 / p25) / 1.349
    return max(SIGMA_MIN, min(SIGMA_MAX, sigma))


def multiple_band_sigma(score: float, sigma: float) -> tuple[float, float]:
    """50% interval around the point estimate, scaled to the channel's own
    upload-to-upload volatility. A consistent channel gets a tight band; a
    spiky channel gets an honest wide one."""
    center = score_to_multiple(score)
    hw = 0.6745 * sigma  # 50% of a lognormal falls within +/-0.6745 sigma
    return round(center * math.exp(-hw), 2), round(center * math.exp(hw), 2)


def verdict_for(score: float) -> dict:
    for threshold, label, emoji, note in VERDICTS:
        if score >= threshold:
            return {"label": label, "emoji": emoji, "note": note, "floor": threshold}
    return {"label": "DON'T FILM", "emoji": "⛔", "note": "", "floor": 0}


# --------------------------------------------------------------------------- #
# sub-score tables
# --------------------------------------------------------------------------- #


def _band(value: float, table: list[tuple[float, float]], default: float) -> float:
    """First matching upper bound wins. Table must be ascending by bound."""
    for bound, points in table:
        if value <= bound:
            return points
    return default


def _enum(value, table: dict, field: str) -> float:
    key = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if key not in table:
        raise ValueError(f"{field}: expected one of {sorted(table)}, got {value!r}")
    return table[key]


def _need(evidence: dict, field: str):
    if field not in evidence or evidence[field] is None:
        raise ValueError(
            f"missing required evidence field: {field!r}. "
            "Every check must produce a concrete finding before a score exists."
        )
    return evidence[field]


# ---- Mode A: fresh news / launch (brief §3) -------------------------------- #

# Spreads are wide on purpose. In the first build the ungated Mode A floor was
# 62 (SAFE FILLER) — the continuous scale carried no information and only the
# gates could say no. A niche, non-demoable launch must be able to land in
# ONLY IF territory without a gate firing.
A_LAUNCH_SIZE = {"major": 92.0, "mid": 65.0, "niche": 25.0}
A_ACCESS = {
    "public_free": 95.0,
    "public_paid": 80.0,
    "limited": 45.0,   # regional rollout, paywalled behind a high tier, gradual access
    "waitlist": 20.0,
    "enterprise": 12.0,
}
A_DEMOABLE = {"yes": 90.0, "partial": 60.0, "no": 20.0}

A_WEIGHTS = {
    "viewer_access": 0.28,   # brief §3.2: "the single strongest predictor in Mode A"
    "launch_size": 0.22,
    "supply": 0.20,
    "timing": 0.18,
    "demoable": 0.12,
}


def score_mode_a(evidence: dict, cfg_sat: dict) -> dict:
    launch = _enum(_need(evidence, "launch_size"), A_LAUNCH_SIZE, "launch_size")
    access_key = str(_need(evidence, "viewer_access")).strip().lower().replace("-", "_")
    access = _enum(access_key, A_ACCESS, "viewer_access")
    demo = _enum(_need(evidence, "demoable"), A_DEMOABLE, "demoable")

    channels_7d = int(_need(evidence, "channels_published_7d"))
    supply = _band(channels_7d, [(0, 92.0), (1, 75.0), (2, 48.0)], 25.0)

    hours_needed = float(_need(evidence, "hours_needed"))
    hours_window = float(_need(evidence, "hours_window_left"))
    if hours_window <= 0:
        ratio = float("inf")
    else:
        ratio = hours_needed / hours_window
    timing = _band(ratio, [(0.2, 95.0), (0.4, 85.0), (0.6, 70.0), (0.8, 55.0), (1.0, 40.0)], 15.0)

    subs = {
        "viewer_access": access,
        "launch_size": launch,
        "supply": supply,
        "timing": timing,
        "demoable": demo,
    }
    raw = sum(subs[k] * w for k, w in A_WEIGHTS.items())

    detail = {
        "viewer_access": f"{access_key} -> can the viewer touch it today",
        "launch_size": f"{evidence['launch_size']} player",
        "supply": f"{channels_7d} channel(s) already published in the last {cfg_sat['mode_a_window_days']}d",
        "timing": f"{hours_needed:g}h of work vs {hours_window:g}h of window ("
        + ("window already gone" if ratio == float("inf") else f"ratio {ratio:.2f}")
        + ")",
        "demoable": f"demoable on screen: {evidence['demoable']}",
    }

    gates = []
    closed_at = cfg_sat["mode_a_closed_at_channels"]
    if channels_7d >= closed_at:
        gates.append(
            {
                "cap": 35,
                "reason": f"WINDOW CLOSED: {channels_7d} channels published in the last "
                f"{cfg_sat['mode_a_window_days']}d (>= {closed_at}). Brief §3.4: the verdict is "
                "NO regardless of how good the news is.",
            }
        )
    if access_key == "waitlist":
        gates.append({"cap": 39, "reason": "Viewer cannot access it: waitlist only. Brief §3.2 / §6."})
    if access_key == "enterprise":
        gates.append({"cap": 32, "reason": "Viewer cannot access it: enterprise-only. Brief §3.2 / §6."})
    if access_key == "limited":
        gates.append({"cap": 60, "reason": "Access is limited (rollout / high paid tier) — capped, not killed."})
    if ratio > 1.0:
        gates.append(
            {
                "cap": 45,
                "reason": f"Cannot ship in time: {hours_needed:g}h needed, {hours_window:g}h left. Brief §3.5.",
            }
        )

    return {"subscores": subs, "weights": A_WEIGHTS, "detail": detail, "raw": raw, "gates": gates}


# ---- Mode B: existing idea / backlog row (brief §4) ------------------------ #

B_ACCESS_PENALTY = {"none": 0.0, "paid_tier": 8.0, "enterprise": 30.0}
# core fit is the baseline expectation, not an achievement — 85, not 90+.
B_FIT = {"core": 85.0, "adjacent": 72.0, "mismatch": 40.0}

# Is the topic gaining or losing steam RIGHT NOW. Supersedes the old static
# `decay` guess: computed by supply.py from the publication-and-success rate of
# the last 30 days vs the 60 before them. `decay` is still accepted as a
# fallback and mapped onto this.
B_MOMENTUM = {"accelerating": 90.0, "steady": 65.0, "unknown": 55.0, "fading": 35.0}
_DECAY_TO_MOMENTUM = {"evergreen": "steady", "months": "steady", "weeks": "fading", "dead_soon": "fading"}

# How Krystian's OWN videos on this topic performed against his own median.
# This is the only input that is about HIS audience rather than someone
# else's, which is why it carries the heaviest weight in the mode.
B_OWN_HISTORY = [(0.5, 22.0), (0.8, 38.0), (1.2, 60.0), (2.0, 80.0), (3.0, 90.0)]
OWN_HISTORY_NEUTRAL = 60.0     # no prior video on the topic: unknown, not bad
OWN_HISTORY_UNCHECKED = 55.0   # lookup could not run: unknown and unverified

# Verifiable packaging sub-questions, each answered against the actual
# competitor set found in the saturation check. Replaces (or backs) the single
# 0-10 gut number, which was the easiest input to inflate.
PACKAGING_CHECKS = (
    "differentiated_angle",     # an angle none of the found competitor titles has
    "thumbnail_stands_out",     # concept visibly different from the top 5 thumbnails
    "verifiable_promise",       # the title's promise is provable in the first 15s
    "curiosity_gap",            # title opens a question the thumbnail doesn't answer
    "title_specific",           # a number/named tool/concrete outcome in the title
)

B_WEIGHTS = {
    "own_history": 0.22,     # the only signal about YOUR audience — heaviest on purpose
    "real_demand": 0.20,     # brief §4.2, measured on competitors' audiences
    "packaging": 0.18,       # brief §4.4: same topic does 3K or 300K on packaging alone
    "saturation": 0.15,
    "executability": 0.10,
    "momentum": 0.09,
    "audience_fit": 0.06,
}


def _packaging_raw(evidence: dict) -> tuple[float, str]:
    checks = evidence.get("packaging_checks")
    if checks is not None:
        if not isinstance(checks, dict) or len(checks) < 3:
            raise ValueError(
                "packaging_checks must be an object with at least 3 of: "
                + ", ".join(PACKAGING_CHECKS)
            )
        unknown = set(checks) - set(PACKAGING_CHECKS)
        if unknown:
            raise ValueError(f"packaging_checks: unknown keys {sorted(unknown)}")
        passed = sum(1 for v in checks.values() if v)
        raw = round(10.0 * passed / len(checks), 1)
        return raw, f"{passed}/{len(checks)} verifiable checks passed -> {raw:g}/10"
    raw = float(_need(evidence, "packaging_strength"))
    if not 0 <= raw <= 10:
        raise ValueError("packaging_strength must be 0-10")
    return raw, f"packaging strength {raw:g}/10 against the competitors found"


def score_mode_b(evidence: dict, cfg_sat: dict) -> dict:
    # 1. Own-channel history — how KRYSTIAN'S videos on this topic performed
    #    against his own median. supply.py / history.py compute this. A null
    #    means the lookup could not run; 0 videos means genuinely untried.
    if "own_topic_videos" not in evidence:
        raise ValueError(
            "missing required evidence field: 'own_topic_videos'. Run "
            "`python scripts/history.py --q \"<topic>\"` (or supply.py mode-b, which includes it). "
            "Pass null only if the lookup genuinely could not run."
        )
    own_n = evidence["own_topic_videos"]
    own_best = None
    if own_n is None:
        own_history = OWN_HISTORY_UNCHECKED
        own_detail = "own-channel history UNCHECKED (lookup unavailable) — treated as neutral"
    elif int(own_n) == 0:
        own_history = OWN_HISTORY_NEUTRAL
        own_detail = "no prior video on this topic on the channel — untried, neutral"
    else:
        own_best = float(_need(evidence, "own_best_topic_ratio"))
        own_history = _band(own_best, B_OWN_HISTORY, 96.0)
        own_detail = (
            f"your best of {int(own_n)} video(s) on this topic did {own_best:.2f}x YOUR median"
        )

    # 2. Real gap vs dead topic — has ANY video on this topic beaten its own
    #    channel's median, and by how much.
    ratio = float(_need(evidence, "best_overperformance_ratio"))
    demand = _band(ratio, [(1.0, 40.0), (1.5, 58.0), (2.0, 68.0), (3.0, 82.0)], 92.0)
    demand_note = ""
    over_age = evidence.get("best_overperformance_age_days")
    if over_age is not None and float(over_age) > 60 and demand > 75.0:
        demand = 75.0
        demand_note = f" [STALE: best overperformer is {float(over_age):.0f}d old — capped]"

    # 3. Saturation. Note the shape: zero competitors is NOT the best outcome.
    #    1-2 proven videos means demand exists and there is still room. Zero
    #    means unproven, and the demand check has to carry the whole idea.
    count_90d = int(_need(evidence, "videos_90d_over_20k"))
    saturation = _band(count_90d, [(0, 55.0), (2, 85.0), (5, 70.0), (10, 50.0), (20, 32.0)], 18.0)

    # 4. Executability.
    hours = float(_need(evidence, "hours_needed"))
    exec_base = _band(hours, [(4, 95.0), (8, 85.0), (16, 70.0), (24, 55.0)], 35.0)
    blockers = str(evidence.get("access_blockers", "none"))
    executability = max(0.0, exec_base - _enum(blockers, B_ACCESS_PENALTY, "access_blockers"))

    # 5. Packaging survival — verifiable checks preferred, 0-10 accepted.
    packaging_raw, packaging_detail = _packaging_raw(evidence)
    packaging = 20.0 + 7.5 * packaging_raw

    # 6. Momentum: is the topic accelerating or fading right now. Falls back to
    #    the legacy static `decay` field when supply.py could not compute it.
    mom = evidence.get("topic_momentum")
    if mom is None and evidence.get("decay") is not None:
        decay_key = str(evidence["decay"]).strip().lower().replace("-", "_")
        if decay_key not in _DECAY_TO_MOMENTUM:
            raise ValueError(f"decay: expected one of {sorted(_DECAY_TO_MOMENTUM)}, got {evidence['decay']!r}")
        mom = _DECAY_TO_MOMENTUM[decay_key]
        mom_detail = f"momentum {mom} (derived from decay={evidence['decay']})"
    elif mom is not None:
        mom_detail = f"topic momentum: {mom} (last 30d vs the 60d before)"
    else:
        raise ValueError("missing required evidence field: 'topic_momentum' (or legacy 'decay')")
    momentum = _enum(mom, B_MOMENTUM, "topic_momentum")

    fit = _enum(evidence.get("audience_fit", "core"), B_FIT, "audience_fit")

    subs = {
        "own_history": own_history,
        "real_demand": demand,
        "packaging": packaging,
        "saturation": saturation,
        "executability": executability,
        "momentum": momentum,
        "audience_fit": fit,
    }
    raw = sum(subs[k] * w for k, w in B_WEIGHTS.items())

    detail = {
        "own_history": own_detail,
        "real_demand": f"best competitor video did {ratio:.2f}x its own channel's median"
        + (f" (n={evidence['overperformance_sample_size']} checked)" if evidence.get("overperformance_sample_size") else "")
        + demand_note,
        "saturation": f"{count_90d} video(s) over {cfg_sat['mode_b_relevant_views']:,} views "
        f"in the last {cfg_sat['mode_b_window_days']}d",
        "packaging": packaging_detail,
        "executability": f"{hours:g}h of work, access blockers: {blockers}",
        "momentum": mom_detail,
        "audience_fit": f"audience fit: {evidence.get('audience_fit', 'core')}",
    }

    gates = []

    # Dead topic — softened by the one thing that outranks competitor data:
    # Krystian's own audience having already proven demand.
    own_best_val = own_best if own_best is not None else 0.0
    if ratio < 1.0:
        if own_best_val >= 1.2:
            detail["real_demand"] += (
                f" [no competitor overperformance, but YOUR channel did {own_best_val:.2f}x "
                "on this topic — own data overrides the dead-topic gate]"
            )
        else:
            gates.append(
                {
                    "cap": 35,
                    "reason": f"DEAD TOPIC: nothing on this topic has ever beaten its own channel's median "
                    f"(best is {ratio:.2f}x), and your own channel shows no overperformance on it either. "
                    "Brief §4.2: 'no competition' means no demand, not an opening.",
                }
            )

    # Big-channel gate — CONDITIONAL. A 100K+ channel covering the topic only
    # closes it if their video actually worked for them (beat their median).
    # A big channel posting a flop on the topic is contested ground, not a
    # closed door — and often free packaging intel.
    big_over = evidence.get("big_channel_overperformed_30d")
    big_covered = evidence.get("big_channel_covered_30d")
    if big_over is None:
        if big_covered is None:
            raise ValueError(
                "missing required evidence field: 'big_channel_overperformed_30d' "
                "(or legacy 'big_channel_covered_30d')"
            )
        big_over = big_covered  # legacy evidence: conservative — covered counts as won
    if bool(big_over):
        gates.append(
            {
                "cap": 38,
                "reason": f"A channel over {cfg_sat['big_channel_subscribers']:,} subs covered this in the "
                f"last {cfg_sat['big_channel_window_days']}d AND beat its own median doing it — "
                "you lose the algorithm fight. Brief §4.1.",
            }
        )
    elif bool(big_covered):
        detail["saturation"] += (
            " [a 100K+ channel covered it but UNDERPERFORMED its own median — "
            "contested, not closed; study why their packaging missed]"
        )

    # Cannibalisation — the checker's own channel already has a fresh video on
    # this. A second one inside the window splits the same audience.
    own_recent = evidence.get("own_recent_topic_video_days")
    recent_limit = cfg_sat.get("own_recent_video_days", 60)
    if own_recent is not None and float(own_recent) < recent_limit:
        gates.append(
            {
                "cap": 45,
                "reason": f"CANNIBALISATION: your own channel published on this topic "
                f"{float(own_recent):.0f}d ago (< {recent_limit}d). A second video splits "
                "your own audience unless the angle is genuinely different.",
            }
        )

    if blockers == "enterprise":
        gates.append({"cap": 45, "reason": "Requires an enterprise tier the viewer cannot access."})

    return {"subscores": subs, "weights": B_WEIGHTS, "detail": detail, "raw": raw, "gates": gates}


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #


def evaluate(
    evidence: dict,
    median_views: int | None = None,
    cfg_sat: dict | None = None,
    median_stats: dict | None = None,
) -> dict:
    cfg_sat = cfg_sat or {
        "mode_a_window_days": 7,
        "mode_a_closed_at_channels": 3,
        "mode_b_window_days": 90,
        "mode_b_relevant_views": 20000,
        "big_channel_subscribers": 100000,
        "big_channel_window_days": 30,
        "own_recent_video_days": 60,
    }
    mode = str(evidence.get("mode", "")).strip().upper()
    if mode == "A":
        result = score_mode_a(evidence, cfg_sat)
    elif mode == "B":
        result = score_mode_b(evidence, cfg_sat)
    else:
        raise ValueError("mode must be 'A' (fresh news) or 'B' (existing idea)")

    raw = result["raw"]
    score = raw
    applied = []
    for gate in result["gates"]:
        if score > gate["cap"]:
            score = float(gate["cap"])
            applied.append(gate)

    score = int(round(max(0.0, min(100.0, score))))

    sigma = sigma_from_stats(median_stats) if median_stats else None
    if sigma is not None:
        lo, hi = multiple_band_sigma(score, sigma)
        band_source = f"50% interval from your channel's own spread (sigma {sigma:.2f})"
    else:
        lo, hi = multiple_band(score)
        band_source = "default band (channel spread unavailable)"

    verdict = verdict_for(score)

    if median_views is None and median_stats:
        median_views = median_stats.get("median_views")

    out = {
        "mode": mode,
        "topic": evidence.get("topic", ""),
        "score": score,
        "raw_score": round(raw, 1),
        "multiple_low": lo,
        "multiple_high": hi,
        "band_source": band_source,
        "verdict": verdict["label"],
        "verdict_emoji": verdict["emoji"],
        "verdict_note": verdict["note"],
        "subscores": {k: round(v, 1) for k, v in result["subscores"].items()},
        "weights": result["weights"],
        "detail": result["detail"],
        "gates_available": result["gates"],
        "gates_applied": applied,
        "gated": bool(applied),
    }
    if median_views:
        out["median_views"] = int(median_views)
        out["predicted_views_low"] = int(round(lo * median_views))
        out["predicted_views_high"] = int(round(hi * median_views))
    return out


def render(result: dict) -> str:
    lines = []
    lines.append(f"MODE: {result['mode']}")
    if result["topic"]:
        lines.append(f"TOPIC: {result['topic']}")
    lines.append("")
    lines.append("sub-scores (weighted):")
    for key, weight in result["weights"].items():
        sub = result["subscores"][key]
        lines.append(f"  {key:<16} {sub:>5.1f}  x{weight:<5.2f}  {result['detail'][key]}")
    lines.append(f"  {'raw':<16} {result['raw_score']:>5.1f}")
    lines.append("")
    if result["gates_applied"]:
        lines.append("HARD GATES TRIPPED:")
        for gate in result["gates_applied"]:
            lines.append(f"  [cap {gate['cap']}] {gate['reason']}")
        lines.append("")
    views = ""
    if "predicted_views_low" in result:
        views = f" (~{result['predicted_views_low']:,}-{result['predicted_views_high']:,} views)"
    lines.append(
        f"SCORE: {result['score']}  ->  predicted "
        f"{result['multiple_low']}-{result['multiple_high']}x your median{views}"
    )
    lines.append(f"        band: {result['band_source']}")
    note = f" — {result['verdict_note']}" if result["verdict_note"] else ""
    lines.append(f"VERDICT: {result['verdict_emoji']} {result['verdict']}{note}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--file", help="Evidence JSON file. Reads stdin if omitted.")
    parser.add_argument("--median", type=int, help="Channel median views. Auto-fetched if omitted and available.")
    parser.add_argument("--no-median", action="store_true", help="Skip the median lookup entirely.")
    parser.add_argument("--json", action="store_true", help="Emit raw JSON.")
    parser.add_argument("--table", action="store_true", help="Print the score->multiple table and exit.")
    args = parser.parse_args()

    if args.table:
        print(f"{'score':>6}  {'multiple band':>16}  verdict")
        for s in range(0, 101, 5):
            lo, hi = multiple_band(s)
            v = verdict_for(s)
            print(f"{s:>6}  {f'{lo}-{hi}x':>16}  {v['emoji']} {v['label']}")
        return 0

    raw = open(args.file, encoding="utf-8").read() if args.file else sys.stdin.read()
    try:
        evidence = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: evidence is not valid JSON: {exc}", file=sys.stderr)
        return 1

    median_views = args.median
    median_stats = None
    cfg_sat = None
    try:
        from ytconfig import load

        cfg_sat = load()["saturation"]
    except Exception:
        pass

    if not args.no_median:
        try:
            import median as median_mod

            median_stats = median_mod.own_median()
            if median_views is None:
                median_views = median_stats["median_views"]
        except Exception as exc:  # median is optional for the score itself
            print(f"note: channel median unavailable ({exc}); reporting multiples only.", file=sys.stderr)

    try:
        result = evaluate(evidence, median_views, cfg_sat, median_stats=median_stats)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
