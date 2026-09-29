import copy
import unittest
from unittest.mock import patch
import auto_optimize as ao
from native_pipeline import decode_maps_after_frame_audit
from test_auto_optimize import source_data


class MultipleVideoTests(unittest.TestCase):
    def test_missing_cover_labels_are_derived_not_an_admission_gate(self):
        data=self.fixture()
        cover=dict(index=3,codec_type='video',codec_name='mjpeg',disposition={'attached_pic':1})
        data['streams'].append(cover)
        self.assertEqual(ao.main_video(data)['index'],0)
        self.assertEqual(ao.cover_labels(cover),dict(filename='cover-3.jpg',mimetype='image/jpeg'))
        after=copy.deepcopy(data);after['streams'][0]['codec_name']='hevc'
        after['streams'][-1]['tags']=ao.cover_labels(cover)
        ao.metadata_check(data,after,'hevc')
        after['streams'][-1]['tags']['mimetype']='image/png'
        with self.assertRaises(ValueError):ao.metadata_check(data,after,'hevc')

    def test_hardware_finalizer_replaces_only_primary_track(self):
        from mux_integrity import finalize_command
        data=self.fixture()
        data['streams'].insert(0,dict(index=4,codec_type='video',codec_name='mjpeg',
                                    disposition={'attached_pic':1}))
        command=finalize_command('encoded','original','output',data,'ffmpeg')
        maps=[command[i+1] for i,value in enumerate(command) if value=='-map']
        self.assertEqual(maps,['1:4','0:V:0','1:1'])
        self.assertEqual(command[command.index('-map_metadata:s:1')+1],'1:s:0')

    def fixture(self):
        data=source_data();second=copy.deepcopy(data['streams'][0]);second['index']=1
        second['width']=640;second['height']=360;second['tags']={'title':'Secondary view'}
        data['streams'].append(second)
        return data

    def test_primary_encoded_secondary_copied_and_fully_checked(self):
        data=self.fixture()
        self.assertEqual(ao.main_video(data)['index'],0)
        self.assertEqual(ao.copied_track_indices(data),[1])
        with patch.object(ao.mm,'encoder_options',return_value=['-c:v','hevc_nvenc']):
            command=ao.encode_command('ffmpeg','in','out',dict(codec='hevc',quality='balanced',encoder='hevc_nvenc'),None,data['streams'])
        self.assertIn('-c:v:0',command);self.assertNotIn('-c:v',command)
        after=copy.deepcopy(data);after['streams'][0]['codec_name']='hevc'
        ao.metadata_check(data,after,'hevc')
        maps,reused=decode_maps_after_frame_audit(after,100)
        self.assertTrue(reused);self.assertIn('0:1',maps)
        after['streams'][1]['codec_name']='hevc'
        with self.assertRaises(ValueError):ao.metadata_check(data,after,'hevc')
