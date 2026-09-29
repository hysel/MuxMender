import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from dv_layer_evidence import layer_preservation_evidence, rpu_inventory, extract_layers
from dv_full_file import rpu_digest, timestamped_video_command


class LayerEvidenceTests(unittest.TestCase):
    def test_mixed_inventory_requires_full_reconstruction(self):
        from dv_layer_evidence import requires_fel_reconstruction
        self.assertFalse(requires_fel_reconstruction(['MEL']))
        for kinds in (['FEL'], ['FEL', 'MEL'], ['MEL', 'FEL']):
            self.assertTrue(requires_fel_reconstruction(kinds))
        for kinds in (None, [], ['unknown'], ['MEL', 'unknown'], ['FEL', 'FEL'], 'FEL'):
            with self.assertRaises(ValueError):requires_fel_reconstruction(kinds)

    def test_mixed_ordered_records_remain_exactly_preserved(self):
        self.records[1]['el_type']='FEL'
        self.rpu.write_text(json.dumps(self.records))
        self.assertEqual(self.check()['enhancement_types'], ['FEL', 'MEL'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.el = self.root / 'el.hevc'
        self.el.write_bytes(b'generated-enhancement-payload')
        self.rpu = self.root / 'rpu.json'
        self.records = [dict(dovi_profile=7, el_type='MEL', frame=i) for i in range(2)]
        self.rpu.write_text(json.dumps(self.records))
        self.config = dict(dv_profile=7, el_present_flag=1, bl_present_flag=1, rpu_present_flag=1)

    def check(self, **changes):
        args = dict(source_el=self.el, output_el=self.el, source_rpu=self.rpu,
                    output_rpu=self.rpu, source_config=self.config,
                    output_config=self.config, expected_frames=2)
        args.update(changes)
        return layer_preservation_evidence(**args)

    def test_positive_and_not_publication_approval(self):
        result = self.check()
        self.assertEqual(result['enhancement_types'], ['MEL'])
        self.assertEqual(result['scope'], 'layer-preservation-only')

    def test_profile8_relabel_is_not_preservation(self):
        with self.assertRaisesRegex(ValueError, 'signaling'):
            self.check(output_config=dict(self.config, dv_profile=8, el_present_flag=0))

    def test_missing_or_changed_payload(self):
        output = self.root / 'changed.hevc'
        for data in (b'', b'different'):
            output.write_bytes(data)
            with self.assertRaises(ValueError):
                self.check(output_el=output)

    def test_full_rpu_coverage_and_order(self):
        output = self.root / 'changed.json'
        for records in (self.records[:1], self.records[::-1],
                        [self.records[0], dict(self.records[1], el_type='FEL')]):
            output.write_text(json.dumps(records))
            with self.assertRaises(ValueError):
                self.check(output_rpu=output)
        for count in (True, 0, 1, 3):
            with self.assertRaises(ValueError):
                self.check(expected_frames=count)

    def test_inspects_every_record_and_propagates_cancellation(self):
        seen = []
        rpu_digest(self.rpu, inspect=lambda r: seen.append(r['frame']))
        self.assertEqual(seen, [0, 1])
        def cancel():
            raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.check(guard=cancel)

    def test_unknown_profile_is_not_accepted(self):
        self.rpu.write_text(json.dumps([dict(dovi_profile=8, el_type='MEL')] * 2))
        with self.assertRaisesRegex(ValueError, 'Profile 7'):
            self.check()

    def test_scene_refresh_must_remain_on_same_picture(self):
        records=[dict(dovi_profile=7,el_type='MEL',vdr_dm_data=dict(scene_refresh_flag=flag)) for flag in (0,1)]
        self.rpu.write_text(json.dumps(records))
        output=self.root/'shifted.json';output.write_text(json.dumps(records[::-1]))
        with self.assertRaisesRegex(ValueError,'ordered RPU'):
            self.check(output_rpu=output)

    def test_trailing_data_rejected_after_large_whitespace(self):
        self.rpu.write_text('[]' + ' ' * 150000 + '{}')
        with self.assertRaisesRegex(ValueError, 'Trailing data'):
            rpu_digest(self.rpu)

    def test_layered_mux_never_uses_single_layer_relabel_filter(self):
        output = self.root / 'output.mkv'
        for clock in (None, self.root / 'timestamps.txt'):
            command = timestamped_video_command('ffmpeg', self.el, output, '24000/1001',
                        timestamps=clock, preserve_enhancement=True)
            self.assertEqual(command[0], 'mkvmerge')
            self.assertNotIn('-bsf:v', command)
            self.assertIn('0:24000/1001fps', command)
            self.assertEqual('--timestamps' in command, clock is not None)
        output.write_bytes(b'existing')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            timestamped_video_command('ffmpeg', self.el, output, '24', preserve_enhancement=True)

    def test_layered_mux_requires_valid_fallback_clock(self):
        for rate in ('0', '-24', 'not-a-clock'):
            with self.assertRaises(ValueError):
                timestamped_video_command('ffmpeg', self.el, self.root/'output.mkv',
                                          rate, preserve_enhancement=True)

    def test_inventory_checks_whole_record_sequence(self):
        self.rpu.write_text(json.dumps(self.records+[dict(dovi_profile=7, el_type='FEL')]))
        self.assertEqual(rpu_inventory(self.rpu)['enhancement_types'], ['FEL', 'MEL'])
        self.rpu.write_text('[]')
        with self.assertRaisesRegex(ValueError, 'No enhancement'):
            rpu_inventory(self.rpu)

    def test_extraction_uses_fresh_owned_directory_and_actual_stream(self):
        config = dict(self.config, side_data_type='DOVI configuration record')
        workflow = SimpleNamespace(directory=self.root, args=SimpleNamespace(ffmpeg='ffmpeg'),
            guard=Mock(), probe=Mock(return_value=dict(format=dict(duration='2'), streams=[dict(
                index=3, codec_type='video', codec_name='hevc', width=160, height=96,
                side_data_list=[config])])), execute=Mock())
        def execute(command, label, duration):
            directory = self.root/'layers'
            if 'export' in command:
                (directory/'metadata.json').write_text(json.dumps(self.records))
            elif 'demux' in command:
                (directory/'base.hevc').write_bytes(b'base')
            elif 'remove' in command:
                (directory/'enhancement-video.hevc').write_bytes(b'enhancement')
        workflow.execute.side_effect = execute
        result = extract_layers(workflow, self.root/'source.mkv', 'layers')
        self.assertEqual(result['frames'], 2)
        self.assertEqual(result['scope'], 'layer-inventory-only')
        self.assertIn('0:3', workflow.execute.call_args_list[0].args[0])
        with self.assertRaises(FileExistsError):
            extract_layers(workflow, self.root/'source.mkv', 'layers')
        for name in ('../outside', '/absolute', ''):
            with self.assertRaises(ValueError):
                extract_layers(workflow, self.root/'source.mkv', name)
