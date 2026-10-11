"""Stage full-source qualification; never launch Docker or change the app."""
import base64
import io
from pathlib import Path
import subprocess
import sys
import uuid
import zipfile
import json
import argparse
import hashlib

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--kind',choices=('audio','hdr-sdr','hdr-sdr-long','quality-profiles','real-quality-profiles'),default='audio')
    parser.add_argument('--request-id',action='append',default=[],help='Private history request locator for real-quality-profiles')
    parser.add_argument('--start-in-research',action='store_true',help='Start generated video-only profiles in the restricted research container')
    parser.add_argument('--runtime-wheel',type=Path,help='Private pinned Linux PyAV wheel for isolated real-profile research; never installed into the app')
    parser.add_argument('--preset-matrix',action='store_true',help='Generated profile comparisons at 1080p, 720p and 480p')
    parser.add_argument('--codec',choices=('hevc','av1'),default='hevc')
    args=parser.parse_args()
    hdr=args.kind.startswith('hdr-sdr')
    longer=args.kind=='hdr-sdr-long'
    profiles=args.kind=='quality-profiles'
    real_profiles=args.kind=='real-quality-profiles'
    if args.preset_matrix and not profiles:parser.error('--preset-matrix requires generated quality-profiles')
    if real_profiles and not 1<=len(args.request_id)<=3:parser.error('Real profiles require 1–3 source request IDs')
    if args.request_id and not real_profiles:parser.error('--request-id requires real-quality-profiles')
    if args.start_in_research and not (profiles or real_profiles):parser.error('--start-in-research requires quality profiles')
    if args.runtime_wheel and not (real_profiles and args.start_in_research):parser.error('--runtime-wheel requires real profiles and --start-in-research')
    if real_profiles and args.start_in_research and not args.runtime_wheel:parser.error('Real profiles need a private pinned Linux PyAV wheel')
    runtime_hash=None
    if args.runtime_wheel:
        if args.runtime_wheel.name!='av-18.1.0-cp311-abi3-manylinux_2_28_x86_64.whl':parser.error('Unsupported qualification runtime wheel')
        runtime_hash=hashlib.sha256(args.runtime_wheel.read_bytes()).hexdigest()
    if args.codec!='hevc' and not longer:parser.error('--codec applies only to hdr-sdr-long')
    title=('Mobius SDR excerpt with copied tracks' if longer else 'HDR-to-SDR short comparison') if hdr else 'Full-source audio fix qualification'
    if longer:title+=' · '+args.codec.upper()
    if profiles:title='NVIDIA quality profile qualification'
    if args.preset_matrix:title='NVIDIA resolution and quality profile qualification'
    if real_profiles:title='Real-video quality profile comparison'
    name=('hdr-sdr-long-' if longer else 'hdr-sdr-short-' if hdr else 'audio-fix-full-')+uuid.uuid4().hex[:12]
    if profiles:name='quality-profiles-'+uuid.uuid4().hex[:12]
    if real_profiles:name='real-quality-profiles-'+uuid.uuid4().hex[:12]
    remote='/work/'+name
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for path in (ROOT/'python').rglob('*.py'):
            bundle.write(path,'python/'+path.relative_to(ROOT/'python').as_posix())
        bundle.write(ROOT/('tools/qualify_real_quality_profiles.py' if real_profiles else 'tools/qualify_quality_profiles.py' if profiles else 'tools/research_hdr_sdr_long.py' if longer else 'tools/research_hdr_sdr.py' if hdr else 'tools/research_audio_fix_full.py'),'run.py')
        if longer:bundle.write(ROOT/'tools/research_hdr_sdr.py','research_hdr_sdr.py')
        if args.runtime_wheel:bundle.write(args.runtime_wheel,'runtime.whl')
    launcher=r'''#!/bin/bash
set -euo pipefail
app=ix-muxmender-muxmender-1
name=NAME
stage=/work/NAME
image=$(docker inspect --format '{{.Config.Image}}' "$app")
media=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/media"}}{{.Source}}{{end}}{{end}}' "$app")
output=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/output"}}{{.Source}}{{end}}{{end}}' "$app")
[[ -n "$image" && -d "$media" && -d "$output" ]] || { echo 'App image or existing mounts unavailable'; exit 1; }
docker image inspect "$image" >/dev/null
echo 'Keep the production queue idle during this serial GPU qualification. Sources are read-only; no replacement is possible.'
docker run -d --pull=never --name "$name" --user 3005:3005 --gpus all --init \
  --network none --security-opt no-new-privileges --memory 16g --cpus 6 \
  --mount type=volume,src=muxmender-research-work,dst=/work \
  --mount "type=bind,src=$media,dst=/media,readonly" \
  --mount "type=bind,src=$output,dst=/output,readonly" \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,video,utility,graphics \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -e PYTHONPATH="$stage/python:/opt/muxmender-runtime" \
  --entrypoint python3 "$image" -B "$stage/run.py"
echo "Started $name. Closing this shell does not stop the container."
'''.replace('NAME',name)
    payload="""import base64,io,json,pathlib,sys,zipfile,hashlib
if not sys.platform.startswith('linux'):raise RuntimeError('Linux-only staging')
root=pathlib.Path(REMOTE);root.mkdir(exist_ok=False)
bundle=zipfile.ZipFile(io.BytesIO(base64.b64decode(ARCHIVE)))
for entry in bundle.namelist():
 p=pathlib.PurePosixPath(entry)
 if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe archive')
bundle.extractall(root)
if RUNTIME_HASH:
 wheel=root/'runtime.whl'
 if hashlib.sha256(wheel.read_bytes()).hexdigest()!=RUNTIME_HASH:raise ValueError('Runtime transfer checksum mismatch')
 with zipfile.ZipFile(wheel) as runtime:
  for entry in runtime.namelist():
   p=pathlib.PurePosixPath(entry)
   if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe runtime wheel')
  runtime.extractall(root/'runtime')
 (root/'runtime-evidence.json').write_text(json.dumps(dict(sha256=RUNTIME_HASH,version='18.1.0',scope='Private isolated Linux research only')))
(root/'launch.sh').write_text(LAUNCHER)
(root/'research-options.json').write_text(json.dumps(dict(codec=CODEC,preset_matrix=PRESET_MATRIX)))
if REQUEST_IDS:
 requests=json.loads(pathlib.Path('/output/ui-requests/requests.json').read_text())['jobs']
 cases=[]
 for identifier in REQUEST_IDS:
  request=next(j for j in requests if j['id']==identifier)
  source=pathlib.Path(request.get('published_path') or request['source']).resolve(strict=True)
  if not source.is_relative_to('/media'):raise ValueError('Source outside read-only media mount')
  cases.append(dict(source=str(source),request_id=identifier,seconds=60))
 (root/'cases.json').write_text(json.dumps(cases))
sys.path.insert(0,str(root/'python'))
from job_tracking import Job
job=Job(root/'reports',TITLE)
job.save(state='pending',phase='Waiting for admin to launch isolated qualification',detail='Not deployed; no source writes or replacements authorized')
print(json.dumps(dict(stage=str(root),volume='muxmender-research-work',launcher=root.name+'/launch.sh')))
""".replace('REMOTE',repr(remote)).replace('LAUNCHER',repr(launcher)).replace('TITLE',repr(title)).replace('CODEC',repr(args.codec)).replace('REQUEST_IDS',repr(args.request_id)).replace('RUNTIME_HASH',repr(runtime_hash)).replace('PRESET_MATRIX',repr(args.preset_matrix)).replace('ARCHIVE',repr(base64.b64encode(archive.getvalue()).decode()))
    # Check generated syntax without executing any Linux payload on Windows.
    import ast
    ast.parse(payload)
    key='C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519';host='muxmender@192.168.1.232'
    run=subprocess.run(['ssh','-i',key,'-o','BatchMode=yes','-o','ConnectTimeout=5',host,
                        'sudo -n /root/muxmender-research-access'],input=payload,text=True,encoding='utf-8',capture_output=True,timeout=120)
    if run.returncode:raise RuntimeError(run.stderr[-1000:])
    result=json.loads(run.stdout)
    # Start the read-only observer before the user launches the container.
    reportroot=Path('E:/MuxMender-TestOutputs/performance-followup-20261001/reports')
    config=reportroot/(name+'-monitor.json')
    config.write_text(json.dumps([dict(id=remote,title=title,host=host,key=key,
                                     command=['sudo','-n','/root/muxmender-research-access'],roots=[remote],kind='tracked',cross_namespace=True,pending_launch=True)]))
    subprocess.Popen([sys.executable,'-B',str(ROOT/'tools/monitor_remote_research.py'),'--config',str(config),
                      '--output',str(reportroot),'--interval','10'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                      creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    if args.start_in_research:
        start="""import os,pathlib,subprocess,sys,json
if not sys.platform.startswith('linux'):raise RuntimeError('Linux-only launch')
root=pathlib.Path(REMOTE)
env=dict(os.environ,PYTHONPATH=str(root/'python')+(':'+str(root/'runtime') if (root/'runtime').is_dir() else ''))
with (root/'launch.log').open('xb') as log:
 child=subprocess.Popen([sys.executable,'-B',str(root/'run.py')],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=env)
print(json.dumps(dict(pid=child.pid)))
""".replace('REMOTE',repr(remote))
        launched=subprocess.run(['ssh','-i',key,'-o','BatchMode=yes','-o','ConnectTimeout=5',host,
            'sudo -n /root/muxmender-research-access'],input=start,text=True,encoding='utf-8',capture_output=True,timeout=30)
        if launched.returncode:raise RuntimeError(launched.stderr[-1000:])
        result['started']=json.loads(launched.stdout)
    print(json.dumps(result))


if __name__=='__main__':main()
