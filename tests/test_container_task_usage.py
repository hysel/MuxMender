from unittest import TestCase
from unittest.mock import Mock
from resource_governor import container_task_usage


class ContainerTaskUsageTests(TestCase):
    def read(self, current, limit):
        root = Mock()
        root.__truediv__ = Mock(side_effect=lambda name: Mock(
            read_text=Mock(return_value={'pids.current': current, 'pids.max': limit}[name])))
        return container_task_usage(root)

    def test_counts_threads_and_remaining_capacity(self):
        self.assertEqual(self.read('233', '256'), dict(container_tasks=233,
                         container_task_limit=256, container_tasks_available=23))

    def test_unlimited_has_no_invented_limit(self):
        self.assertEqual(self.read('233', 'max'), dict(container_tasks=233))

    def test_invalid_and_limit_reduced_below_usage(self):
        for current, limit in [('bad', '256'), ('-1', '256'), ('2', '0')]:
            self.assertEqual(self.read(current, limit), {})
        self.assertEqual(self.read('300', '256')['container_tasks_available'], 0)
