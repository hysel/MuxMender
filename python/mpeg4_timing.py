"""Read MPEG-4 Visual picture clocks; never invent missing times from FPS.

Timing syntax follows ISO/IEC 14496-2 VOL/VOP headers and FFmpeg's decoder:
https://raw.githubusercontent.com/FFmpeg/FFmpeg/n8.0/libavcodec/mpeg4videodec.c
This is evidence recovery, not an encoder or a frame-rate conversion.
"""
from fractions import Fraction
import re
from collections import deque
from decimal import Decimal, localcontext


class Bits:
    def __init__(self,data):self.data=data;self.offset=0
    def get(self,count):
        if self.offset+count>len(self.data)*8:raise ValueError('Truncated MPEG-4 timing header')
        value=0
        for _ in range(count):
            value=(value<<1)|((self.data[self.offset//8]>>(7-self.offset%8))&1)
            self.offset+=1
        return value
    def marker(self):
        if self.get(1)!=1:raise ValueError('Invalid MPEG-4 timing marker')


def vol_clock(payload):
    bits=Bits(payload);bits.get(1);kind=bits.get(8)
    if kind not in (1,17):raise ValueError('Timing recovery supports Simple/Advanced Simple VOL syntax')
    if bits.get(1):bits.get(4);bits.get(3)
    if bits.get(4)==15:bits.get(16)
    if bits.get(1):
        bits.get(2);bits.get(1)
        if bits.get(1):
            for _ in range(3):bits.get(15);bits.marker()
            bits.get(14);bits.marker();bits.get(15);bits.marker()
    if bits.get(2)!=0:raise ValueError('Nonrectangular VOL timing requires another parser')
    bits.marker();resolution=bits.get(16);bits.marker()
    if resolution<=0:raise ValueError('Invalid VOP clock resolution')
    width=max(1,(resolution-1).bit_length())
    if bits.get(1):
        if bits.get(width)==0:raise ValueError('Invalid fixed VOP increment')
    return resolution,width


def picture_clocks(payload):
    """Return presentation-ordered coded picture clocks, including B reordering."""
    starts=list(re.finditer(b'\x00\x00\x01',payload))
    resolution=width=None;base=previous_base=0;rows=[]
    for i,start in enumerate(starts):
        end=starts[i+1].start() if i+1<len(starts) else len(payload)
        unit=payload[start.end():end]
        if not unit:raise ValueError('Empty MPEG-4 start code')
        code=unit[0]
        if 0x20<=code<=0x2f:
            clock=vol_clock(unit[1:])
            if resolution is not None and clock!=(resolution,width):raise ValueError('VOP clock changed')
            resolution,width=clock
        elif code==0xb3:
            raise ValueError('GOV clock reset requires explicit timing support')
        elif code==0xb6:
            if resolution is None:raise ValueError('VOP has no original VOL clock')
            bits=Bits(unit[1:]);kind=bits.get(2)
            if kind==3:raise ValueError('Sprite VOP timing is not qualified')
            increment=0
            while bits.get(1):
                increment+=1
                if increment>60:raise ValueError('Unexpected VOP clock discontinuity')
            bits.marker();tick=bits.get(width);bits.marker();coded=bits.get(1)
            if tick>=resolution:raise ValueError('VOP increment exceeds clock resolution')
            if kind!=2:
                previous_base=base;base+=increment;time=base*resolution+tick
            else:time=(previous_base+increment)*resolution+tick
            if coded:rows.append(dict(time=Fraction(time,resolution),pict_type='IPB'[kind]))
    if not rows:raise ValueError('No coded MPEG-4 picture clocks')
    rows.sort(key=lambda r:r['time'])
    if len({r['time'] for r in rows})!=len(rows):raise ValueError('Ambiguous duplicate picture clocks')
    return rows


def missing_tail_timestamp(payload, frames):
    """Recover only a missing final PTS from an independently aligned VOP clock.

    Every preceding timestamp and every picture type must agree. The one
    microsecond bound covers decimal serialization, not frame-rate drift.
    Output-video timestamps are deliberately not an input to this proof.
    """
    clocks = picture_clocks(payload)
    if len(frames) < 17 or len(clocks) != len(frames):
        raise ValueError('Insufficient or mismatched MPEG-4 tail picture evidence')
    if frames[-1].get('best_effort_timestamp_time') not in (None, 'N/A'):
        raise ValueError('Final picture already has a timestamp')
    offsets = []
    previous = None
    for index, (frame, clock) in enumerate(zip(frames, clocks)):
        if frame.get('pict_type') != clock['pict_type']:
            raise ValueError('MPEG-4 tail picture order/type changed')
        raw = frame.get('best_effort_timestamp_time')
        if raw in (None, 'N/A'):
            if index != len(frames)-1:
                raise ValueError('Only the final missing timestamp can be recovered')
            continue
        stamp = Fraction(raw)
        if previous is not None and stamp <= previous:
            raise ValueError('Nonmonotonic MPEG-4 source timestamps')
        previous = stamp
        offsets.append(stamp - clock['time'])
    if max(offsets) - min(offsets) > Fraction(1, 1000000):
        raise ValueError('MPEG-4 bitstream clock disagrees with source timestamps')
    offset = sorted(offsets)[len(offsets)//2]
    recovered = clocks[-1]['time'] + offset
    if recovered <= previous:
        raise ValueError('Recovered timestamp does not follow source pictures')
    return recovered


def recover_tail_evidence(payload, tail_frames, source_evidence, destination):
    """Create new validation evidence; never edit the original probe output."""
    recovered = missing_tail_timestamp(payload, tail_frames)
    if source_evidence.resolve() == destination.resolve() or destination.exists():
        raise ValueError('Timing recovery requires a new evidence destination')
    count = 0
    tail = deque(maxlen=len(tail_frames))
    missing = []
    with source_evidence.open(encoding='utf-8') as handle:
        for line in handle:
            row = dict(part.split('=',1) for part in line.strip().split('|') if '=' in part)
            if 'width' not in row: continue
            count += 1
            raw = row.get('best_effort_timestamp_time')
            if raw in (None,'N/A'): missing.append(count)
            else: Fraction(raw)
            tail.append(row)
    if missing != [count] or len(tail) != len(tail_frames):
        raise ValueError('Full evidence must have exactly one missing final timestamp')
    for full, short in zip(tail,tail_frames):
        a,b=full.get('best_effort_timestamp_time'),short.get('best_effort_timestamp_time')
        if a in (None,'N/A') and b in (None,'N/A'): continue
        if a in (None,'N/A') or b in (None,'N/A') or Fraction(a)!=Fraction(b):
            raise ValueError('Independent tail probe differs from full source evidence')
    with localcontext() as context:
        context.prec=32
        timestamp=format(Decimal(recovered.numerator)/Decimal(recovered.denominator),'.9f')
    with source_evidence.open(encoding='utf-8') as original, destination.open('x',encoding='utf-8') as out:
        for line in original:
            if 'width=' in line and 'best_effort_timestamp_time=N/A' in line:
                line=line.replace('best_effort_timestamp_time=N/A','best_effort_timestamp_time='+timestamp)
            elif 'width=' in line and 'best_effort_timestamp_time=' not in line:
                line='best_effort_timestamp_time='+timestamp+'|'+line
            out.write(line)
    return dict(frames=count,recovered_timestamp=timestamp,tail_frames=len(tail_frames),
                basis='MPEG-4 VOL/VOP picture clock aligned to every known tail timestamp',
                guessed_from_frame_rate=False,original_evidence_retained=True)
