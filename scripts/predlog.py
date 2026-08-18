#!/usr/bin/env python3
"""Prediction log — the only thing that ever tells you whether the scale means anything.

One line per run, written BEFORE filming. Actuals filled in at +7d and +30d.
Flat CSV, in the repo. No dashboard (brief §9).

    python scripts/predlog.py add --topic "..." --mode B --score 75
    python scripts/predlog.py list
    python scripts/predlog.py fill --id 3 --actual-30d 41000
    python scripts/predlog.py fill --id 3 --video-id dQw4w9WgXcQ   # pulls views live
    python scripts/predlog.py calibrate
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from datetime import date
from pathlib import Path

import score as score_mod
from ytconfig import ROOT, load, prediction_log_path

FIELDS = [
    "id",
    "date",
    "topic",
    "mode",
    "score",
    "verdict",
    "mult_low",
    "mult_high",
    "median_at_prediction",
    "pred_views_low",
    "pred_views_high",
    "gated",
    "video_id",
    "published_at",
    "actual_7d",
    "actual_30d",
    "shadow_check",
    "notes",
]


def _path(cfg=None) -> Path:
    return prediction_log_path(cfg or load())


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in FIELDS})


def add(result: dict, notes: str = "", when: str | None = None) -> dict:
    """Append one prediction. `result` is score.py's evaluate() output."""
    path = _path()
    rows = _read(path)
    next_id = max((int(r["id"]) for r in rows if r.get("id", "").isdigit()), default=0) + 1

    row = {
        "id": str(next_id),
        "date": when or date.today().isoformat(),
        "topic": result.get("topic", ""),
        "mode": result.get("mode", ""),
        "score": str(result.get("score", "")),
        "verdict": result.get("verdict", ""),
        "mult_low": str(result.get("multiple_low", "")),
        "mult_high": str(result.get("multiple_high", "")),
        "median_at_prediction": str(result.get("median_views", "")),
        "pred_views_low": str(result.get("predicted_views_low", "")),
        "pred_views_high": str(result.get("predicted_views_high", "")),
        "gated": "yes" if result.get("gated") else "no",
        "video_id": "",
        "published_at": "",
        "actual_7d": "",
        "actual_30d": "",
        "shadow_check": "",
        "notes": notes,
    }
    rows.append(row)
    _write(path, rows)
    if result.get("verdict") == "DON'T FILM" or result.get("gated"):
        print(
            f"note: killed/gated idea logged. In ~60d, shadow-verify the kill without filming:\n"
            f"  python scripts/predlog.py shadow --id {row['id']} --q \"{row['topic'][:60]}\"",
            file=sys.stderr,
        )
    return row


def fill(entry_id: int, actual_7d=None, actual_30d=None, video_id=None, notes=None) -> dict:
    path = _path()
    rows = _read(path)
    for row in rows:
        if row.get("id") == str(entry_id):
            if video_id:
                row["video_id"] = video_id
                try:
                    import ytapi

                    details = ytapi.video_details([video_id])
                    if details:
                        v = details[0]
                        row["published_at"] = v["published_at"]
                        age = v["age_days"]
                        if age >= 30 and not row["actual_30d"]:
                            row["actual_30d"] = str(v["views"])
                        elif age >= 7 and not row["actual_7d"]:
                            row["actual_7d"] = str(v["views"])
                        print(
                            f"note: {v['title'][:50]} — {v['views']:,} views at {age:.0f}d",
                            file=sys.stderr,
                        )
                except Exception as exc:
                    print(f"note: could not fetch views ({exc})", file=sys.stderr)
            if actual_7d is not None:
                row["actual_7d"] = str(actual_7d)
            if actual_30d is not None:
                row["actual_30d"] = str(actual_30d)
            if notes is not None:
                row["notes"] = notes
            _write(path, rows)
            return row
    raise SystemExit(f"error: no prediction with id {entry_id}")


def _actual_multiple(row: dict, horizon: str = "actual_30d") -> float | None:
    actual = row.get(horizon, "")
    median = row.get("median_at_prediction", "")
    if not actual or not median:
        return None
    try:
        actual_v, median_v = float(actual), float(median)
    except ValueError:
        return None
    if median_v <= 0:
        return None
    return actual_v / median_v


def calibrate(horizon: str = "actual_30d") -> str:
    """Was the scale right?

    The primary metric is the LOG ERROR: ln(actual multiple) - ln(predicted
    centre). Band hit-rate alone is uninformative at small n — a tool that
    always printed 70 would land 'inside the band' ~30% of the time by pure
    channel variance, and telling that apart from a real signal via hit-rate
    needs 100+ filmed videos. The mean log error (bias) and its spread converge
    an order of magnitude faster and cannot be gamed by widening the band.
    """
    rows = _read(_path())
    scored = []
    for row in rows:
        mult = _actual_multiple(row, horizon)
        if mult is None or mult <= 0:
            continue
        try:
            predicted = int(row["score"])
            lo, hi = float(row["mult_low"]), float(row["mult_high"])
        except (ValueError, KeyError):
            continue
        center = score_mod.score_to_multiple(predicted)
        scored.append(
            {
                "id": row["id"],
                "topic": row["topic"],
                "mode": row["mode"],
                "score": predicted,
                "band": (lo, hi),
                "actual_mult": mult,
                "log_err": math.log(mult) - math.log(center),
                "hit": lo <= mult <= hi,
            }
        )

    lines = [f"CALIBRATION ({horizon})", "=" * 62]
    if not scored:
        lines.append(
            f"No entries with both {horizon} and a median recorded yet.\n"
            f"{len(rows)} prediction(s) logged. Fill actuals with:\n"
            f"  python scripts/predlog.py fill --id <n> --{horizon.replace('_', '-')} <views>"
        )
        return "\n".join(lines)

    def _report(subset: list[dict], label: str) -> None:
        bias = math.exp(statistics.fmean(s["log_err"] for s in subset))
        typical = math.exp(statistics.median(abs(s["log_err"]) for s in subset))
        hits = sum(1 for s in subset if s["hit"])
        drift = (
            "predictions run PESSIMISTIC — reality beats them"
            if bias > 1.25
            else "predictions run OPTIMISTIC — reality falls short"
            if bias < 0.8
            else "well centred"
        )
        lines.append(f"{label}: n={len(subset)}")
        lines.append(f"  bias         : actuals average {bias:.2f}x the predicted centre  ({drift})")
        lines.append(f"  typical miss : {typical:.2f}x off the centre")
        lines.append(f"  in band      : {hits}/{len(subset)} (secondary metric — do not tune on this)")

    _report(scored, "ALL")
    for mode in ("A", "B"):
        subset = [s for s in scored if s["mode"] == mode]
        if subset:
            _report(subset, f"mode {mode}")

    if len(scored) < 20:
        lines.append(
            f"\nNote: {len(scored)} entries. Bias stabilises around ~20 — until then read this "
            "as a direction, not a correction."
        )

    unverified_kills = [
        r for r in rows
        if (r.get("verdict") == "DON'T FILM" or r.get("gated") == "yes")
        and not r.get("shadow_check")
        and not r.get(horizon)
    ]
    if unverified_kills:
        lines.append(
            f"\n{len(unverified_kills)} killed idea(s) never shadow-verified — false negatives are "
            "invisible until you run:\n  python scripts/predlog.py shadow --id <n> --q \"<topic>\""
        )

    lines.append("")
    lines.append(f"{'id':>3}  {'mode':>4}  {'pred':>4}  {'band':>12}  {'actual':>8}  {'err':>7}  topic")
    for s in scored:
        band = f"{s['band'][0]}-{s['band'][1]}x"
        lines.append(
            f"{s['id']:>3}  {s['mode']:>4}  {s['score']:>4}  {band:>12}  "
            f"{s['actual_mult']:>7.2f}x  {math.exp(s['log_err']):>6.2f}x  {s['topic'][:34]}"
        )
    return "\n".join(lines)


def shadow(entry_id: int, query: str) -> str:
    """Verify a killed idea WITHOUT filming it.

    The log's structural blind spot: actuals only exist for videos that were
    filmed, so DON'T FILM verdicts — where the tool claims its value — are
    never tested. This closes half of that hole: if someone ELSE shipped the
    topic after the kill and beat their own channel's median, the kill was
    probably wrong, and that is recordable with zero filming.
    """
    from datetime import datetime

    import supply as supply_mod
    from ytconfig import load as load_cfg

    path = _path()
    rows = _read(path)
    row = next((r for r in rows if r.get("id") == str(entry_id)), None)
    if row is None:
        raise SystemExit(f"error: no prediction with id {entry_id}")

    pred_date = datetime.fromisoformat(row["date"]).date()
    days_since = (date.today() - pred_date).days
    if days_since < 14:
        print(
            f"note: prediction is only {days_since}d old — a clean shadow check wants 30-60d.",
            file=sys.stderr,
        )

    res = supply_mod.mode_b_supply(query, load_cfg())
    after = [
        o for o in res.get("overperformers", [])
        if o["age_days"] <= days_since and o.get("overperformance_ratio", 0) >= 1.5
    ]
    if after:
        best = max(after, key=lambda o: o["overperformance_ratio"])
        outcome = (
            f"FALSE NEGATIVE? {best['channel']} did {best['overperformance_ratio']}x its median "
            f"({best['views']:,} views) {best['age_days']:.0f}d ago — after the kill"
        )
    else:
        outcome = f"kill holds: no post-verdict video beat 1.5x its channel median ({days_since}d window)"

    row["shadow_check"] = f"{date.today().isoformat()}: {outcome}"
    _write(path, rows)
    return f"#{row['id']} {row['topic'][:50]}\n  {outcome}"


def render_list() -> str:
    rows = _read(_path())
    if not rows:
        return "No predictions logged yet."
    out = [f"{'id':>3}  {'date':>10}  {'m':>1}  {'score':>5}  {'band':>11}  {'7d':>8}  {'30d':>8}  topic"]
    for row in rows:
        band = f"{row['mult_low']}-{row['mult_high']}x" if row["mult_low"] else ""
        out.append(
            f"{row['id']:>3}  {row['date']:>10}  {row['mode']:>1}  {row['score']:>5}  {band:>11}  "
            f"{row['actual_7d'] or '__':>8}  {row['actual_30d'] or '__':>8}  {row['topic'][:40]}"
        )
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="Append a prediction")
    a.add_argument("--topic")
    a.add_argument("--mode", choices=["A", "B"])
    a.add_argument("--score", type=int)
    a.add_argument("--median", type=int, help="Channel median at prediction time")
    a.add_argument("--gated", action="store_true")
    a.add_argument("--notes", default="")
    a.add_argument("--from-result", help="score.py --json output file (preferred — carries everything)")

    sub.add_parser("list", help="Show the log")

    f = sub.add_parser("fill", help="Record actual views")
    f.add_argument("--id", type=int, required=True)
    f.add_argument("--actual-7d", type=int)
    f.add_argument("--actual-30d", type=int)
    f.add_argument("--video-id", help="Fetch views live from YouTube")
    f.add_argument("--notes")

    c = sub.add_parser("calibrate", help="Was the scale right?")
    c.add_argument("--horizon", default="actual_30d", choices=["actual_7d", "actual_30d"])

    sh = sub.add_parser("shadow", help="Verify a killed idea without filming it")
    sh.add_argument("--id", type=int, required=True)
    sh.add_argument("--q", required=True, help="The topic query, same as supply.py mode-b")

    args = parser.parse_args()

    if args.cmd == "add":
        if args.from_result:
            result = json.loads(Path(args.from_result).read_text(encoding="utf-8"))
        elif not (args.topic and args.mode and args.score is not None):
            parser.error("add needs either --from-result or all of --topic/--mode/--score")
        else:
            lo, hi = score_mod.multiple_band(args.score)
            verdict = score_mod.verdict_for(args.score)
            result = {
                "topic": args.topic,
                "mode": args.mode,
                "score": args.score,
                "verdict": verdict["label"],
                "multiple_low": lo,
                "multiple_high": hi,
                "gated": args.gated,
            }
            if args.median:
                result["median_views"] = args.median
                result["predicted_views_low"] = int(round(lo * args.median))
                result["predicted_views_high"] = int(round(hi * args.median))
        row = add(result, notes=args.notes)
        print(f"logged #{row['id']}: {row['topic']} | mode {row['mode']} | "
              f"{row['score']} = {row['mult_low']}-{row['mult_high']}x median")
        print(f"  -> {_path().relative_to(ROOT)}")
    elif args.cmd == "list":
        print(render_list())
    elif args.cmd == "fill":
        row = fill(args.id, args.actual_7d, args.actual_30d, args.video_id, args.notes)
        print(f"updated #{row['id']}: 7d={row['actual_7d'] or '__'} 30d={row['actual_30d'] or '__'}")
    elif args.cmd == "calibrate":
        print(calibrate(args.horizon))
    elif args.cmd == "shadow":
        print(shadow(args.id, args.q))
    return 0


if __name__ == "__main__":
    sys.exit(main())
