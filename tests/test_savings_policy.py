import unittest
from savings_policy import requirement,meets_requirement
from media_workflow import automatic_arguments


class SavingsTests(unittest.TestCase):
    def test_inner_mux_decision_retains_original_exact_byte_target(self):
        from mux_integrity import savings_decision
        size=20_000_000_001
        policy=requirement(size,'size-aware')
        output=size-policy['required_bytes']
        self.assertTrue(savings_decision(size,output,policy['effective_percent'],policy=policy)['eligible'])
        self.assertFalse(savings_decision(size,output+1,policy['effective_percent'],policy=policy)['eligible'])
        with self.assertRaises(ValueError):savings_decision(size+1,output,5,policy=policy)

    def test_exact_byte_boundary_and_source_identity(self):
        policy=requirement(20_000_000_001,'size-aware')
        self.assertTrue(meets_requirement(20_000_000_001,19_000_000_001,policy))
        self.assertFalse(meets_requirement(20_000_000_001,19_000_000_002,policy))
        with self.assertRaises(ValueError):meets_requirement(20_000_000_002,19_000_000_001,policy)
        self.assertFalse(meets_requirement(100,100,requirement(100,'fixed',0)))

    def test_large_integer_fixed_target_does_not_round_through_float(self):
        size=2**60+1
        self.assertEqual(requirement(size,'fixed',25)['required_bytes'],(size+3)//4)

    def test_size_aware_examples_and_floor(self):
        for size,needed in [(500_000_000,125_000_000),(2_000_000_000,500_000_000),
                            (4_000_000_000,1_000_000_000),(20_000_000_000,1_000_000_000),
                            (200_000_000,100_000_000)]:
            with self.subTest(size=size):
                value=requirement(size,'size-aware')
                self.assertEqual(value['required_bytes'],needed)
                self.assertTrue(value['possible'])
        self.assertFalse(requirement(100_000_000,'size-aware')['possible'])

    def test_fixed_policy_and_bad_inputs(self):
        self.assertEqual(requirement(20_000_000_000,'fixed',10)['required_bytes'],2_000_000_000)
        for size,mode,pct in [(0,'fixed',25),(1,'other',25),(1,'fixed',float('nan'))]:
            with self.assertRaises(ValueError):requirement(size,mode,pct)

    def test_old_jobs_keep_fixed_policy_new_jobs_use_explicit_policy(self):
        settings=dict(mode='encode',hardware='auto',quality='auto',minimum_savings=25,codecs=['hevc'])
        for mode in ('fixed','size-aware'):
            if mode=='size-aware':settings['savings_mode']=mode
            args=automatic_arguments('fixture.mkv','out',settings)
            self.assertEqual(args[args.index('--savings-mode')+1],mode)
