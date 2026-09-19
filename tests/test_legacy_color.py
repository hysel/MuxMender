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
