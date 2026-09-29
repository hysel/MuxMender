import unittest
from codec_selection import select_candidate


class H264CandidateTests(unittest.TestCase):
    def test_adaptive_h264_retains_runtime_requirement(self):
        from auto_optimize import adaptive_candidates
        trial=dict(encoder='h264_nvenc',codec='h264',runtime_supported=True,playback_compatible=True,
                   samples=[dict(quality=dict(passed=False,p5=80))],settings=dict(quality='balanced'))
        candidates=adaptive_candidates(dict(trials=[trial]))
        self.assertTrue(candidates)
        self.assertTrue(all(c['codec']=='h264' for c in candidates))
        self.assertEqual(candidates[0]['nvenc_cq'],20)
        trial['runtime_supported']=False
        self.assertEqual(adaptive_candidates(dict(trials=[trial])),[])

    def test_h264_requires_same_full_sample_evidence(self):
        samples=[dict(reference_id=str(i),bytes=50,quality_pass=True,preservation_pass=True,
                      decode_pass=True,quality_method='woven and field VMAF') for i in range(3)]
        report=dict(schema='muxmender-codec-trials-v1',source_id='generated',color_mode='sdr',
            references=[dict(id=str(i),bytes=100) for i in range(3)],trials=[dict(id='h264',codec='h264',
            encoder='h264_nvenc',source_id='generated',runtime_supported=True,playback_compatible=True,
            settings=dict(quality='transparent'),samples=samples)])
        self.assertEqual(select_candidate(report)['action'],'encode_copy')
        samples[0]['preservation_pass']=False
        self.assertEqual(select_candidate(report)['action'],'keep_original')
