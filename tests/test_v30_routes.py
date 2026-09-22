import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import auto_optimize as ao
import encoder_capabilities as ec
import legacy_color
from media_metadata import canonical_chapters,equivalent_ratio
from test_auto_optimize import source_data
from job_tracking import tracked_call
from codec_selection import select_candidate
from control_service import Controls


class RoutingTests(unittest.TestCase):
    def test_exact_two_millisecond_boundary_not_float_rounding_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'a';b=Path(folder)/'b'
            a.write_text('data_hash=SHA256:abc|pts_time=0.552000|dts_time=0.552000|duration_time=0.010000\n')
            b.write_text('data_hash=SHA256:abc|pts_time=0.550000|dts_time=0.550000|duration_time=0.011000\n')
            ao.compare_packets(a,b)
            b.write_text('data_hash=SHA256:abc|pts_time=0.549999|dts_time=0.550000|duration_time=0.011000\n')
            with self.assertRaisesRegex(ValueError,'timing changed'):ao.compare_packets(a,b)

    def test_muxer_generated_chapter_ids_and_time_bases_are_not_content(self):
        a=[dict(id=4911502047051653766,time_base='1/1000000000',start=0,end=10000000000,tags={'TITLE':'Chapter 06'})]
        b=[dict(id=-8980312020191865135,time_base='1/1000',start=0,end=10000,tags={'title':'Chapter 06'})]
        self.assertEqual(canonical_chapters(a),canonical_chapters(b))
        for key,value in [('end',9999),('tags',{'title':'Wrong chapter'})]:
            changed=copy.deepcopy(b);changed[0][key]=value
            self.assertNotEqual(canonical_chapters(a),canonical_chapters(changed))

    def test_chapter_order_and_invalid_timing_still_rejected(self):
        a=dict(start_time='0',end_time='1',tags={'title':'Intro'})
        b=dict(start_time='1',end_time='2',tags={'title':'Scene'})
        self.assertNotEqual(canonical_chapters([a,b]),canonical_chapters([b,a]))
        for chapter in ({},dict(start_time='nan',end_time='1'),dict(start_time='2',end_time='1')):
            with self.assertRaises(ValueError):canonical_chapters([chapter])

    def test_equivalent_ratios_not_actual_geometry_changes(self):
        self.assertTrue(equivalent_ratio('24000/1001','48000/2002'))
        self.assertTrue(equivalent_ratio('1:1','2:2'))
        self.assertFalse(equivalent_ratio('24/1','25/1'))
        self.assertFalse(equivalent_ratio('0:1','1:1'))
        before=source_data();after=copy.deepcopy(before)
        after['streams'][0].update(codec_name='hevc',sample_aspect_ratio='2:2',avg_frame_rate='48/2')
        ao.metadata_check(before,after,'hevc')
        after['streams'][0]['width']=1918
        with self.assertRaises(ValueError):ao.metadata_check(before,after,'hevc')

    def test_source_format_admitted_but_loss_of_chroma_or_depth_rejected(self):
        for pixel in sorted(ao.PLANAR_FORMATS):
            data=source_data();data['streams'][0]['pix_fmt']=pixel
            ao.eligibility(data)
            after=copy.deepcopy(data);after['streams'][0]['codec_name']='hevc'
            ao.metadata_check(data,after,'hevc')
            after['streams'][0]['pix_fmt']='yuv420p' if pixel!='yuv420p' else 'yuv420p10le'
            with self.assertRaises(ValueError):ao.metadata_check(data,after,'hevc')

    def test_wide_gamut_sdr_not_mistaken_for_hdr(self):
        data=source_data();video=data['streams'][0]
        video.update(color_primaries='bt2020',color_transfer='bt2020-10',color_space='bt2020nc')
        ao.eligibility(data)
        for transfer in ('smpte2084','arib-std-b67'):
            video['color_transfer']=transfer
            with self.assertRaises(ValueError):ao.eligibility(data)

    def test_short_sampling_adapts_instead_of_rejecting(self):
        for duration in (0.5,5,30,120):
            seconds=ao.sampling_window(duration,10)
            self.assertLessEqual(seconds,duration/6)
            positions=[(duration-seconds)*f for f in (.15,.5,.85)]
            self.assertTrue(all(a+seconds<b for a,b in zip(positions,positions[1:])))
            self.assertLessEqual(positions[-1]+seconds,duration)
        self.assertEqual(ao.sampling_window(120,10),10)

    def test_runtime_probe_uses_requested_dimensions_and_format(self):
        with patch.object(ec.subprocess,'run',return_value=SimpleNamespace(returncode=0,stderr='')) as run:
            result=ec.probe_encoder('ffmpeg','hevc_nvenc',3840,2076,pixel_format='yuv444p16le',adapters=[])
        self.assertEqual(result['pixel_format'],'yuv444p16le')
        self.assertIn('nullsrc=size=3840x2076:rate=30,format=yuv444p16le',run.call_args.args[0])

    def test_adaptive_budget_does_not_starve_other_backend(self):
        trials=[dict(encoder=e,codec=c,runtime_supported=True,playback_compatible=True,samples=[])
                for e,c in [('hevc_nvenc','hevc'),('av1_nvenc','av1'),('hevc_amf','hevc')]]
        candidates=ao.adaptive_candidates({'trials':trials},3)
        self.assertEqual({c['encoder'] for c in candidates},{t['encoder'] for t in trials})

    def test_ui_accepts_positive_reductions_below_ten_percent(self):
        with tempfile.TemporaryDirectory() as folder:
            media=Path(folder)/'media';output=Path(folder)/'output';media.mkdir();output.mkdir()
            controls=Controls(media,output,lambda _:False,['hevc'])
            for minimum in (0,0.1,5,10):
                self.assertEqual(controls.settings({'minimum_savings':minimum})['minimum_savings'],minimum)

    def test_zero_threshold_never_approves_equal_or_larger_output(self):
        for size in (99,100,101):
            report=dict(schema='muxmender-codec-trials-v1',source_id='source',color_mode='sdr',references=[dict(id=str(i),bytes=100) for i in range(3)],
                trials=[dict(id='trial',source_id='source',runtime_supported=True,playback_compatible=True,
                    codec='hevc',encoder='hevc_nvenc',settings={'quality':'balanced'},
                    samples=[dict(reference_id=str(i),bytes=size,quality_pass=True,preservation_pass=True,
                                  decode_pass=True,quality_method='VMAF') for i in range(3)])])
            self.assertEqual(select_candidate(report,0)['action'],'encode_copy' if size<100 else 'keep_original')

    def test_failure_reason_persisted_in_dashboard_job(self):
        with tempfile.TemporaryDirectory() as folder:
            def fail():raise ValueError('Chapters changed')
            with self.assertRaises(ValueError):tracked_call(fail,'test',Path(folder))
            data=json.loads(next(Path(folder).glob('job-*/job.json')).read_text())
            self.assertEqual(data['error'],'Chapters changed')
            self.assertEqual(data['state'],'failed')
