#!/usr/bin/env python3
"""Tests for the scale and the hard gates.

These lock in the behaviour the build brief calls non-negotiable — above all,
that the tool can and does say DON'T FILM.

    python -m unittest discover tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import score as s  # noqa: E402

SAT = {
    "mode_a_window_days": 7,
    "mode_a_closed_at_channels": 3,
    "mode_b_window_days": 90,
    "mode_b_relevant_views": 20000,
    "big_channel_subscribers": 100000,
    "big_channel_window_days": 30,
}

GOOD_A = {
    "mode": "A",
    "topic": "major launch",
    "launch_size": "major",
    "viewer_access": "public_free",
    "demoable": "yes",
    "channels_published_7d": 0,
    "hours_needed": 4,
    "hours_window_left": 36,
}

GOOD_B = {
    "mode": "B",
    "topic": "proven topic",
    "videos_90d_over_20k": 2,
    "big_channel_covered_30d": False,
    "best_overperformance_ratio": 2.5,
    "overperformance_sample_size": 10,
    "hours_needed": 6,
    "access_blockers": "none",
    "packaging_strength": 8,
    "decay": "evergreen",
    "audience_fit": "core",
}


class TestScale(unittest.TestCase):
    """The score must mean 'multiple of channel median' at the documented anchors."""

    def test_anchors_match_the_verdict_table(self):
        self.assertAlmostEqual(s.score_to_multiple(85), 3.0, places=2)
        self.assertAlmostEqual(s.score_to_multiple(70), 1.5, places=2)
        self.assertAlmostEqual(s.score_to_multiple(55), 0.9, places=2)
        self.assertAlmostEqual(s.score_to_multiple(40), 0.5, places=2)

    def test_monotonic(self):
        values = [s.score_to_multiple(x) for x in range(0, 101)]
        self.assertEqual(values, sorted(values))

    def test_inverse_round_trips(self):
        for score in (12, 35, 50, 63, 78, 91):
            self.assertAlmostEqual(s.multiple_to_score(s.score_to_multiple(score)), score, places=4)

    def test_verdict_boundaries(self):
        cases = {
            100: "FILM NOW", 85: "FILM NOW", 84: "FILM", 70: "FILM",
            69: "SAFE FILLER", 55: "SAFE FILLER", 54: "ONLY IF", 40: "ONLY IF",
            39: "DON'T FILM", 0: "DON'T FILM",
        }
        for score, expected in cases.items():
            self.assertEqual(s.verdict_for(score)["label"], expected, f"score {score}")

    def test_band_brackets_the_point_estimate(self):
        for score in (20, 45, 60, 75, 90):
            lo, hi = s.multiple_band(score)
            self.assertLess(lo, s.score_to_multiple(score))
            self.assertGreater(hi, s.score_to_multiple(score))


class TestModeAGates(unittest.TestCase):
    def test_strong_launch_scores_film_now(self):
        r = s.evaluate(GOOD_A, cfg_sat=SAT)
        self.assertGreaterEqual(r["score"], 85)
        self.assertEqual(r["verdict"], "FILM NOW")
        self.assertFalse(r["gated"])

    def test_window_closed_kills_a_perfect_idea(self):
        """Brief §3.4: 3+ channels = NO regardless of how good the news is."""
        r = s.evaluate({**GOOD_A, "channels_published_7d": 3}, cfg_sat=SAT)
        self.assertEqual(r["verdict"], "DON'T FILM")
        self.assertTrue(r["gated"])
        self.assertIn("WINDOW CLOSED", r["gates_applied"][0]["reason"])

    def test_waitlist_caps_hard(self):
        r = s.evaluate({**GOOD_A, "viewer_access": "waitlist"}, cfg_sat=SAT)
        self.assertEqual(r["verdict"], "DON'T FILM")

    def test_enterprise_only_caps_harder_than_waitlist(self):
        waitlist = s.evaluate({**GOOD_A, "viewer_access": "waitlist"}, cfg_sat=SAT)
        enterprise = s.evaluate({**GOOD_A, "viewer_access": "enterprise"}, cfg_sat=SAT)
        self.assertLess(enterprise["score"], waitlist["score"])

    def test_limited_access_caps_but_does_not_kill(self):
        r = s.evaluate({**GOOD_A, "viewer_access": "limited"}, cfg_sat=SAT)
        self.assertLessEqual(r["score"], 60)
        self.assertNotEqual(r["verdict"], "DON'T FILM")

    def test_cannot_ship_in_time_caps(self):
        r = s.evaluate({**GOOD_A, "hours_needed": 72, "hours_window_left": 48}, cfg_sat=SAT)
        self.assertLessEqual(r["score"], 45)
        self.assertTrue(r["gated"])

    def test_zero_window_is_not_a_crash(self):
        r = s.evaluate({**GOOD_A, "hours_window_left": 0}, cfg_sat=SAT)
        self.assertLessEqual(r["score"], 45)

    def test_access_outweighs_launch_size(self):
        """Brief §3.2: accessibility is the single strongest predictor in Mode A."""
        niche_but_free = s.evaluate({**GOOD_A, "launch_size": "niche"}, cfg_sat=SAT)
        major_but_waitlisted = s.evaluate({**GOOD_A, "viewer_access": "waitlist"}, cfg_sat=SAT)
        self.assertGreater(niche_but_free["score"], major_but_waitlisted["score"])


class TestModeBGates(unittest.TestCase):
    def test_proven_topic_scores_film(self):
        r = s.evaluate(GOOD_B, cfg_sat=SAT)
        self.assertGreaterEqual(r["score"], 70)
        self.assertFalse(r["gated"])

    def test_dead_topic_gate(self):
        """Brief §4.2: no overperformance means no demand, not an opening."""
        r = s.evaluate({**GOOD_B, "best_overperformance_ratio": 0.7}, cfg_sat=SAT)
        self.assertEqual(r["verdict"], "DON'T FILM")
        self.assertIn("DEAD TOPIC", r["gates_applied"][0]["reason"])

    def test_dead_topic_beats_every_other_strength(self):
        """Even a perfect idea dies if nothing has ever over-performed."""
        perfect_but_dead = {
            **GOOD_B,
            "best_overperformance_ratio": 0.4,
            "packaging_strength": 10,
            "hours_needed": 2,
            "videos_90d_over_20k": 1,
        }
        r = s.evaluate(perfect_but_dead, cfg_sat=SAT)
        self.assertEqual(r["verdict"], "DON'T FILM")

    def test_big_channel_covered_gate(self):
        r = s.evaluate({**GOOD_B, "big_channel_covered_30d": True}, cfg_sat=SAT)
        self.assertEqual(r["verdict"], "DON'T FILM")
        self.assertIn("algorithm fight", r["gates_applied"][0]["reason"])

    def test_zero_competitors_scores_below_two_competitors(self):
        """An empty search is unproven, not an opening."""
        empty = s.evaluate({**GOOD_B, "videos_90d_over_20k": 0}, cfg_sat=SAT)
        proven = s.evaluate({**GOOD_B, "videos_90d_over_20k": 2}, cfg_sat=SAT)
        self.assertLess(empty["score"], proven["score"])

    def test_oversaturation_lowers_score(self):
        crowded = s.evaluate({**GOOD_B, "videos_90d_over_20k": 40}, cfg_sat=SAT)
        self.assertLess(crowded["score"], s.evaluate(GOOD_B, cfg_sat=SAT)["score"])

    def test_packaging_moves_the_score_materially(self):
        """Same topic does 3K or 300K on packaging alone — it must be scored."""
        weak = s.evaluate({**GOOD_B, "packaging_strength": 2}, cfg_sat=SAT)
        strong = s.evaluate({**GOOD_B, "packaging_strength": 10}, cfg_sat=SAT)
        self.assertGreater(strong["score"] - weak["score"], 10)

    def test_demand_is_the_heaviest_input(self):
        self.assertEqual(max(s.B_WEIGHTS, key=s.B_WEIGHTS.get), "real_demand")


class TestEvidenceDiscipline(unittest.TestCase):
    """Missing evidence is an error, not a default."""

    def test_missing_field_raises(self):
        broken = {k: v for k, v in GOOD_A.items() if k != "channels_published_7d"}
        with self.assertRaises(ValueError) as ctx:
            s.evaluate(broken, cfg_sat=SAT)
        self.assertIn("channels_published_7d", str(ctx.exception))

    def test_missing_demand_field_raises(self):
        broken = {k: v for k, v in GOOD_B.items() if k != "best_overperformance_ratio"}
        with self.assertRaises(ValueError):
            s.evaluate(broken, cfg_sat=SAT)

    def test_bad_enum_raises(self):
        with self.assertRaises(ValueError):
            s.evaluate({**GOOD_A, "viewer_access": "probably fine"}, cfg_sat=SAT)

    def test_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            s.evaluate({**GOOD_A, "mode": "C"}, cfg_sat=SAT)

    def test_packaging_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            s.evaluate({**GOOD_B, "packaging_strength": 25}, cfg_sat=SAT)


class TestPredictedViews(unittest.TestCase):
    def test_views_scale_with_median(self):
        r = s.evaluate(GOOD_B, median_views=10000, cfg_sat=SAT)
        self.assertEqual(r["predicted_views_low"], int(round(r["multiple_low"] * 10000)))
        self.assertEqual(r["predicted_views_high"], int(round(r["multiple_high"] * 10000)))
        self.assertLess(r["predicted_views_low"], r["predicted_views_high"])

    def test_no_median_means_no_view_prediction(self):
        r = s.evaluate(GOOD_B, cfg_sat=SAT)
        self.assertNotIn("predicted_views_low", r)


class TestNotARubberStamp(unittest.TestCase):
    """Brief §6: if it never says DON'T FILM, the tool is broken — not lucky."""

    def test_realistic_mediocre_idea_is_not_green(self):
        mediocre = {
            **GOOD_B,
            "best_overperformance_ratio": 1.2,
            "videos_90d_over_20k": 14,
            "packaging_strength": 4,
            "hours_needed": 20,
            "decay": "weeks",
            "audience_fit": "adjacent",
        }
        r = s.evaluate(mediocre, cfg_sat=SAT)
        self.assertLess(r["score"], 55, "a weak idea must not reach SAFE FILLER or above")

    def test_every_gate_can_produce_dont_film(self):
        killers = [
            {**GOOD_A, "channels_published_7d": 5},
            {**GOOD_A, "viewer_access": "waitlist"},
            {**GOOD_A, "viewer_access": "enterprise"},
            {**GOOD_B, "best_overperformance_ratio": 0.5},
            {**GOOD_B, "big_channel_covered_30d": True},
        ]
        for evidence in killers:
            self.assertEqual(
                s.evaluate(evidence, cfg_sat=SAT)["verdict"], "DON'T FILM", evidence.get("topic")
            )

    def test_score_never_leaves_bounds(self):
        extremes = [
            {**GOOD_A, "launch_size": "niche", "viewer_access": "enterprise", "demoable": "no",
             "channels_published_7d": 99, "hours_needed": 500, "hours_window_left": 1},
            {**GOOD_B, "best_overperformance_ratio": 50, "videos_90d_over_20k": 0,
             "packaging_strength": 10, "hours_needed": 1},
        ]
        for evidence in extremes:
            score = s.evaluate(evidence, cfg_sat=SAT)["score"]
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
