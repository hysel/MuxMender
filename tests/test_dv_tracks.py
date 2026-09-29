import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import auto_optimize as ao
import dv_tracks
from test_auto_optimize import source_data


class DVTrackTests(unittest.TestCase):
    def test_primary_ignores_unlabelled_cover_and_keeps_multiple_video(self):
        streams=[dict(index=0,codec_type='video',codec_name='mjpeg',disposition={'attached_pic':1}),
                 dict(index=1,codec_type='video'),dict(index=2,codec_type='video')]
        self.assertIs(dv_tracks.primary(streams),streams[1])

    def check_packets(self,*,bounded=False,corrupt=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);before=source_data();before['streams'][0]['codec_name']='hevc'
            second=copy.deepcopy(before['streams'][0]);second.update(index=1,codec_name='h264')
            before['streams'].append(second);after=copy.deepcopy(before)
            line=lambda timestamp,hash_value:f'packet|pts_time={timestamp}|dts_time={timestamp}|duration_time=1|data_hash={hash_value}\n'
            source=root/'source.txt';output=root/'output.txt'
            source.write_text(line(0,'a')+line(1,'b'))
            output.write_text(line(0,'wrong' if corrupt else 'a')+('' if bounded else line(1,'b')))
            with patch.object(ao.Workflow,'probe',side_effect=[before,after]), \
                 patch.object(ao.Workflow,'copied_packets',side_effect=[{1:source},{1:output}]):
                return dv_tracks.verify('ffmpeg','ffprobe','source','output',root,end_time=1 if bounded else None)

    def test_secondary_packets_are_verified(self):
        self.assertEqual(self.check_packets(),[1])
        with self.assertRaises(ValueError):self.check_packets(corrupt=True)

    def test_sample_prefix_keeps_exact_secondary_payload(self):
        self.assertEqual(self.check_packets(bounded=True),[1])
