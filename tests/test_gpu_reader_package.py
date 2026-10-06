"""Artifact transport tests only: fake ELF bytes are never executed."""
import hashlib
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.build_app_release import inspect_gpu_reader_bundle
from gpu_reader_receipt import qualified_scope
from tools.assemble_gpu_reader_bundle import combine_pairs


class PackageTests(unittest.TestCase):
    def test_reader_qualification_tools_are_not_omitted_from_checkout(self):
        root=Path(__file__).resolve().parents[1]
        exceptions=set((root/'.gitignore').read_text().splitlines())
        for name in ('patch_cuda_ffprobe','assemble_gpu_reader_bundle',
                'benchmark_hdr_gpu_reader','benchmark_native_hdr_reader',
                'benchmark_native_av1_reader','benchmark_real_av1_reader',
                'benchmark_shared_gpu_reader','capture_reader_provenance_remote',
                'qualify_hdr_gpu_remote','qualify_reader_controls_remote',
                'qualify_shared_gpu_reader_remote','stage_reader_integration'):
            with self.subTest(tool=name):
                self.assertIn('!tools/'+name+'.py',exceptions)
                self.assertTrue((root/'tools'/f'{name}.py').is_file())

    def test_scope_assembly_keeps_complete_evidence_and_runtime_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);receipt,checksums=self.make_bundle(root)
            evidence=json.loads((root/'evidence.json').read_text())['pairs'][0]
            witness=dict(before_gpu_pass=True,read_only_mount=True,
                **{key:receipt[key] for key in ('binary_sha256','adapter','visibility')})
            entries=[(evidence['real'],evidence['controls'],witness)]
            hevc=copy.deepcopy(evidence)
            hevc['real']['source']['codec_name']='hevc';hevc['controls']['codec_name']='hevc'
            entries.append((hevc['real'],hevc['controls'],copy.deepcopy(witness)))
            pairs,scopes,witnesses,binding=combine_pairs(entries)
            self.assertEqual([scope['codec'] for scope in scopes],['av1','hevc'])
            self.assertEqual(len(pairs),2)
            self.assertEqual(binding['binary_sha256'],receipt['binary_sha256'])
            receipt['scopes']=scopes
            (root/'qualification.json').write_text(json.dumps(receipt))
            (root/'evidence.json').write_text(json.dumps(dict(pairs=pairs,before_gpu_provenance=witnesses)))
            with patch('tools.build_app_release.GPU_READER_SOURCE_CHECKSUMS',checksums):
                self.assertEqual(len(inspect_gpu_reader_bundle(root)),8)
            dynamic=copy.deepcopy(hevc)
            dynamic['real']['full_pairwise_proof'].update(mode='hdr10plus',hdr10plus_frames=240)
            expanded=combine_pairs([*entries,(dynamic['real'],dynamic['controls'],copy.deepcopy(witness))])
            receipt['scopes']=expanded[1]
            (root/'qualification.json').write_text(json.dumps(receipt))
            (root/'evidence.json').write_text(json.dumps(dict(pairs=expanded[0])))
            with patch('tools.build_app_release.GPU_READER_SOURCE_CHECKSUMS',checksums):
                self.assertEqual(len(inspect_gpu_reader_bundle(root)),8)
            self.assertEqual(expanded[1][2]['hdr_modes'],['hdr10plus','pq'])
            wrong=copy.deepcopy(entries);wrong[1][2]['adapter']['driver']='different'
            with self.assertRaisesRegex(ValueError,'runtime bindings'):combine_pairs(wrong)
            wrong=copy.deepcopy(entries);wrong[1][0]['binary_sha256']='b'*64
            with self.assertRaisesRegex(ValueError,'different reader artifact'):combine_pairs(wrong)
            with self.assertRaisesRegex(ValueError,'Duplicate codec'):combine_pairs([entries[0],entries[0]])
            legacy=copy.deepcopy(entries[:1]);legacy[0][0].pop('binary_sha256')
            derived=combine_pairs(legacy)
            self.assertEqual(derived[0][0]['real']['binary_sha256'],witness['binary_sha256'])
            self.assertNotIn('binary_sha256',legacy[0][0])

    def make_bundle(self,root):
        binary=b'\x7fELFsynthetic non-executable fixture'
        digest=hashlib.sha256(binary).hexdigest()
        (root/'ffprobe-cuda').write_bytes(binary)
        read=dict(strict_success=True,returncode=0,error='',seconds=20)
        real=dict(binary_sha256=digest,source_changed=False,source=dict(codec_name='av1',pix_fmt='yuv420p10le'),
            full_reads=dict(cpu=read,cuda=dict(read,seconds=5)),
            full_pairwise_proof=dict(frames=240,static_hdr_frames=240,hdr10plus_frames=0,hdr_metadata_exact=True,frame_timestamps_exact=True,
                frame_timing_preserved=True,geometry_color_exact=True,max_timestamp_delta_seconds=0,mode='hdr10'))
        controls=dict(binary_sha256=digest,codec_name='av1',control_passed=True,false_passes=[],
            corruption=[dict(case=name,cuda=dict(strict_success=False)) for name in ('early','middle','late')])
        receipt=dict(schema=1,binary_sha256=digest,adapter=dict(uuid='GPU-fixture',driver='fixture'),
            visibility={},scopes=[qualified_scope(real,controls)])
        (root/'qualification.json').write_text(json.dumps(receipt))
        (root/'evidence.json').write_text(json.dumps(dict(pairs=[dict(real=real,controls=controls)])))
        (root/'source').mkdir()
        checksums={}
        for name in ('ffmpeg-8.0.1.tar.xz','nv-codec-headers-n13.0.19.0.tar.gz',
                     'patch_cuda_ffprobe.py','COPYING.LGPLv2.1','LICENSE.md'):
            content=b'synthetic artifact '+name.encode()
            (root/'source'/name).write_bytes(content)
            if name.endswith(('.xz','.gz')):checksums[name]=hashlib.sha256(content).hexdigest()
        return receipt,checksums

    def test_matching_evidence_and_sources_are_included(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);receipt,checksums=self.make_bundle(root)
            with patch('tools.build_app_release.GPU_READER_SOURCE_CHECKSUMS',checksums):
                files=inspect_gpu_reader_bundle(root)
                self.assertEqual(len(files),8)
                self.assertIn('vendor/gpu-reader/source/COPYING.LGPLv2.1',files)
                (root/'ffprobe-cuda').write_bytes(b'\x7fELFchanged')
                with self.assertRaisesRegex(ValueError,'binary does not match'):inspect_gpu_reader_bundle(root)

    def test_green_label_without_complete_proof_is_not_packaged(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);receipt,checksums=self.make_bundle(root)
            data=json.loads((root/'evidence.json').read_text())
            data['pairs'][0]['real'].pop('full_reads')
            (root/'evidence.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'whole-file readers'):inspect_gpu_reader_bundle(root)
