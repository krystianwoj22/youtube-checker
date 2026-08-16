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
        "notes": notes,
    }
    rows.append(row)
    _write(path, rows)
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
    """Was the scale right? Brief §8: after ~15-20 entries this can adjust the
    scale on evidence instead of feel."""
    rows = _read(_path())
    scored = []
    for row in rows:
        mult = _actual_multiple(row, horizon)
        if mult is None:
            continue
        try:
            predicted = int(row["score"])
            lo, hi = float(row["mult_low"]), float(row["mult_high"])
        except (ValueError, KeyError):
            continue
        scored.append(
            {
                "id": row["id"],
                "topic": row["topic"],
                "mode": row["mode"],
                "score": predicted,
                "band": (lo, hi),
                "actual_mult": mult,
                "implied_score": score_mod.multiple_to_score(mult),
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

    hits = sum(1 for s in scored if s["hit"])
    bias = statistics.fmean(s["implied_score"] - s["score"] for s in scored)
    lines.append(f"entries with actuals : {len(scored)}")
    lines.append(f"inside predicted band: {hits}/{len(scored)}  ({hits / len(scored):.0%})")
    lines.append(
        f"mean bias            : {bias:+.1f} score points  "
        + ("(scale runs PESSIMISTIC)" if bias > 3 else "(scale runs OPTIMISTIC)" if bias < -3 else "(well centred)")
    )

    for mode in ("A", "B"):
        subset = [s for s in scored if s["mode"] == mode]
        if subset:
            mode_hits = sum(1 for s in subset if s["hit"])
            mode_bias = statistics.fmean(s["implied_score"] - s["score"] for s in subset)
            lines.append(
                f"  mode {mode}: {mode_hits}/{len(subset)} in band, bias {mode_bias:+.1f}"
            )

    if len(scored) < 15:
        lines.append(
            f"\nNote: {len(scored)} entries. The brief expects ~15-20 before adjusting the scale — "
            "read this as a direction, not a correction."
        )

    lines.append("")
    lines.append(f"{'id':>3}  {'mode':>4}  {'pred':>4}  {'band':>12}  {'actual':>8}  {'hit':>4}  topic")
    for s in scored:
        band = f"{s['band'][0]}-{s['band'][1]}x"
        lines.append(
            f"{s['id']:>3}  {s['mode']:>4}  {s['score']:>4}  {band:>12}  "
            f"{s['actual_mult']:>7.2f}x  {'yes' if s['hit'] else 'NO':>4}  {s['topic'][:38]}"
        )
    return "\n".join(lines)


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
    a.add_argument("--topic", help="required unless --from-result is given")
    a.add_argument("--mode", choices=["A", "B"], help="required unless --from-result is given")
    a.add_argument("--score", type=int, help="required unless --from-result is given")
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

    args = parser.parse_args()

    if args.cmd == "add":
        if args.from_result:
            result = json.loads(Path(args.from_result).read_text(encoding="utf-8"))
        else:
            missing = [n for n in ("topic", "mode", "score") if getattr(args, n) is None]
            if missing:
                parser.error("the following arguments are required: "
                             + ", ".join("--" + n for n in missing)
                             + " (or pass --from-result instead)")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
