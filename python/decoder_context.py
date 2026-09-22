"""Recover original H.264 decoder compatibility context, never guessed tags."""
import hashlib
import re
import subprocess

X264_UUID=bytes.fromhex('dc45e9bde6d948b7962cd820d923eeef')


def x264_build_from_annexb(payload):
    builds=set()
    for nal in re.split(b'\x00\x00\x01',payload):
        if not nal or nal[0]&31!=6:continue
        rbsp=nal[1:].replace(b'\x00\x00\x03',b'\x00\x00')
        offset=0
        while offset<len(rbsp) and rbsp[offset:]!=b'\x80':
            values=[]
            for _ in range(2):
                value=0
                while offset<len(rbsp) and rbsp[offset]==255:
                    value+=255;offset+=1
                if offset>=len(rbsp):return None
                value+=rbsp[offset];offset+=1;values.append(value)
            kind,size=values
            if offset+size>len(rbsp):return None
            data=rbsp[offset:offset+size];offset+=size
            if kind!=5 or not data.startswith(X264_UUID):continue
            match=re.match(rb'x264 - core ([1-9][0-9]{0,3})(?: |\x00|$)',data[16:])
            if not match:return None
            builds.add(int(match[1]))
    return next(iter(builds)) if len(builds)==1 else None


def inspect_x264_build(ffmpeg,source):
    try:
        result=subprocess.run([ffmpeg,'-v','error','-nostdin','-i',str(source),
            '-map','0:v:0','-c','copy','-frames:v','1','-bsf:v','h264_mp4toannexb',
            '-f','h264','-'],capture_output=True,timeout=30)
    except (OSError,subprocess.SubprocessError):return None
    if result.returncode:return None
    build=x264_build_from_annexb(result.stdout)
    if build is None:return None
    return dict(x264_build=build,basis='Original first access-unit x264 UUID SEI',
                access_unit_sha256=hashlib.sha256(result.stdout).hexdigest())
