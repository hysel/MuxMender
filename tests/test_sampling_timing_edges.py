import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from auto_optimize import compare_packets, check_reference_window, Workflow


class SamplingTimingEdges(unittest.TestCase):
    def window(self,duration,rate='24000/1001'):
        return dict(format={'duration':str(duration)},streams=[dict(codec_type='video',
                    avg_frame_rate=rate,time_base='1/1000')])

    def test_unexplained_timing_case_a_sample_remains_rejected(self):
        result=check_reference_window(self.window(20),10)
        self.assertEqual(result['maximum_seconds'],20)
        self.assertEqual(result['boundary_allowance_seconds'],0)
        for value in (20.019,20.1,25,float('nan'),float('inf'),0,-1):
            with self.assertRaises(ValueError):check_reference_window(self.window(value),10)
        with self.assertRaises(ValueError):check_reference_window(self.window(20.3,'1/10'),10)
        with self.assertRaises(ValueError):check_reference_window(self.window(20.019,'0/0'),10)

    def test_subtitle_tail_uses_complete_video_packet_span_not_container_length(self):
        packets=[dict(pts_time='.083',duration_time='.041'),
                 dict(pts_time='18.769',duration_time='.041')]
        proof=check_reference_window(self.window(21.731),10,iter(packets))
        self.assertEqual(proof['duration'],18.81)
        self.assertEqual(proof['container_duration'],21.731)
        self.assertEqual(proof['method'],'complete-primary-video-packet-span')
        self.assertEqual(proof['maximum_seconds'],20)

    def test_video_span_proof_does_not_relax_bound_or_hide_missing_packet_times(self):
        for packets in ([],[dict(pts_time='20',duration_time='.041')],
                        [dict(duration_time='.041')],
                        [dict(pts_time='1')],[dict(pts_time='nan',duration_time='.041')],
                        [dict(pts_time='1',duration_time='0')],
                        [dict(pts_time='-2',duration_time='.041'),dict(pts_time='19',duration_time='.041')]):
            with self.subTest(packets=packets),self.assertRaises(ValueError):
                check_reference_window(self.window(25),10,iter(packets))

    def test_video_span_uses_presentation_order_not_packet_decode_order(self):
        packets=[dict(pts_time='18.769',duration_time='.041'),
                 dict(pts_time='.083',duration_time='.041')]
        self.assertEqual(check_reference_window(self.window(25),10,packets)['duration'],18.81)

    def test_workflow_demux_proof_is_complete_unique_and_cleanup_eligible(self):
        from replacement_cleanup import disposable
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            workflow=Workflow(SimpleNamespace(ffprobe='ffprobe',timeout=10),root,lambda:None)
            def probe(command,path,*unused):
                self.assertIn('packet=stream_index,pts_time,duration_time',command)
                self.assertIn('V:0',command)
                path.write_text('stream_index=0|pts_time=.083|duration_time=.041\n'
                                'stream_index=0|pts_time=18.769|duration_time=.041\n')
                path.with_suffix(path.suffix+'.stderr').write_text('')
            with patch('auto_optimize.run_probe',side_effect=probe) as call:
                for _ in range(2):
                    self.assertEqual(workflow.reference_window(root/'reference-0.mkv',self.window(25),10)['duration'],18.81)
                self.assertEqual(call.call_count,2)
                paths=list(root.glob('*-all-packets.txt'))
                self.assertEqual(len(paths),2)
                self.assertTrue(all(disposable(p) for p in paths))
            with patch('auto_optimize.run_probe') as call:
                workflow.reference_window(root/'reference-1.mkv',self.window(10),10)
                call.assert_not_called()

    def compare(self,left,right,**kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'a',Path(tmp)/'b'
            a.write_text(left);b.write_text(right)
            return compare_packets(a,b,**kwargs)

    def rows(self,times,duration='.010'):
        return ''.join(f'data_hash=SHA256:{i:064x}|pts_time={t}|dts_time={t}|duration_time={duration}\n'
                       for i,t in enumerate(times))

    def test_actual_timing_case_c_tail_pattern(self):
        a=self.rows(['11.569','11.580','11.592','11.602'])
        b=self.rows(['11.568','11.579','11.589','11.600'])
        with self.assertRaisesRegex(ValueError,'Copied packet timing changed'):self.compare(a,b)

    def test_no_drift_payload_loss_reorder_or_large_offsets(self):
        a=self.rows(['1','2','3'])
        for b in (self.rows(['1.006','2','3']),self.rows(['.996','2','3.004']),
                  self.rows(['1','2']),self.rows(['1','2','3'],'.013'),
                  a.replace('SHA256:','SHA256:changed')):
            with self.assertRaises(ValueError):self.compare(a,b)

    def test_short_packets_and_missing_duration_keep_strict_checks(self):
        for duration in ('.004','N/A'):
            with self.assertRaises(ValueError):
                self.compare(self.rows(['1'],duration),self.rows(['1.003'],duration))
