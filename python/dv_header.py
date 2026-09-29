"""Recover absent container DV signaling from a short, unchanged HEVC copy.

This is routing evidence only. Full RPU/frame/quality validation remains required.
Existing declarations are never overridden and source files are never edited.
"""
import copy
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

_cache={}


def recover(data,source,ffprobe='ffprobe',ffmpeg=None):
    videos=[s for s in data.get('streams',[]) if s.get('codec_type')=='video' and not s.get('disposition',{}).get('attached_pic')]
    if not videos:return None
    video=videos[0]
    if video.get('codec_name')!='hevc' or any('dv_profile' in s for s in (video.get('side_data_list') or [])):return None
    source=Path(source)
    if not source.is_file():return None
    stat=source.stat()
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    key=(str(source.resolve()),*identity(stat),str(ffprobe))
    cached=_cache.get(key)
    configuration=cached.get('configuration') if cached else None
    decoded_color=cached.get('decoded_color',{}) if cached else {}
    if configuration is None:
        # Missing/wrong color tags cannot prove absence of DV. Look beyond the
        # first packet, which may not even produce a decoded picture.
        try:duration=float((data.get('format') or {}).get('duration',video.get('duration',0)))
        except (TypeError,ValueError):duration=0
        positions=[0.0]+([duration*f for f in (.15,.5,.85)] if math.isfinite(duration) and duration>6 else [])
        intervals=','.join(f'{p:g}%+0.5' for p in positions)
        frames=subprocess.run([str(ffprobe),'-v','error','-threads','2','-select_streams','V:0','-read_intervals',intervals,
            '-show_frames','-of','json',str(source)],capture_output=True,text=True,check=True,timeout=30)
        decoded=json.loads(frames.stdout).get('frames',[])
        present=[frame for frame in decoded if any('dolby vision' in str(s.get('side_data_type','')).lower() or 'dovi' in str(s.get('side_data_type','')).lower()
                   for s in (frame.get('side_data_list') or []))]
        if not present:return None
        for field in ('color_transfer','color_primaries','color_space','color_range'):
            values={frame[field] for frame in present if frame.get(field) not in (None,'unknown','unspecified')}
            if len(values)==1:decoded_color[field]=values.pop()
        try:
            offset=float(present[0].get('best_effort_timestamp_time',0))-float((data.get('format') or {}).get('start_time',0))
        except (TypeError,ValueError):offset=0
        if not math.isfinite(offset):offset=0
        binary=ffmpeg or str(Path(shutil.which(str(ffprobe)) or str(ffprobe)).with_name('ffmpeg'))
        if not shutil.which(binary) or not shutil.which('mkvmerge'):
            raise ValueError('Dolby Vision is present without a container header; FFmpeg and mkvmerge are needed to inspect it')
        with tempfile.TemporaryDirectory(prefix='muxmender-dv-header-') as folder:
            root=Path(folder);raw=root/'header.hevc';remux=root/'header.mkv'
            subprocess.run([binary,'-v','error','-nostdin','-n','-ss',str(max(0,offset)),'-i',str(source),'-map','0:V:0',
                '-t','2','-c','copy','-bsf:v','hevc_mp4toannexb','-f','hevc','-fs','67108864',str(raw)],
                capture_output=True,check=True,timeout=60)
            subprocess.run(['mkvmerge','-o',str(remux),str(raw)],capture_output=True,check=True,timeout=30)
            probe=subprocess.run([str(ffprobe),'-v','error','-select_streams','V:0','-show_streams','-of','json',str(remux)],
                                 capture_output=True,text=True,check=True,timeout=30)
            configs=[s for v in json.loads(probe.stdout).get('streams',[]) for s in (v.get('side_data_list') or []) if 'dv_profile' in s]
            if len(configs)!=1 or configs[0].get('rpu_present_flag')!=1:
                raise ValueError('Dolby Vision bitstream header could not be recovered unambiguously')
            configuration=configs[0]
        if identity(source.stat())!=identity(stat):raise ValueError('Source changed during DV header inspection')
        if len(_cache)>=64:_cache.clear()
        _cache[key]=copy.deepcopy(dict(configuration=configuration,decoded_color=decoded_color))
    video['side_data_list']=list(video.get('side_data_list') or [])+[copy.deepcopy(configuration)]
    recovered_color={}
    for field,value in decoded_color.items():
        if video.get(field) in (None,'unknown','unspecified'):
            video[field]=value;recovered_color[field]=value
    return dict(method='unchanged-hevc-header-remux',configuration=copy.deepcopy(configuration),
                decoded_color_recovered=recovered_color,routing_only=True,full_bitstream_validation_required=True)
