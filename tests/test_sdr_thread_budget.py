import unittest
from unittest.mock import Mock, patch

from resource_governor import sdr_thread_budget, parallel_sdr_profile, SDRWorkerBudget,HDRQualityWorkerBudget


class SDRThreadBudgetTests(unittest.TestCase):
    def test_hdr_quality_needs_eight_gib_and_retains_pressure_backoff(self):
        budget=HDRQualityWorkerBudget()
        self.assertEqual(budget.select(self.good),4)
        for key,value in [('available_gib',7.99),('cpu_percent',75),('io_pressure',10),('container_tasks_available',0)]:
            self.assertEqual(budget.select(dict(self.good,**{key:value})),2)

    def setUp(self):
        self.good=dict(cpus=8,cpu_percent=15,container_cpu_percent=10,
                       available_gib=16,host_available_gib=24,io_pressure=0,
                       memory_pressure=0,container_tasks=30,
                       container_task_limit=256,container_tasks_available=226)

    def test_idle_allocation_can_use_four(self):
        self.assertEqual(sdr_thread_budget(self.good),4)

    def test_eight_gib_allocation_does_not_need_eight_gib_free(self):
        self.assertEqual(sdr_thread_budget(dict(self.good,available_gib=7,
                                              container_limit_gib=8)),4)
        self.assertEqual(sdr_thread_budget(dict(self.good,available_gib=5.99)),2)

    def test_host_load_is_not_subtracted_twice_from_container_allocation(self):
        self.assertEqual(sdr_thread_budget(dict(self.good,cpu_percent=40,
                                              container_cpu_percent=5)),4)
        self.assertEqual(sdr_thread_budget(dict(self.good,cpu_percent=5,
                                              container_cpu_percent=35)),2)
        self.assertEqual(sdr_thread_budget(dict(self.good,cpu_percent=60,
                                              container_cpu_percent=5)),2)

    def test_arc_requires_existing_bounded_reclaim_proof(self):
        data=dict(self.good,available_gib=7,host_available_gib=7,host_free_gib=5,
                  zfs_reclaimable_gib=8,zfs_need_free_gib=0)
        self.assertEqual(sdr_thread_budget(data),4)
        for key,value in [('host_available_gib',5),('host_free_gib',3),
                          ('zfs_reclaimable_gib',0),('zfs_need_free_gib',1),
                          ('io_pressure',5),('memory_pressure',.1),
                          ('cpu_percent',60),('container_tasks_available',31)]:
            with self.subTest(key=key):
                self.assertEqual(sdr_thread_budget(dict(data,**{key:value})),2)
        del data['zfs_reclaimable_gib']
        self.assertEqual(sdr_thread_budget(data),2)

    def test_pressure_reverts_to_two_without_rejecting_media(self):
        for key,value in [('container_cpu_percent',65),('cpu_percent',65),('cpus',4),
                          ('available_gib',4),('io_pressure',8),('memory_pressure',1),
                          ('container_tasks_available',31)]:
            with self.subTest(key=key):
                self.assertEqual(sdr_thread_budget(dict(self.good,**{key:value})),2)

    def test_missing_or_invalid_allocation_measurement_is_not_idle(self):
        for key in ('container_cpu_percent','container_tasks_available','container_tasks'):
            for value in (None,float('nan'),float('inf'),-1,'10',False):
                with self.subTest(key=key,value=value):
                    self.assertEqual(sdr_thread_budget(dict(self.good,**{key:value})),2)
        self.assertEqual(sdr_thread_budget({}),2)

    def test_measured_unlimited_task_allocation_is_supported(self):
        data={k:v for k,v in self.good.items() if k not in ('container_task_limit','container_tasks_available')}
        self.assertEqual(sdr_thread_budget(data),4)
        del data['container_tasks']
        self.assertEqual(sdr_thread_budget(data),2)

    def test_only_measured_sdr_profile_uses_higher_budget(self):
        base=dict(codec_name='h264',pix_fmt='yuv420p',field_order='progressive')
        self.assertTrue(parallel_sdr_profile(base))
        self.assertTrue(parallel_sdr_profile(dict(base,codec_name='hevc')))
        for key,value in [('codec_name','mpeg4'),('pix_fmt','yuv420p10le'),
                          ('field_order','tt'),('field_order','unknown'),
                          ('color_transfer','smpte2084'),('color_transfer','arib-std-b67')]:
            self.assertFalse(parallel_sdr_profile(dict(base,**{key:value})))
        self.assertFalse(parallel_sdr_profile({}))

    def test_sampler_is_cached_and_does_not_probe_gpu(self):
        with patch('resource_governor.Governor') as governor,patch('resource_governor.time.sleep') as sleep,\
             patch('resource_governor.time.monotonic',return_value=10) as clock:
            governor.return_value.sample.return_value=self.good
            budget=SDRWorkerBudget()
            self.assertEqual(budget.threads(),4)
            self.assertEqual(budget.threads(),4)
            self.assertEqual(governor.return_value.sample.call_count,2)
            self.assertTrue(all(c.kwargs=={'include_gpu':False} for c in governor.return_value.sample.call_args_list))
            sleep.assert_called_once_with(.25)
            clock.return_value=16
            governor.return_value.sample.return_value={}
            self.assertEqual(budget.threads(),2)

    def test_sampler_fallback_never_swallows_guard_errors(self):
        with patch('resource_governor.Governor') as governor,patch('resource_governor.time.sleep'):
            governor.return_value.sample.return_value=self.good
            budget=SDRWorkerBudget()
            guard=Mock(side_effect=[None,InterruptedError('Cancelled')])
            with self.assertRaises(InterruptedError):budget.threads(guard)
            governor.return_value.sample.side_effect=OSError('Unavailable')
            self.assertEqual(budget.threads(),2)


if __name__ == '__main__':
    unittest.main()
