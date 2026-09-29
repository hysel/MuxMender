import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import ExitStack

import auto_optimize as ao
import full_conversion_research as research
from full_research_app import cases, command
from test_auto_optimize import source_data


class FullResearchTests(unittest.TestCase):
    def test_writeable_source_refused(self):
        with patch.object(research.os,'statvfs',create=True,return_value=SimpleNamespace(f_flag=0)):
            with self.assertRaises(ValueError):research.require_read_only(Path('.'))

    def test_command_keeps_floors_and_no_publication(self):
        cmd=command(dict(source='/media/example.mkv',cq=26),Path('/output/case'))
        for flag,value in [('--vmaf-mean','90'),('--vmaf-p5','90'),('--research-full-av1-cq','26')]:
            self.assertEqual(cmd[cmd.index(flag)+1],value)
        self.assertNotIn('--adaptive',cmd)
        self.assertNotIn('publish_worker',cmd)

    def test_manifest_cannot_escape_media_or_repeat_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);media=root/'media';media.mkdir()
            source=media/'source.mkv';source.write_bytes(b'fixture')
            manifest=root/'cases.json'
            row=dict(id='case-1',source=str(source),cq=26)
            manifest.write_text(json.dumps([row,row]))
            with self.assertRaises(ValueError):cases(manifest,media)
            row['source']=str(manifest)
            manifest.write_text(json.dumps([row]))
            with self.assertRaises(ValueError):cases(manifest,media)

    def test_sample_failure_still_measures_full_copy_without_approval(self):
        self.exercise(False)

    def test_full_preservation_failure_retains_output(self):
        self.exercise(True)

    def exercise(self, fail_validation):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);media=root/'media';media.mkdir()
            source=media/'source.mkv';source.write_bytes(b'original'*1000)
            output=root/'output'
            full_settings=[];quality_labels=[]
            def probe(workflow,path):
                data=source_data()
                if Path(path)!=source:data['format']['duration']='10'
                return data
            def execute(workflow,cmd,label,duration,**kwargs):
                Path(cmd[-1]).write_bytes(b'x'*(1000 if label.startswith('reference') else 100))
            def encode(workflow,src,dst,settings,info,before,label,duration):
                if label=='research-full-encode':full_settings.append(settings)
                dst.write_bytes(b'x'*100)
            def quality(workflow,ref,out,label,count,duration):
                quality_labels.append(label)
                return dict(mean=99 if label.startswith('self') else 92,p5=99 if label.startswith('self') else 87,
                            passed=label.startswith('self'))
            def validate(workflow,ref,out,before,codec,label,frames):
                if fail_validation and label=='research-full':raise ValueError('Fixture metadata mismatch')
            with ExitStack() as stack:
                for obj,name,value in [
                    (research,'require_read_only',lambda source:None),
                    (ao.Workflow,'probe',probe),(ao.Workflow,'execute',execute),
                    (ao.Workflow,'encode_preserving_color',encode),(ao.Workflow,'quality',quality),
                    (ao.Workflow,'validate',validate)]:stack.enter_context(patch.object(obj,name,value))
                for obj,name,value in [
                    (ao.Workflow,'frame_file',root/'frames'),(ao,'compare_frames',1),
                    (ao.subprocess,'check_output','libvmaf'),(ao.mm,'ffmpeg_encoder_names',{'av1_nvenc'}),
                    (ao,'probe_encoder',{'status':'working'}),
                    (ao.mm,'probe',SimpleNamespace(dolby_vision=False))]:
                    stack.enter_context(patch.object(obj,name,return_value=value))
                cleanup=stack.enter_context(patch.object(ao.Workflow,'cleanup_terminal_artifacts'))
                args=command(dict(source=str(source),cq=26),output)[4:]
                args[args.index('--savings-mode')+1]='fixed'
                args[args.index('--min-free-gib')+1]='1'
                # Shared frontend command begins with python -B -m auto_optimize.
                if fail_validation:
                    with self.assertRaisesRegex(ValueError,'Fixture metadata'):ao.main(args)
                else:self.assertEqual(ao.main(args),0)
                cleanup.assert_called_once()
            folder=next(output.glob('auto-*'))
            state=json.loads((folder/'status.json').read_text())
            self.assertTrue(state['research_only'])
            self.assertFalse(state['publication_authorized'])
            self.assertEqual(state['sample_decision']['action'],'keep_original')
            self.assertNotEqual(state['state'],'validated-copy-awaiting-playback')
            self.assertTrue((folder/'research-full-av1.mkv').exists())
            self.assertEqual(source.read_bytes(),b'original'*1000)
            self.assertEqual(full_settings[0]['nvenc_cq'],26)
            self.assertEqual(full_settings[0]['nvenc_preset'],'p7')
            self.assertEqual(full_settings[0]['nvenc_maxrate_mbps'],200)
            if not fail_validation:
                self.assertIn('research-full',quality_labels)
                self.assertFalse(state['all_checks_passed'])


if __name__=='__main__':unittest.main()
