import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from gpu_admission import decide,observe,load,save,family,headroom,stage_context


HEALTHY=dict(gpu_encode_percent=20,gpu_decode_percent=10,gpu_compute_percent=10,
    vram_free_gib=6,gpu_temperature=50,available_gib=16,host_available_gib=32,
    cpu_percent=20,container_cpu_percent=20,memory_pressure=0,io_pressure=0)
VIDEO=dict(width=1920,height=1080,pix_fmt='yuv420p',avg_frame_rate='24/1',field_order='progressive',color_transfer='bt709')


class AdaptiveGpuTests(unittest.TestCase):
    def test_brief_overlap_cannot_falsely_double_throughput(self):
        state=self.learned();decide(state,HEALTHY,'fixture',35,10)
        for i in range(5):observe(state,'fixture',10,10,.1,True,40+i)
        self.assertEqual(state['groups']['fixture']['paired'],[])
        self.assertEqual(state['groups']['fixture']['mode'],'trial')

    def test_headroom_is_complete_finite_and_engine_specific(self):
        self.assertTrue(headroom(HEALTHY)[0])
        for key in HEALTHY:
            missing=dict(HEALTHY);missing.pop(key)
            self.assertFalse(headroom(missing)[0],key)
            self.assertFalse(headroom(dict(HEALTHY,**{key:float('nan')}))[0],key)
        for key,value in [('gpu_encode_percent',90),('gpu_decode_percent',90),
                          ('gpu_compute_percent',90),('vram_free_gib',2),('gpu_temperature',80),
                          ('available_gib',3),('cpu_percent',90),('io_pressure',10)]:
            self.assertFalse(headroom(dict(HEALTHY,**{key:value}))[0],key)

    def learned(self):
        state={};decide(state,HEALTHY,'fixture',0,0)
        for i in range(3):observe(state,'fixture',10,10,False,True,i+1)
        return state

    def test_two_needs_baseline_backlog_and_sustained_health(self):
        state={};self.assertEqual(decide(state,HEALTHY,'fixture',0,10),1)
        self.assertEqual(decide(state,HEALTHY,'fixture',35,10),1)
        state=self.learned()
        self.assertEqual(decide(state,HEALTHY,'fixture',20,10),1)
        self.assertEqual(decide(state,HEALTHY,'fixture',35,0),1)
        self.assertEqual(decide(state,HEALTHY,'fixture',35,10),2)

    def test_no_benefit_reverts_and_cools_down(self):
        state=self.learned();decide(state,HEALTHY,'fixture',35,10)
        for i in range(3):observe(state,'fixture',10,25,True,True,40+i)
        self.assertEqual(state['groups']['fixture']['mode'],'serial')
        self.assertEqual(decide(state,HEALTHY,'fixture',100,10),1)

    def test_gain_keeps_two_until_pressure_or_failure(self):
        state=self.learned();decide(state,HEALTHY,'fixture',35,10)
        for i in range(3):observe(state,'fixture',10,12,True,True,40+i)
        self.assertEqual(decide(state,HEALTHY,'fixture',50,10),2)
        self.assertEqual(decide(state,dict(HEALTHY,gpu_encode_percent=90),'fixture',55,10),1)
        self.assertEqual(decide(state,HEALTHY,'fixture',56,10,paused=True),1)
        observe(state,'fixture',10,12,True,False,60)
        self.assertEqual(state['groups']['fixture']['mode'],'serial')

    def test_unknown_quiet_timeout_and_short_measurement_do_not_promote(self):
        state=self.learned()
        self.assertEqual(decide(state,HEALTHY,'fixture',35,10,maximum=1),1)
        self.assertEqual(decide(state,HEALTHY,None,100,10),1)
        state=self.learned();decide(state,HEALTHY,'fixture',35,10)
        self.assertEqual(decide(state,HEALTHY,'fixture',400,10),1)
        observe(state,'fixture',10,.5,False,True,401)
        self.assertEqual(len(state['groups']['fixture']['single']),3)

    def test_paths_do_not_identify_stage_family(self):
        self.assertEqual(family(['ffmpeg','-i','one.mkv','-c:v','hevc_nvenc','a.mkv'],10,VIDEO),
                         family(['ffmpeg','-i','two.mkv','-c:v','hevc_nvenc','b.mkv'],10,VIDEO))
        self.assertNotEqual(family(['ffmpeg','-c:v','hevc_nvenc'],10,VIDEO),family(['ffmpeg','-c:v','av1_nvenc'],10,VIDEO))
        self.assertNotEqual(family(['ffmpeg','-c:v','hevc_nvenc'],10,VIDEO),family(['ffmpeg','-c:v','hevc_nvenc'],10,dict(VIDEO,width=3840,height=2160)))
        self.assertIsNone(family(['ffmpeg','-c:v','hevc_nvenc'],10))
        self.assertIsNone(family([],None))

    def test_state_is_bounded_and_malformed_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'adaptive.json';state={}
            for i in range(30):decide(state,HEALTHY,str(i),i,0)
            self.assertEqual(len(state['groups']),16)
            save(path,state);self.assertEqual(load(path),state)
            path.write_text('{"schema":1,"groups":[]}')
            self.assertEqual(load(path),{})
            path.write_text('x'*131073);self.assertEqual(load(path),{})

    @unittest.skipUnless(os.name=='posix','Linux shared-slot tests only')
    def test_existing_os_slots_enforce_two_and_cleanup_records(self):
        from validation_resources import validation_slot,AdmissionBudget
        command=['ffmpeg','-c:v','hevc_nvenc'];key=family(command,10,VIDEO)
        with tempfile.TemporaryDirectory() as directory:
            gpu=Path(directory)/'gpu';gpu.mkdir()
            state={};decide(state,HEALTHY,key,1,0)
            state['groups'][key].update(mode='parallel',single=[1,1,1],paired=[1,1,1])
            save(gpu/'adaptive.json',state)
            env=dict(MUXMENDER_VALIDATION_LOCK_ROOT=directory)
            with patch.object(AdmissionBudget,'gpu_sample',return_value=HEALTHY),stage_context(VIDEO):
                with validation_slot(command,pool='gpu',env=env,estimated_duration=10):
                    with validation_slot(command,pool='gpu',env=env,estimated_duration=10):
                        self.assertEqual(len(load(gpu/'adaptive.json')['active']),2)
                        with self.assertRaises(TimeoutError):
                            with validation_slot(command,pool='gpu',env=env,estimated_duration=10,timeout=0):pass
            self.assertEqual(load(gpu/'adaptive.json')['active'],{})
            self.assertFalse(list(gpu.glob('wait-*.lock')))
