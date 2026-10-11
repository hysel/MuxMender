"""Publish explicitly selected existing copies using the shared transaction."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time


def main():
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Publication runs inside the Linux app only')
    parser=argparse.ArgumentParser()
    parser.add_argument('--request',action='append',required=True)
    parser.add_argument('--output',type=Path,default=Path('/output'))
    parser.add_argument('--media',type=Path,default=Path('/media'))
    parser.add_argument('--confirm',action='store_true',required=True)
    args=parser.parse_args()
    if len(set(args.request))!=len(args.request) or any(not re.fullmatch('[a-f0-9]{32}',x) for x in args.request):
        raise ValueError('Unique exact request identifiers required')
    from autonomous_queue import write
    from job_tracking import tracked_call,progress
    from task_progress import digest
    from validated_replace import replace_validated
    root=args.output/'ui-requests'
    os.environ['MUXMENDER_VALIDATION_LOCK_ROOT']=str(args.output/'.validation-resources')
    def run():
        for index,identifier in enumerate(args.request,1):
            queue=json.loads((root/'requests.json').read_text())
            if any(j['state'] in ('running','pending') for j in queue['jobs']):
                raise RuntimeError('Finish or cancel queued work before publishing approved copies')
            job=next(j for j in queue['jobs'] if j['id']==identifier)
            folder=root/('request-'+identifier)
            runs=list(folder.glob('auto-*/status.json'))
            if len(runs)!=1:raise ValueError('Exactly one validated run required')
            result=runs[0].parent
            receipt_path=result/'approved-replacement.json'
            if receipt_path.exists():
                receipt=json.loads(receipt_path.read_text())
                if receipt.get('original_removed') is not True or digest(Path(receipt['target']))!=receipt['output_sha256']:
                    raise ValueError('Existing receipt needs manual review')
                continue
            if job['state']!='awaiting-playback' or job['settings']['mode']!='encode':
                raise ValueError('Only finished safe-copy requests can be approved')
            progress('Publishing approved copy',detail=f'Video {index} of {len(args.request)}; shared verification and cleanup')
            journal=result/'replacement.json'
            if journal.exists():
                record=json.loads(journal.read_text())
                if record.get('state')!='replaced' or digest(Path(record['target']))!=record['output_sha256']:
                    raise ValueError('Existing publication journal needs manual recovery')
            else:
                record=replace_validated(Path(job['source']),args.media,args.media,result,
                    job['settings']['minimum_savings'],identifier,
                    savings_mode=job['settings'].get('savings_mode','fixed'))
            write(receipt_path,dict(original_removed=True,old_bytes=record['original_bytes'],
                new_bytes=record['output_bytes'],saved_bytes=record['saved_bytes'],
                output_sha256=record['output_sha256'],target=record['target'],
                request_id=identifier,approved_at=time.time(),
                method='Shared verified replacement of existing safe copy',
                artifact_cleanup=record.get('artifact_cleanup')))
        return 0
    return tracked_call(run,'Approved safe-copy replacements',folder=args.output/'approved-copy-publication')


if __name__=='__main__':raise SystemExit(main())
