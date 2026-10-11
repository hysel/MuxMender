"""Linux image qualification using generated media; no production mounts."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest


def runtime(version, public_runtime=False):
    import app_version, app_api, auto_optimize, quality_profiles
    from ui.app import HTML
    from output_presets import encoder_options
    assert app_version.VERSION == version
    assert app_api.describe()['app_version'] == version
    assert subprocess.check_output(['ffmpeg','-version'],text=True,stderr=subprocess.STDOUT).startswith('ffmpeg version 9.0.2 ')
    assert subprocess.check_output(['ffprobe','-version'],text=True,stderr=subprocess.STDOUT).startswith('ffprobe version 9.0.2 ')
    if public_runtime:
        assert not Path('/usr/local/bin/ffmpeg').exists(), 'Public image must not inherit the nonfree fallback'
        assert not Path('/usr/local/bin/ffprobe').exists(), 'Public image must not inherit the nonfree fallback'
        assert not Path('/opt/muxmender-readers/qualification.json').exists(), 'Public image must not ship a private GPU receipt'
        assert not Path('/opt/muxmender-readers/evidence.json').exists(), 'Public image must not ship private reader evidence'
    else:
        assert subprocess.check_output(['/usr/local/bin/ffmpeg','-version'],text=True,stderr=subprocess.STDOUT).startswith('ffmpeg version 8.0.1 ')
    assert 'MuxMender' in HTML and 'id="terminal-style"' in HTML
    assert 'id="quality-gate-profile"' in HTML
    assert quality_profiles.profile('balanced')['mean'] == 94
    assert callable(auto_optimize.Workflow.reference_window)
    options=encoder_options(dict(width=1920,height=1080,sample_aspect_ratio='1:1'),
                            'tv1080',encoder='hevc_nvenc')
    assert options[-2:]==['-cq','0']
    sys.path.insert(0,'/qualification')
    patterns=('quality_profiles','quality_automation','quality_profile_qualification',
              'real_quality_qualification','sampling_timing_edges','reference_sampling',
              'finished_cleanup','queue_action_status','queue_cancellation','queue_sizes_ui','remove_queued_ui','workbench',
              'control_service','copy_approval','copy_approval_ui','release_monitor','job_scheduling_benchmark','iso_container_recovery','aac_priming','staged_preflight',
              'av1_intermediate_qualification','approved_copy_publication','batch_performance_report',
              'source_audio_preflight','dts_terminal_duration','activity_reports','ffmpeg9_release_package')
    suite=unittest.TestSuite(unittest.defaultTestLoader.discover('/qualification/tests',
        pattern='test_'+name+'.py') for name in patterns)
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():raise RuntimeError('Packaged regression checks failed')
    print('Packaged runtime, UI, policies and regressions passed',flush=True)


def reaper():
    code='import os,time; p=os.fork(); print(p,flush=True) if p else (time.sleep(.05),os._exit(0)); os._exit(0)'
    child=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,check=True,timeout=5)
    pid=int(child.stdout.strip());deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        if not Path('/proc',str(pid)).exists():return
        time.sleep(.05)
    raise RuntimeError('Image failed orphan reaping')


def gpu(public_runtime=False):
    from gpu_frame_reader import load_qualification
    reader=load_qualification()
    if public_runtime:
        if reader is not None:raise RuntimeError('Public image unexpectedly includes host-specific GPU reader qualification')
    elif reader is None:raise RuntimeError('Bundled qualified GPU reader not accepted')
    for encoder in ('hevc_nvenc','av1_nvenc'):
        subprocess.run(['ffmpeg','-hide_banner','-nostdin','-v','error','-xerror',
            '-f','lavfi','-i','color=c=black:s=192x192:r=5:d=0.4',
            '-frames:v','2','-c:v',encoder,'-preset','p5','-f','null','-'],check=True,timeout=30)
    sys.path.insert(0,'/qualification')
    os.environ['MUXMENDER_QUALIFY_GPU']='1'
    suite=unittest.defaultTestLoader.discover('/qualification/tests',pattern='test_output_presets.py')
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():raise RuntimeError('Image GPU preset validation failed')
    print('Image GPU encoding and generated presets passed; '+
          ('public reader remains unqualified until host-specific checks' if public_runtime else 'private reader checks passed'),flush=True)


def main():
    if not sys.platform.startswith('linux'):raise RuntimeError('Image smoke tests are Linux-only')
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=('runtime','reaper','gpu'))
    parser.add_argument('--public-runtime', action='store_true', help='Require clean-base runtime without inherited FFmpeg 8 fallback')
    parser.add_argument('--version',required=True)
    args=parser.parse_args()
    if args.mode=='runtime':runtime(args.version, public_runtime=args.public_runtime)
    elif args.mode=='reaper':reaper()
    else:gpu(public_runtime=args.public_runtime)


if __name__=='__main__':main()
