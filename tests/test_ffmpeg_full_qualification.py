import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('full_qualification',ROOT/'tools/qualify_ffmpeg_full.py')
full=importlib.util.module_from_spec(spec);spec.loader.exec_module(full)
observer_spec=importlib.util.spec_from_file_location('build_observer',ROOT/'tools/monitor_ffmpeg_qualification_build.py')
observer=importlib.util.module_from_spec(observer_spec);observer_spec.loader.exec_module(observer)


class FullQualificationTests(unittest.TestCase):
    def test_build_properties_are_read_without_inventing_completion(self):
        props=observer.parse_properties('ActiveState=active\nResult=success\nExecMainStatus=0\n')
        self.assertEqual(props['ActiveState'],'active')
        self.assertNotIn('completed',props)
        self.assertEqual(observer.parse_properties('permission denied\n'),{})

    def test_windows_guard_precedes_subprocess_execution(self):
        with patch.object(full.sys,'platform','win32'),patch.object(full.subprocess,'run') as execute:
            with self.assertRaisesRegex(RuntimeError,'Linux-only'):full.main()
            execute.assert_not_called()

    def test_exact_reader_evidence_rejects_missing_changed_and_truncated_frames(self):
        frames=[dict(width=192,height=108,best_effort_timestamp_time='0.000000',side_data_list=[])]
        self.assertEqual(full.exact_frames(frames,copy.deepcopy(frames)),1)
        for left,right in [(frames,[]),([],[]),(frames,[dict(frames[0],width=194)]),
                           (frames,[dict(frames[0],best_effort_timestamp_time='0.001000')]),
                           (frames,[dict(frames[0],side_data_list=[{'side_data_type':'unexpected'}])])]:
            with self.assertRaises(ValueError):full.exact_frames(left,right)

    def test_gpu_fixture_is_not_below_decoder_minimum_height(self):
        source=(ROOT/'tools/qualify_ffmpeg_full.py').read_text()
        reader_section=source.split("for codec in ('hevc','av1'):",1)[1]
        self.assertIn('testsrc2=size=320x180:rate=12:duration=2',reader_section)
        self.assertNotIn('size=192x108',reader_section)

    def test_build_and_launcher_are_isolated_and_include_required_features(self):
        docker=(ROOT/'deploy/truenas/Dockerfile.ffmpeg-full-qualification').read_text()
        launcher=(ROOT/'deploy/truenas/launch-ffmpeg-full-qualification.sh').read_text()
        for feature in ('--enable-libx264','--enable-libx265','--enable-libaom','--enable-libvmaf',
                        '--enable-libplacebo','--enable-libzimg','--enable-nvenc','--enable-nvdec'):
            self.assertIn(feature,docker)
        self.assertIn('make -j2 ffprobe',docker)
        self.assertIn('source/source.sha256',docker)
        self.assertIn('libplacebo-7.351.0',docker)
        self.assertIn('vulkan-headers-libplacebo.tar.gz',docker)
        self.assertIn('command -v xxd',docker)
        self.assertIn('-Dbuilt_in_models=true',docker)
        self.assertIn('[a][b]libvmaf=n_threads=2',docker)
        for protection in ('--read-only','--cap-drop ALL','--memory 8g','--cpus 2'):
            self.assertIn(protection,launcher)
        for forbidden in ('docker stop','--privileged','dst=/media','nvidia-driver'):
            self.assertNotIn(forbidden,docker+launcher)


if __name__=='__main__':unittest.main()
