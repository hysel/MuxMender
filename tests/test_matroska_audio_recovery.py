import json
import tempfile
import sys
import subprocess
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import auto_optimize as ao
import matroska_audio_recovery as recovery


ERROR = ('[aost#0:1/copy @ 0x123] Non-monotonic DTS; previous: 484795, current: 484747; '
         'Error submitting a packet to the muxer: Invalid argument')


def data():
    return dict(streams=[dict(index=0, codec_type='video', codec_name='h264',
                             disposition={}, tags={}),
                         dict(index=1, codec_type='audio', codec_name='aac', disposition={})])


class AudioMuxRecoveryTests(unittest.TestCase):
    def test_relay_input_uses_identified_audio_ids_and_retains_subtitles(self):
        original=dict(container=dict(properties=dict(timestamp_scale=1000000)),
                      tracks=[dict(id=4,type='video'),dict(id=9,type='audio',codec='DTS'),
                              dict(id=12,type='subtitles')])
        relay=dict(tracks=[dict(id=3,type='audio',codec='DTS')])
        command=['mkvmerge','-o','out.mkv','--track-order','0:0,1:9,1:12',
                 'video.mkv','--no-video','source.mkv']
        result=recovery.relay_mux_command(command,'source.mkv','relay.mka',original,relay)
        self.assertEqual(result[result.index('--track-order')+1],'0:0,2:3,1:12')
        self.assertEqual(result[result.index('source.mkv')-1],'--no-audio')
        self.assertIn('force_passthrough_packetizer',result)
        self.assertNotIn('--sync',result)
        self.assertEqual(command[-1],'source.mkv')
        with self.assertRaisesRegex(ValueError,'inventory'):
            recovery.relay_mux_command(command,'source.mkv','relay.mka',original,dict(tracks=[]))

    def test_only_full_matroska_copied_audio_failure_qualifies(self):
        self.assertTrue(recovery.eligible('source.mkv', 'out.mkv', data(), 'full-encode', None, ERROR))
        for source, label, hdr, error in [
                ('source.mp4', 'full-encode', None, ERROR),
                ('source.mkv', 'trial', None, ERROR),
                ('source.mkv', 'full-encode', 'hdr10', ERROR),
                ('source.mkv', 'full-encode', None, 'Cancelled'),
                ('source.mkv', 'full-encode', None, ERROR.replace('/copy', '/aac'))]:
            self.assertFalse(recovery.eligible(source, 'out.mkv', data(), label, hdr, error))

    def test_video_only_maps_only_primary_without_timestamp_repair(self):
        video = data()['streams'][0] | dict(pix_fmt='yuv420p')
        with patch.object(ao.mm, 'encoder_options', return_value=['-c:v', 'av1_nvenc']):
            command = ao.encode_command('ffmpeg', 'source.mkv', 'out.mkv',
                dict(codec='av1', encoder='av1_nvenc', quality='compact'), None,
                [video, data()['streams'][1]], video_only=True)
        self.assertEqual(command[command.index('-map')+1], '0:0')
        self.assertIn('-copyts', command)
        self.assertNotIn('-disposition:1', command)
        self.assertNotIn('-fflags', command)
        self.assertEqual(command[command.index('-fps_mode:v:0')+1], 'passthrough')

    def test_missing_tool_does_not_retry(self):
        with patch.object(recovery.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'requires MKVToolNix'):
                recovery.recover(None, 'source.mkv', 'out.mkv', {}, None, data(), 'full-encode', 10, ERROR)

    def test_retry_retains_original_tracks_and_requires_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); source = root/'source.mkv'; source.write_bytes(b'source')
            output = root/'out.mkv'
            work = ao.Workflow(SimpleNamespace(), root, lambda: None)
            calls = []
            def encode(*args, **kwargs):
                self.assertTrue(kwargs['video_only']); Path(args[1]).write_bytes(b'video')
            def mux(command, *args):
                calls.append(command)
                Path(command[command.index('-o')+1]).write_bytes(b'recovered')
            identified = dict(tracks=[dict(id=4, type='video'), dict(id=9, type='audio')])
            with patch.object(recovery.shutil, 'which', return_value='mkvmerge'), \
                    patch.object(recovery.subprocess, 'check_output', return_value=json.dumps(identified)), \
                    patch.object(work, '_encode_preserving_color', side_effect=encode), \
                    patch.object(work, 'execute', side_effect=mux):
                recovery.recover(work, source, output, {}, None, data(), 'full-encode', 10, ERROR)
            self.assertEqual(source.read_bytes(), b'source')
            self.assertEqual(output.read_bytes(), b'recovered')
            self.assertIn('--disable-lacing', calls[0])
            self.assertIn('0:0,1:9', calls[0])
            self.assertNotIn('--sync', calls[0])
            report = json.loads((root/'audio-mux-recovery.json').read_text())
            self.assertTrue(report['validation_required'])
            self.assertEqual(report['state'], 'encoded-awaiting-validation')

    def test_unrelated_failure_propagates_without_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            work = ao.Workflow(SimpleNamespace(), Path(folder), lambda: None)
            with patch('aac_priming.inspect', return_value=[]), \
                    patch.object(work, '_encode_preserving_color', side_effect=RuntimeError('Cancelled')), \
                    patch.object(recovery, 'recover') as retry:
                with self.assertRaisesRegex(RuntimeError, 'Cancelled'):
                    work.encode_preserving_color(Path('source.mkv'), Path('out.mkv'), {}, None,
                                                 data(), 'full-encode', 10)
                retry.assert_not_called()

    def test_qualifying_failure_dispatches_once(self):
        with tempfile.TemporaryDirectory() as folder:
            work = ao.Workflow(SimpleNamespace(), Path(folder), lambda: None)
            with patch('aac_priming.inspect', return_value=[]), \
                    patch.object(work, '_encode_preserving_color', side_effect=RuntimeError(ERROR)), \
                    patch.object(recovery, 'recover') as retry:
                work.encode_preserving_color(Path('source.mkv'), Path('out.mkv'), {}, None,
                                             data(), 'full-encode', 10)
                retry.assert_called_once()

    def test_existing_unregistered_output_is_never_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); output = root/'out.mkv'; output.write_bytes(b'keep')
            work = ao.Workflow(SimpleNamespace(), root, lambda: None)
            identified = dict(tracks=[dict(id=0, type='video'), dict(id=1, type='audio')])
            def mux(command, *args):
                Path(command[command.index('-o')+1]).write_bytes(b'recovered')
            with patch.object(recovery.shutil, 'which', return_value='mkvmerge'), \
                    patch.object(recovery.subprocess, 'check_output', return_value=json.dumps(identified)), \
                    patch.object(work, '_encode_preserving_color'), \
                    patch.object(work, 'execute', side_effect=mux):
                with self.assertRaisesRegex(ValueError, 'unregistered'):
                    recovery.recover(work, root/'source.mkv', output, {}, None,
                                     data(), 'full-encode', 10, ERROR)
            self.assertEqual(output.read_bytes(), b'keep')

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Native media qualification runs on Linux only')
    def test_generated_dts_full_preservation(self):
        ffmpeg = shutil.which('ffmpeg'); ffprobe = shutil.which('ffprobe')
        if not all((ffmpeg, ffprobe, shutil.which('mkvmerge'))):
            self.skipTest('Media tools unavailable')
        with tempfile.TemporaryDirectory(prefix='audio-mux-qualification-', dir='/work') as folder:
            root = Path(folder); source = root/'source.mkv'; output = root/'output.mkv'
            subprocess.run([ffmpeg, '-v', 'error', '-nostdin', '-f', 'lavfi', '-i',
                'testsrc2=size=64x64:rate=24:duration=2', '-f', 'lavfi', '-i',
                'sine=frequency=440:sample_rate=48000:duration=2', '-c:v', 'libx264',
                '-threads:v', '2', '-color_primaries', 'bt709', '-color_trc', 'bt709',
                '-colorspace', 'bt709', '-color_range', 'tv', '-c:a', 'dca',
                '-strict', '-2', '-metadata:s:a:0', 'language=eng', str(source)],
                check=True, capture_output=True, timeout=30)
            args = SimpleNamespace(ffmpeg=ffmpeg, ffprobe=ffprobe, timeout=60, source=source,vmaf_mean=90,vmaf_p5=90)
            work = ao.Workflow(args, root, lambda: None)
            before = work.probe(source)
            frames = work.frame_file(source, 'source', before['format'])
            info = SimpleNamespace(bit_depth=8, hdr=False, dolby_vision=False, mastering_display_metadata=None)
            with patch.object(ao.mm, 'encoder_options', return_value=['-c:v', 'libx264', '-crf', '18']):
                recovery.recover(work, source, output,
                    dict(codec='h264', encoder='libx264', quality='compact'), info,
                    before, 'full-encode', float(before['format']['duration']), ERROR)
            # No changed packet payload/count/timestamps, no audio-clock waiver.
            count = work.validate(source, output, before, 'h264', 'generated-full', frames)
            self.assertEqual(count, 48)
            self.assertTrue(work.quality(source,output,'generated-quality',count,2)['passed'])

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Native media qualification runs on Linux only')
    def test_generated_truehd_full_preservation(self):
        ffmpeg=shutil.which('ffmpeg');ffprobe=shutil.which('ffprobe')
        if not all((ffmpeg,ffprobe,shutil.which('mkvmerge'))):self.skipTest('Media tools unavailable')
        with tempfile.TemporaryDirectory(prefix='truehd-mux-qualification-',dir='/work') as folder:
            root=Path(folder);source=root/'source.mkv';output=root/'output.mkv'
            subprocess.run([ffmpeg,'-v','error','-nostdin','-f','lavfi','-i',
                'testsrc2=size=64x64:rate=24:duration=2','-f','lavfi','-i',
                'sine=frequency=440:sample_rate=48000:duration=2','-c:v','libx264',
                '-threads:v','2','-color_primaries','bt709','-color_trc','bt709',
                '-colorspace','bt709','-color_range','tv','-c:a','truehd','-strict','-2',
                '-metadata:s:a:0','language=eng',str(source)],check=True,capture_output=True,timeout=30)
            args=SimpleNamespace(ffmpeg=ffmpeg,ffprobe=ffprobe,timeout=60,source=source,vmaf_mean=90,vmaf_p5=90)
            work=ao.Workflow(args,root,lambda:None);before=work.probe(source)
            frames=work.frame_file(source,'source',before['format'])
            info=SimpleNamespace(bit_depth=8,hdr=False,dolby_vision=False,mastering_display_metadata=None)
            with patch.object(ao.mm,'encoder_options',return_value=['-c:v','libx264','-crf','18']):
                recovery.recover(work,source,output,dict(codec='h264',encoder='libx264',quality='compact'),
                                 info,before,'full-encode',2,ERROR)
            count=work.validate(source,output,before,'h264','generated-full',frames)
            self.assertEqual(count,48)
            self.assertTrue(work.quality(source,output,'generated-quality',count,2)['passed'])


if __name__ == '__main__':
    unittest.main()
