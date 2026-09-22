import copy
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import auto_optimize as ao
import legacy_color as lc
from test_auto_optimize import source_data
from control_service import Controls


class ColorTests(unittest.TestCase):
    def test_mpeg4_absent_signal_requires_parseable_video_header(self):
        absent=bytes.fromhex('000001b5090000012000')
        self.assertEqual(lc.mpeg4_absent_signal_headers(absent),1)
        self.assertEqual(lc.mpeg4_absent_signal_headers(absent+absent),2)
        self.assertEqual(lc.mpeg4_absent_signal_headers(bytes.fromhex('000001b589100000012000')),1)
        self.assertIsNone(lc.mpeg4_absent_signal_headers(bytes.fromhex('000001b581100000012000')))
        for raw in ('000001b5','000001b588','000001b50d','000001b511','0000012009'):
            self.assertIsNone(lc.mpeg4_absent_signal_headers(bytes.fromhex(raw)))
        self.assertIsNone(lc.mpeg4_absent_signal_headers(absent+bytes.fromhex('000001b50d')))

    def test_mpeg4_default_range_requires_all_windows(self):
        from types import SimpleNamespace
        absent=SimpleNamespace(returncode=0,stdout=bytes.fromhex('000001b5090000012000'))
        with patch.object(lc.subprocess,'run',return_value=absent) as run:
            proof=lc.inspect_mpeg4_default_range('ffmpeg','source',100)
            self.assertEqual(proof['value'],'tv')
            self.assertEqual(proof['effective']['color_space'],'bt709')
            self.assertEqual(run.call_count,3)
        with patch.object(lc.subprocess,'run',side_effect=[absent,SimpleNamespace(returncode=0,stdout=b'')]):
            self.assertIsNone(lc.inspect_mpeg4_default_range('ffmpeg','source',100))

    def test_unspecified_colors_require_known_range_and_are_not_filled(self):
        data=self.missing();data['streams'][0]['color_range']='tv'
        effective,report=lc.resolve(data,[{}]*24)
        self.assertEqual(set(report['preserved_unspecified']),set(lc.FIELDS)-{'color_range'})
        self.assertEqual(report['assumed'],[])
        ao.eligibility(effective)
        self.assertNotIn('color_primaries',effective['streams'][0])
        effective['streams'][0]['color_transfer']='smpte2084'
        self.assertFalse(lc.is_supported(effective['streams'][0]))

    def test_range_recovery_requires_absent_h264_signal_flags_in_every_window(self):
        from types import SimpleNamespace
        absent=SimpleNamespace(returncode=0,stderr='video_signal_type_present_flag 0 = 0')
        explicit=SimpleNamespace(returncode=0,stderr='video_signal_type_present_flag 1 = 1\nvideo_full_range_flag 1 = 1')
        with patch.object(lc.subprocess,'run',return_value=absent) as run:
            proof=lc.inspect_h264_default_range('ffmpeg',Path('source'),100)
        self.assertEqual(proof['value'],'tv');self.assertEqual(run.call_count,3)
        with patch.object(lc.subprocess,'run',side_effect=[absent,explicit]):
            self.assertIsNone(lc.inspect_h264_default_range('ffmpeg',Path('source'),100))
        with patch.object(lc.subprocess,'run',return_value=SimpleNamespace(returncode=0,stderr='')):
            self.assertIsNone(lc.inspect_h264_default_range('ffmpeg',Path('source'),100))
        with patch.object(lc.subprocess,'run',side_effect=FileNotFoundError):
            self.assertIsNone(lc.inspect_h264_default_range('ffmpeg',Path('source'),100))

    def test_unspecified_transfer_is_preserved_not_guessed(self):
        data=source_data();data['streams'][0].pop('color_transfer')
        effective,report=lc.resolve(data,[dict(color_primaries='bt709',color_space='bt709',color_range='tv')]*24)
        self.assertEqual(report['preserved_unspecified'],['color_transfer'])
        self.assertEqual(report['assumed'],[])
        self.assertTrue(report['replacement_allowed'])
        self.assertNotIn('color_transfer',effective['streams'][0])
        ao.eligibility(effective)
        after=copy.deepcopy(effective);after['streams'][0]['codec_name']='hevc'
        ao.metadata_check(effective,after,'hevc')
        after['streams'][0]['color_transfer']='bt709'
        with self.assertRaises(ValueError):ao.metadata_check(effective,after,'hevc')
        data['streams'][0].pop('color_range')
        self.assertFalse(lc.can_preserve_unspecified_transfer(data['streams'][0]))

    def test_scan_type_needs_decoded_evidence(self):
        frames=[dict(interlaced_frame=0,repeat_pict=0) for _ in range(24)]
        self.assertTrue(lc.confirm_progressive(frames))
        self.assertFalse(lc.confirm_progressive(frames[:2]))
        self.assertFalse(lc.confirm_progressive([{}]*24))
        frames[-1]['interlaced_frame']=1
        self.assertFalse(lc.confirm_progressive(frames))
        frames[-1].update(interlaced_frame=0,repeat_pict=1)
        self.assertFalse(lc.confirm_progressive(frames))

    def missing(self):
        data=source_data()
        for key in lc.FIELDS:data['streams'][0].pop(key,None)
        return data

    def test_missing_is_not_silently_assumed(self):
        data=self.missing();resolved,report=lc.resolve(data,[{}])
        self.assertEqual(report['missing'],list(lc.FIELDS))
        self.assertFalse(report['replacement_allowed'])
        self.assertNotIn('color_space',data['streams'][0])

    def test_declared_frame_metadata_recovered(self):
        frame={k:source_data()['streams'][0][k] for k in lc.FIELDS}
        resolved,report=lc.resolve(self.missing(),[frame]*3)
        ao.eligibility(resolved)
        self.assertEqual(len(report['recovered']),4)
        self.assertFalse(report['assumed'])

    def test_conflicting_frames_and_stream_rejected(self):
        with self.assertRaises(ValueError):lc.resolve(source_data(),[dict(color_space='smpte170m')])
        with self.assertRaises(ValueError):lc.resolve(self.missing(),[dict(color_range='tv'),dict(color_range='pc')])

    def test_assumption_explicit_and_never_replacement_authority(self):
        resolved,report=lc.resolve(self.missing(),[{}],'bt709-limited')
        ao.eligibility(resolved)
        self.assertEqual(len(report['assumed']),4)
        self.assertFalse(report['replacement_allowed'])
        data=source_data();data['streams'][0]['color_range']='pc'
        with self.assertRaises(ValueError):lc.resolve(data,[],'bt709-limited')

    def test_hdr_side_data_and_transfer_rejected(self):
        with self.assertRaises(ValueError):lc.resolve(self.missing(),[dict(side_data_list=[dict(side_data_type='DOVI metadata')])])
        resolved,_=lc.resolve(self.missing(),[dict(color_transfer='smpte2084')])
        with self.assertRaises(ValueError):ao.eligibility(resolved)

    def test_known_sd_preserved_not_changed_to_bt709(self):
        data=source_data()
        for key in ('color_space','color_transfer','color_primaries'):data['streams'][0][key]='smpte170m'
        self.assertEqual(ao.eligibility(data)['color_space'],'smpte170m')
        after=copy.deepcopy(data);after['streams'][0]['codec_name']='hevc'
        ao.metadata_check(data,after,'hevc')
        after['streams'][0]['color_space']='bt709'
        with self.assertRaises(ValueError):ao.metadata_check(data,after,'hevc')

    def test_inspection_is_bounded_and_read_only(self):
        with patch.object(lc.subprocess,'check_output',return_value='{"frames": []}') as probe:
            lc.inspect_frames('ffprobe',Path('input.mkv'),100)
        command=probe.call_args.args[0]
        self.assertEqual(command[command.index('-read_intervals')+1],'10.000%+#24,50.000%+#24,90.000%+#24')
        self.assertEqual(probe.call_args.kwargs['timeout'],60)

    def test_ui_blocks_assumption_full_encode_and_replace(self):
        with tempfile.TemporaryDirectory() as folder:
            media=Path(folder)/'media';output=Path(folder)/'output';media.mkdir();output.mkdir()
            controls=Controls(media,output,lambda _:False,['hevc'],replacement_root=media)
            for mode in ('encode','replace'):
                with self.assertRaises(ValueError):controls.settings(dict(mode=mode,legacy_color='bt709-limited'))
            settings=controls.settings(dict(mode='test',legacy_color='bt709-limited'))
            self.assertIn('--legacy-color',controls.build_command(dict(source='x',settings=settings),output))

    def test_cli_blocks_assumed_full_copy_before_encoder(self):
        with tempfile.TemporaryDirectory() as folder:
            inputs=Path(folder)/'inputs';inputs.mkdir()
            source=inputs/'input.mkv';source.write_bytes(b'original')
            with patch.object(ao.Workflow,'probe',return_value=self.missing()),patch.object(lc,'inspect_frames',return_value=[{}]),patch.object(ao,'probe_encoder') as encoder:
                ao.main([str(source),'--output-dir',str(Path(folder)/'output'),'--execute','--encode-best','--legacy-color','bt709-limited'])
            encoder.assert_not_called()
            self.assertEqual(source.read_bytes(),b'original')


if __name__=='__main__':unittest.main()
