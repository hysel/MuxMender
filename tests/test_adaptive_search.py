import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import auto_optimize as ao
from test_auto_optimize import source_data


class AdaptiveTests(unittest.TestCase):
    def test_bounded_verified_encoders_and_hardest_scene(self):
        report={'trials':[dict(encoder='av1_nvenc',codec='av1',runtime_supported=True,
            playback_compatible=True,samples=[dict(reference_id='0',quality={'p5':94}),
                                             dict(reference_id='2',quality={'p5':86})])]}
        self.assertEqual(ao.hardest_reference(report,'av1_nvenc'),2)
        rows=ao.adaptive_candidates(report,2)
        self.assertEqual([r['nvenc_cq'] for r in rows],[23,22])
        self.assertTrue(all(r['nvenc_preset']=='p7' for r in rows))
        report['trials'][0]['runtime_supported']=False
        self.assertEqual(ao.adaptive_candidates(report),[])

    def test_adaptive_nvenc_options(self):
        for encoder,codec in [('av1_nvenc','av1'),('hevc_nvenc','hevc')]:
            with patch.object(ao.mm,'encoder_options',return_value=['-c:v',encoder,'-cq','21','-preset','p6']):
                command=ao.encode_command('ffmpeg',Path('in'),Path('out'),dict(codec=codec,
                    encoder=encoder,quality='balanced',nvenc_cq=23,nvenc_preset='p7'),None,[])
            self.assertEqual(command[command.index('-cq')+1],'23')
            self.assertEqual(command[command.index('-preset')+1],'p7')
            self.assertIn('-n',command)
            self.assertNotIn('-vf',command)

    def test_workflow_refines_and_requires_all_scenes(self):
        self.exercise_workflow(True)

    def test_failed_screen_stops_each_candidate_and_exhausts_budget(self):
        self.exercise_workflow(False)

    def exercise_workflow(self, adaptive_passes):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'input').mkdir();source=root/'input/source.mkv';source.write_bytes(b'original'*1000)
            output=root/'output'
            calls=[]
            def execute(workflow,command,label,duration):
                Path(command[-1]).write_bytes(b'x'*(1000 if label.startswith('reference-') else 100))
            def probe(workflow,path):
                data=source_data()
                if Path(path)!=source:data['format']['duration']='10'
                return data
            def quality(workflow,reference,encoded,label,count,duration):
                calls.append(label)
                passed=label.startswith('self-') or ('-p7-' in label and adaptive_passes)
                return dict(mean=99 if label.startswith('self-') else 96,
                            p5=99 if label.startswith('self-') else 92 if passed else 85,
                            passed=passed)
            with patch.object(ao.Workflow,'probe',probe), \
                 patch.object(ao.Workflow,'execute',execute), \
                 patch.object(ao.Workflow,'frame_file',return_value=root/'frames'), \
                 patch.object(ao.Workflow,'validate'), \
                 patch.object(ao.Workflow,'quality',quality), \
                 patch.object(ao,'compare_frames',return_value=1), \
                 patch.object(ao.subprocess,'check_output',return_value='libvmaf'), \
                 patch.object(ao.mm,'ffmpeg_encoder_names',return_value={'av1_nvenc'}), \
                 patch.object(ao,'probe_encoder',return_value={'status':'working'}), \
                 patch.object(ao.mm,'probe',return_value=None), \
                 patch.object(ao.mm,'encoder_options',return_value=['-c:v','av1_nvenc','-cq','21','-preset','p6']):
                self.assertEqual(ao.main([str(source),'--output-dir',str(output),'--hardware','nvidia',
                    '--playback-verified-codecs','av1','--execute','--adaptive']),0)
            run=next(output.glob('auto-*'))
            state=json.loads((run/'status.json').read_text())
            self.assertEqual(state['decision']['action'],'encode_copy' if adaptive_passes else 'keep_original')
            self.assertEqual(len([c for c in calls if '-p7-' in c]),3 if adaptive_passes else 4)
            search=json.loads((run/'adaptive-search.json').read_text())
            self.assertEqual(search['extra_trials'],1 if adaptive_passes else 4)
            self.assertEqual(search['cpu_fallback'],'not_run_requires_explicit_opt_in')
            self.assertEqual(source.read_bytes(),b'original'*1000)
