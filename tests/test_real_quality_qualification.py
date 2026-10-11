import unittest
from unittest.mock import patch
from tools import qualify_real_quality_profiles as research


class RealProfileSafetyTests(unittest.TestCase):
    def test_windows_guard_precedes_runtime_or_media_access(self):
        with patch.object(research.sys,'platform','win32'),patch.object(research.subprocess,'run') as process:
            with self.assertRaisesRegex(RuntimeError,'Linux-only'):research.run(None)
        process.assert_not_called()

    def test_only_bound_full_success_or_measured_keep_is_an_accepted_outcome(self):
        policy=dict(id='balanced',mean=94,p5=90)
        status=dict(state='validated-copy-awaiting-playback',quality_policy=policy)
        selection=dict(quality_policy=policy)
        self.assertEqual(research.assess(status,selection,policy,dict(state='cleaned')),
            dict(passed=True,outcome='validated_copy'))
        for other in (dict(state='needs-attention'),{}):
            self.assertFalse(research.assess(status,selection,policy,other)['passed'])
        self.assertFalse(research.assess(status,{},policy,dict(state='cleaned'))['passed'])
        status['state']='trials-completed'
        selection.update(action='keep_original',reason_code='already_efficient_for_settings')
        self.assertEqual(research.assess(status,selection,policy,dict(state='cleaned')),
            dict(passed=True,outcome='original_kept'))
        selection['reason_code']='evaluation_inconclusive'
        self.assertFalse(research.assess(status,selection,policy,dict(state='cleaned'))['passed'])
