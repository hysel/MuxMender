"""Run isolated SDR/HDR clips through the shared engine, never replacing inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--ffprobe', required=True)
    parser.add_argument('--case', action='append', choices=('real-sdr','real-hdr10'))
    parser.add_argument('--after-status', type=Path)
    parser.add_argument('--nvenc-maxrate-mbps',type=int)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    state_path = root/'batch-status.json'
    if state_path.exists():
        raise ValueError('Use a fresh test root; earlier evidence is retained')
    cases = args.case or ['real-sdr','real-hdr10']
    state = dict(state='running', pid=os.getpid(), started=time.time(), total=len(cases), steps=[])
    def save():
        state['updated'] = time.time()
        temporary = root/'batch-status.tmp'
        temporary.write_text(json.dumps(state, indent=2))
        temporary.replace(state_path)
    save()
    if args.after_status:
        state['state'] = 'waiting'
        while json.loads(args.after_status.read_text()).get('state') not in ('completed','completed-with-failures'):
            save()
            time.sleep(5)
        state['state'] = 'running'
        save()
    for index, label in enumerate(cases, 1):
        source = root/'input'/(label+'.mkv')
        before = digest(source)
        step = dict(name=label, state='running', started=time.time())
        state['steps'].append(step)
        state['current'] = index
        save()
        command = [sys.executable, '-u', '-B', '-m', 'auto_optimize', str(source),
            '--output-dir', str(root/label), '--hardware', 'nvidia',
            '--playback-verified-codecs', 'hevc', 'av1', '--execute', '--encode-best',
            '--adaptive', '--seconds', '5', '--minimum-savings-percent', '10',
            '--vmaf-mean', '90', '--vmaf-p5', '90', '--min-free-gib', '2',
            '--timeout', '1800', '--ffmpeg', args.ffmpeg, '--ffprobe', args.ffprobe]
        if args.nvenc_maxrate_mbps is not None:
            command+=['--nvenc-maxrate-mbps',str(args.nvenc_maxrate_mbps)]
        try:
            with (root/(label+'.log')).open('x') as log:
                child = subprocess.Popen(command, cwd=root, stdin=subprocess.DEVNULL,
                                         stdout=log, stderr=subprocess.STDOUT)
                step['pid'] = child.pid
                save()
                while child.poll() is None:
                    save()
                    time.sleep(2)
                step['exit_code'] = child.returncode
            outcomes = [json.loads(p.read_text()) for p in (root/label).glob('auto-*/status.json')]
            step['source_unchanged'] = digest(source) == before
            step['outcomes'] = [{k:s.get(k) for k in ('state','saved_percent','decision')}
                                for s in outcomes]
            step['state'] = 'passed' if child.returncode == 0 and step['source_unchanged'] else 'failed'
            # A passed command can deliberately retain a source; outcomes above
            # remain authoritative, not the process exit code.
        except Exception as exc:
            step.update(state='failed', error=str(exc))
        step['finished'] = time.time()
        save()
    state.update(state='completed' if all(s['state']=='passed' for s in state['steps'])
                 else 'completed-with-failures', finished=time.time())
    save()


if __name__ == '__main__':
    main()
