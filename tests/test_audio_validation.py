import copy
import unittest
from audio_validation import normalize_rounding
from workflow_worker import compare_packets


class AudioRoundingTests(unittest.TestCase):
    def fixture(self):
        a=[dict(stream_index=1,pts_time='0.010000',duration_time='0.011000',data_hash='same')]
        b=[dict(a[0],duration_time='0.010000')]
        decoded=dict(streams=[dict(index=1,codec_name='dts',sample_rate='48000',time_base='1/1000')],
                     frames=[dict(stream_index=1,pts_time='0.010000',nb_samples=512)])
        return a,b,decoded,copy.deepcopy(decoded)

    def test_exact_sample_backed_rounding(self):
        a,b,count=normalize_rounding(*self.fixture())
        self.assertEqual(count,1)
        self.assertEqual(compare_packets(a,b),0)

    def test_wrong_duration_samples_pts_and_missing_frames_fail(self):
        for change in ('duration','samples','pts','missing','clock'):
            a,b,d,e=self.fixture()
            if change=='duration':b[0]['duration_time']='0.009000'
            if change=='samples':e['frames'][0]['nb_samples']=511
            if change=='pts':b[0]['pts_time']='0.011000'
            if change=='missing':e['frames']=[]
            if change=='clock':e['streams'][0]['time_base']='1/100'
            with self.assertRaises(ValueError):normalize_rounding(a,b,d,e)

    def test_payload_and_packet_side_data_still_fail(self):
        for change in ('data_hash','side_data_list'):
            a,b,d,e=self.fixture()
            b[0][change]='changed'
            x,y,_=normalize_rounding(a,b,d,e)
            with self.assertRaises(ValueError):compare_packets(x,y)
