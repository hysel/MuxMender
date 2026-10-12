import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
import stat
from types import SimpleNamespace
from unittest.mock import patch

from gpu_reader_receipt import qualified_scope
from host_reader_qualification import verified_receipt


class HostQualificationTests(unittest.TestCase):
    def installer(self):
        path=Path(__file__).resolve().parents[1]/'deploy/truenas/install_reader_qualification.py'
        spec=importlib.util.spec_from_file_location('host_installer',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_destination_rejects_linked_writable_or_nonroot_parents(self):
        module=self.installer()
        for mode,uid in ((stat.S_IFLNK|0o755,0),(stat.S_IFDIR|0o775,0),(stat.S_IFDIR|0o755,3005)):
            with patch.object(Path,'lstat',return_value=SimpleNamespace(st_mode=mode,st_uid=uid)):
                with self.assertRaises(ValueError):module.trusted_directory(Path('/private/qualification'))
        with patch.object(Path,'lstat',return_value=SimpleNamespace(st_mode=stat.S_IFDIR|0o755,st_uid=0)):
            module.trusted_directory(Path('/private/qualification'))

    def evidence(self):
        binary=b'\x7fELFtest-reader';digest=hashlib.sha256(binary).hexdigest()
        read=dict(strict_success=True,returncode=0,error='',seconds=20)
        real=dict(binary_sha256=digest,source_changed=False,
            source=dict(codec_name='av1',pix_fmt='yuv420p10le'),
            full_reads=dict(cpu=read,cuda=dict(read,seconds=5)),
            full_pairwise_proof=dict(frames=240,static_hdr_frames=240,hdr_metadata_exact=True,
                frame_timestamps_exact=True,frame_timing_preserved=True,geometry_color_exact=True,
                max_timestamp_delta_seconds=0,mode='hdr10'))
        controls=dict(binary_sha256=digest,codec_name='av1',control_passed=True,false_passes=[],
            corruption=[dict(cuda=dict(strict_success=False)) for _ in range(3)])
        receipt=dict(schema=1,binary_sha256=digest,adapter=dict(uuid='GPU-test',driver='test'),
            visibility=dict(CUDA_VISIBLE_DEVICES=None,NVIDIA_VISIBLE_DEVICES='all',CUDA_DEVICE_ORDER=None),
            scopes=[qualified_scope(real,controls)])
        return receipt,dict(pairs=[dict(real=real,controls=controls)]),binary

    def test_only_evidence_derived_scopes_are_exported(self):
        receipt,evidence,binary=self.evidence();receipt['private_path']='not copied'
        result=json.loads(verified_receipt(receipt,evidence,binary))
        self.assertNotIn('private_path',result)
        self.assertEqual(result['scopes'],receipt['scopes'])
        self.assertEqual(verified_receipt(result,evidence,binary),verified_receipt(receipt,evidence,binary))

    def test_incomplete_tampered_or_generated_only_evidence_is_rejected(self):
        for mutate in (lambda r,e:r['scopes'][0]['hdr_modes'].append('sdr'),
                       lambda r,e:e.update(pairs=[]),
                       lambda r,e:e['pairs'][0]['real'].update(source_changed=True),
                       lambda r,e:e['pairs'][0]['real'].update(binary_sha256='0'*64),
                       lambda r,e:r.update(visibility={}),
                       lambda r,e:e['pairs'][0]['controls']['corruption'][0]['cuda'].update(strict_success=True)):
            receipt,evidence,binary=self.evidence();mutate(receipt,evidence)
            with self.assertRaises(ValueError):verified_receipt(receipt,evidence,binary)
        receipt,evidence,binary=self.evidence()
        with self.assertRaises(ValueError):verified_receipt(receipt,evidence,binary+b'changed')

    def test_installer_cannot_change_windows(self):
        module=self.installer()
        with patch.object(module.sys,'platform','win32'),patch.object(module,'bounded_read') as read:
            with self.assertRaises(RuntimeError):module.install('unused','unused')
            read.assert_not_called()
