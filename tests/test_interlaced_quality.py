import unittest
from unittest.mock import patch
from types import SimpleNamespace
import auto_optimize as ao
from auto_optimize import quality_graph
from test_auto_optimize import source_data


class InterlacedQualityTests(unittest.TestCase):
    def test_container_labels_do_not_override_decoded_field_dominance(self):
        for order in ('tt','bb','tb','bt'):
            data=source_data();data['streams'][0]['field_order']=order
            with patch.object(ao.mm,'encoder_options',return_value=['-c:v','h264_nvenc']):
                command=ao.encode_command('ffmpeg','in.mkv','out.mkv',
                    dict(codec='h264',encoder='h264_nvenc',quality='transparent'),
                    SimpleNamespace(hdr=False,dolby_vision=False),data['streams'])
            self.assertIn('+ildct+ilme',command)
            self.assertFalse(any(x.startswith('-top') for x in command))

    def test_fields_compared_in_presentation_order_at_double_clock(self):
        graph=quality_graph('fields.json','30000/1001',separate_fields=True)
        self.assertEqual(graph.count('separatefields,'),2)
        self.assertEqual(graph.count('N*1001/(60000*TB)'),2)
        self.assertNotIn('yadif',graph)
        self.assertNotIn('scale',graph)

    def test_progressive_graph_is_unchanged(self):
        self.assertNotIn('separatefields',quality_graph('frames.json','25/1'))
