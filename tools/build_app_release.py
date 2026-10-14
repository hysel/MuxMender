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
    'ffmpeg-9.0.2.tar.xz':'8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e',
    'nv-codec-headers-n13.0.19.0.tar.gz':'86d15d1a7c0ac73a0eafdfc57bebfeba7da8264595bf531cf4d8db1c22940116'}

FFMPEG9_SOURCE_CHECKSUMS={
    'ffmpeg-9.0.2.tar.xz':'8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e',
    'nv-codec-headers-n13.0.19.0.tar.gz':'86d15d1a7c0ac73a0eafdfc57bebfeba7da8264595bf531cf4d8db1c22940116',
    'vmaf-3.0.0.tar.gz':'7178c4833639e6b989ecae73131d02f70735fdb3fc2c7d84bc36c9c3461d93b1',
    'libplacebo-7.351.0.tar.gz':'716954501d9b76e6906fddda66febc5886493d0673dd265ec1e6e52f4e5cd7c6',
    'vulkan-headers-libplacebo.tar.gz':'400dc4bc49438f24ab9e90e6e587d9b1621a236f05eba80f6c048d7a1a96d353'}


def inspect_ffmpeg9_sources(directory):
    directory=Path(directory).resolve(strict=True)
    files={}
    for name,digest in FFMPEG9_SOURCE_CHECKSUMS.items():
        path=directory/name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('FFmpeg 9 source checksum mismatch: '+name)
        files['vendor/ffmpeg9-source/'+name]=path
    return files


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


def portable_release_content(path):
    content=path.read_bytes()
    if path.suffix=='.sh' or path.name.startswith('Dockerfile'):
        content=content.replace(b'\r\n',b'\n')
    return content


def inspect_gpu_reader_bundle(directory):
    """Bundle a proven executable plus matching evidence and complete sources."""
    import importlib.util
    directory=Path(directory).resolve(strict=True)
    names=('ffprobe-cuda','qualification.json','evidence.json','source/ffmpeg-9.0.2.tar.xz',
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


def create_release(root, archive, release_note, hdr_tool_archive=None, dovi_tool_archive=None, fel_runtime_archives=None,gpu_reader_bundle=None,ffmpeg9_sources=None):
    root=Path(root).resolve(strict=True);archive=Path(archive)
    release=re.fullmatch(r'RELEASE-(\d{8}-v\d+)\.md',Path(release_note).name)
    if release:
        tree=ast.parse((root/'python/app_version.py').read_text())
        versions=[ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node,ast.Assign) and any(
                      isinstance(target,ast.Name) and target.id=='VERSION' for target in node.targets)]
        if versions!=[release.group(1)]:
            raise ValueError('Release note and app version disagree; update app_version.py before packaging')
    selected=['python','tests','README.md','pyproject.toml','deploy/truenas/Dockerfile.app','deploy/truenas/requirements-av1-runtime.txt',release_note,
              'deploy/truenas/stage-release.sh','tools/smoke_app_release.py','tools/monitor_release_stage.py',
              'tools/benchmark_job_scheduling.py','tools/qualify_av1_intermediate.py',
              'tools/publish_approved_copies.py','tools/analyze_batch_performance.py','tools/qualify_iso_container_recovery.py',
              'tools/qualify_quality_profiles.py','tools/qualify_real_quality_profiles.py',
              'tools/research_hdr_sdr.py','tools/research_hdr_sdr_long.py',

              'docs/processing-timeouts.md','deploy/truenas/install_gpu_monitor.py',
              'deploy/truenas/install_reader_qualification.py',
              'tools/benchmark_sdr_gpu_reader.py','tools/benchmark_shared_sdr_reader.py',
              'docs/gpu-monitor-setup.md',

              'docs/processing-dashboard.md','docs/output-presets.md','tools/build_app_release.py',
              'tools/compare_encoders.py','tools/run_truenas_sample_batch.py','tools/dv_fel_research.py','tools/install_fel_runtime.py',
              'tools/monitor_remote_research.py','tools/probe_dv_renderer.py','tools/inspect_hevc_layers.py',
              'tools/publish_reviewed_research.py',
              'tools/research_coverage.py',
              'tools/benchmark_hdr_reader.py',

              'docs/post-task-cleanup.md',


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
    if 'vendor/ffmpeg9-source/' in (root/'deploy/truenas/Dockerfile.app').read_text():
        if ffmpeg9_sources is None:raise ValueError('This Dockerfile requires --ffmpeg9-sources')
        files.update(inspect_ffmpeg9_sources(ffmpeg9_sources))
        files['deploy/truenas/build_ffmpeg9.sh']=root/'deploy/truenas/build_ffmpeg9.sh'
        files['deploy/truenas/ffmpeg9-source.sha256']=root/'deploy/truenas/ffmpeg9-source.sha256'
        files['vendor/ffmpeg9-source/source.sha256']=root/'deploy/truenas/ffmpeg9-source.sha256'
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
                content=monitor if name=='deploy/truenas/install_gpu_monitor.py' else portable_release_content(path)
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
    parser.add_argument('--ffmpeg9-sources',type=Path,help='Pinned FFmpeg 9 and metric dependencies for the source-build stage')
    args=parser.parse_args()
    print(json.dumps(create_release(args.root,args.archive,args.release_note,args.hdr_tool_archive,args.dovi_tool_archive,args.fel_runtime_archives,args.gpu_reader_bundle,args.ffmpeg9_sources),indent=2))
