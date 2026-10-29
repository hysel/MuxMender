"""Prepare private host receipts from complete, executable-bound evidence."""
import hashlib
import json
from gpu_reader_receipt import qualified_scope


def verified_receipt(receipt, evidence, binary, *, maximum_pairs=8):
    """Pure verification shared by the installer, private app cache and tests.

    This neither grants new scopes nor turns generated controls into full-source
    evidence. Runtime GPU/driver attestation remains the loader's responsibility.
    The bounded app cache can retain more format pairs than an installer bundle;
    every pair still requires the same complete proof.
    """
    if not isinstance(receipt, dict) or not isinstance(evidence, dict):
        raise ValueError('Qualification metadata must be structured')
    digest=hashlib.sha256(binary).hexdigest()
    if not binary.startswith(b'\x7fELF') or receipt.get('schema')!=1 or receipt.get('binary_sha256')!=digest:
        raise ValueError('Receipt does not match the Linux reader executable')
    adapter=receipt.get('adapter')
    if not isinstance(adapter,dict) or set(adapter)!={'uuid','driver'} or any(not isinstance(v,str) or not v for v in adapter.values()):
        raise ValueError('GPU and driver binding is incomplete')
    visibility=receipt.get('visibility')
    if not isinstance(visibility,dict) or set(visibility)!={'CUDA_VISIBLE_DEVICES','NVIDIA_VISIBLE_DEVICES','CUDA_DEVICE_ORDER'}:
        raise ValueError('Device visibility binding is incomplete')
    if any(value is not None and not isinstance(value,str) for value in visibility.values()):
        raise ValueError('Invalid device visibility binding')
    if type(maximum_pairs) is not int or not 1<=maximum_pairs<=32:raise ValueError('Invalid reader evidence budget')
    pairs=evidence.get('pairs')
    if not isinstance(pairs,list) or not 1<=len(pairs)<=maximum_pairs:
        raise ValueError('Complete reader evidence pairs are required')
    scopes=[]
    for pair in pairs:
        if not isinstance(pair,dict) or not isinstance(pair.get('real'),dict) or pair['real'].get('binary_sha256')!=digest:
            raise ValueError('Qualification evidence belongs to a different reader')
        scopes.append(qualified_scope(pair['real'],pair.get('controls')))
    if scopes!=receipt.get('scopes'):
        raise ValueError('Receipt scopes do not match verified evidence')
    # Drop unrelated input fields rather than publishing arbitrary bundle data.
    return json.dumps(dict(schema=1,binary_sha256=digest,adapter=adapter,
        visibility=visibility,scopes=scopes),sort_keys=True,indent=2).encode()+b'\n'
