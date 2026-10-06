import unittest
from runtime_support import bounded_ffmpeg_threads


class ThreadBudgetTests(unittest.TestCase):
    def test_per_input_and_gpu_output_defaults(self):
        command=['ffmpeg','-i','source.mkv','-i','reference.mkv','-c:v:0','hevc_nvenc','-cq','24','-pix_fmt','p010le','out.mkv']
        result=bounded_ffmpeg_threads(command)
        self.assertEqual(result.count('-threads'),2)
        self.assertEqual(result[result.index('-threads:v')+1],'2')
        self.assertEqual(result[result.index('-cq')+1],'24')
        self.assertEqual(result[result.index('-pix_fmt')+1],'p010le')
        self.assertEqual(result[-1],'out.mkv')
        self.assertEqual(command.count('-threads'),0)
        self.assertEqual(bounded_ffmpeg_threads(result),result)

    def test_explicit_settings_are_not_overridden(self):
        command=['ffmpeg','-filter_threads','4','-filter_complex_threads','3','-threads','6','-thread_type','slice','-i','source',
                 '-c:v:0','av1_nvenc','-threads:v','1','out']
        self.assertEqual(bounded_ffmpeg_threads(command),command)

    def test_no_effect_on_non_ffmpeg_or_copy_codec(self):
        for command in (['ffprobe','-threads','4','-show_frames','source'],['python3','worker.py']):
            self.assertEqual(bounded_ffmpeg_threads(command),command)
        result=bounded_ffmpeg_threads(['ffmpeg','-i','source','-c','copy','out'])
        self.assertNotIn('-threads:v',result)

    def test_later_input_explicit_setting_remains_scoped(self):
        result=bounded_ffmpeg_threads(['ffmpeg','-i','a','-threads','7','-i','b','-f','null','-'])
        self.assertEqual(result[result.index('-i')-2:result.index('-i')],['-threads','2'])
        self.assertIn('7',result)
        self.assertEqual(result.count('-threads'),2)

    def test_qualified_override_only_changes_implicit_input_workers(self):
        command=['ffmpeg','-i','source','-threads','1','-i','reference',
                 '-c:v:0','hevc_nvenc','-cq','24','output.mkv']
        result=bounded_ffmpeg_threads(command,decoder_threads=4)
        self.assertEqual(result[result.index('-i')-2:result.index('-i')],['-threads','4'])
        self.assertIn(['-threads','1'],[result[i:i+2] for i in range(len(result)-1)])
        self.assertEqual(result[result.index('-threads:v')+1],'2')
        for flag in ('-filter_threads','-filter_complex_threads'):
            self.assertEqual(result[result.index(flag)+1],'2')
        self.assertEqual(bounded_ffmpeg_threads(result),result)

    def test_invalid_worker_budget_is_not_unbounded(self):
        for value in (0,-1,8,True,2.0,'4',None):
            with self.subTest(value=value),self.assertRaises(ValueError):
                bounded_ffmpeg_threads(['ffmpeg','-i','source','output'],decoder_threads=value)
