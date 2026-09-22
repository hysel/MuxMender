import unittest
from unittest.mock import patch
from types import SimpleNamespace
import hdr_inspection as hdr
import tempfile
from pathlib import Path
from job_tracking import tracked_call, progress
from dashboard import Catalog


class HDRInspectionTests(unittest.TestCase):
    def test_dolby_policy_includes_combined_metadata_but_not_hdr10plus_alone(self):
        dv={'side_data_type':'DOVI configuration record'}
        plus={'side_data_type':'HDR Dynamic Metadata SMPTE2094-40 (HDR10+)'}
        for items in ([dv],[dv,plus]):
            with self.assertRaises(hdr.AutomaticHDRSkip) as error:
                hdr.enforce_automatic_policy({'side_data_list':items})
            self.assertEqual(error.exception.reason_code,'dolby_vision_temporarily_disabled')
        hdr.enforce_automatic_policy({'color_transfer':'smpte2084','side_data_list':[plus]})
        with self.assertRaises(hdr.AutomaticHDRSkip):
            hdr.enforce_automatic_policy({},hdr.classify({},[{'side_data_list':[dv,plus]}]))

    def test_auto_skips_dolby_before_gpu_or_frame_inspection(self):
        import auto_optimize as ao
        import json
        from test_auto_optimize import source_data
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'input').mkdir();source=root/'input/source.mkv';source.write_bytes(b'original')
            data=source_data();data['streams'][0]['side_data_list']=[{'side_data_type':'DOVI configuration record'}]
            args=SimpleNamespace(source=source,output_dir=root/'out',ffmpeg='ffmpeg',ffprobe='ffprobe')
            with patch.object(ao.Workflow,'probe',return_value=data), \
                 patch.object(hdr,'inspect') as inspect, patch.object(ao,'probe_encoder') as encoder:
                self.assertEqual(ao.run(args),0)
            inspect.assert_not_called();encoder.assert_not_called()
            record=json.loads((root/'out/eligibility.json').read_text())
            self.assertEqual(record['reason_code'],'dolby_vision_temporarily_disabled')
            self.assertEqual(source.read_bytes(),b'original')
            from autonomous_queue import outcome
            self.assertEqual(outcome(root/'out',0),('skipped',record['reason']))

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
