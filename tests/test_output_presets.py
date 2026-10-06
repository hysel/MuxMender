import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import os
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fractions import Fraction
import output_presets as presets
import auto_optimize as ao
from media_workflow import automatic_arguments


class OutputPresetTests(unittest.TestCase):
    def test_original_has_no_encoder_or_resolution_change(self):
        self.assertEqual(presets.encoder_options({},'original'),[])
        self.assertEqual(presets.scale_filter({},'original'),'')

    def test_every_target_preserves_display_aspect_without_upscaling(self):
        for identifier in presets.PRESETS:
            for w,h,sar in ((3840,2160,'1:1'),(1920,800,'1:1'),(720,576,'16:15'),(1080,1920,'1:1')):
                source=dict(width=w,height=h,sample_aspect_ratio=sar)
                target=presets.geometry(source,identifier)
                self.assertLessEqual(target['width'],w);self.assertLessEqual(target['height'],h)
                self.assertEqual(Fraction(w,h)*Fraction(sar.replace(':','/')),
                    Fraction(target['width'],target['height'])*Fraction(target['sar'].replace(':','/')))

    def test_interlaced_height_preserves_field_pairs(self):
        target=presets.geometry(dict(width=1920,height=1080,sample_aspect_ratio='1:1',field_order='tt'),'small480')
        self.assertEqual(target['height']%4,0)
        self.assertIn('interl=1',presets.scale_filter(dict(width=1920,height=1080,sample_aspect_ratio='1:1',field_order='tt'),'small480'))

    def test_target_has_explicit_bitrate_not_total_media_claim(self):
        self.assertEqual([presets.preset(p)['video_bps'] for p in ('tv1080','mobile720','small480')],
                         [8000000,4000000,1500000])
        with self.assertRaises(ValueError):presets.preset('unsafe')

    def test_cli_and_app_use_shared_target_arguments(self):
        settings=dict(mode='encode',hardware='nvidia',minimum_savings=25,codecs=['hevc'],quality='auto',
                      output_preset='mobile720',hdr_policy='sdr')
        args=automatic_arguments('source.mkv','output',settings)
        self.assertEqual(args[args.index('--output-preset')+1],'mobile720')
        self.assertEqual(args[args.index('--hdr-policy')+1],'sdr')

    def test_expected_geometry_does_not_mutate_source_or_ignore_other_fields(self):
        before=dict(streams=[dict(index=0,codec_type='video',width=1920,height=1080,
                                  sample_aspect_ratio='1:1',pix_fmt='yuv420p')])
        expected=presets.expected_metadata(before,'mobile720')
        self.assertEqual(before['streams'][0]['width'],1920)
        self.assertEqual(expected['streams'][0]['width'],1280)
        self.assertEqual(expected['streams'][0]['pix_fmt'],'yuv420p')

    def test_metric_only_resizes_reference(self):
        graph=ao.quality_graph('preset.json','24',reference_filter='scale=1280:720')
        self.assertIn('[1:V:0]scale=1280:720,',graph)
        self.assertNotIn('[0:V:0]scale',graph)

    @unittest.skipUnless(sys.platform.startswith('linux'),'Native media tests run on Linux only')
    def test_generated_full_conversion_and_quality_for_each_target(self):
        ffmpeg=shutil.which('ffmpeg');ffprobe=shutil.which('ffprobe')
        if not all((ffmpeg,ffprobe)):self.skipTest('Media tools unavailable')
        with tempfile.TemporaryDirectory(prefix='preset-qualification-',dir='/work') as folder:
            root=Path(folder);source=root/'source.mkv'
            receipts=[]
            subprocess.run([ffmpeg,'-v','error','-nostdin','-f','lavfi','-i',
                'testsrc=size=1920x1080:rate=24:duration=2,format=yuv420p','-c:v','libx264','-crf','18','-threads:v','2',
                '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',str(source)],
                check=True,capture_output=True,timeout=60)
            encoders=[('h264','h264_nvenc'),('hevc','hevc_nvenc'),('av1','av1_nvenc')] if os.environ.get('MUXMENDER_QUALIFY_GPU')=='1' else [('h264','libx264')]
            for identifier,codec,encoder in ((p,c,e) for p in ('tv1080','mobile720','small480') for c,e in encoders):
                workdir=root/(identifier+'-'+codec);workdir.mkdir();output=workdir/'output.mkv';policy=presets.preset(identifier)
                args=SimpleNamespace(ffmpeg=ffmpeg,ffprobe=ffprobe,timeout=120,source=source,
                                     output_preset=identifier,vmaf_mean=policy['mean'],vmaf_p5=policy['p5'])
                work=ao.Workflow(args,workdir,lambda:None);before=work.probe(source)
                frames=work.frame_file(source,'original',before['format'])
                info=ao.mm.probe(source,ffprobe)
                context=nullcontext() if encoder.endswith('_nvenc') else patch.object(ao.mm,'encoder_options',return_value=['-c:v','libx264','-crf','18','-threads:v:0','2'])
                with context:
                    work._encode_preserving_color(source,output,dict(codec=codec,encoder=encoder,quality='balanced'),
                                                  info,before,'full',2)
                count=work.validate(source,output,before,codec,'full',frames)
                self.assertEqual(count,48)
                quality=work.quality(source,output,'full',count,2)
                self.assertTrue(quality['passed'],json.dumps(quality))
                evidence=json.loads((workdir/'full-output-preset.json').read_text())
                self.assertTrue(evidence['passed'])
                receipts.append(dict(preset=identifier,codec=codec,encoder=encoder,
                                     frames=count,quality=quality,bitrate=evidence))
            recorded=os.environ.get('MUXMENDER_FIXTURE_RESULTS')
            if recorded:
                path=Path(recorded)
                if not path.resolve().is_relative_to('/work'):raise ValueError('Fixture evidence must remain in isolated work')
                with path.open('x') as handle:json.dump(receipts,handle,indent=2)


if __name__=='__main__':unittest.main()
