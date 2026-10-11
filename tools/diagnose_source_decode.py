"""Linux-only, read-only source diagnosis; extracted tracks are disposable."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    if sys.platform != 'linux':
        raise RuntimeError('Linux-only diagnostics')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--request-id', action='append', required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    from job_tracking import tracked_call, progress
    rows = []
    def run():
        requests = json.loads(Path('/output/ui-requests/requests.json').read_text())['jobs']
        if any(j.get('state') in ('running', 'pending') for j in requests):
            raise RuntimeError('Production must be idle')
        os.nice(10)
        total = len(args.request_id)*4
        for index, identifier in enumerate(args.request_id):
            request = next(j for j in requests if j['id'] == identifier)
            source = Path(request['source']).resolve(strict=True)
            if not source.is_relative_to('/media'):
                raise ValueError('Read-only media source required')
            stat = source.stat()
            identity = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
            metadata = json.loads(subprocess.check_output(['mkvmerge','-J',str(source)],text=True))
            tracks = [next(t for t in metadata['tracks'] if t['type'] == kind) for kind in ('audio','video')]
            for track in tracks:
                kind = track['type']
                codec_id = track['properties']['codec_id']
                if codec_id not in ('A_AC3','V_MPEG4/ISO/AVC'):
                    raise ValueError('Diagnostic currently qualifies only AC3/AVC track extraction')
                extracted = args.output/f'case-{index+1}-{kind}.essence'
                try:
                    progress(f'Case {index+1} · extracting {kind}',len(rows),total,
                             unit='isolated track decodes',detail='Read-only source; temporary elementary stream')
                    with (args.output/f'case-{index+1}-{kind}-extract.log').open('x') as log:
                        subprocess.run(['mkvextract',str(source),'tracks',f"{track['id']}:{extracted}"],
                                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
                    with extracted.open('rb') as stream:
                        digest = hashlib.file_digest(stream,'sha256').hexdigest()
                    for runtime in ('baseline','candidate'):
                        progress(f'Case {index+1} · {runtime} · strict {kind} decode',len(rows),total,
                                 unit='isolated track decodes',detail='No concealment, repair, publication or quality waiver')
                        env = dict(os.environ)
                        if runtime == 'candidate':
                            binary = '/output/ffmpeg9-full-runtime-export-20261010/bin/ffmpeg'
                            env['LD_LIBRARY_PATH'] = ':'.join(('/output/ffmpeg9-diagnostic-host-lib-20261010',
                                '/output/ffmpeg9-full-os-libs-20261010','/output/ffmpeg9-full-deps-export-20261010/lib',
                                '/usr/lib/x86_64-linux-gnu'))
                        else:
                            binary = '/usr/local/bin/ffmpeg'
                            env.pop('LD_LIBRARY_PATH',None)
                        command = [binary,'-v','error','-nostdin','-xerror','-threads','2',
                                   '-f','ac3' if kind=='audio' else 'h264','-i',str(extracted)]
                        command += ['-map','0:a:0','-c:a','pcm_s16le','-f','hash','-hash','sha256','-'] if kind=='audio' else ['-map','0:v:0','-f','null','-']
                        started = time.monotonic()
                        result = subprocess.run(command,env=env,capture_output=True,text=True,timeout=7200)
                        (args.output/f'case-{index+1}-{kind}-{runtime}.log').write_text(result.stderr)
                        rows.append(dict(case=index+1,kind=kind,runtime=runtime,codec_id=codec_id,
                            extracted_bytes=extracted.stat().st_size,extracted_sha256=digest,
                            exit_code=result.returncode,strict_pass=result.returncode==0 and not result.stderr.strip(),
                            diagnostic=result.stderr[-2000:],decoded_hash=result.stdout.strip(),
                            seconds=round(time.monotonic()-started,3)))
                        (args.output/'result.json').write_text(json.dumps(dict(results=rows,
                            complete=len(rows)==total,production_changed=False,quality_gates_changed=False,
                            scope='Elementary-track diagnosis; exported runtime dependencies, not image qualification'),indent=2))
                finally:
                    extracted.unlink(missing_ok=True)
            after=source.stat()
            if identity != (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
                raise ValueError('Source identity changed')
        progress('Elementary track diagnostics finished',total,total,unit='isolated track decodes')
        return 0
    return tracked_call(run,'Source integrity — isolated audio/video diagnostics',folder=args.output/'reports')


if __name__=='__main__':
    raise SystemExit(main())
