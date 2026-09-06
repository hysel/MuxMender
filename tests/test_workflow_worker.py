import unittest
from workflow_worker import compare_packets


class WorkerValidationTests(unittest.TestCase):
    def test_interleaving_is_not_track_content(self):
        a=[dict(stream_index=s,pts_time=str(t),data_hash=f'{s}-{t}') for s,t in ((1,0),(1,1),(2,0),(2,1))]
        b=[a[0],a[2],a[1],a[3]]
        self.assertEqual(compare_packets(a,b),0)
        with self.assertRaises(ValueError):compare_packets(a,[a[1],a[2],a[0],a[3]])
        with self.assertRaises(ValueError):compare_packets(a,b[:-1])
        with self.assertRaises(ValueError):compare_packets(a,[dict(p,stream_index=3) for p in b])

    def test_missing_audio_duration_needs_next_pts_evidence(self):
        a=[dict(stream_index=1,pts_time='-0.023',duration_time='0.023',data_hash='same'),dict(stream_index=1,pts_time='0.0',data_hash='next')]
        b=[dict(stream_index=1,pts_time='-0.023',data_hash='same'),dict(stream_index=1,pts_time='0.0',data_hash='next')]
        self.assertEqual(compare_packets(a,b,True),1)
        with self.assertRaises(ValueError):compare_packets(a,b,False)
        with self.assertRaises(ValueError):compare_packets(a[:1],b[:1],True)
        b[0]['pts_time']='0.01'
        with self.assertRaises(ValueError):compare_packets(a,b,True)

    def test_payload_or_padding_changes_are_not_allowed(self):
        a=[dict(stream_index=1,pts_time='0',data_hash='same',side_data_list=[{'skip_samples':1024}])]
        for b in ([dict(stream_index=1,pts_time='0',data_hash='different',side_data_list=[{'skip_samples':1024}])],
                  [dict(stream_index=1,pts_time='0',data_hash='same',side_data_list=[{'skip_samples':0}])]):
            with self.assertRaises(ValueError):compare_packets(a,b,True)
