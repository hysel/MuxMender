"""Prepare neutral comparison frames remotely; download retained research clips."""
import base64
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

KEY = 'C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519'
HOST = 'muxmender@192.168.1.232'
REMOTE = '/work/hdr-sdr-short-bd7e938b8315'
LOCAL = Path('E:/MuxMender-TestOutputs/hdr-sdr-review-20261006')


def remote(script, timeout=120):
    result = subprocess.run(['ssh', '-i', KEY, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
                             HOST, 'sudo -n /root/muxmender-research-access'],
                            input=script, text=True, encoding='utf-8', capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    return result.stdout


def main():
    script = r'''
import json,sys,subprocess,zipfile
from pathlib import Path
root=Path(REMOTE)
review=root/'review';review.mkdir(exist_ok=True)
data=json.loads((root/'result.json').read_text())
if len(data['rows'])!=18 or not all(r['passed'] for r in data['rows']):
 raise RuntimeError('Completed passing comparison required')
for scene in range(1,4):
 output=review/f'scene-{scene}-comparison.png'
 if output.exists():continue
 args=['ffmpeg','-hide_banner','-nostdin','-v','error','-n']
 tones=('hable','mobius','reinhard')
 for tone in tones:
  args+=['-threads','2','-ss','5','-i',str(root/f'scene-{scene}-tv1080-{tone}.mkv')]
 graph=';'.join(f'[{i}:v]scale=640:-2,setsar=1,pad=iw:ih+40:0:40:color=black,drawtext=text={tone.upper()}:fontsize=24:fontcolor=white:x=20:y=8[v{i}]' for i,tone in enumerate(tones))
 graph+=';[v0][v1][v2]hstack=inputs=3,format=rgb24[out]'
 args+=['-filter_complex_threads','2','-filter_complex',graph,'-map','[out]','-frames:v','1','-threads','2',str(output)]
 subprocess.run(args,check=True,stdin=subprocess.DEVNULL,capture_output=True,timeout=60)
bundle=review/'review.zip'
with zipfile.ZipFile(bundle,'w',zipfile.ZIP_STORED) as z:
 z.write(root/'result.json','result.json')
 for p in sorted(review.glob('scene-*-comparison.png')):z.write(p,p.name)
 for row in data['rows']:
  p=root/row['output'];z.write(p,p.name)
print(json.dumps({'bundle_bytes':bundle.stat().st_size,'images':3,'clips':len(data['rows'])}))
'''.replace('REMOTE', repr(REMOTE))
    print(remote(script), flush=True)
    print('Downloading review clips and comparison images...', flush=True)
    encoded = remote("import base64\nfrom pathlib import Path\nprint(base64.b64encode(Path("+
                     repr(REMOTE+'/review/review.zip')+").read_bytes()).decode())", timeout=180)
    LOCAL.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(encoded))) as bundle:
        for entry in bundle.namelist():
            path=Path(entry)
            if path.is_absolute() or len(path.parts)!=1:
                raise ValueError('Unsafe review archive')
        bundle.extractall(LOCAL)
    remote("from pathlib import Path\nPath("+repr(REMOTE+'/review/review.zip')+").unlink()\nprint('Transfer scratch removed')")
    print(json.dumps(dict(local=str(LOCAL),images=3,clips=18)),flush=True)


if __name__=='__main__':main()
