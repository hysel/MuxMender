"""Bounded Linux excerpt benchmark of the installed shared validation engine.

No publication, relaxed checks, production queue edits or CPU encoding fallback.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

# Never allow loose development files in writable output to shadow the image.
if sys.platform.startswith('linux'):
    sys.path=[p for p in sys.path if p and not Path(p).resolve().is_relative_to('/output')]
    sys.path[:0]=['/opt/muxmender','/opt/muxmender-runtime']


def image_engine():
    import auto_optimize as ao
    if Path(ao.__file__).resolve()!=Path('/opt/muxmender/auto_optimize.py'):
        raise RuntimeError('Benchmark must use the installed image engine')
    return ao


def identity(path):
    stat=path.stat();return (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)


def idle():
    state=json.loads(Path('/output/ui-requests/requests.json').read_text())
    if not state.get('paused') or any(j['state'] in ('pending','running') for j in state['jobs']):
        raise RuntimeError('Production queue must be paused and empty for this benchmark')


def prepare_workflow(case,folder):
    """Use the image's existing evidence-based SDR color helpers."""
    ao=image_engine();source=Path(case['clip'])
    args=SimpleNamespace(ffmpeg='ffmpeg',ffprobe='ffprobe',timeout=7200,source=source,
        output_preset='original',vmaf_mean=case.get('mean',94),vmaf_p5=90,
        quality_profile=case.get('profile','balanced'))
    workflow=ao.Workflow(args,folder,lambda:None)
    before=workflow.probe(source);info=ao.mm.probe(source,'ffprobe')
    import legacy_color
    video=ao.main_video(before)
    if any(video.get(key) in legacy_color.UNKNOWN for key in legacy_color.FIELDS):
        sampled=legacy_color.inspect_frames('ffprobe',source,float(before['format']['duration']))
        evidence=None
        if video.get('codec_name')=='h264' and video.get('color_range') in legacy_color.UNKNOWN:
            evidence=legacy_color.inspect_h264_default_range('ffmpeg',source,float(before['format']['duration']))
            if evidence:video['color_range']=evidence['value']
        before,report=legacy_color.resolve(before,sampled,'inspect')
        if report.get('assumed') or (report['missing'] and not report.get('preserved_unspecified')):
            raise ValueError('Source color remains unresolved; no benchmark assumption allowed')
        args.resolved_color={k:v for k,v in report['effective'].items() if v not in legacy_color.UNKNOWN}
        (folder/'color-inspection.json').write_text(json.dumps(dict(report,range_evidence=evidence),indent=2))
    return workflow,before,info


def task(case,folder):
    ao=image_engine()
    from job_tracking import tracked_call
    from replacement_cleanup import prune_generated
    folder=Path(folder);folder.mkdir()
    result={}
    def execute():
        source=Path(case['clip']);started=time.monotonic()
        workflow,before,info=prepare_workflow(case,folder)
        duration=float(before['format']['duration']);frames=workflow.frame_file(source,'source',before['format'])
        output=folder/'encoded.mkv';settings=case['settings']
        tick=time.monotonic()
        workflow._encode_preserving_color(source,output,settings,info,before,'full',duration)
        result['encode_wall_seconds']=time.monotonic()-tick;tick=time.monotonic()
        count=workflow.validate(source,output,before,settings['codec'],'full',frames)
        result['validation_wall_seconds']=time.monotonic()-tick;tick=time.monotonic()
        quality=workflow.quality(source,output,'full',count,duration)
        result.update(quality_wall_seconds=time.monotonic()-tick,quality=quality,frames=count,
            source_bytes=source.stat().st_size,output_bytes=output.stat().st_size,
            seconds=time.monotonic()-started,publication_authorized=False)
        return 0
    try:
        code=tracked_call(execute,'Scheduling benchmark excerpt',folder=folder/'reports')
        if code:raise RuntimeError('Excerpt validation execution failed')
        return result
    finally:
        # Only benchmark-owned generated files; original source lives outside.
        cleanup=prune_generated(folder,execute=True)
        (folder/'cleanup-summary.json').write_text(json.dumps({k:cleanup[k] for k in ('state','files','bytes')}))


def main():
    if not sys.platform.startswith('linux'):raise RuntimeError('Linux app benchmark only')
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--request',action='append',required=True)
    parser.add_argument('--seconds',type=int,default=30)
    parser.add_argument('--intermediate-request',help='Optional failed safe-copy case for 90/90 AV1 scene research')
    args=parser.parse_args()
    engine=image_engine()
    if len(args.request)!=2 or len(set(args.request))!=2 or not 10<=args.seconds<=60:
        raise ValueError('Use two distinct approved-copy cases and 10–60 second excerpts')
    idle();root=args.output
    if not root.is_absolute() or not root.resolve().is_relative_to('/output') or root.exists():
        raise ValueError('Use a new private directory under /output')
    root.mkdir()
    import app_version
    (root/'engine.json').write_text(json.dumps(dict(version=app_version.VERSION,
        module=str(Path(engine.__file__).resolve()),sha256=hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest())))
    from job_tracking import tracked_call,progress
    from replacement_cleanup import prune_generated
    from gpu_frame_reader import load_qualification
    os.environ['MUXMENDER_VALIDATION_LOCK_ROOT']=str(root/'admission')
    os.environ['MUXMENDER_PAUSE_LEASE']='/output/ui-requests/gpu-yield-lease.json'
    results=[];cases=[];stop=threading.Event()
    def telemetry():
        from resource_governor import Governor
        governor=Governor()
        with (root/'telemetry.jsonl').open('x') as log:
            while not stop.is_set():
                try:record=dict(at=time.time(),resources=governor.sample())
                except Exception as exc:record=dict(at=time.time(),error=type(exc).__name__)
                log.write(json.dumps(record)+'\n');log.flush();stop.wait(3)
    def run():
        if load_qualification() is None:raise RuntimeError('Installed GPU reader qualification is unavailable')
        for index,identifier in enumerate(args.request):
            if len(identifier)!=32 or any(x not in '0123456789abcdef' for x in identifier):raise ValueError('Invalid request')
            folder=Path('/output/ui-requests')/('request-'+identifier)
            receipts=list(folder.glob('auto-*/approved-replacement.json'))
            if len(receipts)!=1:raise ValueError('A confirmed approved-copy receipt is required')
            source=Path(json.loads(receipts[0].read_text())['target'])
            if source.is_symlink() or not source.resolve().is_relative_to('/media'):raise ValueError('Invalid media source')
            stamp=identity(source);case=root/('case-'+str(index));case.mkdir()
            metadata=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(source)],timeout=60))
            video=next(s for s in metadata['streams'] if s['codec_type']=='video')
            if video.get('color_transfer') in ('smpte2084','arib-std-b67') or any('dv_profile' in s for s in video.get('side_data_list',[])):
                raise ValueError('Use SDR sources for this initial scheduling comparison')
            start=int(float(metadata['format']['duration'])*.5)
            with (case/'extract.log').open('x') as log:
                subprocess.run(['mkvmerge','-o',str(case/'source.mkv'),'--split',f'parts:{start}s-{start+args.seconds}s',str(source)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
            clips=list(case.glob('*.mkv'))
            if len(clips)!=1:raise ValueError('Expected one keyframe-aligned excerpt')
            selected=json.loads((receipts[0].parent/'selection.json').read_text())['selected']['settings']
            cases.append(dict(clip=str(clips[0]),source=source,identity=stamp,settings=selected,
                clip_hash=hashlib.sha256(clips[0].read_bytes()).hexdigest(),height=video['height'],width=video['width']))
        thread=threading.Thread(target=telemetry,daemon=True);thread.start()
        try:
            for workers in (1,2,4):
                idle();progress('Scheduling benchmark: '+str(workers)+' workers',len(results),3,unit='configurations',detail='Four equal tasks; complete excerpt validation and unchanged 94/90 quality gates')
                started=time.monotonic();rows=[]
                with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn')) as executor:
                    futures=[executor.submit(task,cases[i%2],str(root/f'workers-{workers}-task-{i}')) for i in range(4)]
                    for future in as_completed(futures):rows.append(future.result())
                elapsed=time.monotonic()-started
                results.append(dict(workers=workers,wall_seconds=elapsed,tasks_per_hour=4*3600/elapsed,
                    tasks=rows,all_quality_passed=all(r['quality']['passed'] for r in rows)))
                (root/'benchmark.json').write_text(json.dumps(dict(results=results,complete=len(results)==3,
                    scope='Two real SDR excerpts repeated twice; installed engine, not full-movie throughput',
                    publication_authorized=False),indent=2))
                for case in cases:
                    if identity(case['source'])!=case['identity'] or hashlib.sha256(Path(case['clip']).read_bytes()).hexdigest()!=case['clip_hash']:
                        raise ValueError('Source or benchmark input changed')
            if args.intermediate_request:
                identifier=args.intermediate_request
                if len(identifier)!=32 or any(x not in '0123456789abcdef' for x in identifier):raise ValueError('Invalid scene research request')
                idle();queue=json.loads(Path('/output/ui-requests/requests.json').read_text())
                previous=next(j for j in queue['jobs'] if j['id']==identifier)
                if previous['state']!='skipped' or previous['settings'].get('quality_profile')!='space-saver':
                    raise ValueError('Scene research requires an existing rejected Space saver case')
                source=Path(previous['source']);stamp=identity(source)
                if source.is_symlink() or not source.resolve().is_relative_to('/media'):raise ValueError('Invalid scene source')
                trials=list((Path('/output/ui-requests')/('request-'+identifier)).glob('auto-*/trials.json'))
                if len(trials)!=1:raise ValueError('Exactly one rejected trial report required')
                data=json.loads(trials[0].read_text());candidate=next(t for t in data['trials'] if t['id']=='av1_nvenc-compact')
                failed=next(s for s in candidate['samples'] if s.get('quality',{}).get('passed') is False)
                reference=next(r for r in data['references'] if r['id']==failed['reference_id'])
                scene=root/'difficult-scene';scene.mkdir();start=int(reference['position'])
                with (scene/'extract.log').open('x') as log:
                    subprocess.run(['mkvmerge','-o',str(scene/'source.mkv'),'--split',f'parts:{start}s-{start+10}s',str(source)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
                clips=list(scene.glob('*.mkv'))
                if len(clips)!=1:raise ValueError('Expected one difficult-scene excerpt')
                clip=clips[0];baseline=hashlib.sha256(clip.read_bytes()).hexdigest();scene_results=[]
                for cq in (22,23,24):
                    idle();progress('Intermediate AV1 scene: CQ '+str(cq),detail='Unchanged Space saver gates: mean 90 / fifth-percentile 90; no publication')
                    case=dict(clip=str(clip),mean=90,profile='space-saver',settings=dict(codec='av1',encoder='av1_nvenc',quality='balanced',nvenc_cq=cq,nvenc_preset='p7'))
                    with ProcessPoolExecutor(max_workers=1,mp_context=multiprocessing.get_context('spawn')) as executor:
                        row=executor.submit(task,case,str(root/('intermediate-cq-'+str(cq)))).result()
                    scene_results.append(dict(cq=cq,**row,saved_percent=100*(1-row['output_bytes']/row['source_bytes'])))
                    (root/'intermediate-scene.json').write_text(json.dumps(dict(results=scene_results,complete=len(scene_results)==3,publication_authorized=False,scope='Difficult scene only; all-scene and full-output tests still required'),indent=2))
                if identity(source)!=stamp or hashlib.sha256(clip.read_bytes()).hexdigest()!=baseline:raise ValueError('Scene source changed')
        finally:stop.set();thread.join(timeout=10)
        return 0
    try:return tracked_call(run,'Installed engine: 1 / 2 / 4 worker comparison',folder=root/'reports')
    finally:
        cleanup=prune_generated(root,execute=True)
        (root/'cleanup-summary.json').write_text(json.dumps({k:cleanup[k] for k in ('state','files','bytes')}))


if __name__=='__main__':raise SystemExit(main())
