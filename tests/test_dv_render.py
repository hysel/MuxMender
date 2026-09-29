import unittest
from dv_render import render_command,single_layer_configuration,native_quality_command,render_configuration,combine_quality_views


class NativeRenderTests(unittest.TestCase):
    def test_quality_views_keep_the_weaker_scores_and_reject_mismatched_coverage(self):
        good=dict(mean=99,p5=98,frames=24,passed=True)
        native=dict(self=good,candidate=good,domain='dv-libplacebo-common-render-v1')
        fallback=dict(self=good,candidate=dict(good,mean=91,p5=86,passed=False))
        result=combine_quality_views(native,fallback)
        self.assertEqual(result['candidate']['mean'],91)
        self.assertEqual(result['candidate']['p5'],86)
        self.assertFalse(result['candidate']['passed'])
        self.assertEqual(native['candidate']['mean'],99)
        fallback['candidate']['frames']=23
        with self.assertRaises(ValueError):combine_quality_views(native,fallback)

    def test_mel_render_requires_complete_layer_evidence_and_never_admits_fel(self):
        config=dict(dv_profile=7,el_present_flag=1,bl_present_flag=1,rpu_present_flag=1)
        metadata=dict(streams=[dict(index=0,codec_type='video',side_data_list=[config])])
        proof=dict(scope='layer-preservation-only',enhancement_types=['MEL'],frames=24,configuration=config,
                   enhancement_video_bytes=100,rpu_sha256='a'*64,enhancement_video_sha256='b'*64)
        self.assertEqual(render_configuration(metadata,24,proof),config)
        for changed in (dict(proof,enhancement_types=['FEL']),dict(proof,frames=23),dict(proof,rpu_sha256='')):
            with self.assertRaises(ValueError):render_configuration(metadata,24,changed)
        with self.assertRaises(ValueError):render_configuration(metadata,24)

    def test_streaming_comparison_has_two_native_renderers_and_no_prefix_trim(self):
        command=native_quality_command('ffmpeg','candidate.mkv','source.mkv','score.json','24000/1001')
        graph=command[command.index('-filter_complex')+1]
        self.assertEqual(graph.count('apply_dolbyvision=1'),2)
        self.assertNotIn('trim=',graph)
        self.assertNotIn('ffv1',command)
        self.assertEqual(command[-3:],['-f','null','-'])
    def test_render_applies_dv_without_geometry_or_rate_override(self):
        command=render_command('ffmpeg','source.mkv','new.mkv',device=2)
        self.assertIn('vulkan=gpu:2',command)
        self.assertIn('-noautorotate',command)
        self.assertIn('-n',command)
        self.assertIn('apply_dolbyvision=1',command[command.index('-vf')+1])
        self.assertNotIn('-r',command)
        self.assertNotIn('w=',command[command.index('-vf')+1])
        self.assertEqual(command[command.index('-fps_mode')+1],'passthrough')

    def test_layered_sources_cannot_silently_use_base_only_render(self):
        def metadata(profile,el=0,rpu=1):
            return dict(streams=[dict(codec_type='video',index=0,side_data_list=[
                dict(dv_profile=profile,el_present_flag=el,bl_present_flag=1,rpu_present_flag=rpu)])])
        for profile in (5,8):self.assertEqual(single_layer_configuration(metadata(profile))['dv_profile'],profile)
        for value in (metadata(7,1),metadata(5,0,0),metadata('5')):
            with self.assertRaises(ValueError):single_layer_configuration(value)

    def test_device_requires_nonnegative_integer(self):
        for value in (True,-1,'0:bad'):
            with self.assertRaises(ValueError):render_command('ffmpeg','in','out',device=value)
