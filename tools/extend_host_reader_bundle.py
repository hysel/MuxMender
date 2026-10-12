"""Extend a private receipt from completed SDR evidence; never install or deploy."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from gpu_reader_receipt import sdr_comparison_pair,qualified_scope
from gpu_frame_reader import visibility_matches
from host_reader_qualification import verified_receipt


def extend(receipt,evidence,binary,report,witness):
    verified_receipt(receipt,evidence,binary)
    digest=receipt['binary_sha256']
    if report.get('binary_sha256')!=digest or witness.get('reader_sha256_after')!=digest:
        raise ValueError('Reader changed across the source comparison')
    adapters=report.get('adapters',[])
    if len(adapters)!=1 or {key:adapters[0].get(key) for key in ('uuid','driver')}!=receipt['adapter']:
        raise ValueError('SDR evidence belongs to another GPU or driver')
    if not visibility_matches(receipt['visibility'],report.get('visibility'),receipt['adapter']['uuid']):
        raise ValueError('Device visibility changed')
    metadata=witness.get('source_metadata',{})
    streams=metadata.get('streams',[]);info=metadata.get('format',{})
    if len(streams)!=1 or any(streams[0].get(key)!=report.get('source',{}).get(key)
                              for key in ('codec_name','pix_fmt','width','height')):
        raise ValueError('Metadata witness does not match the compared source')
    if int(info.get('size',-1))!=report.get('source_bytes') or float(info.get('duration',-1))!=report.get('duration_seconds'):
        raise ValueError('Source size or duration changed')
    pair=sdr_comparison_pair(report,info.get('format_name'))
    scope=qualified_scope(**pair)
    key=lambda item:(item['codec'],item['pixel_format'],tuple(item['hdr_modes']))
    if any(key(item)==key(scope) for item in receipt['scopes']):
        raise ValueError('Scope already exists; preserve or review it explicitly')
    updated=dict(receipt,scopes=[*receipt['scopes'],scope])
    proof=dict(evidence,pairs=[*evidence['pairs'],pair],sdr_source_witness=witness)
    payload=verified_receipt(updated,proof,binary)
    return payload,proof


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('base','report','witness','destination'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    binary=(args.base/'ffprobe-cuda').read_bytes()
    payload,evidence=extend(json.loads((args.base/'qualification.json').read_text()),
        json.loads((args.base/'evidence.json').read_text()),binary,json.loads(args.report.read_text()),
        json.loads(args.witness.read_text()))
    args.destination.mkdir(parents=True,exist_ok=False)
    # Artifact creation only. No native binary is executed on the local host.
    (args.destination/'ffprobe-cuda').write_bytes(binary)
    (args.destination/'qualification.json').write_bytes(payload)
    (args.destination/'evidence.json').write_text(json.dumps(evidence,indent=2))
    print('Private receipt bundle prepared; not installed or deployed')


if __name__=='__main__':main()
