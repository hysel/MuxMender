"""Read-only media validation of a retained full-file Web UI conversion.

Writes a new dashboard job/report, never overwrites historical validation.
"""
import argparse
import json
from pathlib import Path
import time
import uuid
import workflow_worker as w
from job_tracking import tracked_call


def run(folder):
    folder=folder.resolve(strict=True)
    request=json.loads((folder/'request.json').read_text(encoding='utf-8'))
    if request['kind']!='convert':raise ValueError('Full-file jobs only')
    source=Path(request['source']).resolve(strict=True)
    output=(folder/'Optimized.mkv').resolve(strict=True)
    if source==output:raise ValueError('Source and output must differ')
    before={p:(p.stat().st_size,p.stat().st_mtime_ns) for p in (source,output)}
    expected=request.get('fingerprint')
    if expected!={'size':before[source][0],'mtime_ns':before[source][1]}:
        raise ValueError('Source differs from original scan')
    report=folder/('revalidation-'+uuid.uuid4().hex+'.json')
    result=dict(source=str(source),output=str(output),status='running')
    probe=request['ffprobe']
    try:
        print('Checking stream metadata',flush=True)
        original=w.probe_with_frame_color(source,probe)
        actual=w.probe_with_frame_color(output,probe)
        for key in ('width','height','bit_depth','color_primaries','color_transfer','color_space','color_range','audio_codecs','subtitle_codecs'):
            if getattr(original,key)!=getattr(actual,key):raise ValueError('Mismatch: '+key)
        if actual.video_codec!=request['codec'] or actual.hdr or actual.dolby_vision:
            raise ValueError('Unexpected codec/HDR signaling')
        for key in ('sample_aspect_ratio','display_aspect_ratio','field_order'):
            if w.shape(source,probe).get(key)!=w.shape(output,probe).get(key):raise ValueError('Mismatch: '+key)
        print('Comparing all video packet timestamps',flush=True)
        a,ab=w.video_summary(source,probe)
        b,bb=w.video_summary(output,probe)
        if len(a)!=len(b) or any(abs(x-y)>.002 for x,y in zip(a,b)):raise ValueError('Video timing/count mismatch')
        result['video_packets']=len(a)
        for selector in ('a','s'):
            print('Hashing and comparing complete tracks: '+selector,flush=True)
            result[selector]=w.compare_media_packets(probe,source,output,selector)
        if w.chapter_summary(probe,source,600)!=w.chapter_summary(probe,output,600):raise ValueError('Chapters changed')
        def attachments(path):
            return w.np.checked_json([probe,'-v','error','-select_streams','t','-show_streams','-show_data_hash','sha256',
                '-show_entries','stream=codec_name,extradata_hash:stream_tags=filename,mimetype','-of','json',str(path)],timeout=60).get('streams',[])
        if attachments(source)!=attachments(output):raise ValueError('Attachments changed')
        print('Decoding complete output video (read-only)',flush=True)
        w.np.stage([request['ffmpeg'],'-hide_banner','-nostdin','-v','error','-xerror','-threads','2',
            '-i',str(output),'-map','0:v:0','-f','null','-','-progress','pipe:1','-nostats'],
            original.duration_seconds,80,20,timeout=14400,stall=120)
        savings=100*(1-before[output][0]/before[source][0])
        if savings<float(request.get('min_savings',5)):raise ValueError('Savings below threshold')
        result.update(status='verified-full-file-awaiting-playback',total_savings_percent=savings,
                      source_bytes=before[source][0],output_bytes=before[output][0],
                      video_savings_percent=100*(1-bb/ab),full_output_decode=True)
    except BaseException as exc:
        result.update(status='failed',error=str(exc))
        raise
    finally:
        unchanged=all((p.stat().st_size,p.stat().st_mtime_ns)==v for p,v in before.items())
        result.update(media_stat_unchanged=unchanged,finished=time.time())
        if not unchanged:result.update(status='failed',error='Media changed externally')
        with report.open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2)
        print('Validation report: '+str(report),flush=True)
        if not unchanged:raise ValueError('Media changed externally')
    print(json.dumps(result,indent=2),flush=True)
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job_folder',type=Path)
    args=parser.parse_args()
    raise SystemExit(tracked_call(lambda:run(args.job_folder),'Revalidate retained full episode'))
