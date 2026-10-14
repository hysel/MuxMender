"""Reusable Linux-only FFmpeg comparison. Never edits sources or retires code."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))


def load_ledger(path):
    ledger=json.loads(path.read_text())
    if ledger.get('schema')!=1:raise ValueError('Unsupported fix ledger schema')
    ids=set()
    for fix in ledger['fixes']:
        if not re.fullmatch(r'(FF|APP|SAFE|PERF|POL)-\d{3}',fix['id']) or fix['id'] in ids:
            raise ValueError('Invalid or duplicate fix ID')
        ids.add(fix['id'])
        for pattern in fix['tests']:
            if not re.fullmatch(r'test_[a-z0-9_]+\.py',pattern):raise ValueError('Unsafe regression pattern')
    return ledger


def disposition(fix,baseline,candidate,regressions):
    if fix['kind']!='upstream-workaround':return 'application-or-protection: retain'
    if not fix.get('raw_scenario') or baseline is None or candidate is None:return 'coverage gap: no upstream conclusion'
    if candidate.get('error') or baseline.get('error'):return 'execution unavailable: no upstream conclusion'
    if candidate.get('passed') is not True:return 'issue persists: retain handling'
    if baseline.get('passed') is not False:return 'baseline did not reproduce: no upstream conclusion'
    if regressions is not True:return 'regression coverage incomplete: retain handling'
    if candidate.get('negative_controls_passed') is not True:return 'negative-control coverage incomplete: retain handling'
    return 'upstream fix candidate: full-file and negative-control review required'


def pcm_equal(reference,output):
    return bool(reference) and reference==output


def run_command(command,timeout):
    result=subprocess.run(command,capture_output=True,timeout=timeout)
    if result.returncode:raise RuntimeError('Command failed: '+result.stderr.decode(errors='replace')[-1600:])
    return result.stdout


def binary_receipt(path):
    path=path.resolve(strict=True)
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):digest.update(chunk)
    return {'path':str(path),'sha256':digest.hexdigest(),
            'version':run_command([str(path),'-version'],15).decode(errors='replace')}


def main():
    if not sys.platform.startswith('linux'):raise RuntimeError('Linux-only FFmpeg suite; no native media runs on Windows')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ffmpeg',type=Path,required=True)
    parser.add_argument('--baseline-ffprobe',type=Path,required=True)
    parser.add_argument('--candidate-ffmpeg',type=Path)
    parser.add_argument('--candidate-ffprobe',type=Path)
    parser.add_argument('--baseline-only',action='store_true',help='Collect baseline evidence while the candidate runtime is unavailable')
    parser.add_argument('--ledger',type=Path,required=True,help='Local development ledger outside the published repository')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--command-timeout',type=int,default=120)
    parser.add_argument('--skip-regressions',action='store_true',help='Diagnostic only; never a retirement recommendation')
    args=parser.parse_args()
    if args.command_timeout<1:parser.error('Timeout must be positive')
    if not args.baseline_only and (args.candidate_ffmpeg is None or args.candidate_ffprobe is None):
        parser.error('Candidate executable pair is required unless --baseline-only is set')
    ledger=load_ledger(args.ledger)
    args.output.mkdir(exist_ok=False)
    from job_tracking import tracked_call,progress
    from auto_optimize import Workflow,metadata_check,main_video

    def run():
        report={'schema':1,'ledger_sha256':hashlib.sha256(args.ledger.read_bytes()).hexdigest(),
                'production_changed':False,'code_retired':False,'publication_authorized':False,
                'scope':'Generated raw sentinels and existing regression suites; full-file hardware qualification remains separate',
                'runtimes':{},'raw':{},'regressions':{},'fixes':[]}
        target=args.output/'compatibility-report.json'
        def save():target.write_text(json.dumps(report,indent=2))
        save()
        runtimes={'baseline':(args.baseline_ffmpeg.resolve(),args.baseline_ffprobe.resolve())}
        if not args.baseline_only:runtimes['candidate']=(args.candidate_ffmpeg.resolve(),args.candidate_ffprobe.resolve())
        for label,(ffmpeg,ffprobe) in runtimes.items():
            report['runtimes'][label]={'ffmpeg':binary_receipt(ffmpeg),'ffprobe':binary_receipt(ffprobe)}
        save()
        with tempfile.TemporaryDirectory(prefix='fixtures-',dir=args.output) as temporary:
            fixtures=Path(temporary);ffmpeg=runtimes['baseline'][0]
            progress('Generating reproducible compatibility fixtures',directory=args.output)
            # Native codecs avoid making the sentinel fixtures depend on GPUs.
            audio=fixtures/'source.m4a'
            run_command([str(ffmpeg),'-v','error','-nostdin','-n','-f','lavfi','-i','sine=frequency=997:sample_rate=48000:duration=2',
                         '-c:a','aac','-threads','2',str(audio)],args.command_timeout)
            chapters=fixtures/'chapters.ffmetadata'
            chapters.write_text(';FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1000\ntitle=Chapter 1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=1000\nEND=2000\ntitle=Chapter 2\n')
            video=fixtures/'source.mp4'
            run_command([str(ffmpeg),'-v','error','-nostdin','-n','-f','lavfi','-i','color=size=64x64:rate=25:duration=2',
                         '-i',str(chapters),'-map','0:v','-map_metadata','1','-map_chapters','1','-c:v','mpeg4','-threads','2',str(video)],args.command_timeout)
            report['fixtures']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (audio,video,chapters)}
            for label,(ffmpeg,ffprobe) in runtimes.items():
                report['raw'][label]={}
                def probe(path):return json.loads(run_command([str(ffprobe),'-v','error','-show_streams','-show_chapters','-show_format','-show_data_hash','sha256','-of','json',str(path)],args.command_timeout))
                for scenario,source,suffix in [('aac-priming',audio,'.mkv'),('native-chapters',video,'.mp4')]:
                    progress('Testing raw FFmpeg without MuxMender workaround',detail=label+' / '+scenario,directory=args.output)
                    record={'fixture_sha256':report['fixtures'][source.name],'passed':None,'managed_passed':None}
                    report['raw'][label][scenario]=record
                    output=fixtures/(label+'-'+scenario+suffix)
                    try:
                        # This raw command deliberately does NOT use Workflow,
                        # AAC finalization or verified negative chapter maps.
                        run_command([str(ffmpeg),'-v','error','-nostdin','-n','-copyts','-i',str(source),'-map','0',
                                     '-map_metadata','0','-map_chapters','0','-c','copy','-avoid_negative_ts','disabled',str(output)],args.command_timeout)
                        if scenario=='aac-priming':
                            def pcm(path):return run_command([str(ffmpeg),'-v','error','-nostdin','-xerror','-i',str(path),'-map','0:a:0','-c:a','pcm_s16le','-f','s16le','-'],args.command_timeout)
                            before=pcm(source);after=pcm(output)
                            record['source_pcm_sha256']=hashlib.sha256(before).hexdigest()
                            record['output_pcm_sha256']=hashlib.sha256(after).hexdigest()
                            record['source_pcm_bytes']=len(before);record['output_pcm_bytes']=len(after)
                            record['passed']=pcm_equal(before,after)
                            if not before:raise ValueError('Fixture has no decoded audio')
                            changed=bytes([before[0]^1])+before[1:]
                            record['negative_controls_passed']=not pcm_equal(before,changed) and not pcm_equal(before,before[:-2])
                            record['validation_scope']='Complete fixture PCM equality; not presentation timing or full-file publication proof'
                        else:
                            before=probe(source);after=probe(output)
                            record['source_streams']=len(before['streams']);record['output_streams']=len(after['streams'])
                            try:metadata_check(before,after,main_video(before)['codec_name']);record['passed']=True
                            except ValueError as exc:record.update(passed=False,validation_reason=str(exc))
                            changed=copy.deepcopy(before);main_video(changed)['width']+=2
                            try:metadata_check(before,changed,main_video(before)['codec_name']);record['negative_controls_passed']=False
                            except ValueError:record['negative_controls_passed']=True
                            managed=fixtures/(label+'-chapter-managed');managed.mkdir()
                            admission=managed/'admission';admission.mkdir()
                            settings=SimpleNamespace(ffmpeg=str(ffmpeg),ffprobe=str(ffprobe),timeout=args.command_timeout)
                            try:
                                normalized=Workflow(settings,admission,lambda:None).probe(source)
                                worker=Workflow(settings,managed,lambda:None);worker.prepare_chapter_mapping(source,normalized)
                                fixed=managed/'output.mp4'
                                worker.execute([str(ffmpeg),'-v','error','-nostdin','-n','-copyts','-i',str(source),'-map','0',
                                                '-map_metadata','0','-map_chapters','0','-c','copy',str(fixed)],'verified-chapter-map',2)
                                metadata_check(normalized,worker.probe(fixed),main_video(normalized)['codec_name'])
                                record['managed_passed']=True
                            except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:
                                # A managed-route failure must not rewrite the
                                # independently measured raw upstream result.
                                record.update(managed_passed=False,managed_error=str(exc))
                    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:record['error']=str(exc)
                    save()
            for path in (audio,video,chapters):
                if hashlib.sha256(path.read_bytes()).hexdigest()!=report['fixtures'][path.name]:
                    raise ValueError('Compatibility input fixture changed during testing')
            # Fixtures and temporary output copies are deleted by this scope,
            # even when a test fails. Receipts and logs stay in the report root.
        if not args.skip_regressions:
            patterns=sorted({p for fix in ledger['fixes'] for p in fix['tests']})
            for label,(ffmpeg,ffprobe) in runtimes.items():
                report['regressions'][label]={}
                if ffmpeg.parent!=ffprobe.parent:raise ValueError('Regression PATH requires paired binaries in one directory')
                env=dict(os.environ,PYTHONPATH=os.pathsep.join(filter(None,
                    (str(ROOT/'python'),os.environ.get('PYTHONPATH')))),
                    PATH=str(ffmpeg.parent)+os.pathsep+os.environ.get('PATH',''))
                for index,pattern in enumerate(patterns):
                    progress('Running application regression tests',detail=f'{label}: {index+1}/{len(patterns)}',directory=args.output)
                    log=args.output/(label+'-'+pattern+'.log')
                    record={'passed':False,'skipped':None};report['regressions'][label][pattern]=record
                    try:
                        completed=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(ROOT/'tests'),'-p',pattern],
                            capture_output=True,text=True,env=env,cwd=ROOT,timeout=args.command_timeout)
                        text=completed.stdout+completed.stderr;log.write_text(text)
                        skipped=re.search(r'OK \(skipped=(\d+)\)',text)
                        ran=re.search(r'Ran (\d+) tests?',text)
                        record.update(returncode=completed.returncode,tests=int(ran.group(1)) if ran else 0,
                                      skipped=int(skipped.group(1)) if skipped else 0,
                                      passed=completed.returncode==0 and bool(ran) and int(ran.group(1))>0 and not skipped)
                    except subprocess.TimeoutExpired:record['error']='User-selected regression timeout reached'
                    save()
        for fix in ledger['fixes']:
            scenario=fix.get('raw_scenario')
            regressions=all(report['regressions'].get(label,{}).get(p,{}).get('passed') is True
                            for label in runtimes for p in fix['tests'])
            record={'id':fix['id'],'title':fix['title'],'regressions_complete':regressions,
                    'recommendation':disposition(fix,report['raw'].get('baseline',{}).get(scenario),
                                                 report['raw'].get('candidate',{}).get(scenario),regressions)}
            report['fixes'].append(record)
        report['comparison_complete']=True;report['temporary_media_removed']=True;save()
        progress('Compatibility comparison complete',detail='Report only; no code removed or release approved',directory=args.output)
    return tracked_call(run,'FFmpeg fix compatibility suite',folder=args.output)


if __name__=='__main__':raise SystemExit(main())
