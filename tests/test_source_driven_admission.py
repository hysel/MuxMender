from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import auto_optimize as ao
import encoder_capabilities as ec
import legacy_color
from test_auto_optimize import source_data


class SourceDrivenAdmissionTests(unittest.TestCase):
    def test_interlaced_and_additional_formats_reach_runtime_trials(self):
        for fmt in ('yuv420p16le','gbrp10le','rgb24','yuvj444p'):
            data=source_data();data['streams'][0].update(pix_fmt=fmt,field_order='tt')
            self.assertEqual(ao.eligibility(data)['pix_fmt'],fmt)
        with patch.object(ec.subprocess,'run',return_value=SimpleNamespace(returncode=1,stderr='unsupported field encoding')):
            result=ec.probe_encoder('ffmpeg','hevc_nvenc',pixel_format='yuv420p',field_order='tt',adapters=[])
        self.assertEqual(result['status'],'failed')
        self.assertIn('setfield=tff',result['command'][result['command'].index('-i')+1])
        self.assertIn('+ildct+ilme',result['command'])

    def test_color_labels_are_not_a_small_historical_allowlist(self):
        data=source_data();data['streams'][0].update(color_transfer='iec61966-2-1',color_primaries='smpte432')
        ao.eligibility(data)
        data['streams'][0]['color_transfer']='smpte2084'
        with self.assertRaises(ValueError):ao.eligibility(data)

    def test_interlace_must_survive_frame_validation(self):
        row='width=160|height=96|pix_fmt=yuv420p|sample_aspect_ratio=1:1|interlaced_frame=1|top_field_first=1|repeat_pict=0|best_effort_timestamp_time=0.0\n'
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'a.txt';b=Path(tmp)/'b.txt';a.write_text(row);b.write_text(row)
            self.assertEqual(ao.compare_frames(a,b),1)
            for changed in (row.replace('interlaced_frame=1','interlaced_frame=0'),row.replace('top_field_first=1','top_field_first=0')):
                b.write_text(changed)
                with self.assertRaises(ValueError):ao.compare_frames(a,b)

    def test_scan_recovery_needs_consistent_field_evidence(self):
        rows=[dict(interlaced_frame=1,top_field_first=0,repeat_pict=0) for _ in range(24)]
        self.assertEqual(legacy_color.confirm_interlaced(rows),'bb')
        rows[2]['top_field_first']=1
        self.assertIsNone(legacy_color.confirm_interlaced(rows))
