from array import array
import io
from pathlib import Path
import tempfile
import unittest
from dv_fel_render import exact_frame,layout,plane_bytes,rpu_records,decode_command
from dv_fel_quality import metric_command,measure_research_quality,renderer_plugin


class FelRenderTransportTests(unittest.TestCase):
    def test_explicit_renderer_path_is_checked_not_silently_substituted(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'libfelbaker.so'
            args=SimpleNamespace(fel_render_plugin=path)
            with self.assertRaisesRegex(RuntimeError,'requires FelBaker'):renderer_plugin(args)
            path.write_bytes(b'fixture placeholder, never loaded')
            self.assertEqual(renderer_plugin(args),path.resolve())

    def test_all_decoder_pools_are_bounded(self):
        command=decode_command('ffmpeg','layer.hevc','yuv420p10le')
        self.assertEqual([command[i+1] for i,v in enumerate(command) if v=='-threads'],['2','1'])
        self.assertEqual(command[command.index('-filter_threads')+1],'1')
        self.assertNotIn('-vf',command)

    def records(self,data,**kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'metadata.rpu';path.write_bytes(data)
            return list(rpu_records(path,**kwargs))

    def test_chunk_boundaries_preserve_payload_and_emulation_bytes(self):
        records=[b'\x19\x08\x00\x00\x03\x01',b'\x19\x08\xff']
        data=b''.join(b'\0\0\0\1'+p for p in records)
        for size in range(1,20):self.assertEqual(self.records(data,chunk_size=size),records)

    def test_invalid_empty_and_oversized_exports(self):
        for data in (b'',b'\0\0',b'wrong',b'\0\0\0\1',b'\0\0\0\1\0\0\0\1',b'\0\0\0\1abcdef'):
            with self.assertRaises(ValueError):self.records(data,max_record=5)

    def test_guard_cancels_read(self):
        def guard():raise RuntimeError('stop')
        with self.assertRaisesRegex(RuntimeError,'stop'):self.records(b'\0\0\0\1\x19',guard=guard)

    def test_exact_frame_rejects_short_data(self):
        self.assertEqual(exact_frame(io.BytesIO(b'1234'),4),b'1234')
        with self.assertRaises(ValueError):exact_frame(io.BytesIO(b'123'),4)

    def test_geometry_and_plane_packing(self):
        self.assertEqual(layout(8,4,1),[(8,4),(4,2),(4,2)])
        self.assertEqual(layout(8,4,0),[(8,4)]*3)
        raw=array('H',range(8));plane=memoryview(raw).cast('B').cast('H',shape=(2,4))
        self.assertEqual(plane_bytes(plane,4,2),raw.tobytes())
        with self.assertRaises(ValueError):plane_bytes(plane,2,4)

    def test_metric_preserves_source_dimensions_and_declares_rgb(self):
        command=metric_command('ffmpeg',[7,9],3840,2160,'24000/1001','quality.json')
        self.assertEqual(command.count('3840x2160'),2)
        self.assertIn('pipe:7',command);self.assertIn('pipe:9',command)
        self.assertEqual(command.count('gbrp16le'),2)
        self.assertEqual(command.count('smpte2084'),2)
        self.assertNotIn('-thread_queue_size',command)
        self.assertEqual([command[i+1] for i,value in enumerate(command) if value=='-threads'],['1','1'])
        self.assertNotIn('-frames:v',command)
        graph=command[command.index('-filter_complex')+1]
        self.assertIn('[0:V:0]',graph);self.assertIn('[1:V:0]',graph)
        self.assertNotIn('trim=',graph)

    def test_self_metric_splits_one_renderer_and_rejects_invalid_values(self):
        command=metric_command('ffmpeg',[8],1920,1080,'24','self.json')
        graph=command[command.index('-filter_complex')+1]
        self.assertIn('split=2[self0][self1]',graph);self.assertNotIn('[1:V:0]',graph)
        for fds in ([],[-1],[True],[1,2,3]):
            with self.assertRaises(ValueError):metric_command('ffmpeg',fds,1920,1080,'24','self.json')

    def test_optional_native_comparison_never_grants_replacement(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        score=dict(mean=96,p5=94,frames=24,passed=True)
        fallback=dict(self=dict(score),candidate=dict(score),domain='hdr-common-render-v1')
        work=SimpleNamespace(args=SimpleNamespace())
        with patch('dv_fel_quality.measure_fel_quality') as measure:
            result=measure_research_quality(work,{}, {},{},24,'24',fallback)
            measure.assert_not_called();self.assertFalse(result['native_fel_quality_verified'])
            self.assertFalse(result['publication_authorized'])
            work.args.fel_render_plugin='/runtime/libfelbaker.so'
            measure.return_value=dict(self=dict(score),candidate=dict(score,mean=89,passed=False),
                                      domain='dv-felbaker-common-render-v1')
            result=measure_research_quality(work,{}, {},{},24,'24',fallback)
            self.assertEqual(result['candidate']['mean'],89)
            self.assertFalse(result['candidate']['passed']);self.assertTrue(result['native_fel_quality_evaluated'])
            self.assertFalse(result['publication_authorized'])
            measure.side_effect=RuntimeError('renderer failed')
            with self.assertRaisesRegex(RuntimeError,'renderer failed'):
                measure_research_quality(work,{}, {},{},24,'24',fallback)

    @unittest.skipUnless(__import__('sys').platform=='linux','POSIX inherited descriptors')
    def test_stage_inherits_only_requested_pipe(self):
        import os,sys
        from native_pipeline import stage
        read,write=os.pipe()
        try:
            os.write(write,b'ok');os.close(write);write=None
            code=f"import os; assert os.read({read},2)==b'ok'; print('frame=1'); print('progress=end')"
            stage([sys.executable,'-c',code],1,timeout=10,expected_frames=1,pass_fds=(read,))
        finally:
            os.close(read)
            if write is not None:os.close(write)
