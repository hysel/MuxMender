import unittest
from gpu_ticket_research import choose,admitted


class TicketResearchTests(unittest.TestCase):
    def ticket(self,sequence,seconds):return dict(sequence=sequence,seconds=seconds)

    def test_long_stage_gets_a_turn_after_two_short_trials(self):
        waiting=[self.ticket(1,1200)]+[self.ticket(i,20) for i in range(2,22)]
        order=[]
        while waiting:
            selected=choose(waiting);order.append(selected['sequence']);waiting=admitted(waiting,selected)
        self.assertEqual(order[:3],[2,3,1])
        self.assertEqual(sorted(order),list(range(1,22)))

    def test_fifo_within_classes_and_unknown_evidence(self):
        self.assertEqual(choose([self.ticket(3,20),self.ticket(2,30)])['sequence'],2)
        self.assertEqual(choose([self.ticket(3,1200),self.ticket(2,1800)])['sequence'],2)
        self.assertEqual(choose([dict(sequence=1),self.ticket(2,20)])['sequence'],1)
        self.assertIsNone(choose([]))

    def test_new_long_jobs_cannot_reset_waiting_long_bypass_count(self):
        rows=[self.ticket(1,1000),self.ticket(2,10),self.ticket(3,10)]
        for _ in range(2):rows=admitted(rows,choose(rows))
        rows+=[self.ticket(4,1000),self.ticket(5,10)]
        self.assertEqual(choose(rows)['sequence'],1)

    def test_original_ticket_records_are_not_mutated(self):
        rows=[self.ticket(1,1000),self.ticket(2,10)]
        admitted(rows,choose(rows));self.assertNotIn('bypasses',rows[0])

    def test_invalid_or_duplicate_sequence_cannot_reorder_work(self):
        for rows in ([dict(sequence='bad',seconds=10)],[self.ticket(1,10),self.ticket(1,20)]):
            with self.assertRaises(ValueError):choose(rows)
