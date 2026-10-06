"""Create an exclusive, portable Docker context without Windows directory modes."""
import argparse
import ast
import base64
import hashlib
import io
import json
import re
from pathlib import Path
import tarfile

GPU_READER_SOURCE_CHECKSUMS={
    'ffmpeg-8.0.1.tar.xz':'05ee0b03119b45c0bdb4df654b96802e909e0a752f72e4fe3794f487229e5a41',
    'nv-codec-headers-n13.0.19.0.tar.gz':'86d15d1a7c0ac73a0eafdfc57bebfeba7da8264595bf531cf4d8db1c22940116'}


def prepared_gpu_monitor(root):
    """Embed the matching collector so the shipped installer works on its own."""
    root=Path(root)
    template=(root/'deploy/truenas/install_gpu_monitor.py').read_text()
    marker="COLLECTOR_B64 = ''"
    if template.count(marker)!=1:
        raise ValueError('GPU monitor installer template must contain one collector placeholder')
    collector=(root/'python/gpu_activity.py').read_bytes()
    ast.parse(collector)
    return template.replace(marker,'COLLECTOR_B64 = '+repr(base64.b64encode(collector).decode('ascii'))).encode()


def inspect_gpu_reader_bundle(directory):
    """Bundle a proven executable plus matching evidence and complete sources."""
    import importlib.util
    directory=Path(directory).resolve(strict=True)
    names=('ffprobe-cuda','qualification.json','evidence.json','source/ffmpeg-8.0.1.tar.xz',
           'source/nv-codec-headers-n13.0.19.0.tar.gz','source/patch_cuda_ffprobe.py',
           'source/COPYING.LGPLv2.1','source/LICENSE.md')
    files={}
    for name in names:
        path=directory/name
        if (path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(directory)
                or any(parent.is_symlink() for parent in path.parents)):
            raise ValueError('Missing or linked GPU reader bundle input: '+name)
        limit=65536 if name=='qualification.json' else 2*1024*1024 if name=='evidence.json' else 64*1024*1024
        if not 0<path.stat().st_size<=limit:raise ValueError('Empty or oversized GPU reader bundle input: '+name)
        files['vendor/gpu-reader/'+name]=path
    receipt=json.loads((directory/'qualification.json').read_text())
    evidence=json.loads((directory/'evidence.json').read_text())
    if not isinstance(receipt,dict) or not isinstance(evidence,dict):raise ValueError('Reader bundle metadata is malformed')
    binary=(directory/'ffprobe-cuda').read_bytes()
    if not binary.startswith(b'\x7fELF') or receipt.get('binary_sha256')!=hashlib.sha256(binary).hexdigest():
        raise ValueError('GPU reader binary does not match its qualification')
    if (receipt.get('schema')!=1 or not isinstance(receipt.get('adapter'),dict)
            or set(receipt['adapter'])!={'uuid','driver'} or not all(isinstance(v,str) and v for v in receipt['adapter'].values())
            or not isinstance(receipt.get('visibility'),dict)):
        raise ValueError('GPU reader runtime binding is incomplete')
    spec=importlib.util.spec_from_file_location('reader_receipt',Path(__file__).resolve().parents[1]/'python/gpu_reader_receipt.py')
    validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
    pairs=evidence.get('pairs',[])
    if not isinstance(pairs,list) or not 1<=len(pairs)<=8:raise ValueError('Reader evidence pairs are missing')
    scopes=[]
    for pair in pairs:
        if not isinstance(pair,dict) or not isinstance(pair.get('real'),dict) or not isinstance(pair.get('controls'),dict):
            raise ValueError('Reader evidence pair is malformed')
        if pair['real'].get('binary_sha256')!=receipt['binary_sha256']:
            raise ValueError('Reader evidence belongs to another executable')
        scopes.append(validator.qualified_scope(pair['real'],pair['controls']))
    if scopes!=receipt.get('scopes'):raise ValueError('Reader scopes do not match complete evidence')
    for name,digest in GPU_READER_SOURCE_CHECKSUMS.items():
        if hashlib.sha256((directory/'source'/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('GPU reader source archive checksum mismatch: '+name)
    return files


def create_release(root, archive, release_note, hdr_tool_archive=None, dovi_tool_archive=None, fel_runtime_archives=None,gpu_reader_bundle=None):
    root=Path(root).resolve(strict=True);archive=Path(archive)
    release=re.fullmatch(r'RELEASE-(\d{8}-v\d+)\.md',Path(release_note).name)
    if release:
        tree=ast.parse((root/'python/app_version.py').read_text())
        versions=[ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node,ast.Assign) and any(
                      isinstance(target,ast.Name) and target.id=='VERSION' for target in node.targets)]
        if versions!=[release.group(1)]:
            raise ValueError('Release note and app version disagree; update app_version.py before packaging')
    selected=['python','tests','deploy/truenas/Dockerfile.app','deploy/truenas/requirements-av1-runtime.txt',release_note,
              'docs/av1-hdr-metadata.md','docs/dv-aac-duration-validation.md',
              'docs/cooperative-pause.md','docs/processing-timeouts.md','deploy/truenas/install_gpu_monitor.py',
              'docs/dashboard-polling.md','docs/validation-scheduling.md','docs/gpu-monitor-setup.md',
              'docs/performance-results.md','docs/performance-qualification-plan.md',
              'docs/per-video-codec-selection.md','docs/adaptive-gpu-admission.md','docs/processing-dashboard.md','docs/app-api.md','docs/output-presets.md','tools/build_app_release.py',
              'tools/compare_encoders.py','tools/run_truenas_sample_batch.py','tools/dv_fel_research.py','tools/install_fel_runtime.py',
              'tools/monitor_remote_research.py','tools/probe_dv_renderer.py','tools/inspect_hevc_layers.py',
              'tools/publish_reviewed_research.py','docs/research-checkpoint-20260922.md',
              'tools/research_coverage.py',
              'tools/benchmark_hdr_reader.py','docs/artifact-retention.md',
              'docs/source-audio-preflight.md','docs/aac-priming-preservation.md',
              'docs/changing-hdr-brightness.md','docs/post-task-cleanup.md','docs/activity-reports.md',
              'docs/conversion-reliability.md','docs/input-diagnostics.md',
              'docs/validation-performance-20260922.md',
              'tools/smoke_auto_optimize.py','tools/smoke_hdr_auto.py','tools/smoke_hdr_dynamic.py','tools/smoke_timestamp.py','tools/monitor_queue.py','tools/qualify_frame_reader.py',
              'tools/benchmark_frame_threads.py','tools/benchmark_packet_validation.py',
              'tools/benchmark_validation_pipeline.py','tools/benchmark_gpu_decode.py',
              'tools/benchmark_nvenc_presets.py','tools/build_research_snapshot.py']
    files={}
    for item in selected:
        path=root/item
        if not path.exists():raise ValueError('Missing release input: '+item)
        for entry in [path,*(path.rglob('*') if path.is_dir() else [])]:
            if any(part=='__pycache__' or part.endswith('.egg-info') for part in entry.parts) or entry.suffix=='.pyc':continue
            if entry.is_symlink() or not entry.resolve().is_relative_to(root):raise ValueError('Linked release input: '+str(entry))
            files[entry.relative_to(root).as_posix()]=entry
    if 'vendor/gpu-reader/' in (root/'deploy/truenas/Dockerfile.app').read_text():
        readme=root/'deploy/truenas/gpu-reader-README.md'
        if not readme.is_file():raise ValueError('Missing GPU reader package notice')
        files['vendor/gpu-reader/README.md']=readme
    if gpu_reader_bundle is not None:files.update(inspect_gpu_reader_bundle(gpu_reader_bundle))
    if hdr_tool_archive is not None:
        vendor=Path(hdr_tool_archive).resolve(strict=True)
        if hashlib.sha256(vendor.read_bytes()).hexdigest()!='06385f37a639d61ba21d4be3150c863846933bc3b58110e094d8fc8f1c2249f2':
            raise ValueError('HDR10+ tool archive checksum mismatch')
        files['vendor/hdr10plus.tar.gz']=vendor
    elif 'vendor/hdr10plus.tar.gz' in (root/'deploy/truenas/Dockerfile.app').read_text():
        raise ValueError('This Dockerfile requires --hdr-tool-archive')
    if dovi_tool_archive is not None:
        vendor=Path(dovi_tool_archive).resolve(strict=True)
        if hashlib.sha256(vendor.read_bytes()).hexdigest()!='5dae82cb2becd3b9fd726127f936a8d32635e60746d16238fdfded12aa05988c':
            raise ValueError('Dolby Vision tool archive checksum mismatch')
        files['vendor/dovi.tar.gz']=vendor
    elif 'vendor/dovi.tar.gz' in (root/'deploy/truenas/Dockerfile.app').read_text():
        raise ValueError('This Dockerfile requires --dovi-tool-archive')
    if fel_runtime_archives is not None:
        import importlib.util
        spec=importlib.util.spec_from_file_location('fel_runtime_installer',Path(__file__).with_name('install_fel_runtime.py'))
        installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        directory=installer.inspect_archives(fel_runtime_archives)
        for name in installer.CHECKSUMS:files['vendor/fel-runtime-archives/'+name]=directory/name
    elif 'vendor/fel-runtime-archives' in (root/'deploy/truenas/Dockerfile.app').read_text():
        raise ValueError('This Dockerfile requires --fel-runtime-archives with pinned packages and license')
    manifest={}
    monitor=prepared_gpu_monitor(root)
    # Exclusive creation prevents silently replacing a previously staged release.
    with tarfile.open(archive,'x',format=tarfile.PAX_FORMAT) as tar:
        for name,path in sorted(files.items()):
            info=tar.gettarinfo(str(path),arcname=name)
            info.mode=0o755 if info.isdir() else 0o644
            info.uid=info.gid=0;info.uname=info.gname='root';info.pax_headers={}
            if info.isfile():
                content=monitor if name=='deploy/truenas/install_gpu_monitor.py' else path.read_bytes()
                info.size=len(content)
                tar.addfile(info,io.BytesIO(content))
                manifest[name]=hashlib.sha256(content).hexdigest()
            elif info.isdir():tar.addfile(info)
            else:raise ValueError('Unsupported release input: '+name)
    return dict(archive=str(archive),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),files=manifest)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--release-note',required=True)
    parser.add_argument('--hdr-tool-archive',type=Path)
    parser.add_argument('--dovi-tool-archive',type=Path)
    parser.add_argument('--fel-runtime-archives',type=Path)
    parser.add_argument('--gpu-reader-bundle',type=Path,help='Optional attested reader, evidence and pinned source/license bundle')
    args=parser.parse_args()
    print(json.dumps(create_release(args.root,args.archive,args.release_note,args.hdr_tool_archive,args.dovi_tool_archive,args.fel_runtime_archives,args.gpu_reader_bundle),indent=2))
