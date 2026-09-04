import unittest
from pathlib import Path
from types import SimpleNamespace

from muxmender import (
    MediaInfo,
    build_ffmpeg_command,
    choose_target_codec,
    delete_original_allowed,
    output_path,
    recommend,
)


def sample(**overrides):
    values = dict(
        path="movie.mkv", size_bytes=10_000, duration_seconds=120.0,
        container="matroska", video_codec="h264", width=3840, height=2160,
        pixel_format="yuv420p10le", bit_depth=10, color_primaries="bt2020",
        color_transfer="smpte2084", color_space="bt2020nc", color_range="tv",
        hdr=True, dolby_vision=False, audio_codecs=["truehd", "ac3"],
        subtitle_codecs=["subrip"],
    )
    values.update(overrides)
    return MediaInfo(**values)


class MuxMenderTests(unittest.TestCase):
    def test_auto_prefers_compatible_hevc(self):
        self.assertEqual(choose_target_codec("auto"), "hevc")

    def test_h264_is_recommended_for_transcode(self):
        result = recommend(sample(), "hevc")
        self.assertEqual(result.recommendation, "transcode")

    def test_efficient_codec_is_not_reencoded(self):
        result = recommend(sample(video_codec="av1"), "hevc")
        self.assertEqual(result.recommendation, "keep")

    def test_efficient_mp4_is_remuxed_without_reencoding(self):
        result = recommend(sample(video_codec="hevc", container="mov,mp4,m4a,3gp,3g2,mj2"), "hevc")
        self.assertEqual(result.recommendation, "remux")

    def test_dolby_vision_is_skipped(self):
        result = recommend(sample(dolby_vision=True), "hevc")
        self.assertEqual(result.recommendation, "skip")

    def test_output_is_sidecar_by_default(self):
        result = output_path(Path("C:/media/movie.mp4"), Path("C:/media"), None)
        self.assertEqual(result.name, "movie.mp4.muxmender.mkv")

    def test_command_maps_every_stream_and_copies_audio(self):
        command = build_ffmpeg_command(
            Path("movie.mkv"), Path(".movie.partial.mkv"), sample(), "hevc", "balanced"
        )
        self.assertIn("libx265", command)
        self.assertIn("yuv420p10le", command)
        self.assertEqual(command[command.index("-c:a") + 1], "copy")
        self.assertEqual(command[command.index("-map") + 1], "0")

    def test_original_deletion_needs_exact_confirmation(self):
        args = SimpleNamespace(delete_originals=True, confirm_delete="no")
        with self.assertRaises(ValueError):
            delete_original_allowed(args)
        args.confirm_delete = "DELETE_ORIGINALS"
        self.assertTrue(delete_original_allowed(args))


if __name__ == "__main__":
    unittest.main()
