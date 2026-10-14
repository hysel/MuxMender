"""Verify hosted main-branch provenance before a candidate can reach Docker."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPOSITORY='hysel/MuxMender'
WORKFLOW=REPOSITORY+'/.github/workflows/build-candidate.yml'


def command(archive,revision):
    if not re.fullmatch('[a-f0-9]{40}',revision):raise ValueError('Exact source revision required')
    return ['gh','attestation','verify',str(archive),'--repo',REPOSITORY,
            '--signer-workflow',WORKFLOW,'--source-ref','refs/heads/main',
            '--source-digest',revision,'--deny-self-hosted-runners','--format','json']


def verify(archive,receipt):
    archive=Path(archive)
    if archive.is_symlink() or not archive.is_file():raise ValueError('Regular archive required')
    if receipt.get('schema')!=1 or not re.fullmatch(r'sha256:[a-f0-9]{64}',receipt.get('image_id','')):
        raise ValueError('Invalid candidate receipt')
    args=command(archive,receipt.get('revision',''))
    with archive.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    if sha!=receipt.get('sha256') or archive.stat().st_size!=receipt.get('size_bytes'):
        raise ValueError('Archive differs from candidate receipt')
    # A privileged service must first copy inputs into its private directory;
    # this function does not grant privileges or prevent mutation by the owner.
    result=subprocess.run(args,check=True,capture_output=True,text=True,timeout=120)
    attestations=json.loads(result.stdout)
    if not isinstance(attestations,list) or not attestations:raise ValueError('No verified provenance')
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=sha:raise ValueError('Archive changed during verification')
    return dict(archive_sha256=sha,revision=receipt['revision'],image_id=receipt['image_id'],
                provenance_verified=True,qualification_approved=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(verify(args.archive,json.loads(args.receipt.read_text())),indent=2))
