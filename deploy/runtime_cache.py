"""Reuse an immutable dependency image; cached bytes are not qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def identity(image):
    value=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',image],text=True).strip()
    if not re.fullmatch(r'sha256:[a-f0-9]{64}',value):raise ValueError('Invalid runtime image identity')
    return value


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def save(image,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    image_id=identity(image)
    partial=folder/'runtime.tar.partial'
    subprocess.run(['docker','image','save','--output',str(partial),image_id],check=True)
    sha=digest(partial)
    partial.rename(folder/'runtime.tar')
    (folder/'runtime.json').write_text(json.dumps(dict(schema=1,image_id=image_id,sha256=sha)),encoding='utf-8')


def load(image,folder):
    folder=Path(folder)
    receipt=json.loads((folder/'runtime.json').read_text())
    if receipt.get('schema')!=1 or not re.fullmatch(r'sha256:[a-f0-9]{64}',receipt.get('image_id','')):
        raise ValueError('Invalid runtime receipt')
    if digest(folder/'runtime.tar')!=receipt.get('sha256'):raise ValueError('Cached runtime checksum mismatch')
    subprocess.run(['docker','load','--input',str(folder/'runtime.tar')],check=True)
    if identity(receipt['image_id'])!=receipt['image_id']:raise ValueError('Loaded runtime identity mismatch')
    subprocess.run(['docker','tag',receipt['image_id'],image],check=True)
    print(json.dumps(dict(runtime_image_id=receipt['image_id'],qualification_reused=False)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('save','load'))
    parser.add_argument('image')
    parser.add_argument('folder',type=Path)
    args=parser.parse_args()
    (save if args.action=='save' else load)(args.image,args.folder)
