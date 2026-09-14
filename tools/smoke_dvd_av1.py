"""Explicit real-AMD smoke test. Generates all media; never reads library files."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-root',type=Path,required=True)
    parser.add_argument('--ffmpeg',required=True)
    parser.add_argument('--ffprobe',required=True)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    root=args.work_root/('dvd-cli-smoke-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    root.mkdir(parents=True,exist_ok=False)
    source=root/'input';source.mkdir()
    subtitles=root/'captions.srt'
    subtitles.write_text('1\n00:00:00,500 --> 00:00:04,500\nGenerated subtitle preservation check.\n',encoding='utf-8')
    media=source/'Generated-DVD.mkv'
    raw=root/'generated-raw.mkv'
    subprocess.run([args.ffmpeg,'-n','-v','error','-f','lavfi','-i','testsrc2=size=720x480:rate=60000/1001',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-i',str(subtitles),'-t','6',
        '-map','0:v','-map','1:a','-map','2:s','-vf','tinterlace=mode=interleave_top,setsar=8/9','-c:v','mpeg2video',
        '-flags','+ilme+ildct','-top','1','-field_order','tt','-b:v','8M','-minrate','8M','-maxrate','8M','-bufsize','1835008',
        '-c:a','ac3','-b:a','192k','-c:s','srt','-metadata:s:a:0','language=eng','-metadata:s:s:0','language=eng',str(raw)],check=True,timeout=60)
    subprocess.run([args.ffmpeg,'-n','-v','error','-i',str(raw),'-map','0','-c','copy','-field_order','tt',str(media)],check=True,timeout=30)
    def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    before=digest(media)
    base=[sys.executable,'-B',str(repo/'python/dvd_av1_batch.py'),str(source),
          '--ffmpeg',args.ffmpeg,'--ffprobe',args.ffprobe,'--timeout','120']
    results=[]
    def run(label,output,execute=False,expected=0):
        command=base+['--output-dir',str(output)]
        if execute:command+=['--execute','--accept-deinterlace']
        with (root/(label+'.log')).open('x',encoding='utf-8') as log:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=180)
        if result.returncode!=expected:raise RuntimeError(f'{label} failed ({result.returncode}); see {root}')
        results.append(label)
    out=root/'output'
    run('dry-run',out)
    assert not out.exists()
    run('encode',out,True)
    output=out/'Generated-DVD.AV1.mkv'
    output_hash=digest(output)
    receipt=json.loads(output.with_suffix('.receipt.json').read_text())
    assert receipt['validation']['frames_checked']>300
    assert receipt['validation']['copied_packet_hashes_verified']
    run('resume',out,True)
    assert digest(output)==output_hash
    states=[json.loads(p.read_text())[0].get('state') for p in out.glob('dvd-av1-*/status.json')]
    assert 'resumed-verified' in states
    blocked=root/'blocked-output';blocked.mkdir()
    sentinel=blocked/output.name;sentinel.write_bytes(b'Existing user output: do not overwrite')
    sentinel_hash=digest(sentinel)
    run('overwrite-refused',blocked,True,1)
    assert digest(sentinel)==sentinel_hash
    assert digest(media)==before
    (root/'result.json').write_text(json.dumps(dict(passed=results,source_unchanged=True,receipt=receipt),indent=2))
    print('PASS '+str(root))
if __name__=='__main__':main()
