import unittest
import tempfile
from pathlib import Path
from fractions import Fraction
from unittest.mock import patch, Mock
from types import SimpleNamespace
from mpeg4_timing import Bits, vol_clock, picture_clocks, missing_tail_timestamp, recover_tail_evidence


def pack(bits):
    bits += '0' * (-len(bits) % 8)
    return int(bits, 2).to_bytes(len(bits)//8, 'big')


def vol():
    # Simple profile, square pixels, rectangular, a 1000-tick clock.
    return pack('0' + format(1,'08b') + '0' + '0001' + '0' + '00'
                + '1' + format(1000,'016b') + '1' + '0')


def vop(kind, tick, coded=True, seconds=0):
    return (b'\x00\x00\x01\xb6' + pack(format(kind,'02b')
            + '1'*seconds + '0' + '1' + format(tick,'010b')
            + '1' + str(int(coded))))


class MPEG4TimingTests(unittest.TestCase):
    def test_recovery_admission_uses_codec_not_extension(self):
        from auto_optimize import Workflow
        with tempfile.TemporaryDirectory() as folder:
            for suffix in ('.avi','.mp4','.mkv','.mov'):
                with self.subTest(suffix=suffix):
                    source=Path(folder)/('original'+suffix)
                    workflow=Workflow.__new__(Workflow)
                    workflow.args=SimpleNamespace(source=source,ffmpeg='ffmpeg')
                    workflow.directory=Path(folder)
                    workflow.probe=Mock(return_value={'streams':[{'codec_type':'video','codec_name':'mpeg4'}],
                                                    'format':{'duration':'2'}})
                    workflow.execute=Mock(side_effect=RuntimeError('extraction reached'))
                    with self.assertRaisesRegex(RuntimeError,'extraction reached'):
                        workflow.recover_mpeg4_tail(source,Path(folder)/'frames.txt','source')
                    command=workflow.execute.call_args.args[0]
                    self.assertEqual(command[command.index('-bsf:v')+1],'dump_extra')
                    with self.assertRaisesRegex(ValueError,'source clock recovery'):
                        workflow.recover_mpeg4_tail(Path(folder)/'output.mkv',None,'output')
                    workflow.probe.return_value['streams'][0]['codec_name']='h264'
                    with self.assertRaisesRegex(ValueError,'not MPEG-4'):
                        workflow.recover_mpeg4_tail(source,None,'source')

    def test_group_clock_and_b_reordering(self):
        group=b'\x00\x00\x01\xb3'+pack('00000'+'000000'+'1'+'000010'+'00')
        raw=b'\x00\x00\x01\x20'+vol()+group+vop(0,0)+vop(1,80)+vop(2,40)
        self.assertEqual([r['time'] for r in picture_clocks(raw)],
                         [Fraction(2),Fraction(51,25),Fraction(52,25)])

    def test_invalid_group_clock(self):
        for minute in (60,63):
            raw=b'\x00\x00\x01\xb3'+pack('00000'+format(minute,'06b')+'1'+'000000'+'00')
            with self.assertRaisesRegex(ValueError,'Invalid MPEG-4 group'):picture_clocks(raw)

    def test_vol(self):
        self.assertEqual(vol_clock(vol()), (1000,10))

    def test_presentation_order_and_noncoded_picture(self):
        raw=b'\x00\x00\x01\x20'+vol()+vop(0,0)+vop(1,80)+vop(2,40)+vop(1,80,False)
        rows=picture_clocks(raw)
        self.assertEqual([r['pict_type'] for r in rows],list('IBP'))
        self.assertEqual([r['time'] for r in rows],[Fraction(0),Fraction(1,25),Fraction(2,25)])

    def test_truncated_and_unsupported(self):
        with self.assertRaises(ValueError): Bits(b'').get(1)
        with self.assertRaises(ValueError): picture_clocks(vop(0,0))
        with self.assertRaises(ValueError): picture_clocks(b'\x00\x00\x01\xb3\x00')

    def test_b_picture_clock_across_second_boundary(self):
        raw=b'\x00\x00\x01\x20'+vol()+vop(0,960)+vop(1,40,seconds=1)+vop(2,0,seconds=1)
        rows=picture_clocks(raw)
        self.assertEqual([r['time'] for r in rows],[Fraction(24,25),Fraction(1),Fraction(26,25)])
        self.assertEqual([r['pict_type'] for r in rows],list('IBP'))

    def test_duplicate_coded_clocks_are_not_accepted(self):
        raw=b'\x00\x00\x01\x20'+vol()+vop(0,0)+vop(1,0)
        with self.assertRaisesRegex(ValueError,'duplicate'):picture_clocks(raw)

    def test_insufficient_or_nonmissing_tail_is_not_repaired(self):
        clocks=[dict(time=Fraction(i,25),pict_type='P') for i in range(20)]
        frames=[dict(best_effort_timestamp_time=str(Fraction(i,25)),pict_type='P') for i in range(20)]
        with patch('mpeg4_timing.picture_clocks',return_value=clocks):
            with self.assertRaisesRegex(ValueError,'already has'):missing_tail_timestamp(b'',frames)
            with self.assertRaisesRegex(ValueError,'Insufficient'):missing_tail_timestamp(b'',frames[:10])

    def test_recovery_requires_all_known_clock_evidence(self):
        clocks=[dict(time=Fraction(i,25),pict_type='P') for i in range(20)]
        frames=[dict(best_effort_timestamp_time=str(Fraction(i,25)+5),pict_type='P') for i in range(20)]
        frames[-1]['best_effort_timestamp_time']='N/A'
        with patch('mpeg4_timing.picture_clocks',return_value=clocks):
            self.assertEqual(missing_tail_timestamp(b'',frames),Fraction(144,25))
            frames[2]['best_effort_timestamp_time']='5.081'
            with self.assertRaisesRegex(ValueError,'disagrees'): missing_tail_timestamp(b'',frames)
            frames[2]['best_effort_timestamp_time']='N/A'
            with self.assertRaisesRegex(ValueError,'Only the final'): missing_tail_timestamp(b'',frames)

    def test_no_output_timestamp_or_fps_needed(self):
        raw=b'\x00\x00\x01\x20'+vol()+b''.join(vop(1,i*40) for i in range(20))
        frames=[dict(best_effort_timestamp_time=str(Fraction(i,25)+9),pict_type='P') for i in range(20)]
        frames[-1].pop('best_effort_timestamp_time')
        self.assertEqual(missing_tail_timestamp(raw,frames),Fraction(244,25))
        frames[3]['pict_type']='B'
        with self.assertRaisesRegex(ValueError,'order/type'): missing_tail_timestamp(raw,frames)

    def test_recovery_retains_original_evidence_and_checks_alignment(self):
        raw=b'\x00\x00\x01\x20'+vol()+b''.join(vop(1,i*40) for i in range(20))
        frames=[dict(best_effort_timestamp_time=str(Fraction(i,25)+9),pict_type='P') for i in range(20)]
        frames[-1]['best_effort_timestamp_time']='N/A'
        lines=''.join('width=1280|best_effort_timestamp_time='+f['best_effort_timestamp_time']+'\n' for f in frames)
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.txt';target=Path(folder)/'recovered.txt'
            source.write_text(lines)
            result=recover_tail_evidence(raw,frames,source,target)
            self.assertEqual(result['recovered_timestamp'],'9.760000000')
            self.assertEqual(source.read_text(),lines)
            self.assertNotIn('N/A',target.read_text())
            with self.assertRaisesRegex(ValueError,'new evidence'):recover_tail_evidence(raw,frames,source,target)
            frames[2]['best_effort_timestamp_time']='9.0800001'
            with self.assertRaisesRegex(ValueError,'differs'):recover_tail_evidence(raw,frames,source,Path(folder)/'other')


if __name__=='__main__': unittest.main()
