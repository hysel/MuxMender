"""Prepare code-only/generated-media qualification; administrator launches Docker."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from stage_reader_integration import write_context

PINS={
    'ffmpeg-9.0.2.tar.xz':'8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e',
    'nv-codec-headers-n13.0.19.0.tar.gz':'86d15d1a7c0ac73a0eafdfc57bebfeba7da8264595bf531cf4d8db1c22940116',
    'vmaf-3.0.0.tar.gz':'7178c4833639e6b989ecae73131d02f70735fdb3fc2c7d84bc36c9c3461d93b1',
    'av-18.1.0-cp311-abi3-manylinux_2_28_x86_64.whl':'8a032e8d8ebc73dec079364b9b4a6837638a2d106e8472314e685ffbf163e700',
    'libplacebo-7.351.0.tar.gz':'716954501d9b76e6906fddda66febc5886493d0673dd265ec1e6e52f4e5cd7c6',
    'vulkan-headers-libplacebo.tar.gz':'400dc4bc49438f24ab9e90e6e587d9b1621a236f05eba80f6c048d7a1a96d353',
}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,required=True)
    args=parser.parse_args()
    destination=Path('E:/MuxMender-TestOutputs/ffmpeg-full-qualification-20261010-r5')
    destination.mkdir(exist_ok=False)
    files={}
    pins=dict(PINS)
    for name,expected in pins.items():
        source=args.sources/name
        if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest()!=expected:
            raise ValueError('Qualification source checksum mismatch: '+name)
        files['source/'+name]=source
    manifest=destination/'source.sha256'
    manifest.write_text(''.join(digest+'  source/'+name+'\n' for name,digest in pins.items()))
    files['source/source.sha256']=manifest
    for folder in ('python','tests','tools','docs','deploy'):
        for path in (ROOT/folder).rglob('*'):
            if path.is_symlink():raise ValueError('Linked context source')
            if path.is_file() and (path.suffix in ('.py','.js','.json','.md','.sh','.yaml','.yml') or path.name.startswith('Dockerfile')):
                files[path.relative_to(ROOT).as_posix()]=path
    for name in ('README.md','AGENTS.md','pyproject.toml'):files[name]=ROOT/name
    for name in ('Dockerfile.ffmpeg-full-qualification','launch-ffmpeg-full-qualification.sh'):
        files[name]=ROOT/'deploy/truenas'/name
    archive=destination/'qualification.tar';write_context(archive,files)
    host='muxmender@192.168.1.232';key='C:/Users/itama/.ssh/haven42-ubuntu24-alpha2-ed25519'
    remote='/mnt/FR4G/Apps/muxmender/output/'+destination.name
    subprocess.run(['ssh','-i',key,'-o','BatchMode=yes',host,'mkdir -- '+remote],check=True)
    subprocess.run(['scp','-i',key,'-o','BatchMode=yes',str(archive),host+':'+remote+'/qualification.tar'],check=True)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    subprocess.run(['ssh','-i',key,'-o','BatchMode=yes',host,
        'cd '+remote+' && echo '+digest+'"  qualification.tar" | sha256sum -c - && tar -xf qualification.tar && sha256sum -c context.sha256'],check=True,stdout=subprocess.DEVNULL)
    print(json.dumps(dict(stage=remote,archive_sha256=digest,source_pins=pins,production_changed=False),indent=2))


if __name__=='__main__':main()
