import unittest
from unittest.mock import patch
from types import SimpleNamespace
from decoder_context import metadata_reader_options
from dv_preservation_test import frame_info


class MetadataReaderTests(unittest.TestCase):
    def test_slice_context_and_bounds(self):
        self.assertEqual(metadata_reader_options(4),['-threads','4','-thread_type','slice'])
        for value in (0,65,True,2.5,'2'):
            with self.assertRaises(ValueError):metadata_reader_options(value)

    def test_dv_reader_uses_slice_context_and_still_rejects_errors(self):
        with patch('dv_preservation_test.subprocess.run',return_value=SimpleNamespace(stdout='{"frames":[]}',stderr='')) as run:
            self.assertEqual(frame_info('ffprobe','input.mkv'),[])
            cmd=run.call_args.args[0]
            self.assertEqual(cmd[cmd.index('-thread_type')+1],'slice')
        with patch('dv_preservation_test.subprocess.run',return_value=SimpleNamespace(stdout='{"frames":[]}',stderr='decoder error')):
            with self.assertRaisesRegex(ValueError,'Decoder errors'):frame_info('ffprobe','input.mkv')
