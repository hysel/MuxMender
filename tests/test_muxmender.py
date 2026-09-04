import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from muxmender import (
    HardwareRequirementError,
    MediaInfo,
    build_ffmpeg_command,
    choose_target_codec,
    delete_original_allowed,
    output_path,
    output_dimensions,
    progress_percent,
    recommend,
    run_json,
    select_encoder,
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
    def test_progress_percent_from_ffmpeg_output(self):
        self.assertEqual(progress_percent("out_time_us=30000000", 120), 25.0)
        self.assertEqual(progress_percent("out_time_ms=120000000", 120), 100.0)
        self.assertIsNone(progress_percent("progress=continue", 120))

    @patch("muxmender.subprocess.run")
    def test_ffprobe_json_is_decoded_as_utf8(self, mock_run):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout='{"title":"Amélie"}', stderr="")
        self.assertEqual(run_json(["ffprobe"])["title"], "Amélie")
        self.assertEqual(mock_run.call_args.kwargs["encoding"], "utf-8")

    def test_auto_prefers_compatible_hevc(self):
        self.assertEqual(choose_target_codec("auto"), "hevc")

    def test_auto_prefers_detected_gpu_encoder(self):
        selection = select_encoder("hevc", "auto", {"hevc_amf", "libx265"}, ["amd"])
        self.assertEqual(selection.vendor, "amd")
        self.assertEqual(selection.encoder, "hevc_amf")

    def test_each_gpu_vendor_uses_its_ffmpeg_encoder(self):
        for vendor, encoder in (
            ("amd", "hevc_amf"),
            ("nvidia", "hevc_nvenc"),
            ("intel", "hevc_qsv"),
        ):
            with self.subTest(vendor=vendor):
                selection = select_encoder("hevc", "auto", {encoder, "libx265"}, [vendor])
                self.assertEqual(selection.vendor, vendor)
                self.assertEqual(selection.encoder, encoder)

    def test_auto_uses_cpu_when_no_gpu_is_detected(self):
        selection = select_encoder("hevc", "auto", {"libx265"}, [])
        self.assertEqual(selection.vendor, "cpu")

    def test_missing_gpu_encoder_offers_requirement(self):
        with self.assertRaises(HardwareRequirementError):
            select_encoder("av1", "auto", {"libsvtav1"}, ["nvidia"])

    def test_h264_is_recommended_for_transcode(self):
        result = recommend(sample(), "hevc")
        self.assertEqual(result.recommendation, "transcode")

    def test_keep_resolution_returns_exact_source_dimensions(self):
        self.assertEqual(output_dimensions(sample(), "keep"), (3840, 2160))

    def test_resolution_ceiling_downscales_without_changing_aspect_ratio(self):
        self.assertEqual(output_dimensions(sample(), "1080p"), (1920, 1080))
        cinema = sample(width=3840, height=1600)
        self.assertEqual(output_dimensions(cinema, "1080p"), (1920, 800))

    def test_resolution_ceiling_never_upscales(self):
        small = sample(width=1280, height=720)
        self.assertEqual(output_dimensions(small, "2160p"), (1280, 720))

    def test_explicit_downscale_reencodes_efficient_video(self):
        result = recommend(sample(video_codec="hevc"), "hevc", "1080p")
        self.assertEqual(result.recommendation, "transcode")
        self.assertIn("user requested 1080p", result.reason)

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
        self.assertNotIn("-vf", command)

    def test_scaling_filter_requires_explicit_resolution_option(self):
        command = build_ffmpeg_command(
            Path("movie.mkv"), Path(".movie.partial.mkv"), sample(),
            "hevc", "balanced", resolution="1080p",
        )
        self.assertEqual(command[command.index("-vf") + 1], "scale=1920:1080:flags=lanczos")

    def test_amd_command_uses_amf_quality_options(self):
        command = build_ffmpeg_command(
            Path("movie.mkv"), Path(".movie.partial.mkv"), sample(bit_depth=8, hdr=False),
            "hevc", "balanced", encoder="hevc_amf",
        )
        self.assertIn("hevc_amf", command)
        self.assertEqual(command[command.index("-usage") + 1], "transcoding")
        self.assertEqual(command[command.index("-rc") + 1], "cqp")

    def test_nvidia_and_intel_commands_use_vendor_rate_control(self):
        nvidia = build_ffmpeg_command(
            Path("movie.mkv"), Path(".movie.partial.mkv"), sample(),
            "hevc", "balanced", encoder="hevc_nvenc",
        )
        intel = build_ffmpeg_command(
            Path("movie.mkv"), Path(".movie.partial.mkv"), sample(),
            "hevc", "balanced", encoder="hevc_qsv",
        )
        self.assertEqual(nvidia[nvidia.index("-cq") + 1], "21")
        self.assertEqual(intel[intel.index("-global_quality") + 1], "21")

    def test_original_deletion_needs_exact_confirmation(self):
        args = SimpleNamespace(delete_originals=True, confirm_delete="no")
        with self.assertRaises(ValueError):
            delete_original_allowed(args)
        args.confirm_delete = "DELETE_ORIGINALS"
        self.assertTrue(delete_original_allowed(args))


if __name__ == "__main__":
    unittest.main()
