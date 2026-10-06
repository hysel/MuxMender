import unittest
from auto_optimize import compact_record_rows,compare_frame_rows


class StreamedEvidenceTests(unittest.TestCase):
    def line(self):
        return 'best_effort_timestamp_time=0|width=640|height=480|pix_fmt=yuv420p|sample_aspect_ratio=1:1|interlaced_frame=0|repeat_pict=0|color_transfer=bt709\n'

    def rows(self,line):return compact_record_rows(iter([line]),'width')

    def test_streams_use_identical_complete_frame_checks(self):
        self.assertEqual(compare_frame_rows(self.rows(self.line()),self.rows(self.line())),1)
        for replacement in ('width=641','pix_fmt=yuv420p10le','interlaced_frame=1','repeat_pict=1',
                            'color_transfer=smpte2084','best_effort_timestamp_time=0.1',
                            'best_effort_timestamp_time=nan'):
            key=replacement.split('=')[0]
            changed='|'.join(replacement if item.startswith(key+'=') else item for item in self.line().strip().split('|'))
            with self.subTest(replacement=replacement),self.assertRaises((ValueError,KeyError)):
                compare_frame_rows(self.rows(self.line()),self.rows(changed))

    def test_truncated_and_hidden_hdr_evidence_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'count changed'):compare_frame_rows(self.rows(self.line()),iter([]))
        with self.assertRaisesRegex(ValueError,'No decoded frames'):compare_frame_rows(iter([]),iter([]))
        with self.assertRaisesRegex(ValueError,'HDR/geometry'):
            list(self.rows(self.line()+'side_data_type=Mastering display metadata\n'))
