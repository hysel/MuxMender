import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/'tools/patch_cuda_ffprobe.py'
spec=importlib.util.spec_from_file_location('cuda_patch',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class CudaPatchTests(unittest.TestCase):
    def test_unknown_upstream_source_cannot_be_patched(self):
        with self.assertRaisesRegex(ValueError,'anchor changed'):
            module.transform('unexpected upstream source')

    def test_decoder_patches_reject_unknown_upstream(self):
        for transform in (module.transform_hevc_bounds,module.transform_nvdec_status):
            with self.assertRaisesRegex(ValueError,'anchor changed'):transform('unknown')

    def test_bounds_check_preserves_emulation_byte_accounting(self):
        anchor='    if (s->avctx->hwaccel)\n        return FF_HW_CALL(s->avctx, decode_slice, nal->raw_data, nal->raw_size);'
        result=module.transform_hevc_bounds(anchor)
        self.assertIn('nal->skipped_bytes_pos[j]',result)
        self.assertIn('end > nal->size',result)
        self.assertIn('AVERROR_INVALIDDATA',result)
        self.assertIn('MUXMENDER_RESEARCH_CUDA_READER',result)

    def test_pinned_build_is_research_only(self):
        text=(path.parents[1]/'deploy/truenas/Dockerfile.hdr-gpu-reader').read_text()
        self.assertIn('make -j2 ffprobe',text)
        self.assertIn('sha256sum -c -',text)
        self.assertNotIn('ENTRYPOINT',text)
        self.assertIn('--disable-network',text)
        self.assertIn('av1_nvdec',text)

    def test_av1_research_keeps_strict_completion_status(self):
        text=path.read_text()
        self.assertIn('cuvidDecodeStatus_Success',text)
        self.assertIn('ret = AVERROR_INVALIDDATA',text)
        self.assertIn('AV_CODEC_ID_AV1',text)


if __name__=='__main__':unittest.main()
