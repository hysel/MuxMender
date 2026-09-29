import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch
from dv_mel import encode_candidate, compare_candidates, prepare_references, refine_full_candidate
import hashlib
from hdr10plus_preserve import write_decoded_timestamps


class MelCandidateTests(unittest.TestCase):
    def test_decoder_error_in_cut_falls_back_to_complete_unchanged_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mkv';source.write_bytes(b'generated source')
            work=SimpleNamespace(directory=root,guard=Mock(),probe=Mock(return_value=dict(format=dict(duration='24'))))
            with patch('dv_mel.reference_rpu_coverage') as coverage,patch('reference_sampling.recover_reference',
                    side_effect=ValueError('Decoder reported errors during sample recovery')):
                result=prepare_references(work,source,2)
            coverage.assert_not_called()
            self.assertEqual(len(result['references']),1)
            reference=result['references'][0]
            self.assertTrue(reference['whole_source']);self.assertEqual(Path(reference['path']),source)
            self.assertEqual(reference['sha256'],hashlib.sha256(source.read_bytes()).hexdigest())

    def test_fel_native_evidence_requires_both_complete_views(self):
        import copy
        from dv_mel import candidate_evidence
        score=dict(frames=24,mean=96,p5=94,passed=True)
        view=dict(self=dict(score),candidate=dict(score))
        result=dict(source_sha256='a'*64,source_bytes=100,source_unchanged=True,copied_tracks_preserved=True,
            frame_checks=dict(frames=24),status='validated-research-copy',
            layer_checks=dict(frames=24,enhancement_types=['FEL'],scope='layer-preservation-only',
                              rpu_sha256='b'*64,enhancement_video_sha256='c'*64),
            quality=dict(self=dict(score),candidate=dict(score),domain='dv-felbaker-common-render-v1',
                         native_fel_quality_evaluated=True,views=dict(native_dv=copy.deepcopy(view),compatible_fallback=copy.deepcopy(view))))
        self.assertEqual(candidate_evidence(result,'a'*64,100,7),24)
        result['layer_checks']['enhancement_types']=['FEL','MEL']
        self.assertEqual(candidate_evidence(result,'a'*64,100,7),24)
        for change in ('explicit','missing-view','wrong-count','optimistic-score'):
            broken=copy.deepcopy(result)
            if change=='explicit':broken['status']='unqualified-fel-research-copy'
            if change=='missing-view':del broken['quality']['views']['native_dv']
            if change=='wrong-count':broken['quality']['views']['native_dv']['candidate']['frames']=23
            if change=='optimistic-score':broken['quality']['candidate']['mean']=99
            with self.assertRaises(ValueError):candidate_evidence(broken,'a'*64,100,7)

    def test_idr_hints_require_packet_correspondence_and_ignore_extra_slices(self):
        from dv_mel import idr_positions
        from fractions import Fraction
        from hevc_inventory import Inventory
        def nal(kind,first=True,layer=0):
            return b'\x00\x00\x01'+bytes([(kind<<1)|(layer>>5),(layer<<3)|1,128 if first else 0])
        raw=nal(21)+nal(62)+nal(19)+nal(19,False)+nal(19,True,1)+nal(1)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'sample.hevc';path.write_bytes(raw)
            packets=[dict(pts_time='0',flags='K'),dict(pts_time='.250',flags='K'),dict(pts_time='.125',flags='')]
            self.assertEqual(idr_positions(path,packets,'-.751'),[Fraction('1.001')])
            self.assertEqual(idr_positions(path,packets[:-1],'-.751'),[])
            packets[1]['flags']='KD'
            self.assertEqual(idr_positions(path,packets,'-.751'),[])
        inventory=Inventory(track_pictures=True)
        for byte in raw:inventory.feed(bytes([byte]))
        inventory.finish()
        self.assertEqual(inventory.picture_types,[21,19,1])

    def test_failed_cra_coverage_uses_idr_hint_then_revalidates(self):
        from fractions import Fraction
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mkv';source.write_bytes(b'generated source')
            sample=root/'sample.mkv';sample.write_bytes(b'generated cut')
            work=SimpleNamespace(directory=root,guard=Mock(),probe=Mock(return_value=dict(format=dict(duration='24'))))
            proofs=[dict(plan=dict(keyframe_pts=str(p),end_keyframe_pts=str(p+2))) for p in (0,1)]
            with patch('auto_optimize.reference_plan',return_value=dict(seconds=2,positions=[0],whole_source=False)),patch(
                    'reference_sampling.recover_reference',side_effect=[(sample,p) for p in proofs]) as recover,patch(
                    'dv_mel.reference_rpu_coverage',side_effect=[dict(complete=False),dict(complete=True)]) as coverage,patch(
                    'dv_mel.reference_idr_hints',return_value=[Fraction(1)]):
                result=prepare_references(work,source,2)
            self.assertEqual(recover.call_args_list[1].args[3],Fraction(1))
            self.assertEqual(coverage.call_count,2)
            self.assertTrue(result['references'][0]['source_evidence']['rpu_coverage']['complete'])

    def test_fel_research_is_explicit_and_cannot_supply_automatic_quality_evidence(self):
        import dv_mel
        with patch('dv_mel._encode_layered',return_value={'publication_authorized':False}) as encode:
            dv_mel.encode_candidate('work','source',{},'candidate')
            self.assertNotIn('fel_research',encode.call_args.kwargs)
            dv_mel.encode_fel_research_candidate('work','source',{},'candidate')
            self.assertIs(encode.call_args.kwargs['fel_research'],True)
        good=dict(frames=24,mean=99,p5=99,passed=True)
        result=dict(source_sha256='a'*64,source_bytes=100,source_unchanged=True,copied_tracks_preserved=True,
            frame_checks=dict(frames=24),layer_checks=dict(frames=24,enhancement_types=['MEL']),
            quality=dict(self=good,candidate=good,domain='hdr-common-render-v1',native_fel_quality_verified=False))
        with self.assertRaisesRegex(ValueError,'candidate evidence'):
            dv_mel.candidate_evidence(result,'a'*64,100,7)

    def sample_refinement(self, outcomes, budget=4):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mkv';source.write_bytes(b'x'*100)
            sha=hashlib.sha256(source.read_bytes()).hexdigest()
            ref=dict(id='whole',path=str(source),sha256=sha,bytes=100,whole_source=True)
            prepared=dict(source_id=sha,source_bytes=100,references=[ref])
            good=dict(mean=99,p5=99,frames=24,passed=True)
            results=[]
            for outcome in outcomes:
                if isinstance(outcome,Exception):results.append(outcome);continue
                results.append(dict(source_sha256=sha,source_bytes=100,source_unchanged=True,
                    copied_tracks_preserved=True,frame_checks=dict(frames=24),layer_checks=dict(frames=24,enhancement_types=['MEL']),
                    output_bytes=40,quality=dict(self=good,candidate=dict(good,p5=95 if outcome else 80,passed=outcome),
                    domain='dv-libplacebo-common-render-v1')))
            settings=dict(codec='hevc',encoder='hevc_nvenc',quality='balanced',nvenc_cq=24,
                          nvenc_preset='p7',nvenc_maxrate_mbps=10)
            with patch('dv_mel.prepare_references',return_value=prepared),patch(
                    'dv_mel.encode_candidate',side_effect=results) as encode:
                report,decision=compare_candidates(SimpleNamespace(directory=root,guard=Mock()),source,
                    [settings],2,playback_verified_codecs=['hevc'],max_refinements=budget)
            return report,decision,encode.call_args_list

    def test_sample_quality_refinement_reuses_references_and_preserves_caps(self):
        report,decision,calls=self.sample_refinement([False,True])
        self.assertEqual(decision['action'],'encode_copy')
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[1].args[2]['nvenc_cq'],20)
        self.assertEqual(calls[1].args[2]['nvenc_maxrate_mbps'],10)
        self.assertEqual(calls[0].args[1],calls[1].args[1])
        self.assertEqual(report['sample_refinements'],1)

    def test_sample_refinement_has_hard_budget(self):
        report,decision,calls=self.sample_refinement([False,False],budget=1)
        self.assertEqual(len(calls),2)
        self.assertEqual(decision['action'],'keep_original')
        self.assertEqual(report['sample_refinements'],1)

    def test_sample_structural_failure_is_not_quality_refinement(self):
        report,decision,calls=self.sample_refinement([ValueError('RPU mismatch')])
        self.assertEqual(len(calls),1)
        self.assertFalse(decision['cacheable'])
        self.assertNotIn('sample_refinements',report)

    def test_unusable_cut_boundaries_fall_back_to_whole_source_not_format_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mkv';source.write_bytes(b'generated')
            work=SimpleNamespace(directory=root,guard=Mock(),probe=Mock(return_value=dict(format=dict(duration='24'))))
            attempts=[(root/f'cut-{i}.mkv',dict(plan=dict(keyframe_pts=str(i+1),end_keyframe_pts=str(i+3)))) for i in range(3)]
            with patch('reference_sampling.recover_reference',side_effect=attempts) as recover,patch(
                    'dv_mel.reference_rpu_coverage',return_value=dict(complete=False,displayed_frames=22,rpu_records=24)),patch(
                    'dv_mel.reference_idr_hints',return_value=[]):
                result=prepare_references(work,source,2)
            self.assertEqual(recover.call_count,3)
            self.assertEqual(len(result['references']),1)
            self.assertTrue(result['references'][0]['whole_source'])
            self.assertEqual(result['references'][0]['path'],str(source))
            self.assertEqual(len(result['rejected_boundaries']),3)

    def test_full_refinement_uses_shared_search_and_keeps_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mkv';source.write_bytes(b'x'*100)
            sha=hashlib.sha256(source.read_bytes()).hexdigest()
            work=SimpleNamespace(directory=root,guard=Mock())
            good=dict(mean=98,p5=95,frames=24,passed=True)
            def result(p5):
                return dict(source_sha256=sha,source_bytes=100,source_unchanged=True,copied_tracks_preserved=True,
                    frame_checks=dict(frames=24),layer_checks=dict(frames=24,enhancement_types=['MEL']),output_bytes=40,
                    quality=dict(self=good,candidate=dict(good,p5=p5),domain='dv-libplacebo-common-render-v1'))
            settings=dict(codec='hevc',encoder='hevc_nvenc',nvenc_cq=24,nvenc_maxrate_mbps=10)
            with patch('dv_mel.encode_candidate',side_effect=[result(86),result(95)]) as encode:
                report=refine_full_candidate(work,source,settings,source_id=sha,playback_verified_codecs=['hevc'])
            self.assertEqual(report['status'],'validated_copy')
            self.assertEqual(encode.call_args_list[1].args[2]['nvenc_cq'],20)
            self.assertEqual(encode.call_args_list[1].args[2]['nvenc_maxrate_mbps'],10)
            self.assertFalse(report['publication_authorized'])

    def test_full_structural_error_is_not_retried_or_kept_as_optimized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mkv';source.write_bytes(b'generated')
            sha=hashlib.sha256(source.read_bytes()).hexdigest()
            with patch('dv_mel.encode_candidate',side_effect=ValueError('RPU mismatch')) as encode:
                with self.assertRaisesRegex(ValueError,'RPU mismatch'):
                    refine_full_candidate(SimpleNamespace(directory=root,guard=Mock()),source,
                        dict(codec='hevc',encoder='hevc_nvenc'),source_id=sha,playback_verified_codecs=['hevc'])
            self.assertEqual(encode.call_count,1)
            import json
            self.assertEqual(json.loads((root/'mel-full-refinement.json').read_text())['status'],'validation_error')

    def test_full_retry_budget_is_hard_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mkv';source.write_bytes(b'x'*100)
            sha=hashlib.sha256(source.read_bytes()).hexdigest()
            good=dict(mean=99,p5=99,frames=24,passed=True)
            result=dict(source_sha256=sha,source_bytes=100,source_unchanged=True,copied_tracks_preserved=True,
                frame_checks=dict(frames=24),layer_checks=dict(frames=24,enhancement_types=['MEL']),output_bytes=40,
                quality=dict(self=good,candidate=dict(good,p5=80,passed=False),domain='dv-libplacebo-common-render-v1'))
            with patch('dv_mel.encode_candidate',return_value=result) as encode:
                report=refine_full_candidate(SimpleNamespace(directory=root,guard=Mock()),source,
                    dict(codec='hevc',encoder='hevc_nvenc',nvenc_cq=24),source_id=sha,
                    playback_verified_codecs=['hevc'],max_attempts=1)
            self.assertEqual(encode.call_count,1)
            self.assertEqual(report['status'],'quality_retry_budget_exhausted')
            self.assertNotIn('selected',report)

    def test_changed_source_never_starts_full_encode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mkv';source.write_bytes(b'changed')
            with patch('dv_mel.encode_candidate') as encode:
                with self.assertRaisesRegex(ValueError,'identity changed'):
                    refine_full_candidate(SimpleNamespace(directory=root,guard=Mock()),source,
                        dict(codec='hevc',encoder='hevc_nvenc'),source_id='old',playback_verified_codecs=['hevc'])
            encode.assert_not_called()

    def test_short_reference_uses_whole_unchanged_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mkv';source.write_bytes(b'generated')
            work=SimpleNamespace(directory=root,guard=Mock(),probe=Mock(return_value=dict(format=dict(duration='0.5'))))
            result=prepare_references(work,source,2)
            self.assertEqual(len(result['references']),1)
            self.assertTrue(result['references'][0]['whole_source'])
            self.assertEqual(result['references'][0]['sha256'],result['source_id'])
            self.assertEqual(source.read_bytes(),b'generated')

    def test_selector_keeps_failures_candidate_specific_and_preserves_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mkv';source.write_bytes(b'x'*100)
            sha=hashlib.sha256(source.read_bytes()).hexdigest()
            work=SimpleNamespace(directory=root,guard=Mock())
            reference=dict(id='whole',path=str(source),sha256=sha,bytes=100,whole_source=True)
            prepared=dict(source_id=sha,source_bytes=100,references=[reference])
            candidates=[dict(codec='hevc',encoder='hevc_nvenc',quality='transparent',nvenc_cq=q) for q in (24,28)]
            quality=dict(mean=99,p5=98,frames=24,passed=True)
            result=dict(source_sha256=sha,source_bytes=100,source_unchanged=True,copied_tracks_preserved=True,
                        frame_checks=dict(frames=24),layer_checks=dict(frames=24,enhancement_types=['MEL']),output_bytes=40,
                        quality=dict(self=quality,candidate=quality,domain='dv-libplacebo-common-render-v1'))
            with patch('dv_mel.prepare_references',return_value=prepared),patch('dv_mel.encode_candidate',
                    side_effect=[RuntimeError('candidate runtime failed'),result]):
                report,decision=compare_candidates(work,source,candidates,2,playback_verified_codecs=['hevc'])
            self.assertEqual(decision['action'],'encode_copy')
            self.assertEqual(decision['selected']['settings']['nvenc_cq'],28)
            self.assertIn('error',report['trials'][0]['samples'][0])
            self.assertFalse(decision['source_replacement_authorized'])

    def test_unverified_codec_never_encodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mkv';source.write_bytes(b'x'*100)
            sha=hashlib.sha256(source.read_bytes()).hexdigest()
            ref=dict(id='whole',path=str(source),sha256=sha,bytes=100,whole_source=True)
            with patch('dv_mel.prepare_references',return_value=dict(source_id=sha,source_bytes=100,references=[ref])),patch('dv_mel.encode_candidate') as encode:
                _,decision=compare_candidates(SimpleNamespace(directory=root,guard=Mock()),source,
                    [dict(codec='hevc',encoder='hevc_nvenc')],2,playback_verified_codecs=[])
            encode.assert_not_called()
            self.assertEqual(decision['action'],'keep_original')

    def test_terminal_hold_boundary_is_not_an_extra_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'clock.txt'
            rows=[dict(pts_time='3',duration_time='.08'),dict(pts_time='3.08',duration_time='.083')]
            self.assertEqual(write_decoded_timestamps(rows,target,include_end=True),2)
            self.assertEqual(target.read_text().splitlines()[1:],['3000.000000000','3080.000000000','3163.000000000'])

    def test_invalid_requests_do_not_create_files_or_run_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            workflow=SimpleNamespace(directory=Path(tmp),guard=Mock())
            for label,codec in [('../escape','hevc'),('candidate','av1'),('','hevc')]:
                with self.assertRaises(ValueError):
                    encode_candidate(workflow,Path(tmp)/'source.mkv',dict(codec=codec),label)
            self.assertEqual(list(Path(tmp).iterdir()),[])
