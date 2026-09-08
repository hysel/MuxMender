import unittest
import tempfile
import json
import muxmender as mm
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class ExistingRenameTests(unittest.TestCase):
    def test_release_tail_preserved_and_second_preview_unchanged(self):
        for original, title, tail in [
            ('X2.2003.BluRay.720p.x264.DTS-WiKi.mkv', 'X2 (2003)', 'BluRay.720p.x264.DTS-WiKi'),
            ('X-Men Apocalypse 2016 UHD BluRay HDR10 2160p Dts-HDMa7.1 HEVC-d3g.mkv', 'X-Men Apocalypse (2016)', 'UHD BluRay HDR10 2160p Dts-HDMa7.1 HEVC-d3g'),
            ('Film.2001.CustomRelease-GROUP.mp4', 'Film (2001)', 'CustomRelease-GROUP'),
            ('Show.S01E02.1080p.WEB-DL-GROUP.mkv', 'Show - S01E02', '1080p.WEB-DL-GROUP'),
        ]:
            with self.subTest(original=original), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp)/original; source.write_bytes(b'dummy')
                entry = mm.create_rename_plan(source, title)['entries'][0]
                expected = title + ' - ' + tail + source.suffix
                self.assertEqual(Path(entry['destination']).name, expected)
                self.assertEqual(entry['release_suffix'], tail)
                source.rename(Path(tmp)/expected)
                self.assertEqual(mm.create_rename_plan(Path(tmp)/expected, title)['entries'][0]['status'], 'unchanged')

    def test_folder_identity_preview_and_explicit_apply_preserve_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'War Horse (2011)'; folder.mkdir()
            video = folder/'s7-war.horse.1080.mkv'; video.write_bytes(b'local dummy video')
            subtitle = folder/'s7-war.horse.1080.en.srt'; subtitle.write_text('caption', encoding='utf-8')
            original = mm.rename_identity(video)
            plan_path = Path(tmp)/'plan.json'
            self.assertEqual(mm.main([str(video), '--rename-plan', str(plan_path), '--rename-sidecars']), 0)
            self.assertTrue(video.exists()); self.assertTrue(subtitle.exists())
            plan = json.loads(plan_path.read_text(encoding='utf-8'))
            self.assertEqual(Path(plan['entries'][0]['destination']).name, 'War Horse (2011) - s7-war.horse.1080.mkv')
            self.assertEqual(mm.main(['--apply-rename-plan', str(plan_path), '--execute']), 2)
            self.assertTrue(video.exists())
            self.assertEqual(mm.main(['--apply-rename-plan', str(plan_path), '--execute', '--confirm-rename', 'RENAME']), 0)
            output = folder/'War Horse (2011) - s7-war.horse.1080.mkv'
            self.assertEqual(output.read_bytes(), b'local dummy video')
            self.assertEqual(mm.rename_identity(output), original)
            self.assertEqual((folder/'War Horse (2011) - s7-war.horse.1080.en.srt').read_text(encoding='utf-8'), 'caption')
            self.assertFalse(video.exists())

    def test_stale_source_blocks_entire_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'Contact 1997'; folder.mkdir()
            source = folder/'hdc-contact-1080.mp4'; source.write_bytes(b'dummy')
            plan = mm.create_rename_plan(source)
            self.assertTrue(plan['entries'][0]['destination'].endswith('.mp4'))
            path = Path(tmp)/'plan.json'; path.write_text(json.dumps(plan), encoding='utf-8')
            source.write_bytes(b'changed dummy')
            with self.assertRaisesRegex(ValueError, 'changed'):
                mm.apply_rename_plan(path)
            self.assertTrue(source.exists())

    def test_unknown_identity_and_conflicting_year_need_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'Unsorted'; folder.mkdir()
            source = folder/'melite-myrp-1080p.mkv'; source.write_bytes(b'dummy')
            self.assertEqual(mm.create_rename_plan(source)['entries'][0]['status'], 'needs-review')
            self.assertEqual(Path(mm.create_rename_plan(source, 'Minority Report (2002)')['entries'][0]['destination']).name, 'Minority Report (2002) - melite-myrp-1080p.mkv')
            folder2 = Path(tmp)/'Movie (2011)'; folder2.mkdir()
            conflict = folder2/'Movie.2002.1080p.mkv'; conflict.write_bytes(b'dummy')
            self.assertEqual(mm.create_rename_plan(conflict)['entries'][0]['status'], 'needs-review')

    def test_collision_blocks_video_and_companion(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder/'old.mkv'; source.write_bytes(b'original')
            (folder/'old.jpg').write_bytes(b'art')
            existing = folder/'New (2001).mkv'; existing.write_bytes(b'existing')
            plan = mm.create_rename_plan(source, 'New (2001)', True)
            self.assertTrue(all(e['status']=='blocked' for e in plan['entries']))
            self.assertEqual(existing.read_bytes(), b'existing')

    def test_edited_plan_cannot_move_file_outside_its_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'Movie (2001)'; folder.mkdir()
            source = folder/'old.mkv'; source.write_bytes(b'original')
            plan = mm.create_rename_plan(source)
            plan['entries'][0]['destination'] = str(Path(tmp)/'outside.mkv')
            p = Path(tmp)/'plan.json'; p.write_text(json.dumps(plan), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'same directory'):
                mm.apply_rename_plan(p)
            self.assertTrue(source.exists())

from muxmender import (
    HardwareRequirementError,
    MediaInfo,
    build_ffmpeg_command,
    build_dolby_sdr_preview_command,
    choose_target_codec,
    delete_original_allowed,
    dolby_sdr_preview_path,
    dolby_vision_gpu_preflight,
    output_path,
    copy_matching_artwork,
    output_dimensions,
    progress_percent,
    probe,
    recommend,
    run_json,
    parse_args,
    run_native_dolby_preview,
    select_encoder,
    verify_output,
    verify_dolby_sdr_preview,
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
    @patch("muxmender.subprocess.run")
    @patch("muxmender.Path.mkdir")
    @patch("muxmender.Path.exists", return_value=False)
    @patch("muxmender.Path.is_file", return_value=True)
    def test_native_dry_run_never_makes_directory_or_preflights(self, _file, _exists, mkdir, run):
        run.return_value = SimpleNamespace(returncode=0)
        args = parse_args(["movie.mkv", "--dolby-vision-policy", "sdr-preview"])
        self.assertEqual(run_native_dolby_preview(args, Path("movie.mkv")), 0)
        mkdir.assert_not_called()
        run.assert_called_once()
        self.assertIn("--dry-run", run.call_args.args[0])

    @patch("muxmender.subprocess.run")
    @patch("muxmender.Path.exists", return_value=True)
    @patch("muxmender.Path.is_file", return_value=True)
    def test_native_existing_output_never_launches_process(self, _file, _exists, run):
        args = parse_args(["movie.mkv", "--dolby-vision-policy", "sdr-preview", "--execute"])
        self.assertEqual(run_native_dolby_preview(args, Path("movie.mkv")), 2)
        run.assert_not_called()

    def test_native_diagnostic_is_opt_in(self):
        args = parse_args(["movie.mkv"])
        self.assertEqual(args.dolby_preview_backend, "vulkan")
        self.assertFalse(args.execute)

    @patch("muxmender.Path.is_file", return_value=True)
    def test_native_diagnostic_forbids_delete_overwrite_resize(self, _):
        for flags in (["--delete-originals"], ["--overwrite-output"], ["--resolution", "1080p"]):
            args = parse_args(["movie.mkv", "--dolby-vision-policy", "sdr-preview", *flags])
            self.assertEqual(run_native_dolby_preview(args, Path("movie.mkv")), 2)

    @patch("muxmender.Path.is_file", return_value=True)
    def test_native_diagnostic_bounds_duration(self, _):
        for value in ("0", "11", "nan", "inf"):
            args = parse_args(["movie.mkv", "--dolby-vision-policy", "sdr-preview", "--preview-seconds", value])
            self.assertEqual(run_native_dolby_preview(args, Path("movie.mkv")), 2)

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

    def test_explicit_efficient_reencode_keeps_dolby_gate(self):
        self.assertEqual(recommend(sample(video_codec='hevc'), 'hevc').recommendation, 'keep')
        self.assertEqual(recommend(sample(video_codec='hevc'), 'hevc', reencode_efficient=True).recommendation, 'transcode')
        self.assertEqual(recommend(sample(video_codec='hevc', dolby_vision=True), 'hevc', reencode_efficient=True).recommendation, 'skip')
        self.assertEqual(recommend(sample(video_codec='hevc', dolby_vision=True), 'hevc', dolby_vision_policy='copy', reencode_efficient=True).recommendation, 'keep')

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

    def test_dolby_vision_copy_policy_never_reencodes(self):
        mp4 = sample(
            dolby_vision=True,
            dolby_vision_profile=5,
            container="mov,mp4,m4a,3gp,3g2,mj2",
        )
        result = recommend(mp4, "hevc", dolby_vision_policy="copy")
        self.assertEqual(result.recommendation, "remux")
        command = build_ffmpeg_command(
            Path("movie.mp4"), Path(".movie.partial.mkv"), result, "hevc", "balanced"
        )
        self.assertEqual(command[command.index("-c") + 1], "copy")
        self.assertNotIn("libx265", command)

    def test_dolby_vision_copy_policy_refuses_resize(self):
        result = recommend(
            sample(dolby_vision=True, dolby_vision_profile=5),
            "hevc",
            resolution="1080p",
            dolby_vision_policy="copy",
        )
        self.assertEqual(result.recommendation, "skip")

    def test_dolby_sdr_preview_is_explicit_and_full_resolution(self):
        info = recommend(
            sample(dolby_vision=True, dolby_vision_profile=5),
            "hevc",
            dolby_vision_policy="sdr-preview",
        )
        self.assertEqual(info.recommendation, "preview")
        command = build_dolby_sdr_preview_command(
            Path("movie.mkv"), Path(".preview.partial.mkv"), 300, 10
        )
        self.assertIn("apply_dolbyvision=1", command[command.index("-vf") + 1])
        self.assertNotIn("scale=", command[command.index("-vf") + 1])
        self.assertEqual(command[command.index("-ss") + 1], "300")
        self.assertEqual(command[command.index("-t") + 1], "10")
        self.assertIn("-n", command)

    def test_dolby_preview_path_is_separate_sidecar(self):
        result = dolby_sdr_preview_path(Path("movie.muxmender.mkv"), 10)
        self.assertEqual(result.name, "movie.muxmender.dolby-sdr-preview-10s.mkv")

    @patch("muxmender.ffmpeg_filter_names", return_value={"scale"})
    def test_dolby_preflight_fails_before_running_without_libplacebo(self, _mock_filters):
        with patch("muxmender.subprocess.run") as mock_run:
            ok, message = dolby_vision_gpu_preflight("ffmpeg")
        self.assertFalse(ok)
        self.assertIn("libplacebo", message)
        mock_run.assert_not_called()

    @patch("muxmender.ffmpeg_filter_names", return_value={"libplacebo"})
    @patch("muxmender.subprocess.run")
    def test_dolby_preflight_reports_actionable_vulkan_error(self, mock_run, _mock_filters):
        mock_run.return_value = SimpleNamespace(
            returncode=1,
            stderr=(
                "[Vulkan] Failed to allocate memory: VK_ERROR_UNKNOWN\n"
                "Nothing was written into output file"
            ),
        )
        ok, message = dolby_vision_gpu_preflight("ffmpeg")
        self.assertFalse(ok)
        self.assertIn("VK_ERROR_UNKNOWN", message)

    @patch("muxmender.run_json")
    def test_probe_reads_dolby_vision_configuration(self, mock_json):
        mock_json.return_value = {
            "format": {"format_name": "matroska", "duration": "10"},
            "streams": [{
                "codec_type": "video", "codec_name": "hevc", "width": 3840,
                "height": 2160, "pix_fmt": "yuv420p10le", "color_transfer": "smpte2084",
                "side_data_list": [{
                    "side_data_type": "DOVI configuration record",
                    "dv_profile": 5, "dv_bl_signal_compatibility_id": 0,
                    "rpu_present_flag": 1, "el_present_flag": 0,
                }],
            }],
        }
        with patch.object(Path, "stat", return_value=SimpleNamespace(st_size=123)):
            info = probe(Path("movie.mkv"))
        self.assertTrue(info.dolby_vision)
        self.assertEqual(info.dolby_vision_profile, 5)
        self.assertEqual(info.dolby_vision_compatibility_id, 0)
        self.assertTrue(info.dolby_vision_rpu_present)

    @patch("muxmender.probe")
    def test_verification_rejects_lost_dolby_vision_rpu(self, mock_probe):
        source = sample(
            dolby_vision=True, dolby_vision_profile=5,
            dolby_vision_compatibility_id=0, dolby_vision_rpu_present=True,
        )
        mock_probe.return_value = sample(
            size_bytes=9_000, dolby_vision=True, dolby_vision_profile=5,
            dolby_vision_compatibility_id=0, dolby_vision_rpu_present=False,
        )
        valid, message = verify_output(
            source, Path("output.mkv"), "ffprobe", 5, "h264",
            enforce_min_savings=False,
        )
        self.assertFalse(valid)
        self.assertIn("RPU", message)

    def test_output_is_sidecar_by_default(self):
        result = output_path(Path("C:/media/movie.mp4"), Path("C:/media"), None)
        self.assertEqual(result.name, "movie.mkv")
        self.assertEqual(result.parent.name, "MuxMender")

    def test_artwork_matches_clean_name_and_preserves_sources_and_collisions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'Commando 1985 1080p.mkv'
            artwork = source.with_suffix('.jpg')
            artwork.write_bytes(b'original artwork')
            (root/'unrelated.jpg').write_bytes(b'unrelated')
            output = root/'output'/'Commando (1985).mkv'
            output.parent.mkdir()
            result = copy_matching_artwork(source, output)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['status'], 'copied')
            self.assertEqual(output.with_suffix('.jpg').read_bytes(), artwork.read_bytes())
            output.with_suffix('.jpg').write_bytes(b'user artwork')
            result = copy_matching_artwork(source, output)
            self.assertEqual(result[0]['status'], 'existing-preserved')
            self.assertEqual(output.with_suffix('.jpg').read_bytes(), b'user artwork')
            self.assertEqual(artwork.read_bytes(), b'original artwork')

    def test_video_only_mode_does_not_copy_sidecars_or_visit_subfolders(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'Movie.mkv'
            source.with_suffix('.jpg').write_bytes(b'art')
            source.with_suffix('.srt').write_text('subtitles')
            (root/'Subs').mkdir()
            (root/'Subs'/'English.srt').write_text('subtitles')
            output = root/'output'/'Movie.mkv'
            output.parent.mkdir()
            self.assertEqual(copy_matching_artwork(source, output, True), [])
            self.assertEqual(list(output.parent.iterdir()), [])
            self.assertTrue((root/'Subs'/'English.srt').exists())
            self.assertTrue(parse_args(['movie.mkv', '--video-only-folder']).video_only_folder)

    def test_preserve_release_movie_and_episode_output_names(self):
        root = Path('media')
        for original, expected in [
            ('Commando 1985 1080p AMZN WEB-DL DDP 5 1 H 264-PiRaTeS.mkv', 'Commando 1985 1080p AMZN WEB-DL DDP 5 1 H 264-PiRaTeS.mkv'),
            ('Show.Name.S01E07.Episode.Title.2160p.WEB-DL.mp4', 'Show.Name.S01E07.Episode.Title.2160p.WEB-DL.mkv'),
            ('65 (2023).mkv', '65 (2023).mkv'),
        ]:
            self.assertEqual(output_path(root/original,root,Path('output')).name,expected)
            self.assertEqual(output_path(root/original,root,None).name,expected)

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
        self.assertEqual(intel[intel.index("-bf") + 1], "0")
        self.assertNotIn("-bf", nvidia)

    def test_intel_av1_rejects_unverified_mastering_display_preservation(self):
        info = sample()
        info.mastering_display_metadata = True
        with self.assertRaisesRegex(ValueError, 'mastering-display'):
            build_ffmpeg_command(Path('s.mkv'), Path('o.mkv'), info, 'av1', 'balanced', encoder='av1_qsv')
        self.assertIn('hevc_qsv', build_ffmpeg_command(Path('s.mkv'), Path('o.mkv'), info, 'hevc', 'balanced', encoder='hevc_qsv'))
        info.hdr = True
        self.assertIn('av1_qsv', mm.encoder_options('av1','transparent',info,'av1_qsv',experimental_av1_hdr=True))
        info.mastering_display_metadata = False  # ffprobe may expose it only on frames.
        with self.assertRaisesRegex(ValueError,'mastering-display'):
            build_ffmpeg_command(Path('s.mkv'),Path('o.mkv'),info,'av1','balanced',encoder='av1_qsv')
        self.assertIn('av1_qsv',build_ffmpeg_command(Path('s.mkv'),Path('o.mkv'),info,'av1','balanced',encoder='av1_qsv',experimental_av1_hdr=True))
        info.dolby_vision = True
        with self.assertRaisesRegex(ValueError,'without Dolby Vision'):
            mm.encoder_options('av1','transparent',info,'av1_qsv',experimental_av1_hdr=True)

    def test_original_deletion_needs_exact_confirmation(self):
        args = SimpleNamespace(delete_originals=True, confirm_delete="no")
        with self.assertRaises(ValueError):
            delete_original_allowed(args)
        args.confirm_delete = "DELETE_ORIGINALS"
        with self.assertRaises(ValueError):
            delete_original_allowed(args)


if __name__ == "__main__":
    unittest.main()
