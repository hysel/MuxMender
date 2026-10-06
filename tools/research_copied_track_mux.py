"""Read-only-source Linux diagnosis of copied Matroska audio timestamps."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main(root, passthrough=False, complete=False, only_case=None, original_clock=False, decode_clock=False, retain_lacing=False, direct_packets=False, assembly=False, shared=False):
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Native media research runs on Linux only')
    from job_tracking import Job
    from packet_validation import collect_packets,packet_rows
    from itertools import zip_longest
    os.nice(19)
    root=Path(root)
    job=Job(root/'reports','Copied audio mux timestamp diagnosis')
    created=[]
    results=[]
    last_heartbeat=0
    def heartbeat():
        nonlocal last_heartbeat
        now=time.monotonic()
        if now-last_heartbeat>=10:
            job.save()
            last_heartbeat=now
    def collect(path,label,indices):
        # Register owned paths before launching the reader, including partial
        # evidence left by a timeout. Never clean files outside this job root.
        for index in indices:
            target=root/(label+f'-stream-{index}.txt')
            created.extend((target,target.with_suffix(target.suffix+'.stderr')))
        return collect_packets('ffprobe',path,root,label,indices,600,heartbeat,7200)
    def probe(path):
        command=['ffprobe','-v','error','-select_streams','a','-read_intervals','%+12',
                 '-show_packets','-show_data_hash','sha256','-show_streams','-of','json',str(path)]
        return json.loads(subprocess.check_output(command,text=True,timeout=60))
    def copied_probe(path):
        command=['ffprobe','-v','error','-show_streams','-show_chapters','-show_format',
                 '-show_data_hash','sha256','-of','json',str(path)]
        return json.loads(subprocess.check_output(command,text=True,timeout=60))
    def verify_other_tracks(source,output,number):
        from media_metadata import canonical_chapters,canonical_tags,equivalent_stream_language
        left=copied_probe(source);right=copied_probe(output)
        a=[s for s in left['streams'] if s['codec_type']!='video']
        b=right['streams']
        if len(a)!=len(b):raise ValueError('Non-video track inventory changed')
        for x,y in zip(a,b):
            for key in ('codec_type','codec_name','disposition','sample_rate','channels','channel_layout','extradata_hash'):
                if x.get(key)!=y.get(key):raise ValueError('Copied stream metadata changed: '+key)
            for key in ('language','title','filename','mimetype'):
                xt=canonical_tags(x.get('tags',{}));yt=canonical_tags(y.get('tags',{}))
                equal=equivalent_stream_language(xt.get(key),yt.get(key)) if key=='language' else xt.get(key)==yt.get(key)
                if not equal:raise ValueError('Copied stream tag changed: '+key)
            if x['codec_type']=='subtitle':
                xp=collect(source,f'case-{number}-subtitle-source',[x['index']])[x['index']]
                yp=collect(output,f'case-{number}-subtitle-output',[y['index']])[y['index']]
                count=0
                for p,q in zip_longest(packet_rows(xp),packet_rows(yp)):
                    count+=1;heartbeat()
                    if p is None or q is None or any(p.get(k)!=q.get(k) for k in
                            ('pts_time','dts_time','duration_time','data_hash')):
                        raise ValueError('Subtitle packet bytes or clock changed')
                if not count:raise ValueError('Empty subtitle packet evidence')
        if canonical_chapters(left.get('chapters',[]))!=canonical_chapters(right.get('chapters',[])):
            raise ValueError('Chapter metadata changed')
        return dict(non_video_tracks=len(a),subtitle_packets_exact=True,metadata_and_chapters_equal=True)
    try:
        state=json.loads(Path('/output/ui-requests/requests.json').read_text())
        for number,identifier in enumerate(('2dc99ebad7aa4c87a2104dc24282dea9',
                                            '8e26c17d027541ebb7634387e659589c')):
            if only_case is not None and number!=only_case:continue
            request=next(j for j in state['jobs'] if j['id']==identifier)
            source=Path(request['source']).resolve(strict=True)
            if not source.is_relative_to('/media'):
                raise ValueError('Source outside read-only mount')
            def identity():
                value=source.stat()
                return (value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
            original_identity=identity()
            before=probe(source)
            output=root/('case-'+str(number)+'.mka')
            if output.exists():raise ValueError('Research output already exists')
            created.append(output)
            job.save(phase='Remuxing original audio without GPU',completed=number,total=2)
            extra=['--engage','force_passthrough_packetizer','--timestamp-scale','1000000'] if passthrough else []
            input_options=[]
            source_evidence=None
            if original_clock:
                from decimal import Decimal
                identified=json.loads(subprocess.check_output(['mkvmerge','-J',str(source)],text=True,timeout=60))
                ids=[t['id'] for t in identified['tracks'] if t['type']=='audio']
                if len(ids)!=len(before['streams']):raise ValueError('Audio inventory changed')
                source_evidence=collect(source,f'case-{number}-original',
                    [t['index'] for t in before['streams']])
                created.extend(source_evidence.values())
                for stream,track in zip(before['streams'],ids):
                    clock=root/f'case-{number}-track-{track}-timestamps.txt'
                    created.append(clock)
                    with clock.open('x') as handle:
                        handle.write('# timestamp format v4\n')
                        for packet in packet_rows(source_evidence[stream['index']]):
                            pts=Decimal(packet['pts_time'])
                            if not pts.is_finite():raise ValueError('Unavailable original packet clock')
                            handle.write(format(pts*1000,'f')+'\n')
                    input_options+=['--timestamps',str(track)+':'+str(clock)]
            command=['mkvmerge',*extra,'-o',str(output),'--disable-lacing','--no-video',
                     '--no-subtitles','--no-attachments',*input_options,str(source)]
            if retain_lacing:command.remove('--disable-lacing')
            if decode_clock:
                if number!=0:raise ValueError('DTS relay research is limited to the diagnosed DTS case')
                command=['ffmpeg','-hide_banner','-nostdin','-n','-v','error','-xerror','-copyts',
                         '-i',str(source),'-map','0:a','-c:a','copy','-bsf:a',
                         'setts=pts=PTS:dts=if(eq(N\\,0)\\,DTS-0.1/TB\\,max(DTS-0.1/TB\\,PREV_OUTDTS+1)):duration=DURATION',
                         '-avoid_negative_ts','disabled','-f','matroska',str(output)]
            (root/f'case-{number}-command.json').write_text(json.dumps(command,indent=2))
            if direct_packets:
                import av
                from fractions import Fraction
                if number!=0:raise ValueError('Direct relay is limited to the diagnosed DTS case')
                source_evidence=collect(source,f'case-{number}-original',
                    [t['index'] for t in before['streams']])
                created.extend(source_evidence.values())
                delays={}
                for stream in before['streams']:
                    tick=Fraction(stream['time_base']);last=None;delay=0
                    for packet in packet_rows(source_evidence[stream['index']]):
                        heartbeat()
                        dts=Fraction(packet['dts_time'])/tick;pts=Fraction(packet['pts_time'])/tick
                        if dts.denominator!=1 or pts.denominator!=1:raise ValueError('Nonintegral packet clock')
                        clock=max(int(dts),last+1) if last is not None else int(dts)
                        delay=max(delay,clock-int(pts));last=clock
                    delays[stream['index']]=delay+1
                count=0;previous={}
                job.save(phase='Copying exact audio packets through direct container API')
                from copied_audio_relay import relay
                receipt=relay(source,output,heartbeat,
                    lambda count:job.save(phase='Shared exact audio relay',completed=count))
                (root/f'case-{number}-shared-relay.json').write_text(json.dumps(receipt))
            else:
                run=subprocess.run(command,
                                   text=True,capture_output=True,timeout=300)
                (root/f'case-{number}-mux.log').write_text(run.stdout+run.stderr)
                if run.returncode not in (0,1):raise RuntimeError(run.stderr[-1500:])
            if assembly:
                if not direct_packets:raise ValueError('Assembly qualification requires the exact packet relay')
                relay=output
                output=root/f'case-{number}-assembled.mka'
                if output.exists():raise ValueError('Assembly output already exists')
                created.append(output)
                job.save(phase='Checking final mux assembly with original subtitles and metadata')
                identified=json.loads(subprocess.check_output(['mkvmerge','-J',str(source)],text=True,timeout=60))
                relayed=json.loads(subprocess.check_output(['mkvmerge','-J',str(relay)],text=True,timeout=60))
                audio=iter(t['id'] for t in relayed['tracks'])
                order=','.join('1:'+str(next(audio)) if t['type']=='audio' else '0:'+str(t['id'])
                               for t in identified['tracks'] if t['type']!='video')
                from matroska_audio_recovery import relay_input_options
                command=['mkvmerge','--engage','force_passthrough_packetizer',
                         '--timestamp-scale','1000000','--track-order',order,'-o',str(output),'--disable-lacing',
                         '--no-video','--no-audio',str(source),'--no-video','--no-subtitles',
                         '--no-attachments','--no-chapters','--no-global-tags',
                         *relay_input_options(identified,relayed),str(relay)]
                run=subprocess.run(command,text=True,capture_output=True,timeout=300)
                (root/f'case-{number}-assembly.log').write_text(run.stdout+run.stderr)
                if run.returncode not in (0,1):raise RuntimeError(run.stderr[-1500:])
            after=probe(output)
            if len(before['streams'])!=len(after['streams']):raise ValueError('Audio stream count changed')
            if any(a['codec_name']!=b['codec_name'] for a,b in zip(before['streams'],after['streams'])):
                raise ValueError('Audio codec inventory changed')
            mismatches=[]
            for a,b in zip(before['streams'],after['streams']):
                left=[p for p in before['packets'] if p['stream_index']==a['index']]
                right=[p for p in after['packets'] if p['stream_index']==b['index']]
                diffs=[]
                for index,(x,y) in enumerate(zip(left,right)):
                    changed={k:[x.get(k),y.get(k)] for k in
                             ('pts_time','dts_time','duration_time','size','data_hash')
                             if x.get(k)!=y.get(k)}
                    if changed:
                        diffs.append(dict(packet=index,changed=changed))
                        if len(diffs)==5:break
                mismatches.append(dict(source_track=a['index'],codec=a['codec_name'],
                    source_packets=len(left),output_packets=len(right),first_differences=diffs))
            if complete:
                job.save(phase='Checking all copied audio packet bytes and timestamps',completed=number,total=2)
                for side,path,data in (('source',source,before),('output',output,after)):
                    evidence=source_evidence if side=='source' and source_evidence else collect(path,f'case-{number}-{side}',
                        [t['index'] for t in data['streams']])
                    if side=='source':source_evidence=evidence
                    else:output_evidence=evidence
                    created.extend(evidence.values())
                for position,(a,b) in enumerate(zip(before['streams'],after['streams'])):
                    count=0
                    for x,y in zip_longest(packet_rows(source_evidence[a['index']]),
                                         packet_rows(output_evidence[b['index']])):
                        count+=1
                        if count%4096==0:heartbeat()
                        if x is None or y is None:raise ValueError(f'Case {number} track {position}: complete packet count changed')
                        for key in ('pts_time','dts_time','duration_time','data_hash'):
                            if x.get(key)!=y.get(key):
                                mismatch=dict(case=number,track=position,packet=count,field=key,
                                              source=x.get(key),output=y.get(key))
                                (root/'mismatch.json').write_text(json.dumps(mismatch,indent=2))
                                raise ValueError('Complete packet comparison failed: '+json.dumps(mismatch))
                    if count<=0:raise ValueError('Empty complete packet evidence')
                    mismatches[position]['complete_packets_exact']=count
            if identity()!=original_identity:raise ValueError('Source identity changed during research')
            results.append(dict(case=number,tracks=mismatches,source_stat_unchanged=True,
                                scope='All audio packets exact; no full video/quality or replacement approval' if complete else
                                      'First twelve seconds of full audio-only remux; no replacement approval'))
            if assembly:results[-1]['non_video_preservation']=verify_other_tracks(source,output,number)
            output.unlink()
        report=dict(results=results,passthrough=passthrough,complete=complete,original_clock=original_clock,
                    decode_clock=decode_clock,direct_packets=direct_packets,assembly=assembly,publication_authorized=False)
        (root/'result.json').write_text(json.dumps(report,indent=2))
        job.save(state='completed',phase='Copied track diagnosis complete',detail=json.dumps(report),finished=time.time())
        print('MUX_RESULT='+json.dumps(report),flush=True)
    except BaseException as exc:
        job.save(state='failed',phase='Copied track diagnosis needs inspection',error=str(exc),finished=time.time())
        raise
    finally:
        for path in created:
            if path.is_file() and not path.is_symlink():path.unlink()


if __name__=='__main__':main(Path(sys.argv[1]))
