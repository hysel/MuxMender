"""Preserve explicit MP4 AAC decoder priming in a separate Matroska copy."""
import json
import shutil
from fractions import Fraction
from task_progress import run_probe

def priming_tracks(data, packets):
    first={}
    for p in packets:first.setdefault(p['stream_index'],p)
    result={}
    for s in data['streams']:
        if s.get('codec_name')!='aac' or s.get('codec_type')!='audio':continue
        p=first.get(s['index'],{})
        for side in p.get('side_data_list',[]):
            if side.get('side_data_type')!='Skip Samples':continue
            skip=int(side.get('skip_samples',0));discard=int(side.get('discard_padding',0))
            if not skip:continue
            rate=int(s['sample_rate'])
            if discard or rate<=0 or not 0<skip<=rate:raise ValueError('Unsupported AAC priming evidence')
            delay=Fraction(skip,rate)
            if abs(Fraction(p['pts_time'])+delay)>Fraction(1,rate):raise ValueError('AAC priming does not match initial timestamp')
            result[s['index']]=dict(samples=skip,rate=rate,seconds=delay)
    return result

def inspect(workflow, source, before, label):
    if not {'mov','mp4','m4a'}.intersection(before.get('format',{}).get('format_name','').split(',')):return {}
    if not any(s.get('codec_name')=='aac' for s in before['streams']):return {}
    path=workflow.directory/(label+'-aac-priming.json')
    run_probe([workflow.args.ffprobe,'-v','error','-read_intervals','%+1','-select_streams','a',
        '-show_packets','-show_entries','packet=stream_index,pts_time:packet_side_data','-of','json',str(source)],
        path,'Inspecting AAC priming',workflow.args.timeout,workflow.guard)
    tracks=priming_tracks(before,json.loads(path.read_text())['packets'])
    if tracks and not shutil.which('mkvpropedit'):raise ValueError('AAC priming preservation requires mkvpropedit')
    return tracks

def finalize(workflow, source, encoded, output, before, tracks, label, duration):
    # Compensate the container CodecDelay so playback timestamps remain anchored
    # to the source. Audio packet bytes are copied, not decoded/re-encoded here.
    if output.resolve() in (source.resolve(),encoded.resolve()) or output.exists():
        raise ValueError('AAC finalization requires a new, separate output')
    command=[workflow.args.ffmpeg,'-v','error','-nostdin','-n','-copyts','-i',str(encoded)]
    inputs={}
    for index,t in tracks.items():
        inputs[index]=len(inputs)+1
        command+=['-itsoffset',format(float(t['seconds']),'.12f'),'-i',str(source)]
    for s in before['streams']:
        index=s['index'];command+=['-map',f'{inputs[index]}:{index}' if index in inputs else f'0:{index}']
    command+=['-c','copy','-map_metadata','0','-map_chapters','0','-avoid_negative_ts','disabled']
    for i,s in enumerate(before['streams']):
        command += [f'-map_metadata:s:{i}',f'0:s:{i}',f'-disposition:{i}',
                    '+'.join(k for k,v in s.get('disposition',{}).items() if v) or '0']
    command+=['-progress','pipe:1','-nostats',str(output)]
    if any(s.get('disposition',{}).get('attached_pic') for s in before['streams']):
        command=workflow.preserve_covers(command,encoded,workflow.probe(encoded),label+'-aac')
    workflow.execute(command,label+'-aac-copy',duration)
    edit=['mkvpropedit',str(output)];audio=0
    for s in before['streams']:
        if s['codec_type']=='audio':audio+=1
        if s['index'] in tracks:
            delay=round(tracks[s['index']]['seconds']*1000000000)
            edit+=['--edit',f'track:a{audio}','--set',f'codec-delay={delay}']
    workflow.execute(edit,label+'-aac-codec-delay',duration)
