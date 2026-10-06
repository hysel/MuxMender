import json
import tempfile
import unittest
from pathlib import Path
from dv_full_file import rpu_digest, mux_command, timestamped_video_command, ordered_dv_mux_command


class FullDVTests(unittest.TestCase):
    def test_packetized_truehd_uses_original_matroska_scale_not_a_new_audio_clock(self):
        from dv_full_file import copied_matroska_packetizer_options
        streams={'streams':[dict(codec_type='audio',codec_name='truehd')]}
        source={'container':{'type':'Matroska','properties':{'timestamp_scale':1000000}}}
        self.assertEqual(copied_matroska_packetizer_options(streams,source),
                         ['--engage','force_passthrough_packetizer','--timestamp-scale','1000000'])
        for scale in (None,True,0,-1,'1000000',1000000001):
            changed={'container':{'type':'Matroska','properties':{'timestamp_scale':scale}}}
            self.assertEqual(copied_matroska_packetizer_options(streams,changed),[])
        self.assertEqual(copied_matroska_packetizer_options(streams,{}),[])
        self.assertEqual(copied_matroska_packetizer_options(
                         {'streams':[dict(codec_type='audio',codec_name='dts')]},source),[])

    def test_packet_error_identifies_track_ordinal_and_changed_field(self):
        from dv_full_file import compare_track_packets
        packet=dict(stream_index=1,pts_time='0.040000',data_hash='SHA256:example')
        streams=[dict(index=1,codec_type='audio',codec_name='dts')]
        with self.assertRaisesRegex(ValueError,r'track 1, packet 1, pts_time'):
            compare_track_packets([packet],[dict(packet,pts_time='0.043000')],streams)
        self.assertEqual(compare_track_packets([packet],[dict(packet)],streams),{})
    def test_full_frame_reader_uses_shared_admission(self):
        from unittest.mock import patch,Mock
        from dv_full_file import frame_evidence
        guard=Mock();guard.phase='Inspect every source frame for HDR and DV metadata'
        with patch('validation_resources.validation_slot') as slot,patch('dv_full_file._frame_evidence',return_value='evidence') as read:
            self.assertEqual(frame_evidence('ffprobe','source','output',guard,120),'evidence')
        slot.assert_called_once_with(['ffprobe','-show_frames'],guard)
        read.assert_called_once_with('ffprobe','source','output',guard,120)

    def test_hdr_json_retains_all_fields_with_bounded_slice_threads(self):
        from unittest.mock import patch,Mock
        from dv_full_file import _frame_evidence
        guard=Mock();guard.phase='CPU inspection';guard.duration=600;guard.allow_hdr10plus=True
        child=Mock();child.poll.return_value=0;child.returncode=0
        with tempfile.TemporaryDirectory() as tmp,patch('dv_full_file.subprocess.Popen',return_value=child),patch('resource_governor.hdr_validation_threads',return_value=4):
            command=_frame_evidence('ffprobe','source',Path(tmp)/'frames.json',guard,120)
        self.assertEqual(command[command.index('-threads')+1],'4')
        self.assertEqual(command[command.index('-thread_type')+1],'slice')
        self.assertEqual(command[command.index('-of')+1],'json=compact=1')
        self.assertNotIn('-show_entries',command)

    def test_matroska_mux_maps_identified_ids_and_preserves_source_roles(self):
        from dv_full_file import matroska_dv_mux_command
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'out.mkv'
            streams={'streams':[dict(index=0,codec_type='video',tags={'language':'eng','title':'Main'},
                disposition={'default':1}),dict(index=2,codec_type='audio'),dict(index=3,codec_type='subtitle')]}
            tracks={'tracks':[dict(id=4,type='video'),dict(id=8,type='audio'),dict(id=9,type='subtitles')]}
            cmd=matroska_dv_mux_command('video.mkv','source.mkv',out,streams,tracks,start_offset=2.5)
            self.assertEqual(cmd[cmd.index('--track-order')+1],'0:0,1:8,1:9')
            self.assertIn('--disable-lacing',cmd)
            self.assertEqual(cmd[cmd.index('--sync')+1],'0:2500.000000000')
            self.assertEqual(cmd[cmd.index('--language')+1],'0:eng')
            self.assertEqual(cmd[cmd.index('--track-name')+1],'0:Main')
            self.assertEqual(cmd[-2:],['--no-video','source.mkv'])
            bad={'tracks':[dict(id=4,type='video')]}
            with self.assertRaises(ValueError):matroska_dv_mux_command('v','s',out,streams,bad)
            out.write_bytes(b'existing')
            with self.assertRaises(ValueError):matroska_dv_mux_command('v','s',out,streams,tracks)
            self.assertEqual(out.read_bytes(),b'existing')

    def test_frame_timing_rejects_nonfinite_and_nonincreasing_evidence(self):
        from unittest.mock import patch
        import dv_full_file as full
        def row(t):
            return dict(best_effort_timestamp_time=t,width=160,height=96,pix_fmt='yuv420p10le')
        for times in (['NaN'],['Infinity'],['N/A'],['0','0'],['1','0']):
            records=[row(t) for t in times]
            with patch.object(full,'frames',side_effect=lambda *a:iter(records)),patch.object(full.dv,'compare_static_hdr',return_value=False):
                with self.assertRaises(ValueError):full.compare_frames('source','output')
        records=[row('-0.1'),row('0'),row('0.041'),row('0.09')]
        with patch.object(full,'frames',side_effect=lambda *a:iter(records)),patch.object(full.dv,'compare_static_hdr',return_value=False):
            self.assertEqual(full.compare_frames('source','output')['frames'],4)

    def test_source_packet_nan_does_not_pass_timing_check(self):
        from unittest.mock import patch
        import dv_full_file as full
        with patch.object(full,'frames',return_value=iter([dict(best_effort_timestamp_time='0')])):
            with self.assertRaisesRegex(ValueError,'timestamp'):
                full.validate_source_frames('source',[float('nan')])

    def test_real_ffprobe_evidence_contains_picture_fields(self):
        import shutil,subprocess
        from unittest.mock import Mock
        from dv_full_file import frame_evidence,frame_picture_signature
        ffmpeg,ffprobe=shutil.which('ffmpeg'),shutil.which('ffprobe')
        if not ffmpeg or not ffprobe:self.skipTest('FFmpeg fixture tools unavailable')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'generated.mkv';evidence=root/'frames.compact'
            subprocess.run([ffmpeg,'-v','error','-nostdin','-n','-f','lavfi','-i',
                'testsrc2=size=320x180:rate=2','-t','1','-vf','setsar=4/3','-c:v','ffv1',
                '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709',str(source)],
                check=True,capture_output=True,timeout=30)
            guard=Mock();guard.duration=1;guard.phase='Generated fixture';guard.allow_hdr10plus=False
            frame_evidence(ffprobe,source,evidence,guard)
            records=[dict(item.split('=',1) for item in line.split('|')[1:] if '=' in item)
                     for line in evidence.read_text().splitlines() if line.startswith('frame|')]
            self.assertEqual(len(records),2)
            for record in records:
                signature=frame_picture_signature(record)
                self.assertEqual(signature[:3],(320,180,'yuv420p'))
                self.assertEqual(str(signature[3]),'4/3')
                self.assertEqual(record['color_space'],'bt709')

    def test_full_frame_timeout_scales_with_duration_and_remains_bounded(self):
        from dv_full_file import frame_evidence_timeout
        self.assertEqual(frame_evidence_timeout(None),3600)
        self.assertEqual(frame_evidence_timeout(30),3600)
        self.assertEqual(frame_evidence_timeout(3600),14700)
        self.assertEqual(frame_evidence_timeout(86400),86400)
        for bad in (0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):frame_evidence_timeout(bad)

    def test_retained_verification_respects_explicit_savings_floor(self):
        from unittest.mock import patch,Mock
        import dv_full_file as full
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);parent=root/'run';parent.mkdir()
            source=root/'source.mkv';source.write_bytes(b'x'*100)
            output=parent/'retained.mkv';output.write_bytes(b'x'*94)
            (parent/'validation.json').write_text(json.dumps(dict(source=str(source),
                encoder_settings={'encoder':'hevc_nvenc'},original_stat_unchanged=True)))
            with patch.object(full.shutil,'which',side_effect=lambda p:p),patch.object(full.dv,'NvidiaSampleGuard',return_value=Mock()):
                self.assertEqual(full.verify_existing(parent,output=output,dovi_tool='dovi_tool',min_savings=10),0)
            report=json.loads(next(parent.glob('verification-*/validation.json')).read_text())
            self.assertEqual(report['status'],'skipped')
            self.assertFalse(report['publication_allowed'])
            self.assertEqual(source.read_bytes(),b'x'*100)

    def test_retained_verification_cannot_select_source(self):
        import dv_full_file as full
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.mkv';source.write_bytes(b'original')
            (root/'validation.json').write_text(json.dumps(dict(source=str(source),
                encoder_settings={'encoder':'hevc_nvenc'},original_stat_unchanged=True)))
            with self.assertRaisesRegex(ValueError,'never the source'):
                full.verify_existing(root,output=source,dovi_tool='dovi_tool')

    def test_combined_full_evidence_keeps_dynamic_metadata_and_frame_alignment(self):
        from unittest.mock import patch
        import dv_full_file as full
        guard=lambda:None
        guard.allow_hdr10plus=True
        frame=dict(best_effort_timestamp_time='0',interlaced_frame=0,repeat_pict=0,
            width=3840,height=1608,pix_fmt='yuv420p10le',sample_aspect_ratio='1:1',
            side_data_list=[{'side_data_type':'Dolby Vision RPU Data'},
                            {'side_data_type':'HDR Dynamic Metadata SMPTE2094-40 (HDR10+)','anchor':1}])
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.json';output=Path(folder)/'output.json'
            source.write_text(json.dumps({'frames':[frame]}));output.write_text(source.read_text())
            with patch.object(full.dv,'compare_static_hdr',return_value=False):
                self.assertTrue(full.compare_frames(source,output,guard)['hdr10plus_preserved'])
                frame['side_data_list'][1]['anchor']=2
                output.write_text(json.dumps({'frames':[frame]}))
                with self.assertRaisesRegex(ValueError,'HDR10\\+'):
                    full.compare_frames(source,output,guard)
            with self.assertRaises(ValueError):list(full.frames(source))

    def test_frame_picture_signature_is_source_driven(self):
        from dv_full_file import frame_picture_signature as signature
        frame=dict(width=3840,height=1608,pix_fmt='yuv420p10le',sample_aspect_ratio='2:2',
                   color_space='bt2020nc',color_transfer='smpte2084')
        self.assertEqual(signature(frame),signature(dict(frame,width='3840',sample_aspect_ratio='1:1')))
        for key,value in dict(width=1920,height=1600,pix_fmt='yuv420p',sample_aspect_ratio='4:3',
                              color_space='bt709',color_transfer='bt709',chroma_location='left').items():
            with self.subTest(key=key):self.assertNotEqual(signature(frame),signature(dict(frame,**{key:value})))
        for key in ('width','height','pix_fmt'):
            bad=dict(frame);bad.pop(key)
            with self.assertRaisesRegex(ValueError,'refresh frame evidence'):signature(bad)

    def test_frame_picture_change_in_middle_is_rejected(self):
        from unittest.mock import patch
        import dv_full_file as full
        frame=dict(best_effort_timestamp_time='0',width=1920,height=1080,pix_fmt='yuv420p10le')
        before=[dict(frame,best_effort_timestamp_time=str(n)) for n in range(3)]
        after=[dict(f) for f in before];after[1]['height']=1072
        with patch.object(full,'frames',side_effect=[iter(before),iter(after)]),patch.object(full.dv,'compare_static_hdr',return_value=False):
            with self.assertRaisesRegex(ValueError,'geometry'):full.compare_frames('source','output')

    def test_size_preflight_propagates_cq_and_requires_quality(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import dv_full_file as full
        with tempfile.TemporaryDirectory() as folder:
            args=SimpleNamespace(source=Path('source.mkv'),work_dir=Path(folder),
                ffmpeg='ffmpeg',ffprobe='ffprobe',dovi_tool='dovi_tool',
                experimental_nvidia=True,nvenc_cq=29,min_savings=10)
            def sample(options):
                self.assertEqual(options.nvenc_cq,29)
                self.assertTrue(options.measure_quality)
                self.assertEqual(options.minimum_savings_percent,10)
                run=options.work_dir/'dv81-test';run.mkdir()
                (run/'validation.json').write_text(json.dumps(dict(
                    status='verified-structure-awaiting-visual-review',original_stat_unchanged=True,
                    original_video_bytes=1000,output_video_bytes=500,
                    quality={'candidate':{'passed':False}})))
                return 0
            with patch.object(full.dv,'run',side_effect=sample):
                decision=full.nvidia_savings_preflight(args,1200)
            self.assertFalse(decision['eligible'])
            self.assertIn('quality',decision['reason'])

    def test_full_research_progress_does_not_reset_after_preflight(self):
        from unittest.mock import patch
        from dv_preservation_test import NvidiaSampleGuard
        with tempfile.TemporaryDirectory() as tmp, patch('dv_preservation_test.jobs.progress') as progress:
            guard=NvidiaSampleGuard(Path(tmp));guard.overall_span=10
            guard.status(100)
            self.assertEqual(progress.call_args.args[1],10)
            guard.overall_offset,guard.overall_span=10,90
            guard.status(0)
            self.assertEqual(progress.call_args.args[1],10)
            guard.status(50)
            self.assertEqual(progress.call_args.args[1],55)

    def test_intel_timestamp_reconstruction_uses_mux_timebase(self):
        command = timestamped_video_command('ffmpeg','raw.hevc','video.mkv','24000/1001',intel=True)
        bsf = command[command.index('-bsf:v')+1]
        self.assertIn('setts=pts=N*1001/(24000*TB):dts=N*1001/(24000*TB)',bsf)
        self.assertNotIn('time_base=',bsf)
        self.assertNotIn('-y',command)

    def test_explicit_dv_timestamps_use_individual_pictures(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'video.mkv'
            command=timestamped_video_command('ffmpeg','raw.hevc',output,'24000/1001',
                                               timestamps='decoded.txt',mkvmerge='mkvmerge')
            self.assertEqual(command[0],'mkvmerge')
            self.assertEqual(command[command.index('--timestamps')+1],'0:decoded.txt')
            self.assertIn('--disable-lacing',command)
            self.assertNotIn('-r',command)
            output.write_bytes(b'existing')
            with self.assertRaisesRegex(ValueError,'already exists'):
                timestamped_video_command('ffmpeg','raw.hevc',output,'24',timestamps='decoded.txt')
            self.assertEqual(output.read_bytes(),b'existing')

    def test_nvidia_mux_separates_timestamp_generation_and_preserves_tracks(self):
        first = timestamped_video_command('ffmpeg','raw.hevc','video.mkv','24000/1001')
        self.assertEqual(first.count('-i'), 1)
        self.assertEqual(first[first.index('-c')+1], 'copy')
        streams = {'streams': [{'index': 0, 'codec_type': 'video'},
                               {'index': 1, 'codec_type': 'audio'},
                               {'index': 2, 'codec_type': 'subtitle'}]}
        final = ordered_dv_mux_command('ffmpeg','video.mkv','original.mkv','final.mkv',streams)
        self.assertEqual([final[i+1] for i,x in enumerate(final) if x == '-map'], ['0:V:0','1:1','1:2'])
        self.assertEqual(final[final.index('-max_interleave_delta')+1], '0')
        self.assertIn('-copyts', final)
        self.assertNotIn('-y', final)

    def test_dv_nonzero_start_offsets_only_reconstructed_video(self):
        streams={'streams':[{'index':0,'codec_type':'video'},{'index':1,'codec_type':'audio'}]}
        command=ordered_dv_mux_command('ffmpeg','video','source','out',streams,start_offset=2.5)
        first=command.index('-i')
        self.assertEqual(command[first-2:first],['-itsoffset','2.5'])
        self.assertEqual(command.count('-itsoffset'),1)
        self.assertIn('-copyts',command)
        with self.assertRaises(ValueError):ordered_dv_mux_command('ffmpeg','v','s','o',streams,start_offset=float('nan'))
    def test_rpu_streamed_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'rpu.json'
            p.write_text(json.dumps([{'x': 'a'*70000, 'rpu_data_crc32': 1}, {'x':2}]))
            first = rpu_digest(p)
            self.assertEqual(first[0],2)
            p.write_text(json.dumps([{'x': 'a'*70000, 'rpu_data_crc32': 9}, {'x':2}]))
            self.assertEqual(first,rpu_digest(p))
            p.write_text(json.dumps([{'x':2}, {'x':'a'*70000}]))
            self.assertNotEqual(first,rpu_digest(p))

    def test_bad_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'rpu.json'
            for value in ('{}','[{},]','[{} {}]','[{}]oops','[{','[1]'):
                p.write_text(value)
                with self.subTest(value=value), self.assertRaises(ValueError):
                    rpu_digest(p)

    def test_full_mux_does_not_trim_or_overwrite(self):
        cmd = mux_command('ffmpeg','original','injected','fresh','24000/1001')
        for flag in ('-t','-ss','-shortest','-y'):
            self.assertNotIn(flag,cmd)
        self.assertIn('-n',cmd)
        self.assertEqual(cmd[cmd.index('-map_chapters')+1],'1')
