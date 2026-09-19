import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import auto_optimize as ao
from codec_selection import select_candidate
from test_auto_optimize import source_data
from test_codec_selection import evidence


class EfficiencyScreenTests(unittest.TestCase):
    def run_fixture(self, size=1000, quality_pass=True, baseline=97.76, encode_error=False):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'input').mkdir()
            source=root/'input/source.mkv';source.write_bytes(b'original'*1000)
            out=root/'output';calls=[]
            def execute(workflow,command,label,duration):
                if encode_error and not label.startswith('reference-'):
                    raise RuntimeError('Encoder unavailable')
                Path(command[-1]).write_bytes(b'x'*(1000 if label.startswith('reference-') else size))
            def probe(workflow,path):
                data=source_data()
                if Path(path)!=source:data['format']['duration']='10'
                return data
            def quality(workflow,reference,encoded,label,count,duration):
                calls.append(label)
                self_test=label.startswith('self-')
                return dict(mean=baseline if self_test else 96 if quality_pass else 94,
                            p5=96 if self_test else 92 if quality_pass else 85,
                            passed=self_test or quality_pass,frames=1)
            with patch.object(ao.Workflow,'probe',probe), \
                 patch.object(ao.Workflow,'execute',execute), \
                 patch.object(ao.Workflow,'frame_file',return_value=root/'frames'), \
                 patch.object(ao.Workflow,'validate') as validate, \
                 patch.object(ao.Workflow,'quality',quality), \
                 patch.object(ao,'compare_frames',return_value=1), \
                 patch.object(ao.subprocess,'check_output',return_value='libvmaf'), \
                 patch.object(ao.mm,'ffmpeg_encoder_names',return_value={'av1_nvenc'}), \
                 patch.object(ao,'probe_encoder',return_value={'status':'working'}), \
                 patch.object(ao.mm,'probe',return_value=None), \
                 patch.object(ao.mm,'encoder_options',return_value=['-c:v','av1_nvenc']):
                ao.main([str(source),'--output-dir',str(out),'--hardware','nvidia',
                         '--playback-verified-codecs','av1','--execute'])
            run=next(out.glob('auto-*'))
            self.assertEqual(source.read_bytes(),b'original'*1000)
            self.assertFalse(list(run.glob('full-*')))
            return json.loads((run/'status.json').read_text()),json.loads((run/'trials.json').read_text()),calls,validate.call_count

    def test_oversized_candidates_skip_all_vmaf_and_validation(self):
        state,report,calls,validations=self.run_fixture(size=1100)
        self.assertEqual(calls,[])
        self.assertEqual(validations,0)
        self.assertEqual(state['decision']['reason_code'],'already_efficient_for_settings')
        self.assertTrue(state['decision']['cacheable'])
        self.assertTrue(all(len(t['samples'])==3 for t in report['trials']))
        self.assertTrue(all(t['size_screen']['rejected'] for t in report['trials']))

    def test_viable_size_still_requires_every_quality_check(self):
        state,report,calls,validations=self.run_fixture(size=500)
        self.assertEqual(state['decision']['action'],'encode_copy')
        self.assertEqual(validations,6)
        self.assertEqual(len(calls),9)  # Three shared self-checks, six candidates' scenes.
        self.assertTrue(all(s['quality_pass'] for t in report['trials'] for s in t['samples']))

    def test_quality_failure_short_circuits_remaining_validation(self):
        state,report,calls,validations=self.run_fixture(size=500,quality_pass=False)
        self.assertEqual(state['decision']['reason_code'],'already_efficient_for_settings')
        self.assertEqual(validations,2)
        self.assertEqual(len(calls),3)
        self.assertTrue(all(t['screened_out'] for t in report['trials']))

    def test_encoder_error_is_not_cached_as_efficient(self):
        state,report,calls,validations=self.run_fixture(encode_error=True)
        self.assertEqual(state['decision']['reason_code'],'evaluation_inconclusive')
        self.assertFalse(state['decision']['cacheable'])
        self.assertEqual(calls,[])

    def test_size_screen_flag_cannot_bypass_validation_for_small_output(self):
        report=evidence()
        for t in report['trials']:
            t['size_screen']={'rejected':True}
            for s in t['samples']:
                s.update(encode_completed=True,quality_pass=False,preservation_pass=False,decode_pass=False)
        result=select_candidate(report)
        self.assertEqual(result['action'],'keep_original')
        self.assertFalse(result['cacheable'])

    def test_invalid_or_incomplete_size_evidence_not_an_efficiency_decision(self):
        for bad in ('missing','mismatch','error','unsupported'):
            report=evidence()
            for t in report['trials']:
                t['size_screen']={'rejected':True}
                for s in t['samples']:s.update(bytes=2000,encode_completed=True)
                if bad=='missing':t['samples'].pop()
                if bad=='mismatch':t['source_id']='other'
                if bad=='error':t['samples'][0]['error']='decode failed'
                if bad=='unsupported':t['runtime_supported']=False
            result=select_candidate(report)
            self.assertEqual(result['reason_code'],'evaluation_inconclusive')


if __name__=='__main__':unittest.main()
