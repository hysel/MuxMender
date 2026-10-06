"""Linux-only AV1 GPU reader controls; never approve conversion or replacement."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import struct
import sys
import time
import statistics


def corrupt_variants(payload):
    from av1_content_light import obus
    frames=[];offset=0
    for kind,raw,body in obus(payload):
        end=offset+len(raw)
        if kind in (4,6) and len(body)>256:frames.append((end-len(body),end))
        offset=end
    if len(frames)<3:raise ValueError('Generated AV1 fixture lacks bounded frame payloads')
    variants={}
    for label,index in [('early',0),('middle',len(frames)//2),('late',len(frames)-1)]:
        begin,end=frames[index]
        for part,position in [('header',begin+8),('entropy',begin+(end-begin)*3//4)]:
            data=bytearray(payload);stop=min(end,position+128)
            data[position:stop]=b'\xff'*(stop-position);variants[label+'-'+part]=bytes(data)
    begin,end=frames[-1];variants['truncated']=payload[:begin+(end-begin)//2]
    return variants


def static_metadata_packet(packet):
    """Generated fixture only: copy picture OBUs and add declared HDR test data."""
    from av1_content_light import obus,patch_packet
    packet,_=patch_packet(packet,struct.pack('>HH',1000,400))
    payload=b'\x02'+struct.pack('>8H2I',34000,16000,13250,34500,7500,3000,15635,16450,10000000,1)+b'\x80'
    metadata=b'\x2a'+bytes([len(payload)])+payload
    output=bytearray();inserted=False
    for kind,raw,body in obus(packet):
        if kind in (3,6) and not inserted:output.extend(metadata);inserted=True
        output.extend(raw)
    if not inserted:raise ValueError('Generated IVF packet lacks a frame header')
    return bytes(output)


def static_metadata_ivf(source,destination):
    with source.open('rb') as reader,destination.open('xb') as writer:
        header=reader.read(32)
        if len(header)!=32 or header[:4]!=b'DKIF' or header[8:12]!=b'AV01':raise ValueError('Expected generated AV1 IVF')
        writer.write(header)
        while True:
            frame=reader.read(12)
            if not frame:break
            if len(frame)!=12:raise ValueError('Truncated generated IVF record')
            size=struct.unpack('<I',frame[:4])[0]
            if not 0<size<=64*1024*1024:raise ValueError('Invalid generated IVF packet size')
            packet=reader.read(size)
            if len(packet)!=size:raise ValueError('Truncated generated IVF packet')
            patched=static_metadata_packet(packet)
            writer.write(struct.pack('<I',len(patched))+frame[4:]+patched)


def main():
    if not sys.platform.startswith('linux'):raise RuntimeError('AV1 native research runs on Linux only')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--performance',action='store_true',help='Measure alternating full reads of a generated 30-second 4K clip')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    from job_tracking import Job
    from benchmark_native_hdr_reader import probe
    from hdr10plus_preserve import frame_records
    from hdr10plus_validation import validate_frames
    job=Job(args.output/'reports','AV1 GPU reader · generated PQ control')
    report=dict(binary_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),codec_name='av1',
        production_enabled=False,quality_approved=False,replacement_authorized=False,
        scope='Generated 10-bit PQ control only; no static/dynamic HDR or malformed-input certification')
    fixture=args.output/'generated-pq-av1.mkv'
    owned=[fixture]
    try:
        job.save(phase='Generating AV1 control on assigned NVIDIA GPU',stage_percent=None)
        result=subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-filter_threads','2',
            '-f','lavfi','-i','testsrc2=size=1280x720:rate=24:duration=2,format=yuv420p10le,setparams=range=limited:color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc',
            '-c:v','av1_nvenc','-preset','p4','-cq','24','-pix_fmt','yuv420p10le',
            '-color_primaries','bt2020','-color_trc','smpte2084','-colorspace','bt2020nc',
            '-color_range','tv',str(fixture)],capture_output=True,text=True,timeout=60)
        if result.returncode:raise ValueError('Generated AV1 encoding failed: '+result.stderr[-1500:])
        results={}
        for mode in ('cpu','cuda'):
            job.save(phase='AV1 native JSON: '+mode,stage_percent=None)
            results[mode]=probe('ffprobe' if mode=='cpu' else args.binary,fixture,args.output/(mode+'.json'),mode=='cuda')
        report['readers']=results
        if not results['cpu']['strict_success']:raise ValueError('Installed CPU rejected generated AV1 control')
        if not results['cuda']['strict_success']:
            raise ValueError('GPU AV1 clean decode not confirmed: '+results['cuda']['error'])
        proof=validate_frames(frame_records(args.output/'cpu.json'),frame_records(args.output/'cuda.json'),'pq')
        if proof['frames']!=48:raise ValueError('Generated AV1 frame count changed')
        report['metadata_proof']=proof
        report['control_passed']=True
        raw=args.output/'generated-av1.obu';owned.append(raw)
        subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-i',str(fixture),'-map','0:v:0','-c','copy','-f','obu',str(raw)],check=True,capture_output=True,timeout=30)
        for mode in ('cpu','cuda'):
            target=args.output/('raw-healthy-'+mode+'.json')
            healthy=probe('ffprobe' if mode=='cpu' else args.binary,raw,target,mode=='cuda')
            if not healthy['strict_success'] or len(list(frame_records(target)))!=48:
                raise ValueError('Raw AV1 healthy control failed: '+mode+' '+healthy['error'])
        report['corruption']=[];false_passes=[];cpu_rejections=0
        for name,data in corrupt_variants(raw.read_bytes()).items():
            damaged=args.output/(name+'.obu');owned.append(damaged);damaged.write_bytes(data)
            job.save(phase='Testing malformed AV1: '+name,stage_percent=None)
            readers={mode:probe('ffprobe' if mode=='cpu' else args.binary,damaged,args.output/(name+'-'+mode+'.json'),mode=='cuda') for mode in ('cpu','cuda')}
            report['corruption'].append(dict(case=name,**readers))
            if not readers['cpu']['strict_success']:
                cpu_rejections+=1
                if readers['cuda']['strict_success']:false_passes.append(name)
        report['cpu_corruption_rejections']=cpu_rejections
        report['false_passes']=false_passes
        report['corruption_qualified']=cpu_rejections>0 and not false_passes
        ivf=args.output/'generated.ivf';static_ivf=args.output/'generated-static.ivf';static_mkv=args.output/'generated-static.mkv'
        owned.extend([ivf,static_ivf,static_mkv])
        job.save(phase='Building generated static HDR AV1 fixture',stage_percent=None)
        subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-i',str(fixture),'-map','0:v:0','-c','copy','-f','ivf',str(ivf)],check=True,capture_output=True,timeout=30)
        static_metadata_ivf(ivf,static_ivf)
        subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-i',str(static_ivf),'-map','0:v:0','-c','copy',str(static_mkv)],check=True,capture_output=True,timeout=30)
        for mode in ('cpu','cuda'):
            target=args.output/('static-'+mode+'.json')
            job.save(phase='Static HDR AV1 JSON: '+mode,stage_percent=None)
            result=probe('ffprobe' if mode=='cpu' else args.binary,static_mkv,target,mode=='cuda')
            if not result['strict_success']:raise ValueError('Generated static HDR AV1 reader failed: '+mode+' '+result['error'])
        report['static_hdr_proof']=validate_frames(frame_records(args.output/'static-cpu.json'),frame_records(args.output/'static-cuda.json'),'hdr10')
        if report['static_hdr_proof']['frames']!=48:raise ValueError('Static HDR fixture frame count changed')
        report['scope']='Generated 10-bit PQ, static HDR and malformed inputs only; no dynamic HDR or full-file certification'
        if args.performance:
            performance=args.output/'generated-4k-performance.mkv';owned.append(performance)
            job.save(phase='Generating 30-second 4K AV1 benchmark',stage_percent=None)
            subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-filter_threads','2',
                '-f','lavfi','-i','testsrc2=size=3840x2160:rate=24:duration=30,format=yuv420p10le,setparams=range=limited:color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc',
                '-c:v','av1_nvenc','-preset','p4','-cq','24','-pix_fmt','yuv420p10le',
                '-color_primaries','bt2020','-color_trc','smpte2084','-colorspace','bt2020nc','-color_range','tv',
                str(performance)],check=True,capture_output=True,timeout=180)
            report['performance']=[]
            for trial in range(3):
                for mode in (('cpu','cuda') if trial%2==0 else ('cuda','cpu')):
                    target=args.output/f'performance-{trial}-{mode}.json'
                    job.save(phase='4K AV1 inspection: '+mode,stage_percent=None)
                    result=probe('ffprobe' if mode=='cpu' else args.binary,performance,target,mode=='cuda',
                        heartbeat=lambda elapsed,path:job.save(detail=f'{elapsed:.0f}s reading generated 4K AV1 metadata'))
                    report['performance'].append(dict(round=trial,mode=mode,**result))
                    if not result['strict_success']:raise ValueError('4K AV1 reader failed: '+mode+' '+result['error'])
                proof=validate_frames(frame_records(args.output/f'performance-{trial}-cpu.json'),
                    frame_records(args.output/f'performance-{trial}-cuda.json'),'pq')
                if proof['frames']!=720:raise ValueError('Generated 4K AV1 frame count changed')
                report['performance_metadata_proof']=proof
            report['performance_medians']={mode:statistics.median(r['seconds'] for r in report['performance'] if r['mode']==mode) for mode in ('cpu','cuda')}
            report['performance_time_reduction_percent']=100*(1-report['performance_medians']['cuda']/report['performance_medians']['cpu'])
            report['scope']+='; three full reads per backend of a generated 30-second 4K clip'
        job.save(state='completed' if report['corruption_qualified'] else 'failed',phase='AV1 bounded tests passed' if report['corruption_qualified'] else 'AV1 corruption detection needs investigation',detail=json.dumps(report),finished=time.time())
        return 0 if report['corruption_qualified'] else 1
    except Exception as exc:
        report['error']=str(exc);report['control_passed']=False
        job.save(state='failed',phase='AV1 reader needs investigation',detail=json.dumps(report),error=str(exc),finished=time.time())
        return 1
    finally:
        (args.output/'benchmark.json').write_text(json.dumps(report,indent=2))
        for path in owned:
            if path.parent.resolve()==args.output.resolve() and path.is_file() and not path.is_symlink():path.unlink()


if __name__=='__main__':raise SystemExit(main())
