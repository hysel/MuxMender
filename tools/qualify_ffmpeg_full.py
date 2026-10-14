"""Isolated Linux generated runtime/metric/reader checks; no publication."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'python'))
FIELDS = ('best_effort_timestamp_time,width,height,pix_fmt,sample_aspect_ratio,'
          'interlaced_frame,top_field_first,repeat_pict,color_primaries,color_transfer,'
          'color_space,color_range,side_data_list')


def exact_frames(left, right):
    if not left or len(left)!=len(right):
        raise ValueError(f'CPU/GPU frame count differs: {len(left)} vs {len(right)}')
    for index,(a,b) in enumerate(zip(left,right)):
        if a!=b:
            differences={key:{'cpu':a.get(key),'gpu':b.get(key)}
                         for key in sorted(set(a)|set(b)) if a.get(key)!=b.get(key) or (key in a)!=(key in b)}
            raise ValueError('CPU/GPU frame evidence differs at frame '+str(index+1)+': '+json.dumps(differences))
    return len(left)


def main():
    if sys.platform != 'linux':
        raise RuntimeError('Linux-only qualification; never execute on Windows')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ledger', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    from job_tracking import tracked_call, progress
    from ffmpeg_compatibility_suite import binary_receipt

    def run():
        report = dict(production_changed=False, publication_authorized=False,
                      reader_installation_authorized=False, quality_gates_changed=False,
                      scope='Generated qualification; representative full-file and shared-engine qualification still required',
                      metrics=[], reader=[], errors=[])
        def save():
            (args.output/'result.json').write_text(json.dumps(report, indent=2))
        def command(argv, env=None, timeout=180):
            result = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=timeout)
            if result.returncode:
                raise RuntimeError(result.stderr[-2000:])
            return result.stdout
        candidate = '/opt/ffmpeg9/bin/ffmpeg'
        probe = '/opt/ffmpeg9/bin/ffprobe'
        reader = '/opt/ffmpeg9-reader/ffprobe-cuda'
        baseline = '/usr/local/bin/ffmpeg'
        report['binaries'] = {label:binary_receipt(Path(path)) for label,path in
                              [('baseline',baseline),('candidate',candidate),('probe',probe),('reader',reader)]}
        for option in ('-encoders','-filters','-hwaccels'):
            (args.output/('candidate'+option+'.txt')).write_text(command([candidate,'-hide_banner',option]))
        save()
        progress('Running paired ledger regressions', directory=args.output)
        env = dict(os.environ)
        # Keep dependencies isolated; the suite prepends shared source and
        # preserves this explicitly selected dependency directory.
        env['PYTHONPATH'] = str(ROOT/'python')+':'+str(ROOT/'runtime')
        with (args.output/'comparison.log').open('x') as log:
            result = subprocess.run([sys.executable,'-B',str(ROOT/'tools/ffmpeg_compatibility_suite.py'),
                '--ledger',str(args.ledger.resolve()),
                '--baseline-ffmpeg',baseline,'--baseline-ffprobe','/usr/local/bin/ffprobe',
                '--candidate-ffmpeg',candidate,'--candidate-ffprobe',probe,
                '--output',str(args.output/'comparison')], stdout=log,stderr=subprocess.STDOUT,
                env=env,timeout=1800)
        if result.returncode:
            report['errors'].append('Regression harness execution failed; see comparison.log')
        elif (args.output/'comparison/compatibility-report.json').exists():
            comparison=json.loads((args.output/'comparison/compatibility-report.json').read_text())
            report['regression_summary']={label:dict(modules=len(rows),
                failures=[name for name,row in rows.items() if row.get('returncode',0)!=0 or row.get('error')],
                skipped_tests=sum(row.get('skipped') or 0 for row in rows.values()))
                for label,rows in comparison['regressions'].items()}
        save()
        with tempfile.TemporaryDirectory(prefix='full-qualification-',dir=args.output) as directory:
            temp=Path(directory)
            reference=temp/'reference.mkv';damaged=temp/'damaged.mkv'
            progress('Checking quality metrics and negative controls', directory=args.output)
            command([baseline,'-v','error','-nostdin','-n','-f','lavfi','-i',
                     'testsrc2=size=192x108:rate=12:duration=1','-c:v','libx264','-qp','0',
                     '-threads','2',str(reference)])
            command([baseline,'-v','error','-nostdin','-n','-i',str(reference),'-vf',
                     'drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill',
                     '-c:v','libx264','-qp','0','-threads','2',str(damaged)])
            for label,ffmpeg in [('baseline',baseline),('candidate',candidate)]:
                row=dict(runtime=label,passed=False);report['metrics'].append(row)
                try:
                    for kind,source in [('self',reference),('damaged',damaged)]:
                        metric=temp/(label+'-'+kind+'.json')
                        command([ffmpeg,'-v','error','-nostdin','-i',str(source),'-i',str(reference),
                            '-lavfi',f'[0:v][1:v]libvmaf=log_fmt=json:log_path={metric}:n_threads=2',
                            '-f','null','-'])
                        data=json.loads(metric.read_text())
                        row[kind]=dict(mean=data['pooled_metrics']['vmaf']['mean'],frames=len(data['frames']))
                    row['passed']=(row['self']['frames']==row['damaged']['frames']==12 and
                                   row['self']['mean']>99 and row['damaged']['mean']<row['self']['mean']-10)
                except Exception as exc:row['error']=str(exc)
                save()
            progress('Checking generated CPU/GPU reader parity', directory=args.output)
            for codec in ('hevc','av1'):
                for hdr in (False,True):
                    row=dict(codec=codec,hdr=hdr,passed=False);report['reader'].append(row)
                    source=temp/(codec+('-hdr' if hdr else '-sdr')+'.mkv')
                    try:
                        command([candidate,'-v','error','-nostdin','-n','-f','lavfi','-i',
                            'testsrc2=size=320x180:rate=12:duration=2','-c:v',codec+'_nvenc',
                            '-preset','p4','-cq','18','-pix_fmt','yuv420p10le',
                            '-color_primaries','bt2020' if hdr else 'bt709',
                            '-color_trc','smpte2084' if hdr else 'bt709',
                            '-colorspace','bt2020nc' if hdr else 'bt709',str(source)])
                        row['source_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
                        evidence=[]
                        for binary,gpu in [(probe,False),(reader,True)]:
                            reader_env=dict(os.environ,MUXMENDER_RESEARCH_CUDA_READER='1' if gpu else '0')
                            text=command([binary,'-v','error','-select_streams','v:0','-show_frames',
                                '-show_entries','frame='+FIELDS,'-of','json',str(source)],env=reader_env)
                            evidence.append(json.loads(text)['frames'])
                        for label,frames in zip(('cpu','gpu'),evidence):
                            (args.output/(codec+('-hdr' if hdr else '-sdr')+'-'+label+'-frames.json')).write_text(json.dumps(frames,indent=2))
                        row['frames']=exact_frames(*evidence)
                        changed=copy.deepcopy(evidence[1]);changed[0]['width']+=2
                        try:exact_frames(evidence[0],changed)
                        except ValueError:row['negative_geometry_rejected']=True
                        try:exact_frames(evidence[0],evidence[1][:-1])
                        except ValueError:row['negative_frame_loss_rejected']=True
                        row['passed']=(row['frames']==24 and row.get('negative_geometry_rejected') and
                                       row.get('negative_frame_loss_rejected'))
                    except Exception as exc:row['error']=str(exc)
                    save()
        report['temporary_media_removed']=True
        report['passed']=(not report['errors'] and all(row['passed'] for row in report['metrics']+report['reader'])
            and bool(report.get('regression_summary')) and all(not row['failures'] and not row['skipped_tests']
                for row in report['regression_summary'].values()))
        save()
        progress('Qualification finished',detail='Evidence only; production and reader unchanged',directory=args.output)
        return 0 if report['passed'] else 1
    return tracked_call(run,'Full-feature FFmpeg 9 and rebuilt reader qualification',folder=args.output)


if __name__=='__main__':raise SystemExit(main())
