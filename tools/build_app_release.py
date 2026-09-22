"""Create an exclusive, portable Docker context without Windows directory modes."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile


def create_release(root, archive, release_note, hdr_tool_archive=None):
    root=Path(root).resolve(strict=True);archive=Path(archive)
    selected=['python','tests','deploy/truenas/Dockerfile.app',release_note,
              'docs/per-video-codec-selection.md','tools/build_app_release.py',
              'tools/compare_encoders.py','tools/run_truenas_sample_batch.py',
              'tools/smoke_auto_optimize.py','tools/smoke_hdr_auto.py','tools/smoke_hdr_dynamic.py','tools/smoke_timestamp.py','tools/monitor_queue.py','tools/qualify_frame_reader.py',
              'tools/benchmark_frame_threads.py','tools/benchmark_packet_validation.py',
              'tools/benchmark_validation_pipeline.py','tools/benchmark_gpu_decode.py']
    files={}
    for item in selected:
        path=root/item
        if not path.exists():raise ValueError('Missing release input: '+item)
        for entry in [path,*(path.rglob('*') if path.is_dir() else [])]:
            if any(part=='__pycache__' or part.endswith('.egg-info') for part in entry.parts) or entry.suffix=='.pyc':continue
            if entry.is_symlink() or not entry.resolve().is_relative_to(root):raise ValueError('Linked release input: '+str(entry))
            files[entry.relative_to(root).as_posix()]=entry
    if hdr_tool_archive is not None:
        vendor=Path(hdr_tool_archive).resolve(strict=True)
        if hashlib.sha256(vendor.read_bytes()).hexdigest()!='06385f37a639d61ba21d4be3150c863846933bc3b58110e094d8fc8f1c2249f2':
            raise ValueError('HDR10+ tool archive checksum mismatch')
        files['vendor/hdr10plus.tar.gz']=vendor
    elif 'vendor/hdr10plus.tar.gz' in (root/'deploy/truenas/Dockerfile.app').read_text():
        raise ValueError('This Dockerfile requires --hdr-tool-archive')
    manifest={}
    # Exclusive creation prevents silently replacing a previously staged release.
    with tarfile.open(archive,'x',format=tarfile.PAX_FORMAT) as tar:
        for name,path in sorted(files.items()):
            info=tar.gettarinfo(str(path),arcname=name)
            info.mode=0o755 if info.isdir() else 0o644
            info.uid=info.gid=0;info.uname=info.gname='root';info.pax_headers={}
            if info.isfile():
                with path.open('rb') as stream:tar.addfile(info,stream)
                manifest[name]=hashlib.sha256(path.read_bytes()).hexdigest()
            elif info.isdir():tar.addfile(info)
            else:raise ValueError('Unsupported release input: '+name)
    return dict(archive=str(archive),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),files=manifest)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--release-note',required=True)
    parser.add_argument('--hdr-tool-archive',type=Path)
    args=parser.parse_args()
    print(json.dumps(create_release(args.root,args.archive,args.release_note,args.hdr_tool_archive),indent=2))
