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

    def test_orchestrator_keeps_copy_and_shared_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'fixture.mkv';source.write_bytes(b'original'*100)
            output=root/'work'
            args=SimpleNamespace(hardware='nvidia',playback_verified_codecs=['hevc'],ffmpeg='ffmpeg',ffprobe='ffprobe',
                seconds=10,hevc_nvenc_cq=[30],minimum_savings_percent=25,vmaf_mean=90,vmaf_p5=90,
                execute=True,encode_best=True,min_free_gib=1)
            metadata=dict(streams=[dict(codec_type='video')])
            def sample(options):
                options.source_guard()
                folder=options.work_dir/'dv81-test';folder.mkdir()
                record=evidence(source,options.start,options.seconds,False)
                (folder/'validation.json').write_text(json.dumps(record));return 0
            def full(options):
                options.source_guard()
                folder=options.work_dir/'dv-full-test';folder.mkdir()
                candidate=folder/'fixture.mkv';candidate.write_bytes(b'encoded')
                record=dict(status='verified-full-file-awaiting-playback',source=str(source),output=str(candidate),
                    original_stat_unchanged=True,frames=240,rpu_content_digest='a'*64,
                    chapters_unchanged=True,audio_subtitle_packets_unchanged=True,
                    final_decode_evidence={'video':'strict full-frame audit'},
                    decoded_frame_checks=dict(frames=240,timing_preserved=True,static_hdr_preserved=True,
                                              frame_picture_preserved=True,rpu_present_every_frame=True))
                (folder/'validation.json').write_text(json.dumps(record));return 0
            with patch.object(flow.mm,'probe',return_value=SimpleNamespace(duration_seconds=600)), \
                 patch.object(flow.dv,'require_candidate'),patch.object(flow.shutil,'which',side_effect=lambda x:x), \
                 patch('hdr_inspection.inspect',return_value={'side_data_types':[]}), \
                 patch('auto_optimize.Workflow.preflight_source'),patch.object(flow.dv,'run',side_effect=sample), \
                 patch.object(flow.full,'run',side_effect=full):
                self.assertEqual(flow.run(args,source,output,metadata,fingerprint(source)),0)
            state=json.loads(next(output.glob('auto-*/status.json')).read_text())
            self.assertEqual(state['state'],'validated-copy-awaiting-playback')
            self.assertFalse(state['publication_authorized'])
            self.assertEqual(source.read_bytes(),b'original'*100)
            self.assertTrue(Path(state['output']).is_file())


if __name__=='__main__':unittest.main()
