"""Stage full-source qualification; never launch Docker or change the app."""
import base64
import io
from pathlib import Path
import subprocess
import sys
import uuid
import zipfile
import json

ROOT=Path(__file__).resolve().parents[1]


def main():
    name='audio-fix-full-'+uuid.uuid4().hex[:12]
    remote='/work/'+name
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for path in (ROOT/'python').rglob('*.py'):
            bundle.write(path,'python/'+path.relative_to(ROOT/'python').as_posix())
        bundle.write(ROOT/'tools/research_audio_fix_full.py','run.py')
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
    payload="""import base64,io,json,pathlib,sys,zipfile
if not sys.platform.startswith('linux'):raise RuntimeError('Linux-only staging')
root=pathlib.Path(REMOTE);root.mkdir(exist_ok=False)
bundle=zipfile.ZipFile(io.BytesIO(base64.b64decode(ARCHIVE)))
for entry in bundle.namelist():
 p=pathlib.PurePosixPath(entry)
 if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe archive')
bundle.extractall(root)
(root/'launch.sh').write_text(LAUNCHER)
sys.path.insert(0,str(root/'python'))
from job_tracking import Job
job=Job(root/'reports','Full-source qualification — waiting for isolated container')
job.save(state='pending',phase='Waiting for admin to launch isolated qualification',detail='Not deployed; no source writes or replacements authorized')
print(json.dumps(dict(stage=str(root),volume='muxmender-research-work',launcher=root.name+'/launch.sh')))
""".replace('REMOTE',repr(remote)).replace('ARCHIVE',repr(base64.b64encode(archive.getvalue()).decode())).replace('LAUNCHER',repr(launcher))
    key='C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519';host='muxmender@192.168.1.232'
    run=subprocess.run(['ssh','-i',key,'-o','BatchMode=yes','-o','ConnectTimeout=5',host,
                        'sudo -n /root/muxmender-research-access'],input=payload,text=True,encoding='utf-8',capture_output=True,timeout=120)
    if run.returncode:raise RuntimeError(run.stderr[-1000:])
    result=json.loads(run.stdout)
    # Start the read-only observer before the user launches the container.
    reportroot=Path('E:/MuxMender-TestOutputs/performance-followup-20261001/reports')
    config=reportroot/(name+'-monitor.json')
    config.write_text(json.dumps([dict(id=remote,title='Full-source audio fix qualification',host=host,key=key,
                                     command=['sudo','-n','/root/muxmender-research-access'],roots=[remote],kind='tracked',cross_namespace=True)]))
    subprocess.Popen([sys.executable,'-B',str(ROOT/'tools/monitor_remote_research.py'),'--config',str(config),
                      '--output',str(reportroot),'--interval','10'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    print(json.dumps(result))


if __name__=='__main__':main()
