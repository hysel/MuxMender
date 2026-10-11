import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from dts_terminal_duration import terminal_plan


def packets():
    return [dict(data_hash='SHA256:aaa',size='1884',flags='K__',pts_time='0.000000',
                 dts_time='0.000000',duration_time='0.010000'),
            dict(data_hash='SHA256:bbb',size='1884',flags='K__',pts_time='0.010000',
                 dts_time='0.010000',duration_time='0.005000',side_data_list=[
                 dict(side_data_type='Skip Samples',skip_samples=0,discard_padding=256)])]


class DTSTerminalDurationTests(unittest.TestCase):
    def plan(self,source,output):return terminal_plan(source,output,'1/1000',48000,512)

    def test_restores_exact_source_metadata_not_a_validation_allowance(self):
        source=packets();output=copy.deepcopy(source);output[-1]['duration_time']='0.010000'
        result=self.plan(source,output)
        self.assertEqual(result['packet'],1)
        self.assertEqual(result['duration_ticks'],5)
        self.assertEqual(result['frame_samples'],512)
        self.assertEqual(source,packets())

    def test_equal_packets_need_no_remux(self):
        self.assertIsNone(self.plan(packets(),packets()))

    def test_changed_payload_clock_or_padding_is_never_repaired(self):
        for key,value in [('data_hash','SHA256:changed'),('pts_time','0.011000'),
                          ('dts_time','0.011000'),('flags','__'),('side_data_list',[])]:
            output=packets();output[-1][key]=value;output[-1]['duration_time']='0.010000'
            with self.assertRaises(ValueError):self.plan(packets(),output)

    def test_nonterminal_missing_or_unexplained_duration_is_rejected(self):
        for mutate in [lambda p:p.pop(),lambda p:p[0].update(duration_time='0.020000'),
                       lambda p:p[-1].update(duration_time='0.004000'),
                       lambda p:p[-1].update(duration_time='0.025000')]:
            output=packets();mutate(output)
            with self.assertRaises(ValueError):self.plan(packets(),output)

    def test_missing_hash_and_nonrepresentable_clock_are_rejected(self):
        source=packets();source[0].pop('data_hash')
        output=packets();output[-1]['duration_time']='0.010000'
        with self.assertRaises(ValueError):self.plan(source,output)
        with self.assertRaises(ValueError):terminal_plan(packets(),output,'1/60',48000,512)

    def test_matching_durations_do_not_add_an_extra_validation_gate(self):
        source=packets();output=packets();output[0]['pts_time']='0.001000'
        self.assertIsNone(self.plan(source,output))

    @unittest.skipUnless(sys.platform=='linux','Native fixtures run on Linux only')
    def test_generated_multitrack_full_recovery(self):
        import auto_optimize as ao
        import matroska_audio_recovery as recovery
        ffmpeg=shutil.which('ffmpeg');ffprobe=shutil.which('ffprobe')
        if not all((ffmpeg,ffprobe,shutil.which('mkvmerge'))):self.skipTest('Media tools unavailable')
        with tempfile.TemporaryDirectory(prefix='dts-duration-',dir='/work') as folder:
            root=Path(folder);source=root/'source.mkv';output=root/'output.mkv'
            subprocess.run([ffmpeg,'-v','error','-nostdin','-f','lavfi','-i',
                'testsrc2=size=64x64:rate=24:duration=2','-f','lavfi','-i',
                'sine=frequency=440:sample_rate=48000:duration=2','-f','lavfi','-i',
                'sine=frequency=660:sample_rate=48000:duration=2','-map','0:v','-map','1:a',
                '-map','2:a','-c:v','libx264','-threads:v','2','-color_primaries','bt709',
                '-color_trc','bt709','-colorspace','bt709','-color_range','tv','-c:a','dca',
                '-strict','-2','-metadata:s:a:0','language=eng','-metadata:s:a:1','language=fra',
                str(source)],capture_output=True,check=True,timeout=30)
            options=SimpleNamespace(ffmpeg=ffmpeg,ffprobe=ffprobe,source=source,timeout=60)
            work=ao.Workflow(options,root,lambda:None);before=work.probe(source)
            frames=work.frame_file(source,'source',before['format'])
            info=SimpleNamespace(bit_depth=8,hdr=False,dolby_vision=False,mastering_display_metadata=None)
            error='[aost#0:1/copy @ 0x123] Non-monotonic DTS; Error submitting a packet to the muxer: Invalid argument'
            with patch.object(ao.mm,'encoder_options',return_value=['-c:v','libx264','-crf','18']):
                recovery.recover(work,source,output,dict(codec='h264',encoder='libx264',quality='compact'),
                                 info,before,'full-encode',2,error)
            self.assertEqual(work.validate(source,output,before,'h264','multitrack-full',frames),48)
            self.assertEqual(len([s for s in work.probe(output)['streams'] if s['codec_type']=='audio']),2)


if __name__=='__main__':unittest.main()
