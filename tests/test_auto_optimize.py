import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import auto_optimize as ao


def source_data():
    return dict(streams=[dict(index=0, codec_type='video', codec_name='h264',
        width=1920, height=1080, pix_fmt='yuv420p', field_order='progressive',
        color_space='bt709', color_primaries='bt709', color_transfer='bt709',
        color_range='tv', sample_aspect_ratio='1:1', avg_frame_rate='24/1', disposition={})],
        chapters=[], format=dict(duration='120'))


class AutoOptimizeTests(unittest.TestCase):
    def test_explicit_nvenc_trials_use_same_range_as_adaptive_engine(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(ao,'run',return_value=0) as run:
            (Path(folder)/'input').mkdir()
            source=Path(folder)/'input'/'fixture.mkv';source.write_bytes(b'generated fixture')
            self.assertEqual(ao.main([str(source),'--output-dir',str(Path(folder)/'output'),
                                      '--hardware','nvidia','--playback-verified-codecs','hevc',
                                      '--hevc-nvenc-cq','18','25','26','32']),0)
            self.assertEqual(run.call_args.args[0].hevc_nvenc_cq,[18,25,26,32])

    def test_missing_clock_recovery_never_applies_to_encoded_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            workflow=ao.Workflow(SimpleNamespace(source=root/'source.avi'),root,lambda:None)
            with self.assertRaisesRegex(ValueError,'no qualified source'):
                workflow.recover_mpeg4_tail(root/'output.avi',root/'evidence','test')

    def test_missing_clock_recovery_is_codec_specific_not_filename_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.avi'
            workflow=ao.Workflow(SimpleNamespace(source=source),root,lambda:None)
            with patch.object(workflow,'probe',return_value=source_data()):
                with self.assertRaisesRegex(ValueError,'not MPEG-4'):
                    workflow.recover_mpeg4_tail(source,root/'evidence','test')

    def test_recovered_color_is_materialized_without_pixel_conversion(self):
        with tempfile.TemporaryDirectory() as folder:
            workflow=ao.Workflow(SimpleNamespace(ffmpeg='ffmpeg',resolved_color=dict(
                color_primaries='bt709',color_transfer='bt709',color_space='bt709',color_range='tv')),
                Path(folder),lambda:None)
            with patch.object(ao.mm,'encoder_options',return_value=['-c:v','hevc_nvenc']),patch.object(workflow,'execute') as execute:
                workflow.encode_preserving_color(Path('source'),Path('out'),
                    dict(codec='hevc',quality='balanced',encoder='hevc_nvenc'),None,source_data(),'test',1)
            command=execute.call_args.args[0]
            value=command[command.index('-filter:v:0')+1]
            self.assertEqual(value,'setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=limited')
            self.assertNotIn('scale',value)

    def test_decoder_errors_cannot_become_efficient_size_screen_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            workflow=ao.Workflow(SimpleNamespace(ffprobe='ffprobe',timeout=30),root,lambda:None)
            def probe(command,path,*args):
                path.write_text('best_effort_timestamp_time=0|width=1920\n')
                path.with_suffix(path.suffix+'.stderr').write_text('corrupt decoded frame\n')
            with patch.object(ao,'run_probe',side_effect=probe):
                with self.assertRaisesRegex(ValueError,'decoder reported errors'):
                    workflow.frame_file(root/'reference-0.mkv','reference-0',{'duration':'1'})

    def test_encoder_stops_on_decode_error_before_size_screen(self):
        with patch.object(ao.mm,'encoder_options',return_value=['-c:v','hevc_nvenc']):
            command=ao.encode_command('ffmpeg',Path('source'),Path('out'),
                dict(codec='hevc',quality='balanced',encoder='hevc_nvenc'),None,source_data()['streams'])
        self.assertIn('-xerror',command)
        self.assertLess(command.index('-xerror'),command.index('-i'))

    def test_already_unspecified_color_avoids_bitstream_rewrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'final.mkv';before=source_data()
            for key in ('color_space','color_transfer','color_primaries'):
                before['streams'][0].pop(key)
            w=ao.Workflow(SimpleNamespace(ffmpeg='ffmpeg'),root,lambda:None)
            encoded=out.with_name('final-before-color-finalization.mkv')
            def encode(*args):encoded.write_bytes(b'encoded packets')
            with patch.object(ao,'encode_command',return_value=['encode']), \
                 patch.object(w,'execute',side_effect=encode) as execute, \
                 patch.object(w,'probe',return_value=before):
                w.encode_preserving_color(root/'source',out,dict(codec='hevc'),None,before,'test',10)
            self.assertEqual(execute.call_count,1)
            self.assertEqual(out.read_bytes(),b'encoded packets')
            self.assertIn(out.resolve(),w.color_intermediates)
            with self.assertRaises(FileExistsError):out.hardlink_to(encoded)

    def test_color_cleanup_only_owned_unchanged_temporary_after_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);raw=root/'owned.mkv';out=root/'final.mkv';source=root/'source.mkv'
            raw.write_bytes(b'temporary');source.write_bytes(b'original')
            w=ao.Workflow(SimpleNamespace(ffmpeg='ffmpeg'),root,lambda:None)
            stat=raw.stat();w.color_intermediates[out.resolve()]=(raw,(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns))
            before=source_data();after=copy.deepcopy(before);after['streams'][0]['codec_name']='hevc'
            with patch.object(w,'probe',return_value=after),patch.object(w,'frame_file'), \
                 patch.object(ao,'compare_frames',return_value=1),patch.object(w,'copied_packets',return_value={}),patch.object(w,'execute'):
                w.validate(source,out,before,'hevc','test',root/'frames')
            self.assertFalse(raw.exists());self.assertEqual(source.read_bytes(),b'original')

    def test_ten_bit_sdr_preserved_and_hdr_still_blocked(self):
        data=source_data();data['streams'][0]['pix_fmt']='yuv420p10le'
        ao.eligibility(data)
        for encoder in ('hevc_amf','hevc_nvenc','hevc_qsv'):
            with patch.object(ao.mm,'encoder_options',return_value=['-c:v',encoder]):
                command=ao.encode_command('ffmpeg',Path('in'),Path('out'),
                    dict(codec='hevc',quality='balanced',encoder=encoder),None,data['streams'])
            self.assertEqual(command[command.index('-pix_fmt')+1],'p010le')
        after=copy.deepcopy(data);after['streams'][0]['codec_name']='hevc'
        ao.metadata_check(data,after,'hevc')
        after['streams'][0]['pix_fmt']='yuv420p'
        with self.assertRaises(ValueError):ao.metadata_check(data,after,'hevc')
        data['streams'][0]['color_transfer']='smpte2084'
        with self.assertRaisesRegex(ValueError,'HDR'):ao.eligibility(data)

    def test_cover_art_is_identified_and_preserved(self):
        data=source_data()
        cover=dict(index=1,codec_type='video',codec_name='mjpeg',width=32,height=32,
                   pix_fmt='yuvj420p',disposition={'attached_pic':1},
                   tags={'filename':'cover.jpg','mimetype':'image/jpeg'})
        data['streams'].append(cover)
        ao.eligibility(data)
        after=copy.deepcopy(data);after['streams'][0]['codec_name']='hevc'
        ao.metadata_check(data,after,'hevc')
        after['streams'][1]['disposition']['attached_pic']=0
        with self.assertRaises(ValueError):ao.metadata_check(data,after,'hevc')
        data['streams'][1]['disposition']['attached_pic']=0
        with self.assertRaises(ValueError):ao.eligibility(data)

    def test_cover_packet_requires_one_identical_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'a';b=Path(folder)/'b'
            a.write_text('data_hash=SHA256:abc|pts_time=N/A\n')
            b.write_text('data_hash=SHA256:abc|pts_time=0.000\n')
            ao.compare_packets(a,b,cover=True)
            b.write_text('data_hash=SHA256:changed\n')
            with self.assertRaises(ValueError):ao.compare_packets(a,b,cover=True)
            a.write_text('');b.write_text('')
            with self.assertRaises(ValueError):ao.compare_packets(a,b,cover=True)

    def test_cover_reattachment_uses_generated_path_not_filename(self):
        data=source_data()
        data['streams'].append(dict(index=1,codec_type='video',codec_name='mjpeg',
            disposition={'attached_pic':1},tags={'filename':'../../cover.jpg','mimetype':'image/jpeg'}))
        with tempfile.TemporaryDirectory() as folder:
            w=ao.Workflow(SimpleNamespace(ffmpeg='ffmpeg'),Path(folder),lambda:None)
            def extract(command,*_):Path(command[-1]).write_bytes(b'image')
            with patch.object(w,'execute',side_effect=extract):
                command=w.preserve_covers(['ffmpeg','-map','0','out.mkv'],Path('source'),data,'safe')
            self.assertEqual(command[command.index('-attach')+1],str(Path(folder)/'safe-cover-1.jpg'))
            self.assertIn('-0:1',command)
            self.assertEqual(command[-1],'out.mkv')

    def test_cover_before_movie_is_not_silently_selected(self):
        data=source_data()
        data['streams'].insert(0,dict(codec_type='video',disposition={'attached_pic':1}))
        with self.assertRaisesRegex(ValueError,'precedes'):ao.eligibility(data)

    def test_default_quality_policy_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as folder:
            inputs = Path(folder)/'inputs'
            inputs.mkdir()
            source = inputs/'source.mkv'
            source.write_bytes(b'test fixture')
            output = Path(folder)/'output'
            for extra, expected in [([],90), (['--vmaf-mean','98'],98)]:
                with patch.object(ao, 'run', return_value=0) as run:
                    ao.main([str(source),'--output-dir',str(output),*extra])
                args = run.call_args.args[0]
                self.assertEqual(args.vmaf_mean, expected)
                self.assertEqual(args.vmaf_p5, 90)
                self.assertEqual(args.minimum_savings_percent, 25)

    def test_relaxed_mean_keeps_poor_tail_guard(self):
        scores = dict(frames=[dict(metrics=dict(vmaf=92)) for _ in range(100)])
        self.assertTrue(ao.quality_summary(scores,100,90,90)['passed'])
        for frame in scores['frames'][:6]:
            frame['metrics']['vmaf'] = 89
        self.assertFalse(ao.quality_summary(scores,100,90,90)['passed'])

    def test_intermediate_hevc_changes_only_cq_and_preserves_safe_flags(self):
        options = ['-c:v', 'hevc_nvenc', '-preset', 'p6', '-cq', '21']
        for cq in (18, 22, 23, 24, 28, 30, 32):
            with patch.object(ao.mm, 'encoder_options', return_value=options):
                cmd = ao.encode_command('ffmpeg', Path('input'), Path('output'),
                    dict(codec='hevc', quality='balanced', encoder='hevc_nvenc', nvenc_cq=cq),
                    None, source_data()['streams'])
            self.assertEqual(cmd[cmd.index('-cq')+1], str(cq))
            self.assertEqual(cmd[cmd.index('-preset')+1], 'p6')
            self.assertIn('-n', cmd)
            self.assertNotIn('-vf', cmd)
            self.assertNotIn('-r', cmd)
            self.assertEqual(options[-1], '21')
        with patch.object(ao.mm, 'encoder_options', return_value=options):
            with self.assertRaises(ValueError):
                ao.encode_command('ffmpeg', Path('input'), Path('output'),
                    dict(codec='hevc', quality='balanced', encoder='hevc_nvenc', nvenc_cq=33),
                    None, source_data()['streams'])

    def test_metric_clock_uses_matching_ordinals_not_rounded_pts(self):
        graph = ao.quality_graph('quality.json', '24000/1001')
        self.assertEqual(graph.count('setpts=N*1001/(24000*TB)'), 2)
        self.assertNotIn('PTS-STARTPTS', graph)
        with self.assertRaises(ValueError):
            ao.quality_graph('../outside.json', '24/1')
    def test_positions_are_distinct_and_bounded(self):
        self.assertEqual(ao.sample_positions(120, 10), [16.5, 55, 93.5])
        for duration, seconds in [(5, 1), (float('inf'), 1), (100, 0), (1000, 61)]:
            with self.assertRaises(ValueError):
                ao.sample_positions(duration, seconds)

    def test_source_gate(self):
        ao.eligibility(source_data())
        for key, value in [('pix_fmt', 'rgb24'), ('field_order', 'tt'),
                           ('color_transfer', 'smpte2084'), ('color_range', 'unknown'),
                           ('side_data_list', [{'side_data_type': 'DOVI configuration record'}])]:
            data = source_data()
            data['streams'][0][key] = value
            with self.assertRaises(ValueError):
                ao.eligibility(data)

    def test_quality_requires_all_frames_and_poor_tail_fails(self):
        scores = dict(frames=[dict(metrics=dict(vmaf=99)) for _ in range(100)])
        self.assertTrue(ao.quality_summary(scores, 100, 95, 90)['passed'])
        for frame in scores['frames'][:6]:
            frame['metrics']['vmaf'] = 80
        self.assertFalse(ao.quality_summary(scores, 100, 95, 90)['passed'])
        with self.assertRaises(ValueError):
            ao.quality_summary(scores, 101, 95, 90)
        scores['frames'][0]['metrics']['vmaf'] = float('nan')
        with self.assertRaises(ValueError):
            ao.quality_summary(scores, 100, 95, 90)

    def test_metadata_blocks_resize_color_and_flags(self):
        original = source_data()
        after = copy.deepcopy(original)
        after['streams'][0]['codec_name'] = 'hevc'
        ao.metadata_check(original, after, 'hevc')
        for key, value in [('height', 1082), ('color_transfer', 'unknown'), ('disposition', {'default': 1})]:
            bad = copy.deepcopy(after)
            bad['streams'][0][key] = value
            with self.assertRaises(ValueError):
                ao.metadata_check(original, bad, 'hevc')

    def test_frame_and_packet_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder)/'a', Path(folder)/'b'
            row = 'width=1920|height=1080|pix_fmt=yuv420p|sample_aspect_ratio=1:1|interlaced_frame=0|repeat_pict=0|best_effort_timestamp_time=0.000\n'
            a.write_text(row); b.write_text(row)
            self.assertEqual(ao.compare_frames(a, b), 1)
            for bad in [row.replace('0.000', '0.1'), row.replace('1080', '1082'), row.replace('0.000', 'nan'), row+row]:
                b.write_text(bad)
                with self.assertRaises(ValueError):
                    ao.compare_frames(a, b)
            a.write_text('pts_time=0|duration_time=0.04|data_hash=SHA256:a\n')
            b.write_text(a.read_text())
            ao.compare_packets(a, b)
            b.write_text('pts_time=0|duration_time=0.04\n')
            with self.assertRaises(ValueError):
                ao.compare_packets(a, b)

    def test_encode_is_copy_only_except_video(self):
        with patch.object(ao.mm, 'encoder_options', return_value=['-c:v', 'hevc_nvenc']):
            cmd = ao.encode_command('ffmpeg', Path('input'), Path('output'),
                dict(codec='hevc', quality='balanced', encoder='hevc_nvenc'), None, source_data()['streams'])
        self.assertIn('-n', cmd)
        self.assertNotIn('-y', cmd)
        self.assertNotIn('-vf', cmd)
        self.assertNotIn('-r', cmd)
        self.assertIn('-copyts', cmd)
        self.assertEqual(cmd[cmd.index('-c')+1], 'copy')

    def test_dry_run_no_output_and_no_gpu_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base/'input').mkdir()
            source = base/'input'/'source.mkv'
            source.write_bytes(b'original')
            out = base/'output'
            with patch.object(ao.Workflow, 'probe', return_value=source_data()), patch.object(ao, 'probe_encoder') as gpu:
                self.assertEqual(ao.main([str(source), '--output-dir', str(out)]), 0)
            gpu.assert_not_called()
            self.assertFalse(out.exists())
            self.assertEqual(source.read_bytes(), b'original')

    def test_output_inside_source_blocked_before_job_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'source.mkv'
            source.write_bytes(b'original')
            output = Path(folder)/'output'
            with patch.object(ao, 'tracked_call') as tracked:
                with self.assertRaises(ValueError):
                    ao.main([str(source), '--output-dir', str(output), '--execute'])
            tracked.assert_not_called()
            self.assertFalse(output.exists())

    def test_unknown_playback_does_not_start_trials(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base/'input').mkdir()
            source = base/'input'/'source.mkv'; source.write_bytes(b'original')
            with patch.object(ao.Workflow, 'probe', return_value=source_data()), patch.object(ao, 'probe_encoder') as gpu:
                with self.assertRaises(ValueError):
                    ao.main([str(source), '--output-dir', str(base/'output'), '--execute'])
            gpu.assert_not_called()

    def test_low_space_aborts_before_gpu_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base/'input').mkdir()
            source = base/'input'/'source.mkv'; source.write_bytes(b'original')
            with patch.object(ao.Workflow, 'probe', return_value=source_data()), \
                 patch.object(ao.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)), \
                 patch.object(ao, 'probe_encoder') as gpu:
                with self.assertRaises(RuntimeError):
                    ao.main([str(source), '--output-dir', str(base/'output'), '--execute',
                             '--playback-verified-codecs', 'hevc'])
            gpu.assert_not_called()
            self.assertEqual(source.read_bytes(), b'original')


if __name__ == '__main__':
    unittest.main()
