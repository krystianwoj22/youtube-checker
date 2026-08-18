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
    "own_recent_video_days": 60,
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
    "big_channel_overperformed_30d": False,
    "best_overperformance_ratio": 2.5,
    "overperformance_sample_size": 10,
    "own_topic_videos": 1,
    "own_best_topic_ratio": 1.6,
    "own_recent_topic_video_days": None,
    "hours_needed": 6,
    "access_blockers": "none",
    "packaging_strength": 8,
    "topic_momentum": "steady",
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

    def test_sigma_band_scales_with_channel_volatility(self):
        """A consistent channel earns a tighter band than a spiky one."""
        tight = s.multiple_band_sigma(70, 0.4)
        wide = s.multiple_band_sigma(70, 1.1)
        self.assertGreater(tight[0], wide[0])
        self.assertLess(tight[1], wide[1])
        center = s.score_to_multiple(70)
        for lo, hi in (tight, wide):
            self.assertLess(lo, center)
            self.assertGreater(hi, center)

    def test_sigma_from_stats(self):
        self.assertIsNone(s.sigma_from_stats({"p25_views": 0, "p75_views": 100}))
        sigma = s.sigma_from_stats({"p25_views": 1000, "p75_views": 3000})
        self.assertGreater(sigma, 0.5)
        self.assertLessEqual(sigma, s.SIGMA_MAX)

    def test_evaluate_uses_channel_stats_for_band(self):
        stats = {"median_views": 10000, "p25_views": 6000, "p75_views": 16000}
        r = s.evaluate(GOOD_B, cfg_sat=SAT, median_stats=stats)
        self.assertIn("channel's own spread", r["band_source"])
        self.assertEqual(r["median_views"], 10000)


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

    def test_weak_ungated_launch_is_not_automatically_green(self):
        """The first build's ungated Mode A floor was 62 — the continuous scale
        carried no information. A niche, non-demoable, contested launch must be
        able to land below SAFE FILLER without any gate firing."""
        weak = {
            **GOOD_A,
            "launch_size": "niche",
            "viewer_access": "public_paid",
            "demoable": "no",
            "channels_published_7d": 2,
            "hours_needed": 8,
            "hours_window_left": 10,
        }
        r = s.evaluate(weak, cfg_sat=SAT)
        self.assertFalse(r["gated"])
        self.assertLess(r["score"], 55)


class TestModeBGates(unittest.TestCase):
    def test_proven_topic_scores_film(self):
        r = s.evaluate(GOOD_B, cfg_sat=SAT)
        self.assertGreaterEqual(r["score"], 70)
        self.assertFalse(r["gated"])

    def test_dead_topic_gate(self):
        """Brief §4.2: no overperformance means no demand, not an opening."""
        r = s.evaluate(
            {**GOOD_B, "best_overperformance_ratio": 0.7, "own_topic_videos": 0,
             "own_best_topic_ratio": None},
            cfg_sat=SAT,
        )
        self.assertEqual(r["verdict"], "DON'T FILM")
        self.assertIn("DEAD TOPIC", r["gates_applied"][0]["reason"])

    def test_dead_topic_beats_every_other_strength(self):
        """Even a perfect idea dies if nothing has ever over-performed."""
        perfect_but_dead = {
            **GOOD_B,
            "best_overperformance_ratio": 0.4,
            "own_topic_videos": 0,
            "own_best_topic_ratio": None,
            "packaging_strength": 10,
            "hours_needed": 2,
            "videos_90d_over_20k": 1,
        }
        r = s.evaluate(perfect_but_dead, cfg_sat=SAT)
        self.assertEqual(r["verdict"], "DON'T FILM")

    def test_own_overperformance_overrides_dead_topic_gate(self):
        """Your own audience already proving demand outranks competitor data —
        their audience is not yours."""
        r = s.evaluate(
            {**GOOD_B, "best_overperformance_ratio": 0.7,
             "own_topic_videos": 2, "own_best_topic_ratio": 1.8},
            cfg_sat=SAT,
        )
        self.assertFalse(any("DEAD TOPIC" in g["reason"] for g in r["gates_applied"]))
        self.assertNotEqual(r["verdict"], "DON'T FILM")

    def test_big_channel_win_gate(self):
        r = s.evaluate({**GOOD_B, "big_channel_overperformed_30d": True,
                        "big_channel_covered_30d": True}, cfg_sat=SAT)
        self.assertEqual(r["verdict"], "DON'T FILM")
        self.assertIn("algorithm fight", r["gates_applied"][0]["reason"])

    def test_big_channel_flop_does_not_close_the_topic(self):
        """A 100K+ channel covering the topic only closes it if their video
        actually beat their own median. A big-channel flop is contested ground."""
        r = s.evaluate({**GOOD_B, "big_channel_covered_30d": True,
                        "big_channel_overperformed_30d": False}, cfg_sat=SAT)
        self.assertFalse(r["gated"])
        self.assertIn("UNDERPERFORMED", r["detail"]["saturation"])

    def test_legacy_covered_field_still_gates(self):
        """Old evidence without the overperformed field stays conservative."""
        legacy = {k: v for k, v in GOOD_B.items() if k != "big_channel_overperformed_30d"}
        r = s.evaluate({**legacy, "big_channel_covered_30d": True}, cfg_sat=SAT)
        self.assertEqual(r["verdict"], "DON'T FILM")

    def test_cannibalisation_gate(self):
        r = s.evaluate({**GOOD_B, "own_recent_topic_video_days": 20}, cfg_sat=SAT)
        self.assertTrue(r["gated"])
        self.assertLessEqual(r["score"], 45)
        self.assertIn("CANNIBALISATION", r["gates_applied"][0]["reason"])

    def test_old_own_video_does_not_cannibalise(self):
        r = s.evaluate({**GOOD_B, "own_recent_topic_video_days": 200}, cfg_sat=SAT)
        self.assertFalse(any("CANNIBALISATION" in g["reason"] for g in r["gates_applied"]))

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
        self.assertGreater(strong["score"] - weak["score"], 8)

    def test_own_history_is_the_heaviest_input(self):
        """The only signal about YOUR audience must outweigh signals about
        someone else's."""
        self.assertEqual(max(s.B_WEIGHTS, key=s.B_WEIGHTS.get), "own_history")

    def test_own_history_moves_the_score_materially(self):
        flopped = s.evaluate({**GOOD_B, "own_best_topic_ratio": 0.4}, cfg_sat=SAT)
        smashed = s.evaluate({**GOOD_B, "own_best_topic_ratio": 3.5}, cfg_sat=SAT)
        self.assertGreater(smashed["score"] - flopped["score"], 12)

    def test_no_own_history_is_neutral_not_negative(self):
        untried = s.evaluate({**GOOD_B, "own_topic_videos": 0, "own_best_topic_ratio": None},
                             cfg_sat=SAT)
        flopped = s.evaluate({**GOOD_B, "own_topic_videos": 2, "own_best_topic_ratio": 0.4},
                             cfg_sat=SAT)
        self.assertGreater(untried["score"], flopped["score"])

    def test_null_own_history_means_unchecked_not_zero(self):
        r = s.evaluate({**GOOD_B, "own_topic_videos": None, "own_best_topic_ratio": None},
                       cfg_sat=SAT)
        self.assertIn("UNCHECKED", r["detail"]["own_history"])

    def test_momentum_moves_the_score(self):
        fading = s.evaluate({**GOOD_B, "topic_momentum": "fading"}, cfg_sat=SAT)
        accel = s.evaluate({**GOOD_B, "topic_momentum": "accelerating"}, cfg_sat=SAT)
        self.assertGreater(accel["score"], fading["score"])

    def test_legacy_decay_maps_to_momentum(self):
        legacy = {k: v for k, v in GOOD_B.items() if k != "topic_momentum"}
        r = s.evaluate({**legacy, "decay": "dead_soon"}, cfg_sat=SAT)
        self.assertLess(r["subscores"]["momentum"], 50)

    def test_stale_overperformance_is_capped(self):
        fresh = s.evaluate({**GOOD_B, "best_overperformance_age_days": 10}, cfg_sat=SAT)
        stale = s.evaluate({**GOOD_B, "best_overperformance_age_days": 85}, cfg_sat=SAT)
        self.assertLess(stale["subscores"]["real_demand"], fresh["subscores"]["real_demand"])
        self.assertIn("STALE", stale["detail"]["real_demand"])

    def test_packaging_checks_replace_the_gut_number(self):
        checks_all = {**GOOD_B, "packaging_checks": {
            "differentiated_angle": True, "thumbnail_stands_out": True,
            "verifiable_promise": True, "curiosity_gap": True, "title_specific": True}}
        checks_none = {**GOOD_B, "packaging_checks": {
            "differentiated_angle": False, "thumbnail_stands_out": False,
            "verifiable_promise": False, "curiosity_gap": False, "title_specific": False}}
        hi = s.evaluate(checks_all, cfg_sat=SAT)
        lo = s.evaluate(checks_none, cfg_sat=SAT)
        self.assertEqual(hi["subscores"]["packaging"], 95.0)
        self.assertEqual(lo["subscores"]["packaging"], 20.0)

    def test_packaging_checks_require_at_least_three(self):
        with self.assertRaises(ValueError):
            s.evaluate({**GOOD_B, "packaging_checks": {"curiosity_gap": True}}, cfg_sat=SAT)

    def test_packaging_checks_reject_unknown_keys(self):
        with self.assertRaises(ValueError):
            s.evaluate({**GOOD_B, "packaging_checks": {
                "curiosity_gap": True, "title_specific": True, "vibes": True}}, cfg_sat=SAT)


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

    def test_missing_own_history_raises(self):
        broken = {k: v for k, v in GOOD_B.items() if k != "own_topic_videos"}
        with self.assertRaises(ValueError) as ctx:
            s.evaluate(broken, cfg_sat=SAT)
        self.assertIn("own_topic_videos", str(ctx.exception))

    def test_missing_momentum_and_decay_raises(self):
        broken = {k: v for k, v in GOOD_B.items() if k != "topic_momentum"}
        with self.assertRaises(ValueError):
            s.evaluate(broken, cfg_sat=SAT)

    def test_missing_big_channel_fields_raises(self):
        broken = {k: v for k, v in GOOD_B.items()
                  if k not in ("big_channel_covered_30d", "big_channel_overperformed_30d")}
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
            "own_topic_videos": 2,
            "own_best_topic_ratio": 0.9,
            "packaging_strength": 4,
            "hours_needed": 20,
            "topic_momentum": "fading",
            "audience_fit": "adjacent",
        }
        r = s.evaluate(mediocre, cfg_sat=SAT)
        self.assertLess(r["score"], 55, "a weak idea must not reach SAFE FILLER or above")

    def test_average_everything_is_not_a_promise_of_success(self):
        """The first build scored an exactly-average-looking idea at 74 (FILM,
        'likely 1.5-3x median'). Average inputs must not predict above-median
        outcomes."""
        average = {
            **GOOD_B,
            "best_overperformance_ratio": 1.8,
            "videos_90d_over_20k": 3,
            "own_topic_videos": 0,
            "own_best_topic_ratio": None,
            "packaging_strength": 6,
            "hours_needed": 8,
            "topic_momentum": "steady",
        }
        r = s.evaluate(average, cfg_sat=SAT)
        self.assertLess(r["score"], 70, "average evidence must not reach FILM")

    def test_every_gate_can_produce_dont_film(self):
        killers = [
            {**GOOD_A, "channels_published_7d": 5},
            {**GOOD_A, "viewer_access": "waitlist"},
            {**GOOD_A, "viewer_access": "enterprise"},
            {**GOOD_B, "best_overperformance_ratio": 0.5, "own_topic_videos": 0,
             "own_best_topic_ratio": None},
            {**GOOD_B, "big_channel_overperformed_30d": True},
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
             "own_best_topic_ratio": 20, "packaging_strength": 10, "hours_needed": 1},
        ]
        for evidence in extremes:
            score = s.evaluate(evidence, cfg_sat=SAT)["score"]
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
