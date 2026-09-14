import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import tempfile
import sys
import amd_av1_preview as av
import muxmender as mm


class AMDPresetTests(unittest.TestCase):
    def info(self, **changes):
        values=dict(bit_depth=8,hdr=False,dolby_vision=False,color_primaries='bt709',color_transfer='bt709',color_space='bt709',color_range='tv')
        values.update(changes)
        return SimpleNamespace(**values)

    def test_explicit_qp80_and_existing_hevc_unchanged(self):
        cmd=mm.encoder_options('av1','balanced',self.info(),'av1_amf',experimental_amd_av1_qp80=True)
        self.assertEqual(cmd[cmd.index('-qp_i')+1],'80')
        self.assertEqual(cmd[cmd.index('-qp_p')+1],'80')
        self.assertEqual(cmd[cmd.index('-quality')+1],'quality')
        old=mm.encoder_options('hevc','balanced',self.info(),'hevc_amf')
        self.assertEqual(old[old.index('-qp_i')+1],'21')

    def test_reject_unvalidated_preset_combinations(self):
        for codec,encoder,quality,info in [('hevc','hevc_amf','balanced',self.info()),('av1','av1_nvenc','balanced',self.info()),('av1','av1_amf','compact',self.info()),('av1','av1_amf','balanced',self.info(bit_depth=10)),('av1','av1_amf','balanced',self.info(hdr=True)),('av1','av1_amf','balanced',self.info(dolby_vision=True))]:
            with self.subTest(encoder=encoder,quality=quality,info=info),self.assertRaises(ValueError):
                mm.encoder_options(codec,quality,info,encoder,experimental_amd_av1_qp80=True)


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.orig=dict(width=1920,height=1080,sample_aspect_ratio='1:1',field_order='progressive')
        self.out=dict(width=1920,height=1082,codec_name='av1',sample_aspect_ratio='1:1',side_data_list=[dict(side_data_type='Frame Cropping',crop_top=0,crop_bottom=2,crop_left=0,crop_right=0)])

    def test_exact_or_verified_padding(self):
        self.assertEqual(av.verify_geometry(self.orig,self.out,[(1920,1080)]*3)['frames'],3)
        output=dict(self.out,height=1080,side_data_list=[])
        av.verify_geometry(self.orig,output,[(1920,1080)])

    def test_bad_padding_or_missing_decode_rejected(self):
        for size in ([],[(1920,1082)],[(1920,1080),(1280,720)]):
            with self.assertRaises(ValueError):av.verify_geometry(self.orig,self.out,size)
        for key,value in [('crop_bottom',4),('crop_bottom','2'),('crop_top',2),('crop_left',2)]:
            output=deepcopy(self.out);output['side_data_list'][0][key]=value
            with self.assertRaises(ValueError):av.verify_geometry(self.orig,output,[(1920,1080)])
        for change in (dict(height=1084),dict(width=1280),dict(side_data_list=[]),dict(sample_aspect_ratio='2:1'),dict(codec_name='hevc')):
            with self.assertRaises(ValueError):av.verify_geometry(self.orig,dict(self.out,**change),[(1920,1080)])

    def test_source_crop_interlace_and_output_rotation_rejected(self):
        for change in (dict(field_order='tt'),dict(side_data_list=[{'side_data_type':'Frame Cropping'}]),dict(width=3840)):
            with self.assertRaises(ValueError):av.verify_geometry(dict(self.orig,**change),self.out,[(1920,1080)])
        self.out['side_data_list'].append({'side_data_type':'Display Matrix'})
        with self.assertRaises(ValueError):av.verify_geometry(self.orig,self.out,[(1920,1080)])


class PreviewSafetyTests(unittest.TestCase):
    def test_disposition_options_preserve_zero_and_multiple_flags(self):
        self.assertEqual(av.disposition_options([
            dict(disposition=dict(default=1, forced=0)),
            dict(disposition=dict(default=0, forced=0)),
            dict(disposition=dict(default=1, forced=1))]),
            ['-disposition:0', 'default', '-disposition:1', '0', '-disposition:2', 'default+forced'])
        with self.assertRaises(ValueError): av.disposition_options([{}])

    def test_timeline_diagnostics_keep_counts_and_first_mismatch(self):
        details = {}
        with self.assertRaisesRegex(ValueError, 'timeline'):
            av.compare_timestamps([0, .04], [0, .08], details)
        self.assertEqual(details['source_count'], 2)
        self.assertEqual(details['mismatch_count'], 1)
        self.assertEqual(details['first_mismatches'][0][0], 1)
        av.compare_timestamps([0, .04], [0, .041], details)
        self.assertTrue(details['passed'])
        for a,b in (([], []), ([0], [0,.04])):
            with self.assertRaises(ValueError): av.compare_timestamps(a,b,{})

    def test_success_exit_with_decoder_errors_is_rejected_and_retained(self):
        details = {}
        with patch.object(av.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stderr='decode error', stdout='{}')):
            with self.assertRaisesRegex(ValueError, 'decoder'):
                av.decoded_timestamps(Path('fixture.mkv'), 'ffprobe', details, 10)
        self.assertEqual(details['stderr'], 'decode error')

    def test_container_integrity_warnings_block_promotion(self):
        for line in ('0x00 invalid as first byte of an EBML number',
                     'Element exceeds containing master element', 'Packet corrupt',
                     'Truncating packet of size 351305989', 'EBML number exceeds max length 4'):
            with self.assertRaises(ValueError):
                av.reject_integrity_warning(line)
        self.assertFalse(av.reject_integrity_warning('Multiple codec options specified'))

    def test_stage_observer_sees_all_lines(self):
        lines=[]
        av.np.stage([sys.executable,'-c','print("observed-frame"); print("out_time_us=1000000")'],
                    1, timeout=10, observe=lambda line: lines.append(line) or True)
        self.assertTrue(any('observed-frame' in line for line in lines))

    def test_track_metadata_changes_rejected(self):
        track = dict(index=1, codec_type='audio', codec_name='dts', extradata_hash='abc',
                     tags={'language':'eng'}, disposition={'default':1})
        av.verify_tracks([track], [deepcopy(track)])
        for change in (dict(index=2), dict(codec_name='aac'), dict(extradata_hash='xyz'),
                       dict(tags={'language':'fra'}), dict(disposition={})):
            with self.assertRaises(ValueError):
                av.verify_tracks([track], [dict(track, **change)])
        with self.assertRaises(ValueError):
            av.verify_tracks([track], [])

    def test_amd_plan_does_not_assume_all_sdr_is_eligible(self):
        from library_planner import amd_av1_eligibility
        info=AMDPresetTests().info(width=1920,height=1080)
        geometry={'field_order':'progressive','sample_aspect_ratio':'1:1'}
        with patch('library_planner.classify',return_value=('preview-candidate','')):
            self.assertEqual(amd_av1_eligibility(info,geometry)[0],'preview-candidate')
            info.bit_depth=10
            self.assertEqual(amd_av1_eligibility(info,geometry)[0],'needs-review')
            info.bit_depth=8
            self.assertEqual(amd_av1_eligibility(info,dict(geometry,field_order='tt'))[0],'needs-review')

    def test_invalid_arguments(self):
        for start,seconds,execute,dry in [(float('nan'),30,False,True),(-1,30,False,True),(0,31,True,False),(0,30,True,True)]:
            with self.assertRaises(ValueError):av.validate_args(SimpleNamespace(start=start,seconds=seconds,execute=execute,dry_run=dry))

    def test_dry_run_does_not_encode_or_create_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'dummy.mkv';source.write_bytes(b'fixture')
            output=Path(temp)/'not-created'
            info=AMDPresetTests().info(width=1920,height=1080,duration_seconds=600)
            with patch.object(av,'probe_with_frame_color',return_value=info),patch.object(av,'classify',return_value=('preview-candidate','')),patch.object(av.worker,'shape',return_value={'field_order':'progressive','sample_aspect_ratio':'1:1'}),patch.object(mm,'gpu_vendors') as gpu,patch.object(av.subprocess,'run') as process:
                self.assertEqual(av.main([str(source),'--output-dir',str(output),'--dry-run']),0)
                self.assertEqual(av.main([str(source),'--output-dir',str(output),'--full','--dry-run']),0)
                gpu.assert_not_called();process.assert_not_called()
            self.assertFalse(output.exists());self.assertEqual(source.read_bytes(),b'fixture')
