import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import encoder_capabilities as ec


def adapter(cap='8.9', driver='580', identity='GPU-fixture'):
    return dict(uuid=identity, name='Fixture GPU', driver=driver, memory_mib='8192',
                profile=ec.nvidia_profile(cap))


class NvidiaProfileTests(unittest.TestCase):
    def test_generation_hints_never_exclude_codec(self):
        for cap, name in [('6.1','Pascal'),('7.0','Volta'),('7.5','Turing'),('8.6','Ampere'),
                          ('8.9','Ada'),('12.0','Blackwell'),('99.0','Unknown')]:
            profile=ec.nvidia_profile(cap)
            self.assertEqual(profile['generation'],name)
            self.assertTrue(profile['advisory'])
            self.assertEqual(set(profile['codec_order']),{'hevc','av1'})
        self.assertEqual(ec.codec_order('nvidia',[adapter()])[0],'av1')
        self.assertEqual(ec.codec_order('nvidia',[adapter(),adapter('7.5')])[0],'hevc')
        self.assertEqual(ec.codec_order('amd',[adapter()])[0],'hevc')

    @patch.object(ec.subprocess,'check_output')
    def test_old_smi_fallback_retains_identity(self, check):
        check.side_effect=[subprocess.CalledProcessError(1,'nvidia-smi'), 'GPU-fixture, Quadro, 470.0, 8192\n']
        rows=ec.nvidia_adapters()
        self.assertEqual(rows[0]['uuid'],'GPU-fixture')
        self.assertEqual(rows[0]['profile']['generation'],'Unknown')

    @patch.object(ec.subprocess,'check_output',side_effect=FileNotFoundError())
    def test_missing_smi_is_not_codec_block(self, check):
        self.assertEqual(ec.nvidia_adapters(),[])
        self.assertEqual(ec.codec_order('nvidia',[]),['hevc','av1'])

    def test_positive_cache_and_source_driver_build_identity_invalidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            executable=Path(tmp)/'ffmpeg';executable.write_bytes(b'fixture')
            cache=Path(tmp)/'cache'
            with patch.object(ec.subprocess,'check_output',return_value='FFmpeg build one') as version, \
                 patch.object(ec.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','')) as run:
                def probe(**kw):
                    options=dict(adapters=[adapter()],cache_dir=cache)
                    options.update(kw)
                    return ec.probe_encoder(str(executable),'hevc_nvenc',**options)
                self.assertFalse(probe()['cached'])
                self.assertTrue(probe()['cached'])
                self.assertEqual(run.call_count,1)
                self.assertFalse(probe(width=3840,height=2076,pixel_format='p010le')['cached'])
                self.assertFalse(probe(adapters=[adapter(driver='581')])['cached'])
                self.assertFalse(probe(adapters=[adapter(identity='GPU-other')])['cached'])
                version.return_value='FFmpeg build two'
                self.assertFalse(probe()['cached'])

    def test_failure_timeout_unknown_and_multiple_adapters_are_not_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            executable=Path(tmp)/'ffmpeg';executable.write_bytes(b'fixture')
            with patch.object(ec.subprocess,'check_output',return_value='version'), \
                 patch.object(ec.subprocess,'run') as run:
                for outcome in (subprocess.CompletedProcess([],1,'','Encoder busy'),
                                subprocess.TimeoutExpired('ffmpeg',30)):
                    run.side_effect=outcome if isinstance(outcome,Exception) else None
                    run.return_value=outcome
                    for _ in range(2):
                        result=ec.probe_encoder(str(executable),'av1_nvenc',adapters=[adapter()],cache_dir=Path(tmp)/'cache')
                        self.assertFalse(result['cached'])
                self.assertEqual(run.call_count,4)
                run.side_effect=None;run.return_value=subprocess.CompletedProcess([],0,'','')
                for adapters in ([],[adapter(),adapter('7.5')]):
                    for _ in range(2):
                        self.assertFalse(ec.probe_encoder(str(executable),'hevc_nvenc',adapters=adapters,cache_dir=Path(tmp)/'cache')['cached'])
                self.assertEqual(run.call_count,8)

    def test_corrupt_expired_cache_and_unwritable_cache_are_optional(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=Path(tmp)/'key.json'
            with patch.object(ec,'_cache_path',return_value=cache), \
                 patch.object(ec.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','')):
                for content in ('{broken',json.dumps(dict(checked_at=0,result={'status':'working'}))):
                    cache.write_text(content)
                    self.assertFalse(ec.probe_encoder('ffmpeg','hevc_nvenc',adapters=[adapter()])['cached'])
                with patch.object(Path,'write_text',side_effect=PermissionError()):
                    cache.unlink()
                    self.assertEqual(ec.probe_encoder('ffmpeg','hevc_nvenc',adapters=[adapter()])['status'],'working')
