import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch
from validation_resources import heavy_reader,validation_slot,validation_limited
from validation_resources import AdmissionBudget,resource_pool,publication_limited
from resource_governor import validation_capacity


class ResourceTests(unittest.TestCase):
    def test_first_gpu_sample_primes_cpu_counters_and_reuses_complete_measurement(self):
        budget=AdmissionBudget()
        sample=dict(cpu_percent=25,container_cpu_percent=20,gpu_encode_percent=10)
        with patch.object(budget.governor,'sample',side_effect=[{},sample]) as measure, \
             patch('validation_resources.time.sleep') as pause, \
             patch('validation_resources.time.monotonic',return_value=10):
            self.assertEqual(budget.gpu_sample(),sample)
            self.assertEqual(budget.gpu_sample(),sample)
            self.assertEqual(measure.call_count,2)
            self.assertEqual(measure.call_args_list[0].kwargs,dict(include_gpu=False))
            pause.assert_called_once_with(.25)

    def test_gpu_sampling_failure_keeps_missing_telemetry_fail_closed(self):
        budget=AdmissionBudget()
        with patch.object(budget.governor,'sample',side_effect=OSError('missing counters')):
            self.assertEqual(budget.gpu_sample(),{})

    def test_native_reader_requires_explicit_activation_for_gpu_admission(self):
        command=['/opt/readers/ffprobe-cuda','-show_frames','source.mkv']
        self.assertEqual(resource_pool(command),'validation')
        self.assertEqual(resource_pool(command,{'MUXMENDER_RESEARCH_CUDA_READER':'1'}),'gpu')
        self.assertEqual(resource_pool(command,{'MUXMENDER_RESEARCH_CUDA_READER':'0'}),'validation')
        self.assertIsNone(resource_pool(['ffprobe-cuda','-show_packets'],{'MUXMENDER_RESEARCH_CUDA_READER':'1'}))

    def test_stage_pool_classification(self):
        for command,pool in [(['ffprobe','-show_frames'],'validation'),
            (['ffmpeg','-lavfi','libvmaf=model=x'],'validation'),
            (['ffmpeg','-filter_complex','libplacebo=tonemapping=bt.2390,libvmaf'],'gpu'),
            (['ffmpeg','-c:v','av1_nvenc'],'gpu'),
            (['ffmpeg','-c:v','hevc_nvenc'],'gpu'),
            (['ffmpeg','-c:v:0','hevc_nvenc'],'gpu'),
            (['ffmpeg','-codec:v:1','av1_nvenc'],'gpu'),
            (['ffmpeg','-i','example_hevc_nvenc.mkv','-c','copy'],None),
            (['ffprobe','-show_packets'],None)]:
            self.assertEqual(resource_pool(command),pool)

    @unittest.skipUnless(os.name=='posix','OS lock tests require Linux')
    def test_independent_pools_overlap_without_raising_job_ceiling(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp),patch('validation_resources.AdmissionBudget.sample',return_value=1):
            with validation_slot(['ffprobe','-show_frames']):
                with validation_slot(['ffmpeg','-c:v','hevc_nvenc'],pool='gpu',timeout=0):
                    with validation_slot([],pool='publication',timeout=0):
                        with self.assertRaises(TimeoutError):
                            with validation_slot([],pool='publication',timeout=0):pass
                        with self.assertRaises(TimeoutError):
                            with validation_slot(['ffmpeg','-lavfi','libplacebo'],pool='gpu',timeout=0):pass

    @unittest.skipUnless(os.name=='posix','OS lock tests require Linux')
    def test_gpu_sharing_lease_prevents_launch(self):
        import json,time
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp):
            lease=Path(tmp)/'pause.json'
            lease.write_text(json.dumps(dict(pause=True,expires_at=time.time()+30,reason='External workload')))
            with patch.dict(os.environ,MUXMENDER_PAUSE_LEASE=str(lease)):
                with self.assertRaises(TimeoutError):
                    with validation_slot(['ffmpeg','-c:v','hevc_nvenc'],pool='gpu',timeout=0):pass
                lease.write_text(json.dumps(dict(pause=False)))
                with validation_slot(['ffmpeg','-c:v','hevc_nvenc'],pool='gpu',timeout=0):pass

    def test_cancelled_publication_never_calls_publisher(self):
        calls=[]
        @publication_limited
        def publish(stopped=lambda:False):calls.append(1)
        with self.assertRaises(InterruptedError):publish(stopped=lambda:True)
        self.assertEqual(calls,[])

    def test_gpu_execution_timeout_excludes_admission(self):
        @validation_limited
        def encode(command,timeout,guard,env=None):return timeout
        guard=lambda:None
        with patch('validation_resources.validation_slot') as slot:
            self.assertEqual(encode(['ffmpeg','-c:v','av1_nvenc'],7,guard),7)
        slot.assert_called_once_with(['ffmpeg','-c:v','av1_nvenc'],guard,pool='gpu',env=None,estimated_duration=None)

    def test_publication_worker_receives_shared_resource_root(self):
        import inspect,control_service
        code=inspect.getsource(control_service.Controls.step)
        self.assertIn("publication_env=dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=str(self.output/'.validation-resources'))",code)
        self.assertIn('env=publication_env',code)

    def test_capacity_requires_all_headroom(self):
        healthy=dict(cpus=16,cpu_percent=20,container_cpu_percent=20,available_gib=16,
                     host_available_gib=32,io_pressure=0,memory_pressure=0,
                     gpu_percent=10,vram_free_gib=6,gpu_temperature=50)
        self.assertEqual(validation_capacity(healthy),2)
        for key in healthy:
            partial=healthy.copy();partial.pop(key)
            self.assertEqual(validation_capacity(partial),1,key)
            self.assertEqual(validation_capacity(dict(healthy,**{key:float('nan')})),1,key)
        for key,value in [('available_gib',4),('cpu_percent',80),('container_cpu_percent',80),
                          ('gpu_percent',80),('io_pressure',6),('memory_pressure',1)]:
            self.assertEqual(validation_capacity(dict(healthy,**{key:value})),1,key)

    def test_second_slot_requires_sustained_headroom(self):
        with patch('resource_governor.validation_capacity',return_value=2),patch('resource_governor.Governor'),patch('validation_resources.time.monotonic') as clock:
            budget=AdmissionBudget()
            clock.return_value=0;self.assertEqual(budget.sample(),1)
            clock.return_value=29;self.assertEqual(budget.sample(),1)
            clock.return_value=35;self.assertEqual(budget.sample(),2)
            with patch('resource_governor.validation_capacity',return_value=1):
                clock.return_value=40;self.assertEqual(budget.sample(),1)

    @unittest.skipUnless(os.name=='posix','OS lock tests require Linux')
    def test_two_slots_only_when_approved(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp),patch('validation_resources.AdmissionBudget.sample',return_value=2):
            with validation_slot(['ffprobe','-show_frames']):
                with validation_slot(['ffprobe','-show_frames'],timeout=0):
                    with self.assertRaises(TimeoutError):
                        with validation_slot(['ffprobe','-show_frames'],timeout=0):pass
            self.assertEqual(list(Path(tmp).glob('wait-*.lock')),[])

    @unittest.skipUnless(os.name=='posix','OS lock tests require Linux')
    def test_abandoned_ticket_reclaimed(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp):
            stale=Path(tmp)/'wait-00000000000000000001-dead.lock';stale.touch()
            with validation_slot(['ffprobe','-show_frames'],timeout=0):pass
            self.assertFalse(stale.exists())

    @unittest.skipUnless(os.name=='posix','OS lock tests require Linux')
    def test_reduced_capacity_waits_for_second_slot(self):
        import fcntl
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp),patch('validation_resources.AdmissionBudget.sample',return_value=1):
            with (Path(tmp)/'heavy-reader-2.lock').open('w') as held:
                fcntl.flock(held,fcntl.LOCK_EX)
                with self.assertRaises(TimeoutError):
                    with validation_slot(['ffprobe','-show_frames'],timeout=0):pass

    @unittest.skipUnless(os.name=='posix','OS lock tests require Linux')
    def test_live_older_ticket_cannot_be_overtaken(self):
        import fcntl
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp),patch('validation_resources.AdmissionBudget.sample',return_value=2):
            older=Path(tmp)/'wait-00000000000000000001-older.lock'
            with older.open('w') as held:
                fcntl.flock(held,fcntl.LOCK_EX)
                with self.assertRaises(TimeoutError):
                    with validation_slot(['ffprobe','-show_frames'],timeout=0):pass
                self.assertTrue(older.exists())
            with validation_slot(['ffprobe','-show_frames'],timeout=0):pass
            self.assertFalse(older.exists())

    def test_execution_timeout_not_used_for_admission(self):
        @validation_limited
        def reader(command,timeout,guard):return timeout
        guard=lambda:None
        with patch('validation_resources.validation_slot') as slot:
            self.assertEqual(reader(['ffprobe','-show_frames'],7,guard),7)
        slot.assert_called_once_with(['ffprobe','-show_frames'],guard)

    @unittest.skipUnless(os.name=='posix','OS lock tests require Linux')
    def test_unbounded_wait_remains_cancellable(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp):
            with validation_slot(['ffprobe','-show_frames']):
                calls=[]
                def cancel():
                    calls.append(1)
                    if len(calls)==3:raise InterruptedError('cancelled')
                with patch('validation_resources.time.sleep'),patch('job_tracking.progress') as progress:
                    with self.assertRaises(InterruptedError):
                        with validation_slot(['ffprobe','-show_frames'],guard=cancel):
                            self.fail('Contended slot was admitted')
                    self.assertEqual(progress.call_count,2)
                    self.assertIsNone(progress.call_args.kwargs['stage_percent'])
            with validation_slot(['ffprobe','-show_frames'],timeout=0):pass

    def test_classification(self):
        self.assertTrue(heavy_reader(['ffprobe','-show_frames']))
        self.assertTrue(heavy_reader(['ffmpeg','-lavfi','libvmaf=model=x']))
        self.assertFalse(heavy_reader(['ffmpeg','-c:v','hevc_nvenc']))
        self.assertFalse(heavy_reader(['ffprobe','-show_packets']))

    @unittest.skipUnless(os.name=='posix','OS lock tests require Linux')
    def test_exclusive_and_released_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp):
            with validation_slot(['ffprobe','-show_frames']):
                with self.assertRaises(TimeoutError):
                    with validation_slot(['ffprobe','-show_frames'],timeout=0):pass
            with self.assertRaises(ValueError):
                with validation_slot(['ffprobe','-show_frames']):raise ValueError('test')
            with validation_slot(['ffprobe','-show_frames'],timeout=0):pass

    @unittest.skipUnless(os.name=='posix','OS lock tests require Linux')
    def test_linked_lock_refused(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp):
            target=Path(tmp)/'keep';target.write_text('original')
            (Path(tmp)/'heavy-reader.lock').symlink_to(target)
            with self.assertRaises(OSError):
                with validation_slot(['ffprobe','-show_frames']):pass
            self.assertEqual(target.read_text(),'original')

    @unittest.skipUnless(os.name=='posix','OS lock tests require Linux')
    def test_process_death_releases_slot(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,MUXMENDER_VALIDATION_LOCK_ROOT=tmp):
            code="from validation_resources import validation_slot\nimport sys\nwith validation_slot(['ffprobe','-show_frames']):\n print('ready',flush=True)\n sys.stdin.read()"
            child=subprocess.Popen([sys.executable,'-B','-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(),'ready')
                child.kill();child.wait(timeout=5)
                with validation_slot(['ffprobe','-show_frames'],timeout=0):pass
            finally:
                if child.poll() is None:child.kill();child.wait()
                child.stdin.close();child.stdout.close()
