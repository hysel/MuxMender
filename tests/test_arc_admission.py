import unittest
from resource_governor import Governor,arc_memory,cache_assisted_start


class ArcAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.data=dict(host_available_gib=7.4,host_free_gib=7.1,available_gib=7.4,
                       zfs_reclaimable_gib=104,zfs_need_free_gib=0,cpus=12,
                       cpu_percent=2,io_pressure=0,memory_pressure=0,gpu_percent=0,
                       vram_free_gib=7,gpu_temperature=45)
        self.g=Governor()
        self.g.sample=lambda:dict(self.data)

    def test_serial_start_waits_then_admits_but_not_second_job(self):
        self.assertFalse(self.g.admit('faster',0,100))
        self.assertTrue(self.g.admit('faster',0,131))
        self.assertEqual(self.g.status['ceiling'],1)
        self.assertFalse(self.g.admit('faster',1,200))

    def test_pressure_resets_observation(self):
        self.g.admit('faster',0,100)
        self.data['memory_pressure']=.2
        self.assertFalse(self.g.admit('faster',0,131))
        self.data['memory_pressure']=0
        self.assertFalse(self.g.admit('faster',0,132))
        self.assertTrue(self.g.admit('faster',0,163))

    def test_cache_cannot_bypass_container_limit(self):
        self.data.update(container_limit_gib=8,container_available_gib=2)
        self.assertFalse(self.g.admit('faster',0,100))
        self.assertIn('container memory',self.g.status['reason'])

    def test_missing_invalid_or_pressured_telemetry_fails_closed(self):
        for key,value in [('host_available_gib',5.9),('zfs_reclaimable_gib',7),
                          ('zfs_need_free_gib',1),('io_pressure',5),('memory_pressure',.1),
                          ('host_free_gib',float('nan'))]:
            with self.subTest(key=key):
                data=dict(self.data);data[key]=value
                self.assertFalse(cache_assisted_start(data,8))
        del self.data['zfs_reclaimable_gib']
        self.assertFalse(self.g.admit('faster',0,100))

    def test_credit_is_capped_and_not_added_to_available(self):
        self.data.update(host_free_gib=0,host_available_gib=7.4)
        self.assertFalse(cache_assisted_start(self.data,10))

    def test_arc_excludes_ghosts_and_respects_minimum(self):
        rows=dict(size=20,c_min=12,mru_evictable_data=5,mru_evictable_metadata=1,
                  mfu_evictable_data=4,mfu_evictable_metadata=1,arc_need_free=0,
                  mru_ghost_evictable_data=1000)
        text='\n'.join(f'{k} 4 {v*1024**3}' for k,v in rows.items())
        self.assertEqual(arc_memory(text)['zfs_reclaimable_gib'],8)
        with self.assertRaises(ValueError):arc_memory('size 4 100')


if __name__=='__main__':unittest.main()
