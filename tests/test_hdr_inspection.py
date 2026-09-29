import unittest
import copy
from unittest.mock import patch
from types import SimpleNamespace
import hdr_inspection as hdr
import tempfile
from pathlib import Path
from job_tracking import tracked_call, progress
from dashboard import Catalog


class StaleDVDeclarationTests(unittest.TestCase):
    def test_only_complete_absence_can_recover_container_label(self):
        video=dict(codec_name='hevc',color_transfer='bt709',side_data_list=[
            {'side_data_type':'DOVI configuration record','dv_profile':7},
            {'side_data_type':'CPB properties'}])
        evidence=dict(complete_bitstream=True,source_unchanged=True,bytes=1234,rpu_nals=0,potential_enhancement_nals=0)
        for key,value in [('complete_bitstream',False),('source_unchanged',False),('bytes',0),
                          ('rpu_nals',1),('potential_enhancement_nals',1),('rpu_nals',False)]:
            changed=dict(evidence,**{key:value});untouched=copy.deepcopy(video)
            self.assertFalse(hdr.recover_empty_dv_declaration(untouched,changed))
            self.assertEqual(untouched,video)
        self.assertTrue(hdr.recover_empty_dv_declaration(video,evidence))
        self.assertEqual(video['color_transfer'],'bt709')
        self.assertEqual(video['side_data_list'],[{'side_data_type':'CPB properties'}])



class HDRInspectionTests(unittest.TestCase):
    def test_dolby_policy_includes_combined_metadata_but_not_hdr10plus_alone(self):
        dv={'side_data_type':'DOVI configuration record'}
        plus={'side_data_type':'HDR Dynamic Metadata SMPTE2094-40 (HDR10+)'}
        for items in ([dv],[dv,plus]):
            with self.assertRaises(hdr.AutomaticHDRSkip) as error:
                hdr.enforce_automatic_policy({'side_data_list':items})
            self.assertEqual(error.exception.reason_code,'dolby_vision_requires_preservation_route')
        hdr.enforce_automatic_policy({'color_transfer':'smpte2084','side_data_list':[plus]})
        with self.assertRaises(hdr.AutomaticHDRSkip):
            hdr.enforce_automatic_policy({},hdr.classify({},[{'side_data_list':[dv,plus]}]))

    def test_auto_routes_dolby_without_experimental_flag(self):
        import auto_optimize as ao
        import json
        from test_auto_optimize import source_data
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'input').mkdir();source=root/'input/source.mkv';source.write_bytes(b'original')
            data=source_data();data['streams'][0]['side_data_list']=[{'side_data_type':'DOVI configuration record'}]
            args=SimpleNamespace(source=source,output_dir=root/'out',ffmpeg='ffmpeg',ffprobe='ffprobe')
            with patch.object(ao.Workflow,'probe',return_value=data), \
                 patch.object(hdr,'inspect') as inspect, patch.object(ao,'probe_encoder') as encoder, \
                 patch('dv_workflow.run',return_value=0) as route:
                self.assertEqual(ao.run(args),0)
            inspect.assert_not_called();encoder.assert_not_called()
            route.assert_called_once()
            self.assertEqual(source.read_bytes(),b'original')

    def test_skipped_job_is_not_presented_as_successful_conversion(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            def skip():
                progress('skipped',directory=root,detail='HDR10+ preservation required',original_unchanged=True)
                return 0
            tracked_call(skip,'Measured codec selection',folder=root)
            job=Catalog(root,[root]).snapshot()[0]
            self.assertEqual(job['state'],'skipped')
            self.assertEqual(job['detail'],'HDR10+ preservation required')

    def test_dynamic_metadata_in_frames_not_stream_header(self):
        result=hdr.classify({'color_transfer':'smpte2084'}, [dict(side_data_list=[
            {'side_data_type':'HDR Dynamic Metadata SMPTE2094-40 (HDR10+)'}])])
        self.assertEqual(result['kind'],'HDR10+')
        self.assertFalse(result['conversion_authorized'])

    def test_sampling_does_not_certify_static_only(self):
        result=hdr.classify({'color_transfer':'smpte2084'}, [{}])
        self.assertIn('not observed',result['kind'])
        self.assertTrue(result['full_metadata_scan_required'])

    def test_hlg_and_dolby_not_classified_as_hdr10(self):
        self.assertEqual(hdr.classify({'color_transfer':'arib-std-b67'},[])['kind'],'HLG')
        self.assertEqual(hdr.classify({'side_data_list':[{'side_data_type':'DOVI configuration record'}]},[])['kind'],'Dolby Vision')

    def test_three_bounded_read_only_windows(self):
        with patch.object(hdr.subprocess,'run',return_value=SimpleNamespace(stdout='{"frames":[{}]}')) as run:
            self.assertEqual(hdr.inspect('ffprobe','source',{},120)['sampled_frames'],3)
        self.assertEqual(run.call_count,3)
        for call in run.call_args_list:
            self.assertEqual(call.kwargs['timeout'],30)
            self.assertIn('-show_frames',call.args[0])

    def test_missing_frames_rejected(self):
        with patch.object(hdr.subprocess,'run',return_value=SimpleNamespace(stdout='{"frames":[]}')):
            with self.assertRaises(ValueError):hdr.inspect('ffprobe','source',{},120)

    def test_missing_hdr_labels_recovered_without_guessing(self):
        import json
        frame=dict(color_primaries='bt2020',color_space='bt2020nc',color_range='tv',color_transfer='smpte2084')
        with patch.object(hdr.subprocess,'run',return_value=SimpleNamespace(stdout=json.dumps({'frames':[frame]}))):
            report=hdr.inspect('ffprobe','source',{'color_transfer':'smpte2084'},120)
            self.assertEqual(report['recovered_color'],{key:value for key,value in frame.items() if key!='color_transfer'})
            self.assertFalse(report['conversion_authorized'])
            with self.assertRaisesRegex(ValueError,'Conflicting HDR'):
                hdr.inspect('ffprobe','source',{'color_primaries':'bt709'},120)
