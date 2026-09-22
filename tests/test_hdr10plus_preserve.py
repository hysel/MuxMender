import tempfile
import unittest
from pathlib import Path
from hdr10plus_preserve import frame_records
from hdr10plus_preserve import preservation_mux_command, preserved_tracks_command
from fractions import Fraction


class FrameRecordsTests(unittest.TestCase):
    def test_cover_is_copied_from_source_not_replaced_with_movie(self):
        streams=[dict(index=0,codec_type='video'), dict(index=1,codec_type='audio'),
                 dict(index=2,codec_type='video',disposition={'attached_pic':1})]
        command=preserved_tracks_command('ffmpeg','packaged','source','output',streams)
        maps=[command[i+1] for i,x in enumerate(command) if x=='-map']
        self.assertEqual(maps,['0:v:0','1:1','1:2'])

    def test_final_copy_maps_original_tracks_tags_chapters_and_flags(self):
        streams=[dict(index=0,codec_type='video'),dict(index=1,codec_type='audio',
                 disposition={'default':1}),dict(index=2,codec_type='subtitle'),
                 dict(index=3,codec_type='attachment')]
        command=preserved_tracks_command('ffmpeg','packaged.mkv','source.mkv','out.mkv',streams)
        maps=[command[i+1] for i,x in enumerate(command) if x=='-map']
        self.assertEqual(maps,['0:v:0','1:1','1:2','1:3'])
        self.assertIn('-copyts',command)
        self.assertIn('-n',command)
        self.assertEqual(command[command.index('-map_chapters')+1],'1')
        self.assertEqual(command[command.index('-disposition:1')+1],'default')
        self.assertEqual(command[command.index('-disposition:2')+1],'0')
        self.assertEqual(command[command.index('-c')+1],'copy')
    def test_shared_finalizer_disables_lacing_without_dropping_tracks(self):
        command=preservation_mux_command('mkvmerge','output.mkv','0:0,1:1,1:2',Fraction(24000,1001),
                                         'times.txt',['--language','0:eng'],'video.hevc','source.mkv')
        self.assertEqual(command.count('--disable-lacing'),1)
        self.assertLess(command.index('--disable-lacing'),command.index('video.hevc'))
        self.assertEqual(command[-2:],['--no-video','source.mkv'])
        self.assertIn('0:24000/1001fps',command)
        self.assertNotIn('--no-audio',command)
    def parse(self,text):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'frames.json';path.write_text(text,encoding='utf-8')
            return list(frame_records(path))

    def test_repeated_hdr_values_survive(self):
        self.assertEqual(self.parse('{"frames":[{"anchor":1,"anchor":2}]}'),[{'anchor':[1,2]}])

    def test_record_across_read_boundaries(self):
        value='a'*70000
        self.assertEqual(self.parse('{"frames":[{"value":"'+value+'"},{}]}'),[{'value':value},{}])

    def test_empty_array(self):
        self.assertEqual(self.parse('{"frames":[]}'),[])

    def test_malformed_and_truncated_rejected(self):
        for text in ('{}','{"frames":[{}','{"frames":[{},]}','{"frames":[{} {}]}','{"frames":[]}garbage'):
            with self.subTest(text=text),self.assertRaises(ValueError):self.parse(text)
