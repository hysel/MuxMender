import unittest
from test_muxmender import sample
from muxmender import assess_dolby_preservation, recommend


class PreservationTests(unittest.TestCase):
    def dv(self, **overrides):
        values = dict(dolby_vision=True, video_codec="hevc",
                      dolby_vision_profile=8, dolby_vision_compatibility_id=1,
                      dolby_vision_rpu_present=True)
        values.update(overrides)
        return sample(**values)

    def test_non_dv(self):
        self.assertIsNone(assess_dolby_preservation(sample()))

    def test_candidate_is_not_permission_to_encode(self):
        info = recommend(self.dv(), "hevc")
        self.assertEqual(info.recommendation, "skip")
        self.assertEqual(info.dolby_preservation["route"], "profile8.1-research-candidate")
        self.assertFalse(info.dolby_preservation["reencode_supported"])

    def test_profile5(self):
        plan = assess_dolby_preservation(self.dv(dolby_vision_profile=5))
        self.assertEqual(plan["route"], "profile5-color-pipeline-required")

    def test_enhancement_layer(self):
        for values in ({"dolby_vision_profile": 7}, {"dolby_vision_el_present": True}):
            with self.subTest(values=values):
                self.assertEqual(assess_dolby_preservation(self.dv(**values))["route"],
                                 "preserve-enhancement-layer")

    def test_missing_rpu(self):
        self.assertEqual(assess_dolby_preservation(self.dv(dolby_vision_rpu_present=False))["route"],
                         "inspect-missing-rpu")

    def test_incompatible_configurations_are_not_candidates(self):
        for values in ({"dolby_vision_profile": None}, {"dolby_vision_profile": 20},
                       {"dolby_vision_compatibility_id": 4}, {"bit_depth": 8},
                       {"video_codec": "av1"}, {"color_transfer": "arib-std-b67"},
                       {"color_primaries": "bt709"}):
            with self.subTest(values=values):
                self.assertEqual(assess_dolby_preservation(self.dv(**values))["route"],
                                 "inspect-unsupported-profile")

    def test_copy_stays_unchanged(self):
        self.assertEqual(recommend(self.dv(), "hevc", dolby_vision_policy="copy").recommendation, "keep")

    def test_resize_stays_blocked(self):
        self.assertEqual(recommend(self.dv(), "hevc", resolution="1080p").recommendation, "skip")
