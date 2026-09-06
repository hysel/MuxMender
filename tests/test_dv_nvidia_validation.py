import tempfile
import unittest
from pathlib import Path

from dv_nvidia_validation import compare_frames, validate_source_frames, grouped_packets, compare_track_packets


def record(pts, red='35400/50000', extra=''):
    return (f'frame|best_effort_timestamp_time={pts}|interlaced_frame=0|repeat_pict=0'
            '|side_datum/dolby_vision_rpu_data:side_data_type=Dolby Vision RPU Data'
            '|side_datum/mastering_display_metadata:side_data_type=Mastering display metadata'
            f'|side_datum/mastering_display_metadata:red_x={red}{extra}\n')


class NvidiaDVFrameTests(unittest.TestCase):
    def test_aac_rounding_requires_exact_pts_bytes_order_and_pcm_followup(self):
        streams=[dict(index=1,codec_type='audio',codec_name='aac',time_base='1/1000')]
        a=dict(stream_index=1,pts_time='0.065',duration_time='0.043',data_hash='same')
        self.assertEqual(compare_track_packets([a],[dict(a,duration_time='0.042')],streams),{1:1})
        for bad in (dict(a,pts_time='0.066'),dict(a,data_hash='changed'),dict(a,duration_time='0.040')):
            with self.assertRaises(ValueError): compare_track_packets([a],[bad],streams)
        with self.assertRaises(ValueError):
            compare_track_packets([a],[dict(a,duration_time='0.042')],[dict(streams[0],codec_name='eac3')])

    def test_packets_allow_cross_track_interleaving_only(self):
        a = dict(stream_index=1, pts_time='0', data_hash='a')
        b = dict(stream_index=1, pts_time='1', data_hash='b')
        c = dict(stream_index=2, pts_time='0', data_hash='c')
        self.assertEqual(grouped_packets([a,b,c]), grouped_packets([a,c,b]))
        self.assertNotEqual(grouped_packets([a,b,c]), grouped_packets([b,a,c]))
        self.assertNotEqual(grouped_packets([a,b,c]), grouped_packets([a,c]))
        self.assertNotEqual(grouped_packets([a,b,c]), grouped_packets([a,dict(b,pts_time='2'),c]))

    def test_all_frames_and_static_hdr_are_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder)/'a', Path(folder)/'b'
            a.write_text(record(0)+record(.042))
            b.write_text(record(0)+record(.042, '35401/50000'))
            self.assertEqual(validate_source_frames(a, [0, .042]), 2)
            self.assertEqual(compare_frames(a,b)['static_hdr_rounding_frames'], 1)
            for content in (record(0), record(0)+record(.083),
                            record(0)+record(.042,'35402/50000'),
                            record(0)+record(.042,extra='|side_datum/hdr10:side_data_type=HDR Dynamic Metadata SMPTE2094-40 (HDR10+)')):
                b.write_text(content)
                with self.assertRaises(ValueError):
                    compare_frames(a,b)

    def test_missing_rpu_and_interlacing_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'a'
            for text in (record(0).replace('Dolby Vision RPU Data','unrecognized'),
                         record(0).replace('interlaced_frame=0','interlaced_frame=1')):
                p.write_text(text)
                with self.assertRaises(ValueError):
                    validate_source_frames(p,[0])
