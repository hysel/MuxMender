"""Generated-only evidence for reusing a strict full-frame video decode."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from dv_full_file import frame_evidence,final_decode_maps
from native_pipeline import strict_decode_line,stage,decode_maps_after_frame_audit


class DecodeEvidenceTests(unittest.TestCase):
    def test_shared_workflow_reuses_video_but_still_decodes_audio(self):
        from types import SimpleNamespace
        from auto_optimize import Workflow
        ffmpeg,ffprobe=shutil.which('ffmpeg'),shutil.which('ffprobe')
        if not ffmpeg or not ffprobe:self.skipTest('FFmpeg fixture tools unavailable')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'generated.mkv';output=root/'copy.mkv'
            subprocess.run([ffmpeg,'-v','error','-nostdin','-n','-f','lavfi','-i',
                'testsrc2=size=160x90:rate=10','-f','lavfi','-i','sine=frequency=440:sample_rate=48000',
                '-t','1','-c:v','ffv1','-level','3','-c:a','aac',str(source)],
                check=True,capture_output=True,timeout=30)
            shutil.copyfile(source,output)
            work=root/'validation';work.mkdir()
            workflow=Workflow(SimpleNamespace(ffmpeg=ffmpeg,ffprobe=ffprobe,timeout=30),work,lambda:None)
            before=workflow.probe(source);frames=workflow.frame_file(source,'source',before['format'])
            self.assertEqual(workflow.validate(source,output,before,'ffv1','full',frames),10)
            report=json.loads((work/'full-decode-evidence.json').read_text())
            self.assertTrue(report['video_audit_reused']);self.assertEqual(report['audio_maps'],['0:1'])
            log=next(work.glob('*-full-audio-decode.log')).read_text().splitlines()
            command=json.loads(log[0]);self.assertNotIn('0:v:0',command)
            # Matching copied bytes are not proof of decodable audio.
            packet=json.loads(subprocess.check_output([ffprobe,'-v','error','-select_streams','a:0',
                '-show_packets','-show_entries','packet=pos,size','-of','json',str(source)],timeout=30))['packets'][4]
            damaged=bytearray(source.read_bytes());offset=int(packet['pos'])+int(packet['size'])//2
            damaged[offset:offset+12]=b'\xff'*12
            source.write_bytes(damaged);output.write_bytes(damaged)
            bad=root/'damaged-validation';bad.mkdir()
            workflow=Workflow(SimpleNamespace(ffmpeg=ffmpeg,ffprobe=ffprobe,timeout=30),bad,lambda:None)
            before=workflow.probe(source);frames=workflow.frame_file(source,'source',before['format'])
            with self.assertRaises(RuntimeError):workflow.validate(source,output,before,'ffv1','full',frames)

    def test_shared_decode_reuse_never_accepts_header_or_boolean_counts(self):
        for count in (None,0,-1,True,'120',120.0):
            self.assertEqual(decode_maps_after_frame_audit({'streams':[]},count),(['0:v:0','0:a?'],False))

    def test_audio_only_requires_complete_current_video_evidence(self):
        streams={'streams':[dict(index=0,codec_type='video'),dict(index=1,codec_type='audio'),
                            dict(index=3,codec_type='audio'),dict(index=4,codec_type='subtitle')]}
        checks=dict(frames=120,timing_preserved=True,static_hdr_preserved=True,frame_picture_preserved=True,
                    progressive=True,rpu_present_every_frame=True)
        self.assertEqual(final_decode_maps(streams,checks,120),(['0:1','0:3'],True))
        self.assertEqual(final_decode_maps({'streams':[]},checks,120),([],True))
        for key in checks:
            incomplete=dict(checks);incomplete.pop(key)
            with self.subTest(key=key):
                self.assertEqual(final_decode_maps(streams,incomplete,120),(['0:v:0','0:a?'],False))
        self.assertFalse(final_decode_maps(streams,checks,119)[1])
        self.assertFalse(final_decode_maps(streams,dict(checks,frames=0),0)[1])

    def test_frame_audit_rejects_corruption_and_truncation(self):
        ffmpeg,ffprobe=shutil.which('ffmpeg'),shutil.which('ffprobe')
        if not ffmpeg or not ffprobe:self.skipTest('FFmpeg fixture tools unavailable')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'generated.mkv'
            subprocess.run([ffmpeg,'-v','error','-nostdin','-n','-f','lavfi','-i',
                'testsrc2=size=160x90:rate=10','-t','1','-c:v','ffv1','-level','3',
                '-slicecrc','1',str(source)],check=True,capture_output=True,timeout=30)
            stage([ffmpeg,'-v','error','-nostats','-xerror','-nostdin','-i',str(source),
                   '-map','0:v:0','-f','null','-','-progress','pipe:1'],1,
                  timeout=30,stall=0,strict_decode=True)
            packets=json.loads(subprocess.check_output([ffprobe,'-v','error','-select_streams','v:0',
                '-show_packets','-show_entries','packet=pos,size','-of','json',str(source)],timeout=30))['packets']
            data=source.read_bytes();damaged=bytearray(data)
            packet=packets[4];offset=int(packet['pos'])+int(packet['size'])//2
            damaged[offset]^=0xff
            for label,payload in (('corrupted',damaged),('truncated',data[:int(packets[-2]['pos'])+10])):
                with self.subTest(label=label):
                    path=root/(label+'.mkv');path.write_bytes(payload)
                    guard=Mock();guard.duration=1;guard.phase='Generated corruption';guard.allow_hdr10plus=False
                    with self.assertRaises((RuntimeError,ValueError)):
                        frame_evidence(ffprobe,path,root/(label+'.compact'),guard)
                    result=subprocess.run([ffmpeg,'-v','error','-xerror','-nostdin','-i',str(path),
                        '-map','0:v:0','-f','null','-'],capture_output=True,timeout=30)
                    # Some FFmpeg builds exit zero despite these diagnostics.
                    self.assertTrue(result.returncode or result.stderr.strip())
                    with self.assertRaises(RuntimeError):
                        stage([ffmpeg,'-v','error','-nostats','-xerror','-nostdin','-i',str(path),
                            '-map','0:v:0','-f','null','-','-progress','pipe:1'],1,
                            timeout=30,stall=0,strict_decode=True)

    def test_strict_decode_accepts_progress_not_diagnostics(self):
        for line in ('frame= 2','fps=0.0','stream_0_0_q=-0.0','bitrate=N/A','out_time_us=1000000',
                     'out_time_ms=1000000','out_time=00:00:01.000000','total_size=N/A',
                     'dup_frames=0','drop_frames=0','speed=2x','progress=end',''):
            strict_decode_line(line)
        for line in ('[ffv1] slice CRC mismatch','File ended prematurely','error=value'):
            with self.assertRaises(RuntimeError):strict_decode_line(line)


if __name__=='__main__':unittest.main()
