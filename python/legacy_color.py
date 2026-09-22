"""Recover declared SDR metadata; never infer color from resolution alone."""
import copy
import json
import math
import re
import subprocess

FIELDS=('color_primaries','color_transfer','color_space','color_range')
UNKNOWN=(None,'unknown','unspecified','reserved','')
SDR_PRIMARIES={'bt709','smpte170m','bt470bg','bt470m','smpte240m','bt2020'}
SDR_TRANSFER={'bt709','smpte170m','gamma22','gamma28','bt470m','bt470bg','smpte240m','bt2020-10','bt2020-12'}
SDR_MATRIX={'bt709','smpte170m','bt470bg','smpte240m','bt2020nc'}


def inspect_frames(ffprobe,source,duration):
    if not math.isfinite(duration) or duration<=0:raise ValueError('Invalid duration for color inspection')
    intervals=','.join(f'{duration*f:.3f}%+#24' for f in (.1,.5,.9))
    command=[ffprobe,'-v','error','-select_streams','v:0','-read_intervals',intervals,'-show_frames',
             '-show_entries','frame=color_primaries,color_transfer,color_space,color_range,interlaced_frame,repeat_pict:frame_side_data',
             '-of','json',str(source)]
    return json.loads(subprocess.check_output(command,text=True,timeout=60)).get('frames',[])


def confirm_progressive(frames):
    """Bounded admission evidence only; output/reference full-frame checks still apply."""
    return len(frames)>=24 and all(f.get('interlaced_frame')==0 and f.get('repeat_pict')==0 for f in frames)


def can_preserve_unspecified_transfer(video):
    """Preserve an absent transfer tag, not an assumed BT.709 transfer curve."""
    return (video.get('color_transfer') in UNKNOWN
            and video.get('color_primaries')=='bt709' and video.get('color_space')=='bt709'
            and video.get('color_range') in ('tv','pc'))


def can_preserve_unspecified_color(video):
    return (video.get('color_range') in ('tv','pc')
            and video.get('color_primaries') in SDR_PRIMARIES | set(UNKNOWN)
            and video.get('color_transfer') in SDR_TRANSFER | set(UNKNOWN)
            and video.get('color_space') in SDR_MATRIX | set(UNKNOWN))


def inspect_h264_default_range(ffmpeg, source, duration):
    """H.264 Annex E: absent full-range flag is inferred zero, not guessed from size."""
    if not math.isfinite(duration) or duration<=0:raise ValueError('Invalid duration')
    evidence=[]
    for fraction in (.1,.5,.9):
        try:
            result=subprocess.run([ffmpeg,'-hide_banner','-nostdin','-loglevel','info',
                '-ss',str(duration*fraction),'-i',str(source),'-map','0:v:0','-c:v','copy',
                '-bsf:v','trace_headers','-frames:v','1','-f','null','-'],
                capture_output=True,text=True,timeout=30)
        except (OSError,subprocess.SubprocessError):
            return None  # No evidence means no range recovery.
        flags=re.findall(r'\bvideo_signal_type_present_flag\s+[01]+\s*=\s*(\d+)',result.stderr)
        # Accept only the unambiguous absent-signaling case. Explicit signaling
        # with missing probe evidence remains unresolved, never overwritten.
        if result.returncode or not flags or any(value!='0' for value in flags):
            return None
        evidence.append(dict(position=duration*fraction,video_signal_type_present=0))
    return dict(value='tv',basis='ITU-T H.264 Annex E absent video_full_range_flag = 0',windows=evidence)


def mpeg4_absent_signal_headers(payload):
    """Count MPEG-4 Visual Object headers proving absent video_signal_type.

    Parse only the small fixed header, not compressed picture data. Missing,
    truncated, non-video or explicitly signaled headers are not evidence.
    """
    count=0
    for match in re.finditer(b'\x00\x00\x01\xb5',payload):
        start=match.end()
        end=payload.find(b'\x00\x00\x01',start)
        raw=payload[start:end if end>=0 else len(payload)]
        bits=''.join(f'{byte:08b}' for byte in raw[:3])
        if not bits:return None
        offset=8 if bits[0]=='1' else 1
        if len(bits)<offset+5:return None
        if offset==8 and (int(bits[1:5],2)==0 or int(bits[5:8],2)==0):return None
        if int(bits[offset:offset+4],2)!=1 or bits[offset+4]!='0':return None
        count+=1
    return count or None


def inspect_mpeg4_default_range(ffmpeg,source,duration):
    """ISO/IEC 14496-2 6.3.2: absent video_signal_type implies range zero.

    https://previewnorm.com/iec/ISO%20IEC%2014496-2-1999%20Amd%201-2000%20PDF.pdf
    Section 6.3.2, printed page 109. Do not infer this from AVI/Xvid naming.
    """
    if not math.isfinite(duration) or duration<=0:raise ValueError('Invalid duration')
    evidence=[]
    for fraction in (.1,.5,.9):
        try:
            result=subprocess.run([ffmpeg,'-v','error','-nostdin','-ss',str(duration*fraction),
                '-i',str(source),'-map','0:v:0','-c:v','copy','-frames:v','1','-f','m4v','pipe:1'],
                capture_output=True,timeout=30)
        except (OSError,subprocess.SubprocessError):return None
        count=mpeg4_absent_signal_headers(result.stdout) if result.returncode==0 else None
        if not count:return None
        evidence.append(dict(position=duration*fraction,absent_signal_headers=count))
    return dict(value='tv',effective=dict(color_range='tv',color_primaries='bt709',
                color_transfer='bt709',color_space='bt709'),
                basis='ISO/IEC 14496-2 6.3.2 absent video_signal_type implies video_range=0 and color description values=1',windows=evidence)


def resolve(data,frames,assumption='inspect'):
    effective=copy.deepcopy(data)
    video=next(s for s in effective['streams'] if s['codec_type']=='video')
    evidence=dict(original={k:video.get(k) for k in FIELDS},decoded_frames=len(frames),assumed=[],recovered=[])
    for frame in frames:
        for item in frame.get('side_data_list',[]):
            if any(token in str(item.get('side_data_type','')).lower() for token in ('dovi','dolby','mastering','content light','hdr','display matrix')):
                raise ValueError('HDR/Dolby Vision or geometry side data requires its specialized workflow')
    for key in FIELDS:
        values={f[key] for f in frames if f.get(key) not in UNKNOWN}
        if video.get(key) not in UNKNOWN:values.add(video[key])
        if len(values)>1:raise ValueError('Conflicting color metadata: '+key)
        if values:
            if video.get(key) in UNKNOWN:evidence['recovered'].append(key)
            video[key]=next(iter(values))
    if assumption=='bt709-limited':
        expected=dict(color_primaries='bt709',color_transfer='bt709',color_space='bt709',color_range='tv')
        for key,value in expected.items():
            if video.get(key) in UNKNOWN:
                video[key]=value;evidence['assumed'].append(key)
            elif video[key]!=value:raise ValueError('BT.709 test assumption conflicts with declared '+key)
    missing=[key for key in FIELDS if video.get(key) in UNKNOWN]
    preserved=[key for key in missing if key!='color_range'] if can_preserve_unspecified_color(video) else []
    evidence.update(effective={k:video.get(k) for k in FIELDS},missing=missing,preserved_unspecified=preserved,
                    replacement_allowed=not evidence['assumed'] and (not missing or bool(preserved)))
    return effective,evidence


def is_supported(video):
    if can_preserve_unspecified_color(video):return True
    return (video.get('color_primaries') in SDR_PRIMARIES and video.get('color_transfer') in SDR_TRANSFER
            and video.get('color_space') in SDR_MATRIX)
