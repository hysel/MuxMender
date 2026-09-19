"""Read-only batch control room, served separately from the existing dashboard."""
import argparse
import json
import time
import hashlib
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from dashboard import Catalog, make_handler, contained
from ui.batch import HTML
REVIEW_LOCK=threading.Lock()

def review_key(source, output):
    return hashlib.sha256(json.dumps([source,output]).encode()).hexdigest()

def save_review(roots, request):
    with REVIEW_LOCK:
        batch=next((b for b in batches(roots) if b['id']==request.get('batch')),None)
        if batch is None:raise ValueError('Unknown batch')
        row=next((r for r in batch['episodes'] if r['review_id']==request.get('episode')),None)
        if row is None:raise ValueError('Unknown episode')
        client=request.get('client');status=request.get('status');note=request.get('note','')
        if client not in ('Chrome','Sony TV','Plex') or status not in ('Passed','Failed','Not tested'):
            raise ValueError('Invalid playback review')
        if not isinstance(note,str) or len(note)>1000:raise ValueError('Note too long')
        path=Path(batch['id']).parent/'playback-reviews.json'
        root=next(r for r in roots if contained(path,r))
        if path.is_symlink():raise ValueError('Linked review file rejected')
        previous=read(path,root)
        data=previous if isinstance(previous,dict) else {}
        data.setdefault(row['review_id'],{})[client]=dict(status=status,note=note,updated=time.time(),reported_by='user')
        temporary=path.with_name('playback-reviews.'+hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:12]+'.tmp')
        with temporary.open('x',encoding='utf-8') as f:json.dump(data,f,indent=2)
        temporary.replace(path)
        return {'saved':True}


def read(path, root):
    try:
        if not contained(path, root) or path.stat().st_size > 4*1024**2:
            return None
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return None


def batches(roots):
    result=[]
    for root in roots:
        # Bounded discovery: top-level runs and one nested batch run level.
        candidates=sorted(set(root.glob('*/status.json'))|set(root.glob('*/*/status.json')))
        for path in candidates[:1000]:
            payload=read(path,root)
            rows=payload if isinstance(payload,list) else payload.get('entries',[]) if isinstance(payload,dict) else []
            if not rows or not isinstance(rows,list):continue
            reviews=read(path.parent/'playback-reviews.json',root)
            reviews=reviews if isinstance(reviews,dict) else {}
            entries=[]
            for row in rows[:1000]:
                if not isinstance(row,dict) or not row.get('source'):continue
                source=Path(row['source'])
                output=Path(row['output']) if row.get('output') else None
                report=read(output.parent/'result.json',root) if output else None
                receipt=read(output.with_suffix('.receipt.json'),root) if output else None
                evidence=report if isinstance(report,dict) else receipt if isinstance(receipt,dict) else {}
                old=evidence.get('source_bytes',row.get('fingerprint',{}).get('size'))
                new=evidence.get('output_bytes',row.get('output_bytes'))
                saving=evidence.get('saved_percent',row.get('saved_percent'))
                state=row.get('state',row.get('action','unknown'))
                key=review_key(str(source),str(output) if output else None)
                review=reviews.get(key,{})
                entries.append(dict(episode=row.get('episode',source.stem),state=state,
                    original_bytes=old,output_bytes=new,saved_percent=saving,
                    verification='Passed' if state in ('verified_pending_playback','verified-awaiting-playback','resumed-verified') else 'Failed' if 'fail' in state else 'Pending',
                    review_id=key,reviews=review,
                    playback=' · '.join(client+': '+value['status'] for client,value in review.items()) or 'Not recorded',error=row.get('error',row.get('reason','')),
                    source=str(source),output=str(output) if output else None))
            if entries:result.append(dict(id=str(path),name=path.parent.name,updated=path.stat().st_mtime,episodes=entries))
    return sorted(result,key=lambda x:x['updated'],reverse=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--artifact-root',type=Path,action='append',required=True)
    parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    roots=[p.resolve() for p in args.artifact_root]
    server=ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(Catalog(args.root,roots),page=HTML,batch_provider=lambda:batches(roots),review_writer=lambda data:save_review(roots,data)))
    print(f'Batch dashboard: http://127.0.0.1:{args.port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
