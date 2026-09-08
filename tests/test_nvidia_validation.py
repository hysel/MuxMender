import copy
import unittest

from validate_nvidia import validate_source, copied_subset, compare_sample, metadata_equal, parse_args, disposition_options, startup_audio_lead


class NvidiaValidationTests(unittest.TestCase):
    def test_media_scan_excludes_integrated_recovery_videos(self):
        import tempfile
        from pathlib import Path
        import muxmender as mm
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);video=root/'movie.mkv';video.touch()
            work=root/'.MuxMender-work'/'run';work.mkdir(parents=True)
            (work/'movie.mkv').touch()
            (root/'movie.mkv.original-backup').touch()
            self.assertEqual(list(mm.media_files(root)),[video])

    def test_integrated_av1_requires_verified_output_before_publication(self):
        import tempfile,json
        from pathlib import Path
        from unittest.mock import patch
        import muxmender as mm
        import validate_nvidia as nv
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.mkv';source.write_bytes(b'original')
            destination=Path(folder)/'output.mkv'
            args=mm.parse_args([str(source),'--execute','--hardware','intel','--codec','av1','--quality','transparent'])
            def encode(options):
                options.run.mkdir(parents=True)
                (options.run/'encoded.mkv').write_bytes(b'new')
                return 0
            with patch.object(nv,'av1_hdr_research',side_effect=encode),patch.object(nv,'verify_full_file',return_value=1),patch.object(mm,'publish_output') as publish:
                with self.assertRaises(RuntimeError):nv.run_av1_hdr_integrated(args,source,destination)
                publish.assert_not_called()
                self.assertFalse(destination.exists())
            def verify(options):
                evidence=options.run/'full-verification-test';evidence.mkdir()
                (evidence/'validation.json').write_text(json.dumps(dict(status='verified-full-file-awaiting-playback',checks={'full_video_audio_decode':True},output=str(options.run/'encoded.mkv'),saved_percent=50)))
                return 0
            with patch.object(nv,'av1_hdr_research',side_effect=encode),patch.object(nv,'verify_full_file',side_effect=verify):
                result=nv.run_av1_hdr_integrated(args,source,destination)
                self.assertEqual(result['status'],'complete')
                self.assertEqual(destination.read_bytes(),b'new')
                self.assertEqual(source.read_bytes(),b'original')
                with self.assertRaises(ValueError):nv.run_av1_hdr_integrated(args,source,destination)

    def test_integrated_av1_rejects_incompatible_options_before_encoding(self):
        from pathlib import Path
        from unittest.mock import patch
        import muxmender as mm
        import validate_nvidia as nv
        for flags in (['--resolution','1080p'],['--compatibility-audio','eac3'],['--hardware-fallback','cpu'],['--delete-originals'],['--overwrite-output']):
            args=mm.parse_args(['source.mkv',*flags])
            with self.subTest(flags=flags),patch.object(nv,'av1_hdr_research') as encode:
                with self.assertRaises(ValueError):nv.run_av1_hdr_integrated(args,Path('source.mkv'),Path('fresh.mkv'))
                encode.assert_not_called()

    def test_av1_hdr_research_repairs_only_known_clamp_and_refuses_overwrite(self):
        import struct
        import tempfile
        from pathlib import Path
        from validate_nvidia import repair_av1_hdr_research_ivf
        fields = ('red_x','red_y','green_x','green_y','blue_x','blue_y','white_point_x','white_point_y')
        metadata = dict(zip(fields, ['1/2','1/4','1/4','4/5','1/8','1/16','1/4','1/4']))
        metadata.update(max_luminance='1000', min_luminance='0')
        values = [32768,16384,16384,50000,8192,4096,16384,16384,256000,0]
        payload = b'\x02'+struct.pack('>8H2I',*values)+b'\x80'
        obu = bytes([0x2a,len(payload)])+payload
        header = struct.pack('<4sHH4sHHIIII',b'DKIF',0,32,b'AV01',128,72,24,1,1,0)
        packet = struct.pack('<IQ',len(obu),7)+obu
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'source.ivf', Path(tmp)/'fixed.ivf'
            source.write_bytes(header+packet)
            result = repair_av1_hdr_research_ivf(source,output,metadata)
            expected = bytearray(header+packet);struct.pack_into('>H',expected,32+12+3+6,52429)
            self.assertEqual(output.read_bytes(),expected)
            self.assertEqual(source.read_bytes(),header+packet)
            self.assertEqual(result['edits'][0]['field'],'green_y')
            with self.assertRaises(FileExistsError):
                repair_av1_hdr_research_ivf(source,output,metadata)
            broken = bytearray(header+packet);struct.pack_into('>H',broken,32+12+3+6,49000)
            source.write_bytes(broken)
            with self.assertRaisesRegex(ValueError,'beyond reproduced'):
                repair_av1_hdr_research_ivf(source,Path(tmp)/'rejected.ivf',metadata)
            self.assertFalse((Path(tmp)/'rejected.ivf').exists())
            source.write_bytes((header+packet)[:-1])
            with self.assertRaises(ValueError):
                repair_av1_hdr_research_ivf(source,Path(tmp)/'truncated.ivf',metadata)

            from mux_integrity import repair_av1_hdr_stream
            # A full-file repair exceeds the bounded diagnostic's 3600 frames.
            source.write_bytes(header+packet*3601)
            streamed = Path(tmp)/'streamed.ivf'
            summary = repair_av1_hdr_stream(source,streamed,metadata)
            self.assertEqual(summary['frames'],3601)
            self.assertEqual(summary['edit_count'],3601)
            self.assertEqual(streamed.read_bytes(),header+bytes(expected[32:])*3601)
            self.assertEqual(len(summary['edit_examples']),16)
            # Validate the entire input before creating an output, even when the
            # malformed record follows thousands of valid records.
            source.write_bytes(header+packet*3601+b'bad')
            refused = Path(tmp)/'refused.ivf'
            with self.assertRaises(ValueError):
                repair_av1_hdr_stream(source,refused,metadata)
            self.assertFalse(refused.exists())

    def test_av1_precision_is_local_to_expected_mastering_fields(self):
        from validate_nvidia import av1_quantized_frames
        frames = [dict(best_effort_timestamp_time='0.167', side_data_list=[
            dict(side_data_type='Mastering display metadata',green_y='39850/50000'),
            dict(side_data_type='Content light level metadata',max_content=1000)])]
        before = copy.deepcopy(frames)
        converted = av1_quantized_frames(frames)
        self.assertEqual(frames,before)
        self.assertEqual(converted[0]['side_data_list'][0]['green_y'],'6529/8192')
        self.assertEqual(converted[0]['side_data_list'][1],frames[0]['side_data_list'][1])
        self.assertEqual(converted[0]['best_effort_timestamp_time'],'0.167')

    def test_intel_fixture_selection_keeps_nvidia_default(self):
        self.assertEqual(parse_args([]).hardware, 'nvidia')
        self.assertEqual(parse_args(['--hardware', 'intel']).hardware, 'intel')
        self.assertEqual(str(parse_args(['--hardware', 'intel', 'movie.mkv']).source), 'movie.mkv')
        for arguments in (['--gpu', '1'],):
            with self.assertRaises(SystemExit):
                parse_args(['--hardware', 'intel', *arguments])

    def test_copied_dts_duration_needs_sample_backed_rounding(self):
        stream = dict(index=0, codec_type='audio', codec_name='dts', sample_rate='48000', time_base='1/1000')
        packet = dict(stream_index=0, pts_time='10.000000', duration_time='0.011000', size='20', data_hash='same')
        original = dict(streams=[stream], packets=[packet])
        sample = dict(streams=[stream], packets=[dict(packet, pts_time='0.000000', duration_time='0.010000')])
        frames = [dict(stream_index=0, pts_time='0.000000', nb_samples=512)]
        with self.assertRaises(ValueError):
            copied_subset(original, sample)
        self.assertEqual(copied_subset(original, sample, frames), 10)
        for changed in ('payload', 'duration', 'samples', 'frame_pts'):
            other, decoded = copy.deepcopy(sample), copy.deepcopy(frames)
            if changed == 'payload': other['packets'][0]['data_hash'] = 'different'
            if changed == 'duration': other['packets'][0]['duration_time'] = '0.009000'
            if changed == 'samples': decoded[0]['nb_samples'] = 480
            if changed == 'frame_pts': decoded[0]['pts_time'] = '0.001000'
            with self.assertRaises(ValueError):
                copied_subset(original, other, decoded)

    def test_audio_prefix_detected_even_with_unchanged_track_packets(self):
        streams = [dict(index=0, codec_type='video'), dict(index=1, codec_type='audio')]
        video = dict(stream_index=0, pts_time='0.083')
        audio = [dict(stream_index=1, pts_time=t) for t in ('0.097', '0.129', '10.945')]
        bad = dict(streams=streams, packets=[*audio, video])
        fixed = dict(streams=streams, packets=[video, *audio])
        self.assertAlmostEqual(startup_audio_lead(bad), 10.862)
        self.assertEqual(startup_audio_lead(fixed), 0)
        self.assertIsNone(startup_audio_lead(dict(streams=streams, packets=audio)))
        self.assertIsNone(startup_audio_lead(dict(streams=streams, packets=[dict(stream_index=0, pts_time='nan')])))

    def source(self):
        return {'streams': [dict(index=0, codec_type='video', codec_name='h264', width=1920,
                                height=1040, pix_fmt='yuv420p', color_primaries='bt709',
                                color_transfer='bt709', color_space='bt709', color_range='tv')]}

    def test_dolby_and_unknown_color_fail_closed(self):
        source = self.source()
        validate_source(source, 'SDR')
        source['streams'][0]['side_data_list'] = [{'side_data_type': 'DOVI configuration record'}]
        with self.assertRaisesRegex(ValueError, 'Dolby Vision'):
            validate_source(source, 'SDR')
        source = self.source()
        del source['streams'][0]['color_transfer']
        with self.assertRaises(ValueError):
            validate_source(source, 'SDR')

    def test_sample_bounds(self):
        self.assertEqual(parse_args([]).seconds, 30)
        for args in (['--seconds', '61'], ['--seconds', 'nan'], ['--start', '-1'], ['--gpu', '-1']):
            with self.assertRaises(SystemExit):
                parse_args(args)

    def test_missing_static_hdr_does_not_pass(self):
        self.assertFalse(metadata_equal({'Mastering display metadata': {'max_luminance': '1000/1'}}, {}))
        self.assertTrue(metadata_equal({'test': {'value': '2/2'}}, {'test': {'value': '1/1'}}))

    def test_copied_subset_checks_common_offset_and_packet_bytes(self):
        source = {'streams': [{'index': 0, 'codec_type': 'video'}, {'index': 1, 'codec_type': 'audio'}],
                  'packets': [dict(stream_index=i, pts_time='300', duration_time='1', data_hash=str(i), size='100') for i in range(2)]}
        sample = copy.deepcopy(source)
        for packet in sample['packets']:
            packet['pts_time'] = '0'
        self.assertEqual(copied_subset(source, sample), 300)
        sample['packets'][1]['pts_time'] = '0.5'
        with self.assertRaisesRegex(ValueError, 'timing'):
            copied_subset(source, sample)
        sample['packets'][1]['data_hash'] = 'changed'
        with self.assertRaises(ValueError):
            copied_subset(source, sample)

    def test_compare_rejects_resize_missing_frames_and_hdr_loss(self):
        source = self.source()
        output = copy.deepcopy(source)
        output['streams'][0]['codec_name'] = 'hevc'
        frames = [{'best_effort_timestamp_time': '0', 'interlaced_frame': 0, 'side_data_list': [
            {'side_data_type': 'Content light level metadata', 'max_content': 1000}]}]
        self.assertTrue(all(compare_sample(source, output, frames, frames, 'hevc').values()))
        output['streams'][0]['height'] = 1080
        checks = compare_sample(source, output, frames, [], 'hevc')
        self.assertFalse(checks['height'])
        self.assertFalse(checks['frame_count'])
        self.assertFalse(checks['static_hdr_metadata'])

    def test_unknown_field_order_requires_decoded_progressive_frames(self):
        source = self.source()
        output = copy.deepcopy(source)
        output['streams'][0].update(codec_name='hevc', field_order='progressive')
        frames = [dict(best_effort_timestamp_time='0', interlaced_frame=0)]
        self.assertTrue(compare_sample(source, output, frames, frames, 'hevc')['field_order'])
        frames[0]['interlaced_frame'] = 1
        self.assertFalse(compare_sample(source, output, frames, frames, 'hevc')['field_order'])

    def test_disposition_zero_is_explicit(self):
        data = dict(streams=[dict(disposition={'default': 0, 'forced': 0}),
                             dict(disposition={'default': 0, 'forced': 1})])
        self.assertEqual(disposition_options(data), ['-disposition:0','0','-disposition:1','forced'])


if __name__ == '__main__':
    unittest.main()
