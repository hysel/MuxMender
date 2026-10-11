"""Linux-only, read-only-source chapter/priming qualification; no publication."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))


def main():
    if not sys.platform.startswith('linux'):raise RuntimeError('Linux research qualification only')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--request',action='append',required=True)
    args=parser.parse_args()
    args.output.mkdir(exist_ok=False)
    from job_tracking import tracked_call,progress
    from auto_optimize import Workflow,metadata_check
    from media_metadata import essence_reader_options
    from aac_priming import inspect as inspect_priming
    def run():
        state=json.loads(Path('/output/ui-requests/requests.json').read_text())
        cases=[]
        for identifier in args.request:
            job=next(j for j in state['jobs'] if j['id']==identifier)
            source=Path(job['source']);before_stat=source.stat()
            case_root=args.output/identifier;case_root.mkdir()
            admission_root=case_root/'admission';admission_root.mkdir()
            workflow=Workflow(SimpleNamespace(ffmpeg='ffmpeg',ffprobe='ffprobe',timeout=120),admission_root,lambda:None)
            before=workflow.probe(source)
            # Production admission and conversion do not share a Workflow.
            # Exercise that lifecycle, not only a same-instance remux.
            workflow=Workflow(SimpleNamespace(ffmpeg='ffmpeg',ffprobe='ffprobe',timeout=120),case_root,lambda:None)
            workflow.prepare_chapter_mapping(source,before)
            options=essence_reader_options(before)
            workflow.essence_options[str(source.resolve())]=tuple(options)
            priming=inspect_priming(workflow,source,before,'source')
            audio=[s['index'] for s in before['streams'] if s.get('codec_type')=='audio']
            progress('Checking source audio excerpt',detail='Five-second strict read; not full-file audio qualification')
            if audio:
                workflow.execute(['ffmpeg','-v','error','-nostdin','-xerror',*options,'-i',str(source),'-t','5',
                    *[v for index in audio for v in ('-map',f'0:{index}')],'-f','null','-'],
                    'short-audio-decode',5,strict_decode=True)
            result=dict(request_id=identifier,priming_tracks=sorted(priming),reader_options=options,
                        translated_chapter_tracks=workflow.chapter_tracks.get(str(source.resolve()),()),
                        audio_excerpt_passed=True,publication_authorized=False)
            # Full stream copy only, not a full conversion or visual-quality test.
            # It checks all chapter metadata without spending GPU encoding time.
            if result['translated_chapter_tracks']:
                if shutil.disk_usage(args.output).free<before_stat.st_size+2*1024**3:
                    raise RuntimeError('Insufficient private qualification space')
                with tempfile.TemporaryDirectory(prefix='remux-',dir=case_root) as temp:
                    output=Path(temp)/'copy.mp4'
                    workflow.execute(['ffmpeg','-v','error','-nostdin','-n','-copyts','-i',str(source),
                        '-map','0','-map_chapters','0','-map_metadata','0','-c','copy',str(output)],
                        'chapter-preservation-remux',float(before['format']['duration']))
                    after=workflow.probe(output)
                    metadata_check(before,after,before['streams'][0]['codec_name'])
                    result['complete_chapter_metadata_preserved']=True
            after_stat=source.stat()
            if (before_stat.st_dev,before_stat.st_ino,before_stat.st_size,before_stat.st_mtime_ns)!=(
                    after_stat.st_dev,after_stat.st_ino,after_stat.st_size,after_stat.st_mtime_ns):
                raise RuntimeError('Source changed during qualification')
            result['source_stat_unchanged']=True
            cases.append(result)
        (args.output/'result.json').write_text(json.dumps(dict(cases=cases,passed=True,
             scope='Chapter metadata full-remux and five-second strict audio excerpts. No full encode, quality or publication approval.'),indent=2))
    return tracked_call(run,'ISO container and AAC timing qualification',folder=args.output)


if __name__=='__main__':raise SystemExit(main())
