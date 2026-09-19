import unittest
from unittest.mock import patch
from resource_governor import Governor


class GovernorTests(unittest.TestCase):
    def setUp(self):
        self.g=Governor()
        self.data=dict(cpu_percent=20,available_gib=24,cpus=8,io_pressure=0,memory_pressure=0,
                       gpu_percent=10,vram_free_gib=6,gpu_temperature=50)
        self.g.sample=lambda:dict(self.data)

    def test_ramp_and_ceiling(self):
        self.assertTrue(self.g.admit('shared',0,100))
        self.g.last_launch=100
        self.assertFalse(self.g.admit('shared',1,120))
        self.assertTrue(self.g.admit('shared',1,161))
        self.assertFalse(self.g.admit('shared',2,200))

    def test_busy_host_resets_healthy_window(self):
        self.g.admit('shared',0,100)
        self.data['cpu_percent']=90
        self.assertFalse(self.g.admit('shared',1,200))
        self.data['cpu_percent']=10
        self.assertFalse(self.g.admit('shared',1,210))
        self.assertTrue(self.g.admit('shared',1,241))

    def test_resource_backoffs(self):
        for key,value in [('available_gib',3),('io_pressure',50),('memory_pressure',3),
                          ('gpu_percent',99),('vram_free_gib',1),('gpu_temperature',85)]:
            with self.subTest(key=key):
                old=self.data[key];self.data[key]=value
                self.assertFalse(self.g.admit('shared',0,100))
                self.data[key]=old

    def test_unknown_gpu_is_serial_and_unknown_host_waits(self):
        del self.data['gpu_percent']
        self.assertTrue(self.g.admit('faster',0,100))
        self.assertFalse(self.g.admit('faster',1,200))
        del self.data['cpu_percent']
        self.assertFalse(self.g.admit('shared',0,300))

    def test_cpu_allocation_bounds_ceiling(self):
        self.data['cpus']=2
        self.g.admit('faster',0,100)
        self.assertFalse(self.g.admit('faster',1,200))


if __name__=='__main__':unittest.main()
