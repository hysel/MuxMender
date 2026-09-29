import copy
import subprocess
import unittest
from unittest.mock import patch

import auto_optimize as ao
from nvenc_quality_retry import rate_retry
from test_auto_optimize import source_data
from test_codec_selection import evidence
from codec_selection import select_candidate


def failed_trial():
    return dict(id='hevc-balanced',encoder='hevc_nvenc',runtime_supported=True,
                playback_compatible=True,settings=dict(codec='hevc',encoder='hevc_nvenc',quality='balanced'),
                samples=[dict(reference_id='2',quality={'passed':False,'p5':86},
                              preservation_pass=True,decode_pass=True)])


class RetryPolicyTests(unittest.TestCase):
    def test_source_derived_single_variable_retry(self):
        report={'trials':[failed_trial()]};original=copy.deepcopy(report)
        retry=rate_retry(report,20_000_000_000,4800)
        self.assertEqual(retry['settings']['nvenc_maxrate_mbps'],200)
        self.assertEqual({k:v for k,v in retry['settings'].items() if k!='nvenc_maxrate_mbps'},
                         report['trials'][0]['settings'])
        self.assertEqual(report,original)
        self.assertEqual(retry['maximum_additional_trials'],1)
        self.assertEqual(rate_retry(report,2_000_000_000,4800)['settings']['nvenc_maxrate_mbps'],20)
        self.assertEqual(rate_retry(report,20_000_000_000,100)['settings']['nvenc_maxrate_mbps'],1000)

    def test_no_retry_without_measured_preserved_quality_failure(self):
        for change in ('size','error','unverified','preservation','explicit','other'):
            t=failed_trial()
            if change=='size':t['samples'][0].pop('quality');t['size_screen']={'rejected':True}
            if change=='error':t['samples'][0]['error']='broken frame'
            if change=='unverified':t['runtime_supported']=False
            if change=='preservation':t['samples'][0]['preservation_pass']=False
            if change=='explicit':t['settings']['nvenc_maxrate_mbps']=100
            if change=='other':t['encoder']='av1_nvenc'
            self.assertIsNone(rate_retry({'trials':[t]},20_000_000_000,4800),change)
        for size,duration in [(True,2),(1,0),(1,float('nan')),(1,float('inf'))]:
            self.assertIsNone(rate_retry({'trials':[failed_trial()]},size,duration))

    def test_hard_scene_shared_between_codecs_but_local_evidence_preferred(self):
        report={'trials':[failed_trial()]}
        self.assertEqual(ao.hardest_reference(report,'av1_nvenc'),2)
        report['trials'].append(dict(encoder='av1_nvenc',samples=[dict(reference_id='1',quality={'p5':91})]))
        self.assertEqual(ao.hardest_reference(report,'av1_nvenc'),1)

    def test_exact_rate_options_runtime_test_uses_generated_source(self):
        settings=rate_retry({'trials':[failed_trial()]},20_000_000_000,4800)['settings']
        with patch.object(ao.mm,'encoder_options',return_value=['-c:v','hevc_nvenc','-cq','21']), \
             patch.object(ao.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','')) as run:
            result=ao.probe_rate_retry('ffmpeg',settings,None,source_data()['streams'][0])
        command=run.call_args.args[0]
        self.assertEqual(command[command.index('-maxrate:v:0')+1],'200000000')
        self.assertEqual(command[command.index('-frames:v:0')+1],'64')
        self.assertTrue(command[command.index('-i')+1].startswith('nullsrc='))
        self.assertEqual(command[-3:],['-f','null','-'])
        self.assertEqual(result['status'],'working')

    def test_selection_exposes_distinct_user_outcomes(self):
        report=evidence()
        for t in report['trials']:
            for s in t['samples']:s.update(quality_pass=False,quality={'passed':False})
        result=select_candidate(report)
        self.assertEqual(result['outcome_category'],'quality')
        self.assertNotIn('No worthwhile savings',result['reason'])
        report=evidence()
        for t in report['trials']:
            for s in t['samples']:s['bytes']=1100
        self.assertEqual(select_candidate(report)['outcome_category'],'savings')
        report['trials'][0]['samples'][0]['error']='decode failed'
        self.assertEqual(select_candidate(report)['outcome_category'],'error')
        self.assertFalse(select_candidate(report)['cacheable'])


if __name__=='__main__':unittest.main()
