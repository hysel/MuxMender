import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import dv_workflow as flow
from amd_av1_batch import fingerprint
from codec_selection import select_candidate
from media_workflow import automatic_arguments
from validated_replace import replace_validated


def evidence(source,start=15,seconds=10,combined=False):
    return dict(source=str(source),requested_start=start,requested_seconds=seconds,
                status='verified-structure-awaiting-visual-review',original_stat_unchanged=True,
                original_video_bytes=100,output_video_bytes=50,frames=240,reference_sha256='a'*64,
                rpu_content_and_frame_order_unchanged=True,audio_subtitle_packets_unchanged=True,
                static_hdr_within_one_quantization_unit=True,
                hdr10plus_content_and_frame_order_unchanged=combined,
                quality=dict(domain='hdr-common-render-v1',self=dict(passed=True,mean=99,p5=99,frames=240),
                             candidate=dict(passed=True,mean=95,p5=94,frames=240)))


class DVWorkflowTests(unittest.TestCase):
    def test_shared_preflight_binds_identity_settings_quality_and_savings(self):
        source=Path('fixture.mkv');identity='b'*64
        samples=[flow.sample_evidence(evidence(source,start),source,start,10,False,90,90)
                 for start in (15,50,85)]
        settings=dict(codec='hevc',encoder='hevc_nvenc',nvenc_cq=24,
                      nvenc_maxrate_mbps=None,combined=False)
        report=dict(schema='muxmender-codec-trials-v1',source_id=identity,color_mode='pq',
            references=[dict(id=str(s),bytes=100) for s in (15,50,85)],
            trials=[dict(id='candidate',codec='hevc',encoder='hevc_nvenc',source_id=identity,
                runtime_supported=True,playback_compatible=True,settings=settings,samples=samples)])
        selected=select_candidate(report,25)['selected']
        options=SimpleNamespace(source=source,min_savings=25,experimental_nvidia=True,
            experimental_intel=False,experimental_hdr10plus=False,nvenc_cq=24,nvenc_maxrate_mbps=None)
        check=flow.shared_full_preflight(source,identity,report,selected,90,90,lambda:None)
        with patch.object(flow,'digest',return_value=identity):
            self.assertTrue(check(options)['eligible'])
            for key,value in [('nvenc_cq',28),('nvenc_maxrate_mbps',20),
                              ('experimental_hdr10plus',True),('experimental_intel',True),
                              ('source',Path('other.mkv')),('min_savings',75)]:
                changed=copy.copy(options);setattr(changed,key,value)
                with self.subTest(key=key),self.assertRaises(ValueError):check(changed)
            # Copy at handoff prevents later trial mutation changing evidence.
            report['trials'][0]['samples'][0]['quality']['mean']=80
            self.assertTrue(check(options)['eligible'])
            bad=flow.shared_full_preflight(source,identity,report,selected,90,90,lambda:None)
            with self.assertRaises(ValueError):bad(options)
        with patch.object(flow,'digest',return_value='c'*64),self.assertRaises(ValueError):check(options)

    def test_auto_vendor_discovery_selects_evaluator_not_certification(self):
        for vendors,expected in [(['amd'],True),(['intel'],True),(['amd','intel'],True),
                                 (['nvidia'],False),(['nvidia','intel'],False),([],False)]:
            with self.subTest(vendors=vendors),patch('dv_workflow.mm.gpu_vendors',return_value=vendors):
                self.assertEqual(flow.use_shared_candidate_route(dict(dv_profile=8),'auto'),expected)
        with patch('dv_workflow.mm.gpu_vendors') as discover:
            self.assertTrue(flow.use_shared_candidate_route(dict(dv_profile=8),'intel'))
            self.assertFalse(flow.use_shared_candidate_route(dict(dv_profile=8),'nvidia'))
            self.assertTrue(flow.use_shared_candidate_route(dict(dv_profile=5),'auto'))
        discover.assert_not_called()

    def test_profile7_dispatch_precedes_profile81_vendor_restriction(self):
        data=dict(streams=[dict(index=0,codec_type='video',codec_name='hevc',
            side_data_list=[dict(dv_profile=7,el_present_flag=1,bl_present_flag=1,rpu_present_flag=1)])])
        args=SimpleNamespace(hardware='intel')
        for profile in (5,7,8):
            data['streams'][0]['side_data_list'][0]['dv_profile']=profile
            with patch('dv_mel.run',return_value=7) as route:
                self.assertEqual(flow.run(args,Path('source.mkv'),Path('output'),data,{}),7)
            route.assert_called_once_with(args,Path('source.mkv'),Path('output'),data,{})

    def test_additional_track_publication_requires_packet_proof(self):
        report=dict(status='verified-full-file-awaiting-playback',source='fixture.mkv',original_stat_unchanged=True,
            frames=24,decoded_frame_checks=dict(frames=24,timing_preserved=True,static_hdr_preserved=True,
            frame_picture_preserved=True,rpu_present_every_frame=True),rpu_content_digest='hash',
            chapters_unchanged=True,audio_subtitle_packets_unchanged=True,final_decode_evidence={'complete':True})
        with self.assertRaisesRegex(ValueError,'additional-track'):
            flow.verified_full(report,'fixture.mkv',False,additional_tracks=True)
        report['secondary_video_packets_unchanged']=True
        flow.verified_full(report,'fixture.mkv',False,additional_tracks=True)

    def test_shared_selector_accepts_complete_evidence_only(self):
        samples=[flow.sample_evidence(evidence('fixture.mkv',start),Path('fixture.mkv'),start,10,False,90,90)
                 for start in (15,50,85)]
        report=dict(schema='muxmender-codec-trials-v1',source_id='source-hash',color_mode='pq',
                    references=[dict(id=str(s),bytes=100) for s in (15,50,85)],
                    trials=[dict(id='candidate',codec='hevc',encoder='hevc_nvenc',source_id='source-hash',
                                 runtime_supported=True,playback_compatible=True,settings=dict(cq=30),samples=samples)])
        self.assertEqual(select_candidate(report,25)['action'],'encode_copy')
        report['trials'][0]['samples'][1]['quality_pass']=False
        report['trials'][0]['samples'][1]['quality']['passed']=False
        self.assertEqual(select_candidate(report,25)['action'],'keep_original')

    def test_evidence_identity_domain_and_combined_metadata(self):
        base=evidence('fixture.mkv',combined=True)
        changes=[('source','other.mkv'),('requested_start',14),('reference_sha256',''),
                 ('original_stat_unchanged',False),('frames',0),
                 ('rpu_content_and_frame_order_unchanged',False),
                 ('audio_subtitle_packets_unchanged',False),
                 ('hdr10plus_content_and_frame_order_unchanged',False)]
        for key,value in changes:
            with self.subTest(key=key):
                record=copy.deepcopy(base);record[key]=value
                with self.assertRaises(ValueError):flow.sample_evidence(record,Path('fixture.mkv'),15,10,True,90,90)
        base['quality']['self']['mean']=float('nan')
        with self.assertRaises(ValueError):flow.sample_evidence(base,Path('fixture.mkv'),15,10,True,90,90)

    def test_guard_propagates_stop_before_running_stage(self):
        from dv_preservation_test import NvidiaSampleGuard
        with tempfile.TemporaryDirectory() as tmp:
            guard=NvidiaSampleGuard(Path(tmp))
            def stop():raise KeyboardInterrupt('integration stopped')
            guard.source_guard=stop
            with self.assertRaises(KeyboardInterrupt):guard()

    def test_custom_quality_floors_are_not_ignored(self):
        sample=flow.sample_evidence(evidence('fixture.mkv'),Path('fixture.mkv'),15,10,False,98,98)
        self.assertFalse(sample['quality_pass'])

    def test_sample_requires_additional_track_proof_when_present(self):
        record=evidence('fixture.mkv')
        for value in (None,False):
            record['secondary_video_packets_unchanged']=value
            with self.assertRaisesRegex(ValueError,'additional-track'):
                flow.sample_evidence(record,Path('fixture.mkv'),15,10,False,90,90,additional_tracks=True)
        record['secondary_video_packets_unchanged']=True
        self.assertTrue(flow.sample_evidence(record,Path('fixture.mkv'),15,10,False,90,90,
                                            additional_tracks=True)['preservation_pass'])

    def test_adapter_allows_copies_but_never_replacement(self):
        settings=dict(mode='encode',hardware='auto',quality='auto',codecs=['hevc'],
                      minimum_savings=25,experimental_dv81=True)
        self.assertIn('--experimental-dv81',automatic_arguments('fixture.mkv','out',settings))
        settings['mode']='replace'
        with self.assertRaises(ValueError):automatic_arguments('fixture.mkv','out',settings)

    def test_publisher_rejects_unqualified_integration_even_with_success_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'status.json').write_text(json.dumps(dict(state='validated-copy-awaiting-playback',publication_authorized=False)))
            with self.assertRaisesRegex(ValueError,'not been qualified'):
                replace_validated(Path('fixture.mkv'),root,root,root,25,'test')

    def test_full_report_requires_all_metadata_evidence(self):
        report=dict(status='verified-full-file-awaiting-playback',source='fixture.mkv',
                    original_stat_unchanged=True,frames=240,rpu_content_digest='a'*64,
                    chapters_unchanged=True,audio_subtitle_packets_unchanged=True,
                    final_decode_evidence={'video':'strict full-frame audit'},
                    decoded_frame_checks=dict(frames=240,timing_preserved=True,static_hdr_preserved=True,
                                              frame_picture_preserved=True,rpu_present_every_frame=True,hdr10plus_preserved=True))
        flow.verified_full(report,Path('fixture.mkv'),True)
        for key in ('frame_picture_preserved','hdr10plus_preserved','timing_preserved','rpu_present_every_frame'):
            changed=copy.deepcopy(report);changed['decoded_frame_checks'][key]=False
            with self.subTest(key=key),self.assertRaises(ValueError):flow.verified_full(changed,Path('fixture.mkv'),True)

    def test_interruption_retains_source_and_never_starts_full_encode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'fixture.mkv';source.write_bytes(b'original'*100)
            output=root/'work'
            args=SimpleNamespace(hardware='nvidia',playback_verified_codecs=['hevc'],ffmpeg='ffmpeg',ffprobe='ffprobe',
                seconds=10,hevc_nvenc_cq=[24],minimum_savings_percent=25,vmaf_mean=90,vmaf_p5=90,
                execute=True,encode_best=True,min_free_gib=1)
            metadata=dict(streams=[dict(codec_type='video')])
            def stop(options):
                (output/'STOP').write_text('stop')
                options.source_guard()
                self.fail('STOP must interrupt before sample encoding')
            with patch.object(flow.mm,'probe',return_value=SimpleNamespace(duration_seconds=600)), \
                 patch.object(flow.dv,'require_candidate'),patch.object(flow.shutil,'which',side_effect=lambda x:x), \
                 patch('hdr_inspection.inspect',return_value={'side_data_types':[]}), \
                 patch('auto_optimize.Workflow.preflight_source'),patch.object(flow.dv,'run',side_effect=stop), \
                 patch.object(flow.full,'run') as full:
                with self.assertRaises(KeyboardInterrupt):flow.run(args,source,output,metadata,fingerprint(source))
                full.assert_not_called()
            state=json.loads(next(output.glob('auto-*/status.json')).read_text())
            self.assertEqual(state['state'],'stopped-original-retained')
            self.assertFalse(state['publication_authorized'])
            self.assertEqual(source.read_bytes(),b'original'*100)
            self.assertFalse(list(output.rglob('full-hevc.mkv')))

    def test_orchestrator_authorizes_only_fully_validated_automatic_output(self):
        self.check_orchestrator_publication()
        self.check_orchestrator_publication(combined=True)

    def test_explicit_research_run_still_cannot_publish(self):
        self.check_orchestrator_publication(experimental=True)

    def test_full_failure_reason_reaches_job_status(self):
        self.check_orchestrator_publication(failure='Ordered mux exceeded 1 GiB memory guard; partial retained')

    def check_orchestrator_publication(self,combined=False,experimental=False,failure=None):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'fixture.mkv';source.write_bytes(b'original'*100)
            output=root/'work'
            args=SimpleNamespace(hardware='nvidia',playback_verified_codecs=['hevc'],ffmpeg='ffmpeg',ffprobe='ffprobe',
                seconds=10,hevc_nvenc_cq=None,minimum_savings_percent=25,vmaf_mean=90,vmaf_p5=90,
                execute=True,encode_best=True,min_free_gib=1,experimental_dv81=experimental)
            metadata=dict(streams=[dict(codec_type='video')])
            def sample(options):
                options.source_guard()
                folder=options.work_dir/'dv81-test';folder.mkdir()
                record=evidence(source,options.start,options.seconds,combined)
                (folder/'validation.json').write_text(json.dumps(record));return 0
            def full(options,*,qualified_preflight):
                options.source_guard()
                self.assertTrue(qualified_preflight(options)['eligible'])
                folder=options.work_dir/'dv-full-test';folder.mkdir()
                if failure:
                    (folder/'validation.json').write_text(json.dumps(dict(status='failed',error=failure)))
                    return 1
                candidate=folder/'fixture.mkv';candidate.write_bytes(b'encoded')
                record=dict(status='verified-full-file-awaiting-playback',source=str(source),output=str(candidate),
                    original_stat_unchanged=True,frames=240,rpu_content_digest='a'*64,
                    chapters_unchanged=True,audio_subtitle_packets_unchanged=True,
                    final_decode_evidence={'video':'strict full-frame audit'},
                    decoded_frame_checks=dict(frames=240,timing_preserved=True,static_hdr_preserved=True,
                                              frame_picture_preserved=True,rpu_present_every_frame=True,
                                              hdr10plus_preserved=combined))
                (folder/'validation.json').write_text(json.dumps(record));return 0
            with patch.object(flow.mm,'probe',return_value=SimpleNamespace(duration_seconds=600)), \
                 patch.object(flow.dv,'require_candidate'),patch.object(flow.shutil,'which',side_effect=lambda x:x), \
                 patch('hdr_inspection.inspect',return_value={'side_data_types':['hdr10+'] if combined else []}), \
                 patch('auto_optimize.Workflow.preflight_source'),patch.object(flow.dv,'run',side_effect=sample), \
                 patch.object(flow.full,'run',side_effect=full):
                if failure:
                    with self.assertRaisesRegex(RuntimeError,'DV full preservation failed: '+failure):
                        flow.run(args,source,output,metadata,fingerprint(source))
                else:self.assertEqual(flow.run(args,source,output,metadata,fingerprint(source)),0)
            state=json.loads(next(output.glob('auto-*/status.json')).read_text())
            if failure:
                self.assertEqual(state['state'],'stopped-original-retained')
                self.assertIn(failure,state['error'])
                self.assertEqual(source.read_bytes(),b'original'*100)
                return
            self.assertEqual(state['state'],'validated-copy-awaiting-playback')
            self.assertEqual(state['publication_authorized'],not experimental)
            self.assertEqual(source.read_bytes(),b'original'*100)
            self.assertTrue(Path(state['output']).is_file())
            # Exercise the ordinary publisher against generated bytes only.
            result_dir=next(output.glob('auto-*'))
            self.assertIn(24,json.loads((result_dir/'plan.json').read_text())['cqs'])
            if experimental:
                with self.assertRaisesRegex(ValueError,'not been qualified'):
                    replace_validated(source,root,root,result_dir,25,'generated-dv')
                return
            replace_validated(source,root,root,result_dir,25,'generated-dv')
            self.assertEqual(source.read_bytes(),b'encoded')

    def test_automatic_replacement_needs_no_experimental_switch(self):
        settings=dict(mode='replace',hardware='auto',quality='auto',codecs=['hevc'],minimum_savings=25)
        args=automatic_arguments('fixture.mkv','out',settings)
        self.assertIn('--encode-best',args)
        self.assertNotIn('--experimental-dv81',args)


if __name__=='__main__':unittest.main()
