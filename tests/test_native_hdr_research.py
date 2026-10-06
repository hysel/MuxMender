"""Pure fixture/guard tests; never run native Linux readers on Windows."""
import importlib.util
import copy
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

path=Path(__file__).resolve().parents[1]/'tools/benchmark_native_hdr_reader.py'
spec=importlib.util.spec_from_file_location('native_hdr_research',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class NativeHdrResearchTests(unittest.TestCase):
    def test_shared_integration_refuses_windows_before_generating_media(self):
        spec=importlib.util.spec_from_file_location('shared_reader_research',path.with_name('benchmark_shared_gpu_reader.py'))
        shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
        with patch.object(shared.sys,'platform','win32'),patch.object(shared.subprocess,'run') as process:
            with self.assertRaisesRegex(RuntimeError,'Linux only'):shared.main()
            process.assert_not_called()

    def test_hdr_reader_comparison_keeps_exact_timing_without_duplicate_pass(self):
        real_spec=importlib.util.spec_from_file_location('real_av1_comparison',path.with_name('benchmark_real_av1_reader.py'))
        real=importlib.util.module_from_spec(real_spec);real_spec.loader.exec_module(real)
        frame=dict(width=3840,height=2160,pix_fmt='yuv420p10le',color_range='tv',color_space='bt2020nc',
            color_transfer='smpte2084',color_primaries='bt2020',sample_aspect_ratio='1:1',
            best_effort_timestamp_time='0.042',interlaced_frame=0,repeat_pict=0,chroma_location='left',
            side_data_list=[dict(side_data_type='Mastering display metadata',max_luminance='1000/1')])
        with tempfile.TemporaryDirectory() as directory:
            cpu=Path(directory)/'cpu.json';gpu=Path(directory)/'gpu.json'
            cpu.write_text(json.dumps(dict(frames=[frame])))
            gpu.write_text(json.dumps(dict(frames=[frame])))
            self.assertEqual(real.compare(cpu,gpu)['frames'],1)
            changed=copy.deepcopy(frame);changed['best_effort_timestamp_time']='0.043'
            gpu.write_text(json.dumps(dict(frames=[changed])))
            with self.assertRaisesRegex(ValueError,'not exact'):real.compare(cpu,gpu)
            changed=copy.deepcopy(frame);changed['chroma_location']='topleft'
            gpu.write_text(json.dumps(dict(frames=[changed])))
            with self.assertRaisesRegex(ValueError,'chroma location changed'):real.compare(cpu,gpu)
            gpu.write_text(json.dumps(dict(frames=[])))
            with self.assertRaisesRegex(ValueError,'Frame count changed'):real.compare(cpu,gpu)

    def test_malformed_variants_do_not_change_original(self):
        payload=b''.join(b'\x00\x00\x00\x01'+bytes([2,1])+b'\x45'*600 for _ in range(4))
        variants=module.corrupt_variants(payload)
        self.assertEqual(len(variants),7)
        for name,data in variants.items():
            self.assertNotEqual(data,payload)
            self.assertLessEqual(len(data),len(payload))
        self.assertEqual(payload.count(b'\x45'),2400)

    def test_probe_refuses_windows_before_starting_process(self):
        with patch.object(module.sys,'platform','win32'),patch.object(module.subprocess,'Popen') as process:
            with self.assertRaisesRegex(RuntimeError,'Linux only'):
                module.probe('unused',Path('unused'),Path('unused'),True)
            process.assert_not_called()

    def test_av1_control_refuses_windows_before_generating_media(self):
        av1spec=importlib.util.spec_from_file_location('av1_reader_research',path.with_name('benchmark_native_av1_reader.py'))
        av1=importlib.util.module_from_spec(av1spec);av1spec.loader.exec_module(av1)
        with patch.object(av1.sys,'platform','win32'),patch.object(av1.subprocess,'run') as process:
            with self.assertRaisesRegex(RuntimeError,'Linux only'):av1.main()
            process.assert_not_called()

    def test_av1_fixture_metadata_preserves_picture_bytes(self):
        av1spec=importlib.util.spec_from_file_location('av1_metadata_research',path.with_name('benchmark_native_av1_reader.py'))
        av1=importlib.util.module_from_spec(av1spec);av1spec.loader.exec_module(av1)
        from av1_content_light import obus
        packet=b'\x32\x03\x45\x46\x47'
        result=av1.static_metadata_packet(packet)
        self.assertEqual(b''.join(raw for kind,raw,body in obus(result) if kind!=5),packet)
        self.assertEqual(sum(kind==5 for kind,raw,body in obus(result)),2)

    def test_av1_damaged_fixture_variants_are_bounded(self):
        av1spec=importlib.util.spec_from_file_location('av1_damaged_research',path.with_name('benchmark_native_av1_reader.py'))
        av1=importlib.util.module_from_spec(av1spec);av1spec.loader.exec_module(av1)
        packet=b'\x32\xbc\x05'+b'\x45'*700
        original=packet*4
        variants=av1.corrupt_variants(original)
        self.assertEqual(len(variants),7)
        for value in variants.values():
            self.assertNotEqual(value,original)
            self.assertLessEqual(len(value),len(original))

    def test_real_av1_research_refuses_windows_before_inventory(self):
        real_spec=importlib.util.spec_from_file_location('real_av1_research',path.with_name('benchmark_real_av1_reader.py'))
        real=importlib.util.module_from_spec(real_spec);real_spec.loader.exec_module(real)
        with patch.object(real.sys,'platform','win32'),patch.object(real.subprocess,'run') as process:
            with self.assertRaisesRegex(RuntimeError,'Linux only'):real.main()
            process.assert_not_called()


if __name__=='__main__':unittest.main()
