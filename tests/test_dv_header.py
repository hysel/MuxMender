import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import dv_header


class HeaderRecoveryTests(unittest.TestCase):
    def setUp(self):
        dv_header._cache.clear()
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source=Path(self.tmp.name)/'source.mkv'
        self.source.write_bytes(b'unchanged fixture')
        self.config=dict(dv_profile=8,rpu_present_flag=1,el_present_flag=0,dv_bl_signal_compatibility_id=1)

    def data(self):
        return {'streams':[dict(codec_type='video',codec_name='hevc',color_transfer='smpte2084',side_data_list=None)]}

    def outputs(self,config=None):
        return [SimpleNamespace(stdout=json.dumps({'frames':[{'side_data_list':[{'side_data_type':'Dolby Vision RPU Data'}]}]})),
                SimpleNamespace(),SimpleNamespace(),
                SimpleNamespace(stdout=json.dumps({'streams':[{'side_data_list':[config or self.config]}]}))]

    def test_missing_header_recovered_without_source_change_and_cached(self):
        data=self.data()
        with patch('dv_header.subprocess.run',side_effect=self.outputs()) as run,patch('dv_header.shutil.which',side_effect=lambda x:x):
            result=dv_header.recover(data,self.source)
            self.assertTrue(result['routing_only'])
            self.assertTrue(result['full_bitstream_validation_required'])
            self.assertEqual(data['streams'][0]['side_data_list'],[self.config])
            command=run.call_args_list[1].args[0]
            self.assertIn('copy',command)
            self.assertIn('67108864',command)
            self.assertFalse(Path(command[-1]).parent.exists())
            dv_header.recover(self.data(),self.source)
            self.assertEqual(run.call_count,4)
        self.assertEqual(self.source.read_bytes(),b'unchanged fixture')

    def test_existing_header_never_overridden(self):
        data=self.data();data['streams'][0]['side_data_list']=[self.config]
        with patch('dv_header.subprocess.run') as run:
            self.assertIsNone(dv_header.recover(data,self.source))
            run.assert_not_called()

    def test_non_dv_hdr_does_not_remux(self):
        with patch('dv_header.subprocess.run',return_value=SimpleNamespace(stdout='{"frames":[]}')) as run:
            self.assertIsNone(dv_header.recover(self.data(),self.source))
            self.assertEqual(run.call_count,1)

    def test_no_rpu_rejected(self):
        config=dict(self.config,rpu_present_flag=0)
        with patch('dv_header.subprocess.run',side_effect=self.outputs(config)),patch('dv_header.shutil.which',side_effect=lambda x:x):
            with self.assertRaisesRegex(ValueError,'unambiguously'):
                dv_header.recover(self.data(),self.source)
        self.assertFalse(dv_header._cache)

    def test_other_codec_and_missing_source_do_not_decode(self):
        data=self.data();data['streams'][0]['codec_name']='h264'
        with patch('dv_header.subprocess.run') as run:
            self.assertIsNone(dv_header.recover(data,self.source))
            self.assertIsNone(dv_header.recover(self.data(),self.source.with_name('missing.mkv')))
            run.assert_not_called()

    def test_missing_color_tags_and_later_frames_are_inspected(self):
        data=self.data();data['streams'][0].pop('color_transfer');data['format']={'duration':'100'}
        with patch('dv_header.subprocess.run',side_effect=self.outputs()) as run,patch('dv_header.shutil.which',side_effect=lambda x:x):
            self.assertIsNotNone(dv_header.recover(data,self.source))
            command=run.call_args_list[0].args[0]
            self.assertEqual(command[command.index('-read_intervals')+1],'0%+0.5,15%+0.5,50%+0.5,85%+0.5')

    def test_decoded_color_evidence_fills_only_missing_fields(self):
        data=self.data();data['streams'][0]['color_transfer']='unknown';data['streams'][0]['color_primaries']='bt709'
        outputs=self.outputs()
        outputs[0].stdout=json.dumps({'frames':[dict(best_effort_timestamp_time='50',color_transfer='smpte2084',color_primaries='bt2020',side_data_list=[{'side_data_type':'Dolby Vision RPU Data'}])]})
        with patch('dv_header.subprocess.run',side_effect=outputs) as run,patch('dv_header.shutil.which',side_effect=lambda x:x):
            result=dv_header.recover(data,self.source)
        self.assertEqual(data['streams'][0]['color_transfer'],'smpte2084')
        self.assertEqual(data['streams'][0]['color_primaries'],'bt709')
        self.assertEqual(result['decoded_color_recovered'],{'color_transfer':'smpte2084'})
        command=run.call_args_list[1].args[0]
        self.assertEqual(command[command.index('-ss')+1],'50.0')

    def test_failed_extraction_removes_temporary_files(self):
        commands=[]
        def run(command,**kwargs):
            commands.append(command)
            if len(commands)==1:return self.outputs()[0]
            Path(command[-1]).write_bytes(b'partial fixture')
            raise subprocess.TimeoutExpired(command,60)
        with patch('dv_header.subprocess.run',side_effect=run),patch('dv_header.shutil.which',side_effect=lambda x:x):
            with self.assertRaises(subprocess.TimeoutExpired):
                dv_header.recover(self.data(),self.source)
        self.assertFalse(Path(commands[-1][-1]).parent.exists())
        self.assertEqual(self.source.read_bytes(),b'unchanged fixture')
        self.assertFalse(dv_header._cache)

    def test_other_metadata_survives_and_cache_is_not_mutable_by_caller(self):
        data=self.data();data['streams'][0]['side_data_list']=[{'side_data_type':'Content light level metadata','max_content':1000}]
        original=dict(data['streams'][0]['side_data_list'][0])
        with patch('dv_header.subprocess.run',side_effect=self.outputs()),patch('dv_header.shutil.which',side_effect=lambda x:x):
            dv_header.recover(data,self.source)
        self.assertEqual(data['streams'][0]['side_data_list'][0],original)
        data['streams'][0]['side_data_list'][1]['dv_profile']=5
        other=self.data();dv_header.recover(other,self.source)
        self.assertEqual(other['streams'][0]['side_data_list'][0]['dv_profile'],8)
