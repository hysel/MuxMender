"""Extract HDR10+ through canonical HEVC bytes, without a raw-video disk copy."""
import json
from pathlib import Path
import re
import subprocess
import time

from job_tracking import progress


def extraction_commands(ffmpeg, tool, source, destination):
    return ([str(ffmpeg),'-hide_banner','-nostdin','-v','error','-i',str(source),
             '-map','0:V:0','-c','copy','-bsf:v','hevc_mp4toannexb',
             '-progress','pipe:2','-nostats','-f','hevc','pipe:1'],
            [str(tool),'extract','-o',str(destination),'-'])


def extract_metadata(ffmpeg, tool, source, destination, timeout, guard=lambda:None, duration=None, artifact_root=None):
    from artifact_manifest import command_outputs
    destination=Path(destination)
    _,command=extraction_commands(ffmpeg,tool,source,destination)
    # Register after both children have exited, including on cancellation.
    with command_outputs(artifact_root or destination.parent,command):
        return _extract_metadata(ffmpeg,tool,source,destination,timeout,guard,duration)


def _extract_metadata(ffmpeg, tool, source, destination, timeout, guard, duration):
    """Check both pipe exits and reap both children on cancellation or failure."""
    source,destination=map(Path,(source,destination))
    if destination.resolve()==source.resolve() or destination.exists() or destination.is_symlink():
        raise ValueError('HDR metadata needs a new, separate output')
    producer_command,consumer_command=extraction_commands(ffmpeg,tool,source,destination)
    producer=consumer=None
    started=last=time.monotonic()
    producer_log=destination.with_suffix('.extract-ffmpeg.log')
    consumer_log=destination.with_suffix('.extract-tool.log')
    try:
        with producer_log.open('xb') as errors,consumer_log.open('xb') as messages:
            guard()
            producer=subprocess.Popen(producer_command,stdout=subprocess.PIPE,stderr=errors)
            consumer=subprocess.Popen(consumer_command,stdin=producer.stdout,stdout=messages,stderr=messages)
            producer.stdout.close()
            while producer.poll() is None or consumer.poll() is None:
                guard()
                if time.monotonic()-started>timeout:
                    raise subprocess.TimeoutExpired(consumer_command,timeout)
                for process,label in ((consumer,'HDR metadata extractor'),(producer,'HEVC stream reader')):
                    if process.poll() not in (None,0):
                        raise RuntimeError(label+' failed; see '+str(consumer_log if process is consumer else producer_log))
                if time.monotonic()-last>=2:
                    last=time.monotonic()
                    with producer_log.open('rb') as log:
                        log.seek(max(0,producer_log.stat().st_size-8192));tail=log.read().decode('utf-8',errors='replace')
                    points=re.findall(r'^out_time_us=(-?\d+)$',tail,re.M)
                    seconds=max(0,int(points[-1])/1e6) if points else None
                    percent=min(99.9,100*seconds/duration) if seconds is not None and duration and duration>0 else None
                    progress('Extracting original HDR10+ metadata',stage_percent=percent,
                             detail='Streaming HEVC packets; no raw-video disk copy')
                time.sleep(.1)
            for process,label in ((consumer,'HDR metadata extractor'),(producer,'HEVC stream reader')):
                if process.wait(timeout=10):raise RuntimeError(label+' failed')
        guard()
        if not destination.is_file() or not destination.stat().st_size:
            raise ValueError('HDR metadata extraction produced no records')
        return destination
    finally:
        for process in (consumer,producer):
            if process is not None and process.poll() is None:process.kill()
        for process in (consumer,producer):
            if process is not None:
                process.wait(timeout=10)
                if process.stdout and not process.stdout.closed:process.stdout.close()


def scene_records(path):
    """Stream the tool's SceneInfo records without loading a movie into RAM."""
    decoder=json.JSONDecoder()
    with Path(path).open(encoding='utf-8') as stream:
        buffer='';started=False;need_value=True;seen=False
        while True:
            block=stream.read(65536);buffer+=block
            if not started:
                match=re.search(r'"SceneInfo"\s*:\s*\[',buffer)
                if match:
                    # The match must be a real root-object member, not text
                    # inside a nested string or an unrelated object.
                    prefix=json.loads(buffer[:match.start()]+'"SceneInfo":[]}')
                    if not isinstance(prefix,dict):raise ValueError('Invalid HDR metadata root')
                    buffer=buffer[match.end():];started=True
                elif not block or len(buffer)>65536:raise ValueError('Missing HDR SceneInfo array')
                else:continue
            while True:
                buffer=buffer.lstrip()
                if buffer.startswith(']'):
                    if need_value and seen:raise ValueError('Trailing HDR metadata separator')
                    # Validate the small summary/root suffix as well; a truncated
                    # extraction must not pass just because its array closed.
                    suffix=buffer[1:]
                    for tail in iter(lambda:stream.read(65536),''):
                        suffix+=tail
                        if len(suffix)>4*1024*1024:raise ValueError('HDR metadata summary exceeds memory budget')
                    root=json.loads('{"SceneInfo":[]'+suffix)
                    if not isinstance(root,dict):raise ValueError('Invalid HDR metadata document')
                    return
                if not need_value:
                    if not buffer:break
                    if not buffer.startswith(','):raise ValueError('Invalid HDR metadata separator')
                    buffer=buffer[1:].lstrip();need_value=True
                try:record,end=decoder.raw_decode(buffer)
                except json.JSONDecodeError:break
                if not isinstance(record,dict):raise ValueError('Invalid HDR scene record')
                yield record
                buffer=buffer[end:];need_value=False;seen=True
            if not block:raise ValueError('Truncated HDR metadata')
            if len(buffer)>4*1024*1024:raise ValueError('HDR metadata record exceeds memory budget')


def validate_coverage(path, required_frames, guard=lambda:None):
    if type(required_frames) is not int or required_frames<=0:raise ValueError('Positive source frame count required')
    count=0
    for index,record in enumerate(scene_records(path)):
        if index%4096==0:guard()
        value=record.get('SequenceFrameIndex')
        if type(value) is not int or value!=index:
            raise ValueError('HDR metadata frame coverage is missing, duplicated or reordered')
        count+=1
    if count<required_frames:
        raise ValueError(f'HDR metadata extraction incomplete: {count} records for {required_frames} decoded pictures')
    guard()
    return dict(decoded_frames=required_frames,metadata_records=count,decoded_frame_coverage_complete=True)


def prepare(workflow, source, frames, duration):
    """Extract once per immutable source reference, before spending encoder time."""
    from artifact_manifest import stamp
    from hdr10plus_preserve import frame_records
    from hdr10plus_validation import hdr_metadata
    count=0;dynamic=False
    for frame in frame_records(frames):
        if count%4096==0:workflow.guard()
        count+=1
        dynamic=dynamic or any('2094-40' in item.get('side_data_type','') or
                              'HDR10+' in item.get('side_data_type','') for item in hdr_metadata(frame))
    if not dynamic and workflow.hdr_mode!='hdr10plus':return None
    key=str(source.resolve());identities=(stamp(source),stamp(frames))
    cache=workflow.hdr_metadata_cache
    if key in cache:
        path,expected,metadata_stamp=cache[key]
        if expected!=identities or stamp(path)!=metadata_stamp:
            raise ValueError('HDR metadata reference changed before encoding')
        return path
    import uuid
    path=workflow.directory/('source-hdr10plus-'+uuid.uuid4().hex[:12]+'.json')
    extract_metadata(workflow.args.ffmpeg,'hdr10plus_tool',source,path,workflow.args.timeout,
                     workflow.guard,duration,workflow.directory)
    validate_coverage(path,count,workflow.guard)
    workflow.guard()
    if identities!=(stamp(source),stamp(frames)):
        raise ValueError('Original HDR reference changed during metadata extraction')
    cache[key]=(path,identities,stamp(path))
    return path
