"""Copy Matroska audio presentation packets, bypassing CLI clock rescaling.

This is a transport repair, never validation approval. The final output must
still pass complete packet, decoded audio, metadata and video quality checks.
"""
import argparse
from pathlib import Path
import sys


def decode_clock_plan(rows):
    """Minimum fixed decode-clock delay for a strictly increasing mux clock.

    Packet presentation timestamps and durations are never changed. Matroska
    audio stores presentation timestamps, not this internal decode ordering.
    """
    last=None;delay=0;count=0
    for pts,dts in rows:
        if type(pts) is not int or type(dts) is not int:
            raise ValueError('Audio relay requires complete integer packet clocks')
        last=max(dts,last+1) if last is not None else dts
        delay=max(delay,last-pts);count+=1
    if not count:raise ValueError('Empty audio packet clock evidence')
    return delay+1,count


def relay(source,output,guard=lambda:None,notify=lambda count:None):
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Native audio relay qualification is Linux-only')
    import av
    source=Path(source).resolve(strict=True);output=Path(output)
    if output.exists() or output.is_symlink() or source==output.resolve():
        raise ValueError('Audio relay requires a new, distinct output')
    guard()
    original=source.stat()
    identity=(original.st_dev,original.st_ino,original.st_size,original.st_mtime_ns)
    clocks={};counts={};last={};bases={};codecs={}
    with av.open(str(source)) as container:
        if 'matroska' not in container.format.name:
            raise ValueError('Audio relay requires a Matroska source')
        streams=list(container.streams.audio)
        if not streams:raise ValueError('No audio streams to relay')
        for stream in streams:
            bases[stream.index]=stream.time_base
            codecs[stream.index]=stream.codec_context.name
        for packet in container.demux(*streams):
            if not packet.size:continue
            index=packet.stream.index
            if type(packet.pts) is not int or type(packet.dts) is not int:
                raise ValueError('Audio relay requires complete integer packet clocks')
            if packet.time_base!=bases[index]:raise ValueError('Packet time base changed')
            clock=max(packet.dts,last[index]+1) if index in last else packet.dts
            last[index]=clock;clocks[index]=max(clocks.get(index,0),clock-packet.pts)
            counts[index]=counts.get(index,0)+1
            if sum(counts.values())%4096==0:guard();notify(sum(counts.values()))
    if set(counts)!=set(bases):raise ValueError('Empty audio track in relay')
    delays={index:value+1 for index,value in clocks.items()}
    previous={};copied={};total=0
    # O_EXCL prevents PyAV from truncating a file created by another worker.
    with output.open('xb') as handle, av.open(str(source)) as input_container, \
            av.open(handle,'w',format='matroska',options={'avoid_negative_ts':'disabled'}) as output_container:
        streams=list(input_container.streams.audio)
        if {s.index:s.time_base for s in streams}!=bases:
            raise ValueError('Audio inventory changed during relay')
        mapping={s.index:output_container.add_stream_from_template(s,opaque=True) for s in streams}
        for packet in input_container.demux(*streams):
            if not packet.size:continue
            index=packet.stream.index;presentation=packet.pts
            if type(presentation) is not int or type(packet.dts) is not int:
                raise ValueError('Unresolved audio packet clocks')
            if packet.time_base!=bases[index]:raise ValueError('Packet time base changed')
            clock=packet.dts-delays[index]
            if index in previous:clock=max(clock,previous[index]+1)
            if clock>presentation:raise ValueError('Internal decode clock exceeds presentation')
            previous[index]=clock
            packet.dts=clock;packet.pts=presentation;packet.stream=mapping[index]
            output_container.mux(packet)
            copied[index]=copied.get(index,0)+1;total+=1
            if total%4096==0:guard();notify(sum(counts.values())+total)
    guard()
    current=source.stat()
    if identity!=(current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns):
        raise ValueError('Source changed during audio relay')
    if copied!=counts:raise ValueError('Audio packet inventory changed during relay')
    notify(2*total)
    return dict(packets=total,tracks=len(counts),codecs=codecs,pyav=av.__version__,
                presentation_timestamps_untouched=True,validation_required=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    from job_tracking import progress
    progress('Preserving original audio packet timestamps',detail='Transport repair; full validation still required')
    def notify(count):
        progress('Preserving original audio packet timestamps',completed=count,
                 detail='Audio packets inspected or copied; full validation still required')
        print('MUXMENDER_ACTIVITY='+str(count),flush=True)
    result=relay(args.source,args.output,notify=notify)
    import json
    print(json.dumps(result))


if __name__=='__main__':main()
