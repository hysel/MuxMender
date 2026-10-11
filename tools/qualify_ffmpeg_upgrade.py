"""Isolated Linux FFmpeg comparison; read-only sources, no publication."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))

ARTIFACT='https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n9.0-latest-linux64-gpl-9.0.tar.xz'
ARTIFACT_SHA256='fdfeeb0692943a903badacdeb44ce7ae856340c147ebba63176c31d6742f6ca3'
GEOMETRY_CASE='3a72e8ce455e471085b9be5bf3ef7c83'
CHAPTER_CASES=('37e443289eb54450b859821fe94ff30d','c7b953aa6b6c4c3ea76adf1c45b58951','8b624ee9896249ba80ba2b50245ea42b')


def fetch_verified(url,path,expected):
    digest=hashlib.sha256()
    with urllib.request.urlopen(url,timeout=30) as source,path.open('xb') as target:
        while chunk:=source.read(1024*1024):
            target.write(chunk);digest.update(chunk)
    if digest.hexdigest()!=expected:
        raise ValueError('Downloaded build changed; checksum does not match pinned artifact')


def unpack_verified(archive_path,destination):
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk() or not (destination/member.name).resolve().is_relative_to(destination.resolve()):
                raise ValueError('Unsafe executable archive')
        archive.extractall(destination,filter='data')
    binaries=list(destination.glob('*/bin/ffmpeg'))
    if len(binaries)!=1:raise ValueError('Ambiguous FFmpeg build layout')
    return binaries[0].parent


def main():
    if not sys.platform.startswith('linux'):raise RuntimeError('Linux-only qualification; never execute on Windows')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--archive',type=Path,help='Pre-staged pinned build for research containers without network access')
    parser.add_argument('--candidate-bin',type=Path,help='Isolated, administrator-built stable runtime directory')
    args=parser.parse_args();args.output.mkdir(exist_ok=False)
    from job_tracking import tracked_call,progress
    from auto_optimize import compare_frame_rows,Workflow,metadata_check

    def run():
        root=args.output
        result={'publication_authorized':False,'production_modified':False,
                'artifact_url':ARTIFACT if not args.candidate_bin else 'https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz',
                'artifact_sha256':ARTIFACT_SHA256 if not args.candidate_bin else '8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e',
                'scope':'Branch-build comparison, not stable-tag or custom-reader qualification',
                'geometry':[],'chapters':[]}
        report=root/'result.json'
        def save():report.write_text(json.dumps(result,indent=2))
        save()
        progress('Downloading pinned FFmpeg comparison build',directory=root)
        archive=root/'ffmpeg-comparison.tar.xz'
        if args.candidate_bin:
            binaries=args.candidate_bin
        elif args.archive:
            digest=hashlib.sha256()
            with args.archive.open('rb') as source:
                while chunk:=source.read(1024*1024):digest.update(chunk)
            if digest.hexdigest()!=ARTIFACT_SHA256:raise ValueError('Staged build checksum does not match pinned artifact')
            archive=args.archive
        else:
            fetch_verified(ARTIFACT,archive,ARTIFACT_SHA256)
        if not args.candidate_bin:binaries=unpack_verified(archive,root/'runtime')
        current=Path(shutil.which('ffmpeg')).parent
        versions={}
        for label,folder in [('baseline',current),('candidate',binaries)]:
            versions[label]=subprocess.check_output([str(folder/'ffmpeg'),'-version'],text=True,timeout=10)
        result['versions']=versions;save()
        if not versions['candidate'].startswith(('ffmpeg version n9.0','ffmpeg version 9.0.2')):
            raise ValueError('Unexpected comparison runtime version')
        if args.candidate_bin:result['scope']='Stable 9.0.2 diagnostic build; not complete app, quality-metric or custom-reader qualification'
        state=json.loads(Path('/output/ui-requests/requests.json').read_text())
        jobs={j['id']:j for j in state['jobs']}
        source=Path(jobs[GEOMETRY_CASE]['source']);identity=source.stat()
        def frames(binary,path,position):
            command=[str(binary),'-v','error','-read_intervals',position+'%+#2','-select_streams','v:0',
                     '-show_frames','-show_entries','frame=width,height,pix_fmt,sample_aspect_ratio,interlaced_frame,top_field_first,repeat_pict,color_primaries,color_transfer,color_space,color_range,best_effort_timestamp_time',
                     '-of','json',str(path)]
            return json.loads(subprocess.check_output(command,text=True,timeout=30))['frames']
        for label,folder in [('baseline',current),('candidate',binaries)]:
            for encoder in ('hevc_nvenc','av1_nvenc'):
                progress('Comparing decoded geometry',detail=label+' / '+encoder,directory=root)
                item={'runtime':label,'encoder':encoder,'source_case':GEOMETRY_CASE}
                result['geometry'].append(item)
                with tempfile.TemporaryDirectory(prefix='geometry-',dir=root) as temporary:
                    output=Path(temporary)/'candidate.mkv'
                    command=[str(folder/'ffmpeg'),'-v','error','-nostdin','-xerror','-ss','503.9077367','-i',str(source),
                             '-t','1','-map','0:v:0','-an','-c:v',encoder,'-cq','25','-y',str(output)]
                    completed=subprocess.run(command,capture_output=True,text=True,timeout=90)
                    item.update(returncode=completed.returncode,diagnostic=completed.stderr[-3000:])
                    if completed.returncode==0:
                        before=frames(folder/'ffprobe',source,'503.9077367')
                        after=frames(folder/'ffprobe',output,'0')
                        item['source_geometry']=[{k:f.get(k) for k in ('width','height','pix_fmt','sample_aspect_ratio')} for f in before]
                        item['output_geometry']=[{k:f.get(k) for k in ('width','height','pix_fmt','sample_aspect_ratio')} for f in after]
                        # Compare geometry and color with the production gate.
                        # This two-frame diagnostic is not cadence/quality approval.
                        for a,b in zip(before,after):b['best_effort_timestamp_time']=a['best_effort_timestamp_time']
                        try:compare_frame_rows(before,after);item['geometry_check']='passed'
                        except ValueError as exc:item['geometry_check']=str(exc)
                    save()
        after_stat=source.stat()
        if (identity.st_dev,identity.st_ino,identity.st_size,identity.st_mtime_ns)!=(after_stat.st_dev,after_stat.st_ino,after_stat.st_size,after_stat.st_mtime_ns):
            raise ValueError('Source changed during diagnostic')
        for identifier in CHAPTER_CASES:
            source=Path(jobs[identifier]['source'])
            case=root/identifier;case.mkdir()
            admission=case/'admission';admission.mkdir()
            arguments=argparse.Namespace(ffmpeg=str(binaries/'ffmpeg'),ffprobe=str(binaries/'ffprobe'),timeout=180)
            before=Workflow(arguments,admission,lambda:None).probe(source)
            worker=Workflow(arguments,case,lambda:None)
            worker.prepare_chapter_mapping(source,before)
            item={'source_case':identifier,'runtime':'candidate','verified_mapping':worker.chapter_tracks.get(str(source.resolve()),())}
            result['chapters'].append(item);save()
            progress('Checking full chapter remux with newer FFmpeg',detail='Separate admission and conversion instances',directory=root)
            with tempfile.TemporaryDirectory(prefix='remux-',dir=case) as temporary:
                output=Path(temporary)/'copy.mp4'
                worker.execute([arguments.ffmpeg,'-v','error','-nostdin','-n','-copyts','-i',str(source),
                                '-map','0','-map_chapters','0','-map_metadata','0','-c','copy',str(output)],
                               'chapter-remux-new-runtime',float(before['format']['duration']))
                after=worker.probe(output)
                metadata_check(before,after,before['streams'][0]['codec_name'])
                item['full_remux_metadata_check']='passed';save()
        result['comparison_complete']=True;save()
        progress('FFmpeg comparison complete',detail='Review diagnostics; no release or publication approval',directory=root)
    return tracked_call(run,'FFmpeg upgrade compatibility comparison',folder=args.output)


if __name__=='__main__':raise SystemExit(main())
