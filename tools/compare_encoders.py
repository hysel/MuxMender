"""Short-clip encoder comparison only; never selects or replaces library files."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from types import SimpleNamespace
import uuid

import auto_optimize as ao
from job_tracking import tracked_call, progress


def recipes(profile='standard'):
    rows=[]
    definitions=[
        ('libx265','hevc','-crf',(21,24),['-preset','slow','-x265-params','pools=4:frame-threads=1']),
        ('libsvtav1','av1','-crf',(24,28),['-preset','6','-svtav1-params','lp=4']),
        ('libx264','h264','-crf',(18,21),['-preset','slow']),
        ('libvpx-vp9','vp9','-crf',(24,30),['-b:v','0','-deadline','good','-cpu-used','2']),
        ('libvvenc','vvc','-qp',(24,28),['-preset','medium','-vvenc-params','internalbitdepth=8']),
        ('hevc_nvenc','hevc','-cq',(21,23),['-preset','p7','-tune','hq','-rc','vbr','-b:v','0']),
        ('av1_nvenc','av1','-cq',(21,23),['-preset','p7','-tune','hq','-rc','vbr','-b:v','0']),
    ]
    if profile == 'higher-quality-cpu':
        definitions=[
            ('libx265','hevc','-crf',(17,18,19),['-preset','slow','-x265-params','pools=4:frame-threads=1']),
            ('libsvtav1','av1','-crf',(12,16,20),['-preset','6','-svtav1-params','lp=4']),
        ]
    elif profile != 'standard':
        raise ValueError('Unknown comparison profile')
    for encoder,codec,flag,values,options in definitions:
        for value in values:
            rows.append(dict(id=encoder+'-'+flag.lstrip('-')+str(value),encoder=encoder,codec=codec,
                             options=['-c:v',encoder,*options,flag,str(value),'-threads:v','4']))
    return rows


def command(reference, output, row, streams):
    video=next(s for s in streams if s['codec_type']=='video')
    args=['ffmpeg','-hide_banner','-nostdin','-n','-threads','4','-copyts','-i',str(reference),
          '-map','0','-map_metadata','0','-map_chapters','0','-c','copy',*row['options'],
          '-pix_fmt','yuv420p','-color_range',video['color_range'],'-colorspace','bt709',
          '-color_trc','bt709','-color_primaries','bt709','-fps_mode:v','passthrough',
          '-avoid_negative_ts','disabled']
    for i,stream in enumerate(streams):
        flags='+'.join(k for k,v in stream.get('disposition',{}).items() if v) or '0'
        args += [f'-disposition:{i}',flags]
    return args+['-progress','pipe:1','-nostats',str(output)]


def run(reference, output, profile='standard'):
    selected=recipes(profile)
    # Linux affinity is inherited by every FFmpeg/FFprobe child, bounding CPU use
    # even if an encoder ignores its thread option.
    if not hasattr(os,'sched_getaffinity'):
        raise RuntimeError('This comparison requires Linux CPU-affinity support')
    cpus=sorted(os.sched_getaffinity(0))[:4]
    os.sched_setaffinity(0,cpus)
    run=output/('encoder-comparison-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    run.mkdir()
    original=ao.fingerprint(reference)
    original_hash=ao.digest(reference)
    started=time.monotonic()
    def guard():
        if ao.fingerprint(reference)!=original:raise RuntimeError('Reference changed')
        if shutil.disk_usage(output).free < 4*1024**3:raise RuntimeError('Free space below 4 GiB')
        if time.monotonic()-started > 2700:raise RuntimeError('45-minute comparison budget exhausted')
    args=SimpleNamespace(ffmpeg='ffmpeg',ffprobe='ffprobe',timeout=600,vmaf_mean=95,vmaf_p5=90)
    workflow=ao.Workflow(args,run,guard)
    report=dict(scope='Single difficult scene; not full-video qualification or Plex compatibility',
                reference=str(reference),reference_sha256=original_hash,affinity=cpus,
                profile=profile,results=[])
    def save():ao.save(run/'comparison.json',report)
    save()
    try:
        info=workflow.probe(reference);ao.eligibility(info)
        duration=float(info['format']['duration'])
        if not 1<=duration<=20:raise ValueError('Only an existing 1-20 second reference clip is allowed')
        frames=workflow.frame_file(reference,'reference')
        count=ao.compare_frames(frames,frames)
        self_check=workflow.quality(reference,reference,'self',count,duration)
        if self_check['mean']<98 or self_check['p5']<95:raise RuntimeError('Metric self-check failed')
        report['metric_self_check']=self_check
        available=ao.mm.ffmpeg_encoder_names('ffmpeg')
        for index,row in enumerate(selected):
            guard()
            result=dict(id=row['id'],encoder=row['encoder'],codec=row['codec'],options=row['options'])
            report['results'].append(result)
            if row['encoder'] not in available:
                result['status']='unavailable-in-installed-ffmpeg';save();continue
            target=run/(row['id']+'.mkv')
            try:
                begin=time.monotonic()
                workflow.execute(command(reference,target,row,info['streams']),row['id'],duration)
                result.update(encode_seconds=time.monotonic()-begin,bytes=target.stat().st_size,
                              savings_percent=100*(1-target.stat().st_size/original['size']))
                workflow.validate(reference,target,info,row['codec'],row['id'],frames)
                result['preservation_and_decode_pass']=True
                result['quality']=workflow.quality(reference,target,row['id'],count,duration)
                result['status']='measured'
            except (ValueError,RuntimeError,subprocess.SubprocessError) as exc:
                guard()
                result.update(status='failed-or-time-limited',error=str(exc))
            save()
            progress('Encoder compared',index+1,len(selected),directory=run,unit='settings')
        guard()
        if ao.digest(reference)!=original_hash:raise RuntimeError('Reference hash changed')
        report.update(state='comparison-completed',reference_unchanged=True)
        save()
        print(json.dumps(report,indent=2))
        return 0
    except BaseException as exc:
        report.update(state='stopped',error=str(exc));save();raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',required=True,type=Path)
    parser.add_argument('--output-dir',type=Path,default=Path('/output'))
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--profile',choices=('standard','higher-quality-cpu'),default='standard')
    opts=parser.parse_args()
    reference,output=ao.disjoint(opts.reference,opts.output_dir)
    if not reference.is_file():parser.error('Reference clip does not exist')
    if opts.execute:
        output.mkdir(parents=True,exist_ok=True)
        raise SystemExit(tracked_call(lambda:run(reference,output,opts.profile),
                         'Episode_B · encoder comparison · '+opts.profile+' (short clip)',folder=output))
    print(json.dumps(dict(dry_run=True,reference=str(reference),profile=opts.profile,
                         recipes=recipes(opts.profile)),indent=2))
