"""Explicitly approved, separate audio_tail_case test-copy repair; never publication.

Drops exactly the previously diagnosed incomplete final AC-3 packet. No other
packet may change. This is NOT an automatic source-repair policy.
"""
import argparse
import itertools
import json
from pathlib import Path
from types import SimpleNamespace
import auto_optimize as ao
from job_tracking import tracked_call, progress
from task_progress import run_probe


BAD_HASH='SHA256:eac9f16c2fb5e22b8fb765798de55890a61146c6ecd81042936ecaf6ab77a612'


def run(args):
    root=args.work
    encoded=args.run/'full-av1.mkv'
    plan=json.loads((args.run/'plan.json').read_text())
    original=Path(plan['source'])
    if encoded.is_symlink() or original.is_symlink():raise ValueError('Unexpected linked input')
    stamps={p:(p.stat().st_size,p.stat().st_mtime_ns) for p in (encoded,original)}
    def guard():
        if any((p.stat().st_size,p.stat().st_mtime_ns)!=stamp for p,stamp in stamps.items()):
            raise ValueError('Input changed during repair')
    hashes={str(p):ao.digest(p,guard) for p in stamps}
    if hashes[str(original)]!=json.loads((args.run/'trials.json').read_text())['source_id']:
        raise ValueError('Original no longer matches research input')
    wf=ao.Workflow(SimpleNamespace(ffmpeg='ffmpeg',ffprobe='ffprobe',timeout=14400),root,guard)
    before=wf.probe(encoded)
    if [(s['index'],s['codec_name']) for s in before['streams']]!=[(0,'av1'),(1,'ac3')]:
        raise ValueError('Unexpected test input stream layout')
    duration=float(before['format']['duration'])
    def packets(path,label,index):
        evidence=root/(label+f'-{index}.txt')
        run_probe(['ffprobe','-v','error','-select_streams',str(index),'-show_packets',
            '-show_data_hash','sha256','-show_entries','packet=pts_time,dts_time,duration_time,size,data_hash',
            '-of','compact=p=0',str(path)],evidence,label,14400,guard,duration)
        if evidence.with_suffix(evidence.suffix+'.stderr').stat().st_size:raise ValueError('Packet probe error')
        return evidence
    prior={index:packets(encoded,'before',index) for index in (0,1)}
    count=0;last=None
    for row in ao.compact_rows(prior[1],'data_hash'):count+=1;last=row
    if count<2 or last['data_hash']!=BAD_HASH or last['size']!='1040' or last['pts_time']!='4873.899000':
        raise ValueError('Diagnosed final packet does not match; no repair performed')
    output=root/'audio_tail_case-AV1-Audio-Repaired-Test.mkv'
    command=['ffmpeg','-hide_banner','-nostdin','-n','-copyts','-i',str(encoded),
             '-map','0','-map_metadata','0','-map_chapters','0','-c','copy',
             '-bsf:a:0',f'noise=amount=0:drop=eq(n\\,{count-1})',
             '-avoid_negative_ts','disabled']
    for stream in before['streams']:
        disposition='+'.join(k for k,v in stream.get('disposition',{}).items() if v) or '0'
        command += [f"-disposition:{stream['index']}",disposition]
    command += ['-progress','pipe:1','-nostats',str(output)]
    wf.execute(command,'Creating approved separate repaired copy',duration)
    after={index:packets(output,'after',index) for index in (0,1)}
    ao.compare_packets(prior[0],after[0])
    audio_count=0
    for old,new in itertools.zip_longest(ao.compact_rows(prior[1],'data_hash'),ao.compact_rows(after[1],'data_hash')):
        audio_count+=1
        if audio_count==count:
            if new is not None or old!=last:raise ValueError('Wrong packet removed')
        elif old!=new:raise ValueError('A retained audio packet changed')
    if audio_count!=count:raise ValueError('Unexpected audio packet count')
    ao.metadata_check(before,wf.probe(output),'av1',verified_frame_count=116855)
    proof=dict(original_unchanged=True,video_packets_unchanged=True,
               remaining_audio_packets_unchanged=True,removed_packet=last,
               audio_packets_before=count,audio_packets_after=count-1,
               input_sha256=hashes,repair_scope='User-approved separate test copy only',
               publication_authorized=False,output=str(output),full_decode_passed=False)
    (root/'repair-proof.json').write_text(json.dumps(proof,indent=2))
    wf.execute(['ffmpeg','-hide_banner','-nostdin','-v','error','-xerror','-threads','2',
                '-i',str(output),'-map','0:v:0','-map','0:a?',
                '-progress','pipe:1','-nostats','-fps_mode:v','passthrough',
                '-enc_time_base:v','demux','-f','null','-'],'Full repaired video and audio decode',duration)
    guard()
    for path,value in hashes.items():
        if ao.digest(Path(path),guard)!=value:raise ValueError('Input checksum changed')
    proof.update(full_decode_passed=True,output_sha256=ao.digest(output,guard),output_bytes=output.stat().st_size)
    (root/'result.json').write_text(json.dumps(proof,indent=2))
    progress('Separate repaired test copy validated',stage_percent=100)
    print(json.dumps(proof),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args();args.work.mkdir(exist_ok=False)
    return tracked_call(lambda:run(args),'audio_tail_case approved audio-repair test copy',folder=args.work)


if __name__=='__main__':raise SystemExit(main())
