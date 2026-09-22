import unittest
from fractions import Fraction
from reference_sampling import plan_keyframe, verify_source_slice, verify_decoded_slice, parse_framehash


class ReferenceSamplingTests(unittest.TestCase):
    def test_selects_dts_minus_source_tick_not_fixed_millisecond(self):
        packets=[dict(flags='K_',pts_time='478.395',dts_time='478.311'),
                 dict(flags='K_',pts_time='490.395',dts_time='490.311')]
        for base in ('1/1000','1/90000'):
            plan=plan_keyframe(packets,base,477.72,10,900)
            self.assertEqual(plan['seek'],Fraction('478.311')-Fraction(base))

    def test_rejects_missing_dts_out_of_window_and_source_tail(self):
        for packet,end in [(dict(flags='K_',pts_time='478.395'),900),
                           (dict(flags='K_',pts_time='500',dts_time='499'),900),
                           (dict(flags='K_',pts_time='478.395',dts_time='478.311'),480)]:
            with self.assertRaises(ValueError):plan_keyframe([packet],'1/1000',477.72,10,end)

    def rows(self,offset=0):
        return [dict(data_hash=str(i),pts_time=str(i+offset),dts_time=str(i+offset),
                     duration_time='1') for i in range(4)]

    def test_shared_shift_preserves_audio_video_alignment(self):
        shift=verify_source_slice(self.rows(),self.rows(-1)[1:3])
        self.assertEqual(shift,-1)
        self.assertEqual(verify_source_slice(self.rows(),self.rows(-1)[2:],shift),shift)
        with self.assertRaises(ValueError):verify_source_slice(self.rows(),self.rows(-2)[2:],shift)

    def test_rejects_drift_duration_and_payload_changes(self):
        for key,value in [('pts_time','1.003'),('duration_time','1.003'),('data_hash','changed')]:
            sample=self.rows();sample[1][key]=value
            with self.assertRaises(ValueError):verify_source_slice(self.rows(),sample)

    def test_rejects_ambiguous_or_empty_slice(self):
        with self.assertRaises(ValueError):verify_source_slice(self.rows()*2,self.rows())
        with self.assertRaises(ValueError):verify_source_slice(self.rows(),[])

    def test_missing_initial_dts_requires_exact_pixels_and_display_timing(self):
        source=self.rows();sample=self.rows(-1)
        del sample[0]['dts_time'];del sample[1]['dts_time']
        a=[dict(hash=str(i),size=10,pts=str(i)) for i in range(4)]
        b=[dict(hash=str(i),size=10,pts=str(i-1)) for i in range(4)]
        with self.assertRaises(ValueError):verify_source_slice(source,sample,reorder_depth=2)
        self.assertEqual(verify_source_slice(source,sample,reorder_depth=2,
                         decoded_source=a,decoded_sample=b),-1)
        with self.assertRaises(ValueError):verify_source_slice(source,sample,reorder_depth=1,
                         decoded_source=a,decoded_sample=b)
        b[2]['hash']='corrupt'
        with self.assertRaises(ValueError):verify_source_slice(source,sample,reorder_depth=2,
                         decoded_source=a,decoded_sample=b)

    def test_missing_interior_dts_cannot_use_initial_reorder_exception(self):
        sample=self.rows();del sample[1]['dts_time']
        a=[dict(hash=str(i),size=10,pts=str(i)) for i in range(4)]
        with self.assertRaises(ValueError):verify_source_slice(self.rows(),sample,reorder_depth=3,
                         decoded_source=a,decoded_sample=a)

    def test_decoded_gap_or_changed_timing_rejected(self):
        a=[dict(hash=str(i),size=10,pts=str(i)) for i in range(4)]
        with self.assertRaises(ValueError):verify_decoded_slice(a,[a[0],a[2]])
        b=[dict(x) for x in a];b[2]['pts']='2.001'
        with self.assertRaises(ValueError):verify_decoded_slice(a,b)

    def test_framehash_parser_keeps_exact_timebase(self):
        rows=parse_framehash('#tb 0: 1/1000\n0, 1, 2, 40, 32, abcd\n')
        self.assertEqual(rows,[dict(pts='1/500',size=32,hash='abcd')])
        with self.assertRaises(ValueError):parse_framehash('0,1,2,3,4,abc')

    def test_requires_complete_gop_end(self):
        packets=[dict(flags='K_',pts_time='6',dts_time='5.9')]
        with self.assertRaisesRegex(ValueError,'GOP boundary'):
            plan_keyframe(packets,'1/1000',4,4,20)

    def test_source_driven_long_gop_search_remains_bounded(self):
        packets=[dict(flags='K_',pts_time='6',dts_time='5.9'),
                 dict(flags='K_',pts_time='18',dts_time='17.9')]
        plan=plan_keyframe(packets,'1/1000',4,4,40,search_span=15)
        self.assertEqual(plan['seconds'],12)
        with self.assertRaises(ValueError):
            plan_keyframe(packets,'1/1000',4,4,40,search_span=61)

    def test_avi_clock_quantization_does_not_allow_pixel_changes_or_drift(self):
        a=[dict(hash=str(i),size=10,pts=str(i)) for i in range(4)]
        b=[dict(x) for x in a];b[1]['pts']='1.001'
        self.assertEqual(verify_decoded_slice(a,b,tolerance=Fraction(2,1000)),0)
        b[2]['pts']='2.003'
        with self.assertRaises(ValueError):verify_decoded_slice(a,b,tolerance=Fraction(2,1000))
        b[2]['pts']='2';b[2]['hash']='different'
        with self.assertRaises(ValueError):verify_decoded_slice(a,b,tolerance=Fraction(2,1000))
