import tempfile
import unittest
from pathlib import Path

from dv_full_file import compare_frames, validate_source_frames, grouped_packets, compare_track_packets


def record(pts, red='35400/50000', extra=''):
    return (f'frame|best_effort_timestamp_time={pts}|interlaced_frame=0|repeat_pict=0'
            '|width=3840|height=1608|pix_fmt=yuv420p10le|sample_aspect_ratio=1:1'
            '|side_datum/dolby_vision_rpu_data:side_data_type=Dolby Vision RPU Data'
            '|side_datum/mastering_display_metadata:side_data_type=Mastering display metadata'
            f'|side_datum/mastering_display_metadata:red_x={red}{extra}\n')


class NvidiaDVFrameTests(unittest.TestCase):
    def test_legacy_evidence_needs_refresh_not_a_media_rejection(self):
        from dv_full_file import picture_evidence_complete
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'evidence'
            p.write_text(record(0))
            self.assertTrue(picture_evidence_complete(p))
            p.write_text(record(0)+record(.042).replace('|width=3840',''))
            self.assertFalse(picture_evidence_complete(p))

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

    def test_missing_aac_duration_requires_decoded_followup_without_weakening_packet_checks(self):
        streams=[dict(index=1,codec_type='audio',codec_name='aac',time_base='1/1000')]
        a=dict(stream_index=1,pts_time='0.031',dts_time='0.031',duration_time='0.042',data_hash='same')
        b={k:v for k,v in a.items() if k!='duration_time'}
        self.assertEqual(compare_track_packets([a],[b],streams),{1:1})
        for bad in (dict(b,pts_time='0.032'),dict(b,data_hash='changed')):
            with self.assertRaises(ValueError):compare_track_packets([a],[bad],streams)
        with self.assertRaises(ValueError):compare_track_packets([b],[a],streams)

    def test_decoded_duration_proof_rejects_equal_audio_with_shifted_timing(self):
        from dv_full_file import decoded_track_proof
        with tempfile.TemporaryDirectory() as folder:
            calls=[]
            def execute(command,label):
                calls.append(command)
                pts=0 if len(calls)==1 else 100
                Path(command[-1]).write_text('#tb 0: 1/48000\n0, 0, '+str(pts)+', 1024, 8192, '+'a'*64+'\n')
            with self.assertRaisesRegex(ValueError,'presentation timing'):
                decoded_track_proof(['ffmpeg'],'source','output',1,folder,execute)
            self.assertTrue(all('-copyts' in command and 'pcm_f64le' in command for command in calls))

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

    def test_picture_mismatch_identifies_field_and_frame_without_relaxing_check(self):
        with tempfile.TemporaryDirectory() as folder:
            a,b=Path(folder)/'source',Path(folder)/'output'
            a.write_text(record(0,extra='|chroma_location=topleft'))
            b.write_text(record(0,extra='|chroma_location=left'))
            with self.assertRaisesRegex(ValueError,'chroma_location.*topleft'):
                compare_frames(a,b)
