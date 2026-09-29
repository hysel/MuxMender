"""Optional native FEL research renderer; writes planar GBR16 to stdout.

Not an encoder, quality verdict, or replacement authorization. The parent must
verify layer/RPU/frame correspondence before invoking this worker and validate
its exit status and complete output. Dependencies are loaded only in the worker.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def rpu_records(path, *, guard=lambda: None, chunk_size=65536, max_record=8*1024*1024):
    """Stream dovi_tool's ordered, four-byte-start-code RPU binary unchanged.

    The export is already in display order. Do not split the original HEVC
    bitstream this way, remove emulation-prevention bytes, or reorder records.
    libdovi in the renderer remains responsible for validating each payload.
    """
    if type(chunk_size) is not int or chunk_size<1 or type(max_record) is not int or max_record<1:
        raise ValueError('Positive RPU buffer bounds required')
    prefix=b'\x00\x00\x00\x01';buffer=bytearray();started=False
    with Path(path).open('rb') as stream:
        while True:
            guard();part=stream.read(min(chunk_size,max_record+4))
            buffer.extend(part)
            if not started and len(buffer)>=4:
                if buffer[:4]!=prefix:raise ValueError('Missing exported RPU start code')
                del buffer[:4];started=True
            if started:
                while True:
                    end=buffer.find(prefix)
                    if end<0:break
                    if end==0 or end>max_record:raise ValueError('Empty or oversized RPU record')
                    yield bytes(buffer[:end]);del buffer[:end+4]
            if len(buffer)>max_record+3:raise ValueError('Oversized RPU record')
            if not part:break
    if not started or not buffer or len(buffer)>max_record:
        raise ValueError('Empty, truncated or oversized RPU export')
    yield bytes(buffer)


def exact_frame(pipe, size):
    if type(size) is not int or size<=0:raise ValueError('Invalid decoded frame size')
    data=bytearray()
    while len(data)<size:
        part=pipe.read(size-len(data))
        if not part:raise ValueError('Incomplete decoded FEL layer frame')
        data.extend(part)
    return data


def layout(width,height,subsampling):
    if any(type(v) is not int or v<=0 for v in (width,height)) or subsampling not in (0,1):
        raise ValueError('Invalid planar geometry')
    return [(width,height)]+[((width+(1<<subsampling)-1)>>subsampling,
                             (height+(1<<subsampling)-1)>>subsampling)]*2


def plane_bytes(plane,width,height):
    """Tightly pack a 16-bit plane; never serialize allocator row padding."""
    if plane.ndim!=2 or plane.shape!=(height,width) or plane.itemsize!=2:
        raise ValueError('Unexpected renderer plane layout')
    return plane.tobytes()


def frame_clip(core,vs,decoded,rpu):
    meta,data=decoded;w,h=meta['width'],meta['height']
    name=meta['pix_fmt']
    formats={f'yuv{chroma}p{bits}le':(getattr(vs,f'YUV{chroma}P{bits}'),sub)
             for chroma,sub in (('420',1),('444',0)) for bits in (10,12,16)}
    if name not in formats:raise ValueError('FelBaker input pixel format is unsupported: '+str(name))
    fmt,sub=formats[name]
    template=core.std.BlankClip(width=w,height=h,format=fmt,length=1)
    frame=template.get_frame(0).copy();offset=0
    for p,(pw,ph) in enumerate(layout(w,h,sub)):
        size=pw*ph*2;plane=frame[p]
        # VS planes expose two-dimensional native-endian unsigned shorts.
        # Assign rows separately when allocator stride includes padding.
        if plane.shape!=(ph,pw) or plane.itemsize!=2:raise ValueError('Unexpected input plane layout')
        if plane.c_contiguous:plane.cast('B')[:]=data[offset:offset+size]
        else:
            import ctypes
            address=frame.get_write_ptr(p).value
            for row in range(ph):
                ctypes.memmove(address+row*frame.get_stride(p),bytes(data[offset+row*pw*2:offset+(row+1)*pw*2]),pw*2)
        offset+=size
    if offset!=len(data):raise ValueError('Layer pixel byte count mismatch')
    frame.props['DolbyVisionRPU']=rpu
    frame.props['_Primaries']=9;frame.props['_Transfer']=16
    frame.props['_Matrix']=9;frame.props['_ColorRange']=1
    return core.std.ModifyFrame(template,clips=template,selector=lambda n,f:frame)


def decode_command(ffmpeg,path,pixel_format):
    # Bound decoder, filter, AND raw-video encoder pools independently.
    return [ffmpeg,'-v','error','-xerror','-nostdin','-filter_threads','1','-threads','2','-i',str(path),
            '-map','0:v:0','-fps_mode','passthrough','-pix_fmt',pixel_format,
            '-threads','1','-f','rawvideo','pipe:1']


def render(args):
    if sys.platform!='linux':raise RuntimeError('This optional FEL renderer requires the qualified Linux runtime')
    from dv_fel_runtime import validate_worker
    validate_worker(args.plugin)
    import vapoursynth as vs
    core=vs.core;core.num_threads=2;core.max_cache_size=128
    core.std.LoadPlugin(str(args.plugin.resolve(strict=True)))
    processes=[]
    try:
        streams=[]
        for path in (args.base,args.enhancement):
            metadata=json.loads(subprocess.check_output([args.ffprobe,'-v','error','-show_streams','-of','json',str(path)],timeout=30))
            moving=[s for s in metadata['streams'] if s.get('codec_type')=='video']
            if len(moving)!=1:raise ValueError('Expected one demuxed layer stream')
            meta=moving[0];fmt=meta.get('pix_fmt','')
            if fmt not in {f'yuv{c}p{b}le' for c in ('420','444') for b in (10,12,16)}:
                raise ValueError('FelBaker layer format is unsupported: '+fmt)
            size=sum(w*h*2 for w,h in layout(meta['width'],meta['height'],1 if fmt.startswith('yuv420') else 0))
            command=decode_command(args.ffmpeg,path,fmt)
            child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=sys.stderr)
            processes.append(child);streams.append((child,meta,size))
        frames=0
        for rpu in rpu_records(args.rpu):
            if frames>=args.frames:raise ValueError('More RPU records than verified frames')
            decoded=[(meta,exact_frame(child.stdout,size)) for child,meta,size in streams]
            node=core.fel.Bake(frame_clip(core,vs,decoded[0],rpu),frame_clip(core,vs,decoded[1],rpu),non_parallel=1,dovi_metadata=1)
            frame=node.get_frame(0);meta=streams[0][1]
            if (frame.width,frame.height,frame.format.name)!=(meta['width'],meta['height'],'RGB48'):
                raise ValueError('Reconstructed picture dimensions/format changed')
            for p in (1,2,0):sys.stdout.buffer.write(plane_bytes(frame[p],frame.width,frame.height))
            frames+=1;print('FEL_RENDER_FRAME='+str(frames),file=sys.stderr,flush=True)
            del frame,node,decoded
        if frames!=args.frames:raise ValueError('Incomplete RPU frame coverage')
        for child,meta,size in streams:
            if child.stdout.read(1):raise ValueError('More decoded layer frames than RPU records')
            if child.wait(timeout=30):raise RuntimeError('FEL layer decoder failed')
        sys.stdout.buffer.flush()
    finally:
        for child in processes:
            if child.poll() is None:child.kill()
            child.wait()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('base','enhancement','rpu','plugin'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--frames',type=int,required=True)
    parser.add_argument('--ffmpeg',default='ffmpeg');parser.add_argument('--ffprobe',default='ffprobe')
    args=parser.parse_args(argv)
    if args.frames<=0:parser.error('Positive verified frame count required')
    if sys.platform=='linux':
        import signal
        def cancel(signum,frame):raise SystemExit(143)
        # Let render's finally block reap layer decoders on parent cancellation.
        signal.signal(signal.SIGTERM,cancel)
    render(args)


if __name__=='__main__':main()
