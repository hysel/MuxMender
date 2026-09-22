"""Measured HEVC/AV1 selection and optional full safe-copy encoding."""
import argparse
import hashlib
import itertools
import json
import math
import shutil
import subprocess
import time
import uuid
from fractions import Fraction
from dataclasses import replace
from pathlib import Path

import muxmender as mm
from amd_av1_batch import disjoint, fingerprint
from task_progress import digest, run_probe
from codec_selection import select_candidate, impossible_size_bound, EVALUATION_POLICY
from dvd_av1_batch import save
from encoder_capabilities import probe_encoder, nvidia_adapters, codec_order
from job_tracking import tracked_call, progress, workflow_stage
from native_pipeline import stage,decode_maps_after_frame_audit
import legacy_color
import hdr_inspection
from media_metadata import (canonical_tags, canonical_chapters, equivalent_ratio,
                            equivalent_stream_language, compatible_measured_rate)

PLANAR_FORMATS={f'yuv{chroma}p{depth}' for chroma in ('420','422','444')
                for depth in ('','10le','12le')}


def encoder_pixel_format(video,encoder):
    pixel=video['pix_fmt']
    if pixel=='yuv420p10le' and encoder.endswith(('_amf','_nvenc','_qsv')):return 'p010le'
    if pixel=='yuv444p10le' and encoder.endswith('_nvenc'):return 'yuv444p16le'
    # Let the real encoder prove this format. Full decoded validation must still
    # match the original bit depth/chroma; silent encoder conversion cannot pass.
    return pixel
from packet_validation import collect_packets
from trial_failures import structural_failure_code, previous_structural_failure


def sample_positions(duration, seconds):
    if not math.isfinite(duration) or not 1 <= seconds <= 60 or duration < seconds * 6:
        raise ValueError('Need finite duration of at least six sample lengths; samples must be 1-60 seconds')
    return [round((duration-seconds)*fraction, 3) for fraction in (.15, .5, .85)]


def sampling_window(duration, requested):
    """Adapt short sources without overlapping three reference windows."""
    if not math.isfinite(duration) or duration<=0 or not math.isfinite(requested) or not 1<=requested<=60:
        raise ValueError('Invalid sampling duration')
    return min(requested,duration/6)


def is_cover(stream):
    return stream.get('codec_type') == 'video' and stream.get('disposition', {}).get('attached_pic') == 1


def main_video(data):
    videos = [s for s in data['streams'] if s['codec_type'] == 'video' and not is_cover(s)]
    if len(videos) != 1:
        raise ValueError('Requires exactly one moving video track (cover pictures are separate)')
    v = videos[0]
    if next(s for s in data['streams'] if s['codec_type']=='video') is not v:
        raise ValueError('Cover picture precedes the movie track; stream ordering needs specialized handling')
    covers=[s for s in data['streams'] if is_cover(s)]
    if covers:
        first=data['streams'].index(covers[0])
        if any(not is_cover(s) for s in data['streams'][first:]):
            raise ValueError('Interleaved cover artwork needs stream-order-preserving remux support')
        for cover in covers:
            tags=canonical_tags(cover.get('tags',{}),'cover artwork')
            if cover.get('codec_name') not in ('mjpeg','png') or not tags.get('filename') or tags.get('mimetype') not in ('image/jpeg','image/png'):
                raise ValueError('Cover artwork needs a supported image codec, filename and MIME type')
    return v


def eligibility(data):
    v = main_video(data)
    if v.get('color_transfer') in ('smpte2084','arib-std-b67'):
        raise ValueError('HDR transfer requires the specialized preservation workflow; no automatic SDR conversion')
    if v.get('pix_fmt') not in PLANAR_FORMATS:
        raise ValueError('Pixel format '+str(v.get('pix_fmt'))+' has no implemented preservation path')
    if v.get('field_order') != 'progressive':
        raise ValueError('Interlaced or unconfirmed scan type requires separate review')
    if not legacy_color.is_supported(v):
        raise ValueError('Missing or unsupported color metadata; inspect legacy SDR before selecting a test assumption')
    if v.get('color_range') not in ('tv', 'pc') or v.get('sample_aspect_ratio') in (None, 'N/A', '0:1'):
        raise ValueError('Color range and aspect ratio must be known')
    if any(s.get('side_data_type') != 'CPB properties' for s in v.get('side_data_list', [])):
        raise ValueError('Video side data (including Dolby Vision/rotation) requires specialized review')
    if any(s['codec_type'] not in ('video', 'audio', 'subtitle', 'attachment') for s in data['streams']):
        raise ValueError('Unsupported track type')
    if int(v['width']) <= 0 or int(v['height']) <= 0:
        raise ValueError('Invalid dimensions')
    return v


def quality_summary(data, expected_frames, mean_floor, p5_floor):
    values = [float(f['metrics']['vmaf']) for f in data.get('frames', [])]
    if len(values) != expected_frames or not values or any(not math.isfinite(x) for x in values):
        raise ValueError('Incomplete/invalid VMAF frame evidence')
    mean = sum(values)/len(values)
    p5 = sorted(values)[max(0, math.ceil(.05*len(values))-1)]
    return dict(mean=mean, p5=p5, frames=len(values),
                passed=mean >= mean_floor and p5 >= p5_floor,
                caveat='Objective SDR screening only, not proof of perceptual transparency')


def quality_graph(name, frame_rate):
    """Pair frame ordinals only AFTER count/geometry/timing validation.

    Millisecond container rounding can otherwise make framesync pick the previous
    reference frame. This clock exists only in the metric filter, never in output.
    """
    rate = Fraction(frame_rate)
    if rate <= 0 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.' for c in name):
        raise ValueError('Invalid quality graph parameters')
    clock = f'settb=AVTB,setpts=N*{rate.denominator}/({rate.numerator}*TB)'
    return f'[0:v:0]{clock}[d];[1:v:0]{clock}[r];[d][r]libvmaf=n_threads=2:log_fmt=json:log_path={name}'


def quality_command(ffmpeg, output, reference, graph):
    """Bound decode pools; retain filter threading to preserve metric numerics."""
    return [ffmpeg, '-hide_banner', '-nostdin', '-v', 'warning', '-xerror',
            '-threads', '2', '-i', str(output),
            '-threads', '2', '-i', str(reference), '-filter_complex', graph,
            '-an', '-sn', '-progress', 'pipe:1', '-nostats', '-f', 'null', '-']


def metadata_check(before, after, codec, *, verified_frame_count=None):
    old, new = before['streams'], after['streams']
    if len(old) != len(new):
        raise ValueError('Track count changed')
    for a, b in zip(old, new):
        keys = ['codec_type', 'disposition']
        if a['codec_type'] == 'video' and not is_cover(a):
            keys += ['width', 'height', 'pix_fmt', 'sample_aspect_ratio', 'avg_frame_rate',
                     'color_range', 'color_space', 'color_transfer', 'color_primaries']
            if b['codec_name'] != codec:
                raise ValueError('Unexpected video codec')
        else:
            keys += ['codec_name', 'sample_rate', 'channels', 'channel_layout', 'extradata_hash']
            if is_cover(a):keys += ['width','height','pix_fmt','color_space','color_range','color_transfer','color_primaries']
        def matches(key):
            if key == 'avg_frame_rate':
                return compatible_measured_rate(a.get(key), b.get(key), verified_frame_count)
            if key == 'sample_aspect_ratio':
                return equivalent_ratio(a.get(key), b.get(key))
            return a.get(key) == b.get(key)
        changed=[k for k in keys if not matches(k)]
        if changed:
            raise ValueError('Stream properties changed: '+str(a['index'])+'; '+
                             ', '.join(f'{k}: {a.get(k)!r} -> {b.get(k)!r}' for k in changed))
        old_tags=canonical_tags(a.get('tags', {}), f"source stream {a['index']}")
        new_tags=canonical_tags(b.get('tags', {}), f"output stream {b['index']}")
        for tag in ('language', 'title', 'filename', 'mimetype'):
            equal = (equivalent_stream_language(old_tags.get(tag), new_tags.get(tag))
                     if tag == 'language' else old_tags.get(tag) == new_tags.get(tag))
            if not equal:
                raise ValueError(f"Stream {a['index']} ({a['codec_type']}) tag changed: {tag}: {old_tags.get(tag)!r} -> {new_tags.get(tag)!r}")
    if canonical_chapters(before.get('chapters', [])) != canonical_chapters(after.get('chapters', [])):
        raise ValueError('Chapters changed')
    durations=[float(item['format']['duration']) for item in (before,after)]
    if any(not math.isfinite(value) or value<=0 for value in durations):
        raise ValueError('Invalid duration; finite positive evidence required')
    if abs(Fraction(str(before['format']['duration']))-Fraction(str(after['format']['duration']))) > Fraction(1,10):
        raise ValueError('Duration changed')


def encode_command(ffmpeg, source, output, settings, info, streams):
    video=main_video(dict(streams=streams))
    ten_bit=video.get('pix_fmt')=='yuv420p10le'
    extra={}
    if settings['encoder']=='av1_qsv' and getattr(info,'hdr',False) and not getattr(info,'dolby_vision',False):
        # This path always validates native HDR frame metadata before approval.
        # A direct encoder limitation must fail its candidate, not all codecs.
        extra['experimental_av1_hdr']=True
    options = mm.encoder_options(settings['codec'], settings['quality'], info, settings['encoder'],**extra)
    if 'nvenc_cq' in settings:
        if (settings['encoder'] not in ('hevc_nvenc', 'av1_nvenc') or
                type(settings['nvenc_cq']) is not int or settings['nvenc_cq'] not in range(18,33)):
            raise ValueError('Measured NVENC CQ must be an approved bounded-search value')
        options = list(options)
        options[options.index('-cq') + 1] = str(settings['nvenc_cq'])
    if 'nvenc_preset' in settings:
        if not settings['encoder'].endswith('_nvenc') or settings['nvenc_preset'] != 'p7':
            raise ValueError('Adaptive preset must be NVENC p7')
        options = list(options)
        options[options.index('-preset') + 1] = settings['nvenc_preset']
    command = [ffmpeg, '-hide_banner', '-nostdin', '-n', '-xerror', '-copyts', '-i', str(source),
               '-map', '0', '-map_metadata', '0', '-map_chapters', '0', '-c', 'copy',
               *options, '-pix_fmt', encoder_pixel_format(video,settings['encoder']), '-fps_mode:v', 'passthrough',
               '-enc_time_base:v:0','demux',
               '-avoid_negative_ts', 'disabled']
    # Explicit flags avoid muxer auto-selection of default tracks.
    for i, stream in enumerate(streams):
        flags = '+'.join(k for k, value in stream.get('disposition', {}).items() if value) or '0'
        command += [f'-disposition:{i}', flags]
    return command + ['-progress', 'pipe:1', '-nostats', str(output)]


class Workflow:
    def decoder_options(self, source):
        build=getattr(self.args,'h264_build',None)
        original=getattr(self.args,'source',None)
        source=Path(source)
        reference=(source.parent.resolve()==self.directory.resolve() and source.name.startswith('reference-'))
        if build is not None and (reference or (original is not None and source.resolve()==Path(original).resolve())):
            return ['-x264_build',str(build)]
        return []

    def __init__(self, args, directory, guard):
        self.args, self.directory, self.guard = args, directory, guard
        self.serial = 0
        self.packet_reference_cache = {}
        self.color_intermediates = {}
        self.hdr_mode=getattr(args,'hdr_mode',None)
        self.frame_cache={}
        self.hdr_intermediates={}

    def encode_preserving_color(self, source, output, settings, info, before, label, duration):
        if self.hdr_mode:
            from hdr_auto import encode_preserved
            return encode_preserved(self,source,output,settings,info,before,label,duration)
        video=main_video(before)
        missing=[key for key in ('color_primaries','color_transfer','color_space')
                 if video.get(key) in legacy_color.UNKNOWN]
        encoded=output.with_name(output.stem+'-before-color-finalization.mkv') if missing else output
        command=encode_command(self.args.ffmpeg,source,encoded,settings,info,before['streams'])
        resolved=getattr(self.args,'resolved_color',None)
        if resolved:
            # Decoder AVFrame tags can override encoder context tags. Materialize
            # only independently recovered source signaling; setparams changes
            # metadata, never pixel values, geometry, cadence or color space.
            fields=dict(color_primaries='color_primaries',color_transfer='color_trc',
                        color_space='colorspace',color_range='range')
            values=[]
            for key,option in fields.items():
                if key not in resolved:continue
                value=resolved[key]
                if key=='color_range':value={'tv':'limited','pc':'full'}[value]
                values.append(option+'='+value)
            if values:command[-1:-1]=['-filter:v:0','setparams='+':'.join(values)]
        self.execute(self.preserve_covers(command,source,before,label),label,duration)
        if not missing:return
        encoded_data=self.probe(encoded)
        # Do not rewrite an already-correct bitstream. Some hardware-generated
        # supplemental packets decode correctly but cannot be parsed by FFmpeg's
        # metadata bitstream filter. Full frame/metadata validation still follows.
        if all(main_video(encoded_data).get(key) in legacy_color.UNKNOWN for key in missing):
            output.hardlink_to(encoded)  # Exclusive: never overwrite a destination.
            stat=encoded.stat()
            self.color_intermediates[output.resolve()]=(encoded,(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns))
            return
        names=dict(color_primaries='colour_primaries' if settings['codec']=='hevc' else 'color_primaries',
                   color_transfer='transfer_characteristics',color_space='matrix_coefficients')
        bsf=settings['codec']+'_metadata='+':'.join(names[key]+'=2' for key in missing)
        command=[self.args.ffmpeg,'-hide_banner','-nostdin','-n','-xerror','-copyts','-i',str(encoded),
                 '-map','0','-c','copy','-map_metadata','0','-map_chapters','0',
                 '-avoid_negative_ts','disabled','-bsf:v:0',bsf]
        flags=dict(color_primaries='-color_primaries:v:0',color_transfer='-color_trc:v:0',color_space='-colorspace:v:0')
        for key in missing:command += [flags[key],'2']
        for i,stream in enumerate(before['streams']):
            disposition='+'.join(k for k,v in stream.get('disposition',{}).items() if v) or '0'
            command += [f'-disposition:{i}',disposition]
        command += ['-progress','pipe:1','-nostats',str(output)]
        self.execute(self.preserve_covers(command,encoded,encoded_data,label+'-finalize'),
                     label+'-preserve-unspecified-color',duration)
        stat=encoded.stat()
        self.color_intermediates[output.resolve()]=(encoded,(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns))

    def preserve_covers(self, command, source, data, label, input_index=0):
        """Reattach original image bytes, rather than remuxing them as video tracks."""
        covers=[s for s in data['streams'] if is_cover(s)]
        if not covers:return command
        main_video(data)  # Prove supported trailing order before generating anything.
        options=[]
        for cover in covers:
            index=cover['index']
            tags=canonical_tags(cover.get('tags',{}),'cover artwork')
            image=self.directory/(label+f'-cover-{index}'+('.png' if cover['codec_name']=='png' else '.jpg'))
            self.execute([self.args.ffmpeg,'-hide_banner','-nostdin','-n','-i',str(source),
                '-map',f'0:{index}','-c','copy','-frames:v','1','-f','image2',str(image)],
                label+f'-extract-cover-{index}',1)
            if not image.is_file() or not image.stat().st_size:
                raise ValueError('Cover extraction produced no payload')
            options += ['-map',f'-{input_index}:{index}','-attach',str(image)]
            for key,value in tags.items():
                if key in ('filename','mimetype','title','language'):
                    options += [f'-metadata:s:{index}',f'{key}={value}']
        return command[:-1]+options+command[-1:]

    def execute(self, command, label, duration, *, strict_decode=False):
        command=list(command)
        if str(command[0])==str(getattr(self.args,'ffmpeg','ffmpeg')):
            for index in reversed(range(len(command)-1)):
                if command[index]=='-i':command[index:index]=self.decoder_options(command[index+1])
        self.guard()
        progress(label, directory=self.directory)
        self.serial += 1
        with (self.directory/f'{self.serial:03d}-{label}.log').open('x', encoding='utf-8') as log:
            log.write(json.dumps(command)+'\n')
            def observe(line):
                log.write(line)
                return False
            return stage(command, duration, 0, 100, timeout=self.args.timeout, stall=120,
                         guard=self.guard, observe=observe, cwd=self.directory, strict_decode=strict_decode)

    def probe(self, source):
        progress('Reading media metadata: '+source.name, directory=self.directory)
        raw = subprocess.check_output([self.args.ffprobe, '-v', 'error', '-show_streams',
               '-show_chapters', '-show_format', '-show_data_hash', 'sha256', '-of', 'json', *self.decoder_options(source),str(source)],
               text=True, timeout=60)
        data=json.loads(raw)
        resolved=getattr(self.args,'resolved_color',None)
        if resolved and (source==self.args.source or source.name.startswith('reference-')):
            video=next(s for s in data['streams'] if s['codec_type']=='video')
            for key,value in resolved.items():
                if video.get(key) in legacy_color.UNKNOWN:video[key]=value
                elif video[key]!=value:raise ValueError('Reference color metadata changed: '+key)
        return data

    def frame_file(self, source, label, metadata=None):
        metadata=metadata if metadata is not None else self.probe(source)['format']
        path = self.directory/(label+'-frames.jsonl')
        if self.hdr_mode:
            run_probe([self.args.ffprobe,'-v','error','-threads','2','-select_streams','v:0',
                       '-show_frames','-of','json',*self.decoder_options(source),str(source)],path,'Checking HDR frame timing: '+label,
                      self.args.timeout,self.guard,float(metadata['duration']),float(metadata.get('start_time',0)))
            if path.with_suffix(path.suffix+'.stderr').stat().st_size:
                raise ValueError('HDR frame decoder reported errors: '+label)
            self.frame_cache[str(source.resolve())]=path
            return path
        # Bound CPU contention between queue workers. Do not drop side-data or
        # frames: identical validation fields and full EOF draining are retained.
        run_probe([self.args.ffprobe, '-v', 'error', '-threads', '2', '-select_streams', 'v:0', '-show_frames',
                '-show_entries', 'frame=best_effort_timestamp_time,width,height,pix_fmt,sample_aspect_ratio,interlaced_frame,repeat_pict,color_primaries,color_transfer,color_space,color_range',
                '-of', 'compact=p=0', *self.decoder_options(source),str(source)],path,'Checking frame timing: '+label,
                self.args.timeout,self.guard,float(metadata['duration']),float(metadata.get('start_time',0)))
        if path.with_suffix(path.suffix+'.stderr').stat().st_size:
            raise ValueError('Frame decoder reported errors: '+label)
        if any(row.get('best_effort_timestamp_time') in (None,'N/A') for row in compact_rows(path,'width')):
            return self.recover_mpeg4_tail(source,path,label)
        return path

    def recover_mpeg4_tail(self, source, evidence, label):
        """Recover a source-only absent final PTS using original coded clocks."""
        from mpeg4_timing import recover_tail_evidence
        original=getattr(self.args,'source',None)
        if original is None or source.resolve()!=Path(original).resolve() or source.suffix.lower()!='.avi':
            raise ValueError('Missing decoded timestamp: no qualified source clock recovery')
        metadata=self.probe(source)
        video=main_video(metadata)
        if video.get('codec_name')!='mpeg4':
            raise ValueError('Missing decoded timestamp: source is not MPEG-4 Visual')
        duration=float(metadata['format']['duration'])
        if not math.isfinite(duration) or duration<=0:
            raise ValueError('Invalid source duration for bounded timing recovery')
        position=max(0,duration-10)
        raw=self.directory/(label+'-clock-tail.m4v')
        tail=self.directory/(label+'-clock-frames.json')
        errors=self.directory/(label+'-clock-probe.stderr')
        progress('Recovering missing source timestamp',detail='Checking original MPEG-4 picture clocks; not estimating from frame rate')
        self.execute([self.args.ffmpeg,'-hide_banner','-nostdin','-n','-v','error',
                      '-ss',str(position),'-i',str(source),'-map','0:v:0','-c','copy',
                      '-fs',str(64*1024*1024),'-f','m4v',str(raw)],label+'-clock-tail',10)
        if not 0<raw.stat().st_size<64*1024*1024:
            raise ValueError('MPEG-4 timing tail exceeds bounded evidence size')
        with tail.open('xb') as out,errors.open('xb') as err:
            self.guard()
            result=subprocess.run([self.args.ffprobe,'-v','error','-threads','2',
                '-read_intervals',str(position)+'%','-select_streams','v:0','-show_frames',
                '-show_entries','frame=pict_type,best_effort_timestamp_time',
                '-of','json',str(source)],stdout=out,stderr=err,timeout=min(120,self.args.timeout))
            self.guard()
        if result.returncode or errors.stat().st_size or tail.stat().st_size>4*1024*1024:
            raise ValueError('Independent MPEG-4 timing tail probe failed')
        destination=self.directory/(label+'-recovered-frames.jsonl')
        proof=recover_tail_evidence(raw.read_bytes(),json.loads(tail.read_text())['frames'],evidence,destination)
        proof['source']=str(source)
        proof['original_evidence_sha256']=digest(evidence,self.guard)
        proof['bitstream_tail_sha256']=digest(raw,self.guard)
        proof['recovered_evidence_sha256']=digest(destination,self.guard)
        save(self.directory/(label+'-timing-recovery.json'),proof)
        self.guard()
        return destination

    def compare_frame_files(self,reference,output):
        if self.hdr_mode:
            from hdr10plus_preserve import frame_records
            from hdr10plus_validation import validate_frames
            return validate_frames(frame_records(reference),frame_records(output),mode=self.hdr_mode)['frames']
        return compare_frames(reference,output)

    def packet_file(self, source, label, index):
        path = self.directory/(label+f'-stream-{index}.txt')
        run_probe([self.args.ffprobe, '-v', 'error', '-select_streams', str(index),
                '-show_packets', '-show_data_hash', 'sha256', '-show_entries',
                'packet=pts_time,dts_time,duration_time,data_hash', '-of', 'compact=p=0', str(source)],
                path,'Checking copied track: '+label+f' · track {index}',self.args.timeout,self.guard)
        return path

    def copied_packets(self, source, label, indices, metadata, reuse_sample=False):
        # Only generated clips in this workflow can be reused. Verify content,
        # including cached evidence, on every reuse; no persistent/stat-only cache.
        cacheable=(reuse_sample and source.resolve().parent==self.directory.resolve()
                   and source.name.startswith('reference-') and source.suffix=='.mkv')
        key=(str(source.resolve()),tuple(indices),digest(source,self.guard)) if cacheable and indices else None
        cached=self.packet_reference_cache.get(key) if key else None
        if cached and all(path.is_file() and not path.is_symlink() and digest(path,self.guard)==hash_value
                          for path,hash_value in cached.values()):
            progress('Reusing verified sample track evidence',detail='Generated reference and cached evidence hashes match')
            return {index:item[0] for index,item in cached.items()}
        result=collect_packets(self.args.ffprobe,source,self.directory,label,indices,self.args.timeout,self.guard,
                               float(metadata['duration']),float(metadata.get('start_time',0)))
        if key:self.packet_reference_cache[key]={index:(path,digest(path,self.guard)) for index,path in result.items()}
        return result

    def validate(self, reference, output, before, codec, label, reference_frames):
        actual = self.probe(output)
        frames = self.frame_file(output, label, actual['format'])
        count = self.compare_frame_files(reference_frames, frames)
        metadata_check(before, actual, codec, verified_frame_count=count)
        indices=[s['index'] for s in before['streams'] if s['codec_type'] in ('audio','subtitle') or is_cover(s)]
        original=self.copied_packets(reference,label+'-reference',indices,before['format'],reuse_sample=True)
        encoded=self.copied_packets(output,label,indices,actual['format'])
        for index in indices:
            cover=any(s['index']==index and is_cover(s) for s in before['streams'])
            try:
                compare_packets(original[index],encoded[index],cover=cover)
            except ValueError:
                stream=next(s for s in before['streams'] if s['index']==index)
                from packet_validation import aac_initialization_timestamp_case, packet_rows, compare_decoded_audio
                if stream.get('codec_name')!='aac':raise
                non_output_case=aac_initialization_timestamp_case(original[index],encoded[index])
                if not (non_output_case or aac_initialization_timestamp_case(original[index],encoded[index],missing_initial_duration=True)):
                    raise
                evidence=[]
                first_output=[]
                for side,path,packets in [('source',reference,original[index]),('output',output,encoded[index])]:
                    hashes=self.directory/(label+f'-aac-{index}-{side}.framehash')
                    self.execute([self.args.ffmpeg,'-v','error','-nostdin','-n','-copyts','-threads','2',
                                  '-i',str(path),'-map','0:'+str(index),'-c:a','pcm_f32le',
                                  '-progress','pipe:1','-nostats','-f','framehash','-hash','sha256',str(hashes)],
                                 label+f'-aac-{index}-{side}-presentation',float(before['format']['duration']),strict_decode=True)
                    evidence.append(hashes)
                    first_output.append(next(itertools.islice(packet_rows(packets),1,None))['pts_time'] if non_output_case else None)
                proof=compare_decoded_audio(*evidence,*first_output)
                proof['packet_representation_case']='non-output-initial-pts' if non_output_case else 'missing-initial-duration'
                save(self.directory/(label+f'-aac-{index}-presentation.json'),proof)
                compare_packets(original[index],encoded[index],aac_initialization_verified=True)
        maps,reused=decode_maps_after_frame_audit(actual,count)
        if maps:
            self.execute([self.args.ffmpeg, '-hide_banner', '-nostdin', '-v', 'error', '-xerror',
                          '-i', str(output), *[item for mapping in maps for item in ('-map',mapping)],
                          '-progress', 'pipe:1', '-nostats',
                          *([] if reused else ['-fps_mode:v','passthrough','-enc_time_base:v','demux']),
                          '-f', 'null', '-'], label+('-audio-decode' if reused else '-decode'),
                         float(before['format']['duration']),strict_decode=True)
        save(self.directory/(label+'-decode-evidence.json'),dict(video_audit_reused=reused,
            verified_video_frames=count,audio_maps=maps if reused else 'all',strict_decode=True,
            note='Current complete video frame comparison plus full audio decode; not historical evidence reuse'))
        temporary=self.color_intermediates.pop(output.resolve(),None)
        if temporary:
            path,identity=temporary
            if path.parent.resolve()!=self.directory.resolve() or path.is_symlink():
                raise ValueError('Unsafe color intermediate cleanup path')
            stat=path.stat()
            if (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)!=identity:
                raise ValueError('Color intermediate changed; retained for inspection')
            # This exclusively-created encoder temporary is owned by this run.
            # Source media and pre-existing files never enter this registry.
            path.unlink()
        for path,identity in self.hdr_intermediates.pop(output.resolve(),[]):
            if path.is_symlink() or not path.resolve().is_relative_to(self.directory.resolve()) or path in (reference,output):
                raise ValueError('Unsafe HDR intermediate cleanup path')
            stat=path.stat()
            if (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)!=identity:
                raise ValueError('HDR intermediate changed; retained for inspection')
            path.unlink()  # Exclusively created by this run; never an input file.
        return count

    def quality(self, reference, output, label, count, duration):
        # Safe generated basename and cwd avoid platform/path escaping in filter syntax.
        name = label+'-vmaf.json'
        video = next(s for s in self.probe(reference)['streams'] if s['codec_type'] == 'video')
        graph = quality_graph(name, video['avg_frame_rate'])
        if self.hdr_mode:
            from hdr_auto import quality_graph as hdr_quality_graph
            graph=hdr_quality_graph(name,video['avg_frame_rate'])
        self.execute(quality_command(self.args.ffmpeg,output,reference,graph),
                     label+'-quality', duration)
        result = quality_summary(json.loads((self.directory/name).read_text()), count,
                                 self.args.vmaf_mean, self.args.vmaf_p5)
        result['alignment'] = 'verified-frame-ordinal-v1'
        if self.hdr_mode:
            result['domain']='hdr-common-render-v1'
            result['note']='VMAF on identical fixed HDR-to-SDR rendering; not a native-HDR model. HDR metadata and native frame geometry validated separately.'
        return result


def compact_rows(path, required):
    with path.open(encoding='utf-8') as handle:
        for line in handle:
            row = dict(item.split('=', 1) for item in line.strip().split('|') if '=' in item)
            if required == 'width' and any(word in line.lower() for word in ('dolby', 'dovi', 'mastering display', 'content light', 'hdr dynamic', 'display matrix')):
                raise ValueError('Unexpected HDR/geometry frame side data')
            if required == 'data_hash' and row and 'data_hash' not in row:
                raise ValueError('Missing packet hash evidence')
            if required in row:
                yield row


def compare_frames(reference, output):
    progress('Comparing frame geometry and timestamps',detail='Comparing collected frame evidence; percentage unavailable')
    count = 0
    fields = ('width', 'height', 'pix_fmt', 'sample_aspect_ratio')
    for a, b in itertools.zip_longest(compact_rows(reference, 'width'), compact_rows(output, 'width')):
        if a is None or b is None:
            raise ValueError('Decoded frame count changed')
        if any(not (equivalent_ratio(a.get(k),b.get(k)) if k=='sample_aspect_ratio'
                    else a.get(k)==b.get(k)) for k in fields):
            raise ValueError('Decoded frame geometry/pixel format changed')
        for key in legacy_color.FIELDS:
            if a.get(key) not in legacy_color.UNKNOWN and a.get(key)!=b.get(key):
                raise ValueError('Decoded frame color metadata changed: '+key)
        for frame in (a, b):
            if frame.get('color_transfer') in ('smpte2084','arib-std-b67'):
                raise ValueError('HDR transfer found during SDR frame validation')
            if frame.get('interlaced_frame') != '0' or frame.get('repeat_pict') != '0':
                raise ValueError('Non-progressive/repeated frames require separate review')
            if 'side_data_type' in frame and any(x in frame['side_data_type'].lower() for x in ('dovi', 'dolby', 'mastering', 'content light', 'hdr', 'display matrix')):
                raise ValueError('Unexpected HDR/geometry frame side data')
        timestamps = [Fraction(f['best_effort_timestamp_time']) for f in (a, b)]
        if abs(timestamps[0]-timestamps[1]) > Fraction(1,500):
            raise ValueError('Decoded frame timing changed')
        count += 1
    if not count:
        raise ValueError('No decoded frames')
    return count


def compare_packets(reference, output, cover=False, *, aac_initialization_verified=False):
    progress('Comparing copied track evidence',detail='Checking packet hashes and timestamps; percentage unavailable')
    count=0
    for a, b in itertools.zip_longest(compact_rows(reference, 'data_hash'), compact_rows(output, 'data_hash')):
        count+=1
        if a is None or b is None or a['data_hash'] != b['data_hash']:
            raise ValueError('Copied packet payload/count changed')
        if cover:continue  # Static attachments have no playback timeline.
        for key in ('pts_time', 'dts_time', 'duration_time'):
            if aac_initialization_verified and count==1 and key=='pts_time':continue
            left, right = a.get(key), b.get(key)
            if (aac_initialization_verified and count==1 and key=='duration_time'
                    and right in (None,'N/A')):continue
            if any(value not in (None,'N/A') and not math.isfinite(float(value)) for value in (left,right)):
                raise ValueError('Invalid copied packet timestamp: '+key)
            if left != right and (left in (None, 'N/A') or right in (None, 'N/A') or abs(Fraction(left)-Fraction(right)) > Fraction(1,500)):
                raise ValueError(f'Copied packet timing changed: packet {count}, {key}: {left} -> {right}')
    if cover and count!=1:raise ValueError('Expected exactly one unchanged cover-image packet')


def check_reference_window(probe, seconds):
    """Keep the original sample bound until keyframe/preroll behavior is verified."""
    duration=float(probe['format']['duration'])
    if not math.isfinite(duration) or duration<=0:raise ValueError('Invalid reference clip duration')
    limit=2*seconds
    if duration>limit:raise ValueError(f'Reference clip exceeds bounded sampling window: {duration:.6f}s > {limit:.6f}s')
    return dict(duration=duration,maximum_seconds=limit,boundary_allowance_seconds=0)


def adaptive_candidates(report, limit=8):
    """Only refine runtime-tested encoders; never infer support or relax gates."""
    encoders = {}
    for trial in report['trials']:
        if trial.get('runtime_supported') is True and trial.get('playback_compatible') is True and trial.get('encoder') in ('hevc_nvenc','av1_nvenc','hevc_amf','av1_amf','hevc_qsv','av1_qsv'):
            encoders[trial['encoder']] = trial['codec']
    # Prefer the codec whose weakest scene scored best in the baseline trials.
    def score(encoder):
        values = [min((s.get('quality',{}).get('p5',0) for s in t['samples']),default=0)
                  for t in report['trials'] if t['encoder']==encoder]
        return max(values,default=0)
    candidates=[]
    for encoder in sorted(encoders,key=lambda e:(-score(e),e)):
        if not encoder.endswith('_nvenc'):
            if not any(t.get('encoder')==encoder and t.get('settings',{}).get('quality')=='transparent' for t in report['trials']):
                candidates.append(dict(codec=encoders[encoder],encoder=encoder,quality='transparent'))
            continue
        measured=[t for t in report['trials'] if t['encoder']==encoder]
        size_limited=bool(measured) and all(t.get('size_screen',{}).get('rejected') is True
            and not t.get('error') and not any(s.get('error') for s in t['samples']) for t in measured)
        quality_limited=(any(s.get('quality',{}).get('passed') is False for t in measured for s in t['samples'])
            and not any(t['samples'] and all(s.get('quality',{}).get('passed') is True for s in t['samples']) for t in measured))
        # A quality failure needs better quality first. Otherwise an eight-trial
        # shared budget can expire before CQ20/18 is ever tried on either codec.
        # A no-savings screen has no quality approval. Explore greater compression,
        # then bracket toward better quality; every eligible result still needs
        # all preservation/quality checks. Never treat CQ itself as a quality score.
        order=((28,26,27,30,29,32) if size_limited else
               (20,18,22,23,24,25) if quality_limited else (23,22,24,25,20,18))
        for cq in order:
            candidates.append(dict(codec=encoders[encoder],encoder=encoder,quality='balanced',
                                   nvenc_cq=cq,nvenc_preset='p7'))
    # Fair round-robin: a first NVENC backend must not consume the entire retry
    # budget before another available codec/vendor receives its first retry.
    grouped={encoder:[c for c in candidates if c['encoder']==encoder] for encoder in encoders}
    ordered=sorted(encoders,key=lambda e:(-score(e),e))
    return [item for round_ in itertools.zip_longest(*(grouped[e] for e in ordered))
            for item in round_ if item is not None][:limit]


def hardest_reference(report, encoder):
    scores={}
    for trial in report['trials']:
        if trial['encoder'] != encoder:continue
        for sample in trial['samples']:
            value=sample.get('quality',{}).get('p5')
            if value is not None:
                key=int(sample['reference_id'])
                scores[key]=min(scores.get(key,value),value)
    return min(scores,key=scores.get) if scores else 0


def run(args):
    workflow_stage('inspect')
    source, root = disjoint(args.source, args.output_dir)
    if not source.is_file():
        raise ValueError('Measured auto mode processes one video at a time')
    args.ffmpeg = shutil.which(args.ffmpeg) or args.ffmpeg
    args.ffprobe = shutil.which(args.ffprobe) or args.ffprobe
    baseline = fingerprint(source)
    args.h264_build=None
    args.decoder_context=None
    data = Workflow(args, root, lambda: None).probe(source)
    color_report=None
    scan_report=None
    hdr_report=None
    try:
        videos=[main_video(data)]
        if videos[0].get('codec_name')=='h264':
            from decoder_context import inspect_x264_build
            context=inspect_x264_build(args.ffmpeg,source)
            args.decoder_context=context
            if context:args.h264_build=context['x264_build']
        hdr_inspection.enforce_automatic_policy(videos[0])
        if videos[0].get('color_transfer') in ('smpte2084','arib-std-b67'):
            progress('Inspecting HDR metadata', detail='Read-only frame sampling; no conversion or source changes')
            try:
                hdr_report=hdr_inspection.inspect(args.ffprobe,source,videos[0],data['format']['duration'])
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                raise ValueError('HDR metadata inspection incomplete; original retained: '+str(exc)) from exc
            from hdr_auto import admit
            args.hdr_mode=admit(videos[0],hdr_report)
        frames=None
        if videos[0].get('field_order') in (None,'unknown') and videos[0].get('pix_fmt') in PLANAR_FORMATS:
            progress('Inspecting scan type',detail='Checking decoded frames; full frame validation remains required')
            frames=legacy_color.inspect_frames(args.ffprobe,source,float(data['format']['duration']))
            scan_report=dict(original=videos[0].get('field_order'),decoded_frames=len(frames),
                             progressive_samples=legacy_color.confirm_progressive(frames),
                             full_frame_validation_required=True)
            if scan_report['progressive_samples']:
                videos[0]['field_order']='progressive'
        if not getattr(args,'hdr_mode',None) and len(videos)==1 and any(videos[0].get(k) in legacy_color.UNKNOWN for k in legacy_color.FIELDS):
            progress('Inspecting legacy color metadata',detail='Reading declared color properties from decoded frames; no source changes')
            if frames is None:frames=legacy_color.inspect_frames(args.ffprobe,source,float(data['format']['duration']))
            declared_color={key:videos[0].get(key) for key in legacy_color.FIELDS}
            range_evidence=None
            if videos[0].get('codec_name')=='h264' and videos[0].get('color_range') in legacy_color.UNKNOWN:
                range_evidence=legacy_color.inspect_h264_default_range(args.ffmpeg,source,float(data['format']['duration']))
                if range_evidence:videos[0]['color_range']=range_evidence['value']
            elif videos[0].get('codec_name')=='mpeg4' and videos[0].get('color_range') in legacy_color.UNKNOWN:
                range_evidence=legacy_color.inspect_mpeg4_default_range(args.ffmpeg,source,float(data['format']['duration']))
                if range_evidence:
                    for key,value in range_evidence['effective'].items():
                        if videos[0].get(key) not in legacy_color.UNKNOWN and videos[0][key]!=value:
                            raise ValueError('MPEG-4 bitstream default conflicts with container '+key)
                        videos[0][key]=value
            data,color_report=legacy_color.resolve(data,frames,getattr(args,'legacy_color','inspect'))
            if range_evidence:
                color_report['range_evidence']=range_evidence
                color_report['original']=declared_color
                color_report['recovered']=sorted(set(color_report['recovered'])|
                    {key for key,value in color_report['effective'].items()
                     if declared_color.get(key) in legacy_color.UNKNOWN and value not in legacy_color.UNKNOWN})
            if color_report['missing'] and not color_report.get('preserved_unspecified'):
                raise ValueError('Missing color metadata after frame inspection: '+', '.join(color_report['missing'])+'. Original retained; an explicit sample-only color assumption is available.')
            if color_report['assumed'] and args.encode_best:
                raise ValueError('Assumed color is sample-only; full conversion/replacement requires confirmed color handling')
            args.resolved_color={k:v for k,v in color_report['effective'].items() if v not in legacy_color.UNKNOWN}
        if getattr(args,'hdr_mode',None):
            from hdr_auto import admit
            admit(main_video(data),hdr_report)
            video=main_video(data)
        else:
            video = eligibility(data)
    except ValueError as exc:
        # Structured, expected rejection rather than a worker crash. Never encode.
        root.mkdir(parents=True, exist_ok=True)
        save(root/'eligibility.json', dict(state='unsupported', reason=str(exc),
             reason_code=getattr(exc,'reason_code','unsupported_input'),source=str(source),color_inspection=color_report,scan_inspection=scan_report,hdr_inspection=hdr_report))
        progress('skipped', directory=root, detail=str(exc), original_unchanged=True)
        print('Original kept: unsupported input. '+str(exc))
        return 0
    duration = float(data['format']['duration'])
    requested_seconds=args.seconds
    args.seconds=sampling_window(duration,args.seconds)
    positions=[(duration-args.seconds)*fraction for fraction in (.15,.5,.85)]
    plan = dict(source=str(source), positions=positions, seconds=args.seconds, requested_seconds=requested_seconds, hardware=args.hardware,
                qualities=args.qualities, hevc_nvenc_cq=getattr(args, 'hevc_nvenc_cq', None),
                playback_verified_codecs=args.playback_verified_codecs,
                minimum_savings_percent=args.minimum_savings_percent, full_copy=args.encode_best,
                source_deletion=False, metric='VMAF', mean_floor=args.vmaf_mean, p5_floor=args.vmaf_p5,
                adaptive=getattr(args,'adaptive',False), max_extra_trials=getattr(args,'max_extra_trials',8),color_inspection=color_report,scan_inspection=scan_report,
                hdr_mode=getattr(args,'hdr_mode',None),hdr_inspection=hdr_report,
                quality_domain='hdr-common-render-v1' if getattr(args,'hdr_mode',None) else 'sdr',
                evaluation_policy=EVALUATION_POLICY)
    plan['decoder_context']=getattr(args,'decoder_context',None)
    if not args.execute:
        print(json.dumps(dict(dry_run=True, plan=plan), indent=2))
        return 0
    if not args.playback_verified_codecs:
        raise ValueError('Explicit --playback-verified-codecs required for your target players')
    root.mkdir(parents=True, exist_ok=True)
    directory = root/('auto-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    directory.mkdir()
    required_space = max(args.min_free_gib*1024**3, baseline['size']*1.2 if args.encode_best else 0)
    if shutil.disk_usage(directory).free < required_space:
        raise RuntimeError('Insufficient free output space; source retained')
    def guard():
        if (directory/'STOP').exists():
            raise KeyboardInterrupt('STOP requested')
        if fingerprint(source) != baseline:
            raise RuntimeError('Source changed during work')
        if shutil.disk_usage(directory).free < args.min_free_gib*1024**3:
            raise RuntimeError('Output free space below safety reserve')
    workflow = Workflow(args, directory, guard)
    save(directory/'plan.json', plan)
    state = dict(state='running', source=str(source), original_retained=True)
    save(directory/'status.json', state)
    try:
        guard()
        source_hash = digest(source, guard)
        progress('Checking available encoders and quality tools',directory=directory)
        report = dict(schema='muxmender-codec-trials-v1', source_id=source_hash, color_mode=workflow.hdr_mode or 'sdr', references=[], trials=[])
        workflow_stage('compare')
        filters = subprocess.check_output([args.ffmpeg, '-hide_banner', '-filters'], text=True, stderr=subprocess.STDOUT, timeout=30)
        if 'libvmaf' not in filters:
            raise RuntimeError('FFmpeg libvmaf is required; no unmeasured automatic selection')
        if workflow.hdr_mode:
            from hdr_auto import check_dependencies
            check_dependencies(args.ffmpeg,filters)
        names = mm.ffmpeg_encoder_names(args.ffmpeg)
        vendors = mm.gpu_vendors() if args.hardware == 'auto' else [args.hardware]
        # Container lspci may be absent. Runtime probe remains the authority.
        if args.hardware == 'auto':
            # Missing lspci/nvidia-smi in containers is not proof of no GPU.
            # Probe every compiled backend, preferred detected vendors first.
            vendors=list(dict.fromkeys([*vendors,*mm.HARDWARE_ENCODERS]))
        candidates = []
        adapters = nvidia_adapters() if 'nvidia' in vendors else []
        report['nvidia_adapters'] = adapters
        for vendor in vendors:
            for codec in codec_order(vendor, adapters):
                intermediate = getattr(args, 'hevc_nvenc_cq', None)
                if intermediate and (vendor != 'nvidia' or codec != 'hevc'):
                    continue
                encoder = mm.HARDWARE_ENCODERS[vendor][codec]
                if encoder not in names or codec not in args.playback_verified_codecs:
                    continue
                runtime = probe_encoder(args.ffmpeg, encoder, video['width'], video['height'],
                                        ten_bit='10le' in video['pix_fmt'] or '12le' in video['pix_fmt'],
                                        pixel_format=encoder_pixel_format(video,encoder),
                                        adapters=adapters if vendor=='nvidia' else [],
                                        cache_dir=getattr(args,'capability_cache_dir',None) or root/'.gpu-capabilities')
                save(directory/(encoder+'-runtime.json'), runtime)
                if runtime['status'] == 'working':
                    if intermediate:
                        candidates.extend(dict(codec=codec, encoder=encoder, quality='balanced', nvenc_cq=q)
                                          for q in intermediate)
                    else:
                        candidates.extend(dict(codec=codec, encoder=encoder, quality=q) for q in args.qualities)
        if not candidates:
            raise RuntimeError('No runtime-verified GPU encoder for the allowed codecs; no automatic CPU fallback')
        references = []
        for i, position in enumerate(positions):
            reference = directory/f'reference-{i}.mkv'
            reference_command=[args.ffmpeg, '-hide_banner', '-nostdin', '-n', '-ss', str(position),
                '-i', str(source), '-t', str(args.seconds), '-map', '0', '-c', 'copy', '-map_chapters', '-1',
                '-avoid_negative_ts', 'make_zero', '-progress', 'pipe:1', '-nostats', str(reference)]
            recovery=None
            try:
                workflow.execute(workflow.preserve_covers(reference_command,source,data,'reference-'+str(i)), 'reference-'+str(i), args.seconds)
                probe = workflow.probe(reference)
                window=check_reference_window(probe,args.seconds)
                frames = workflow.frame_file(reference, 'reference-'+str(i), probe['format'])
            except (ValueError,RuntimeError):
                from reference_sampling import recover_reference
                reference,recovery=recover_reference(workflow,source,data,position,args.seconds,
                                                      'reference-'+str(i)+'-keyframe')
                probe=workflow.probe(reference)
                window=check_reference_window(probe,max(args.seconds,15))
                frames = workflow.frame_file(reference, 'reference-'+str(i)+'-recovered', probe['format'])
            count = workflow.compare_frame_files(frames, frames)
            # Do not accept pathological keyframe preroll spanning another sample.
            window=check_reference_window(probe,max(args.seconds,15) if recovery else args.seconds)
            references.append((reference, probe, frames, count))
            report['references'].append(dict(id=str(i), bytes=reference.stat().st_size, position=position,window=window,
                                             recovery=recovery))
            # Defer expensive VMAF until a candidate can actually save space.
        info = mm.probe(source, args.ffprobe)
        if getattr(args,'resolved_color',None):info=replace(info,**args.resolved_color)
        def trial_candidate(settings, adaptive=False):
            trial_id = settings['encoder']+'-'+settings['quality']
            if 'nvenc_cq' in settings:
                trial_id += '-cq'+str(settings['nvenc_cq'])
            if 'nvenc_preset' in settings:
                trial_id += '-'+settings['nvenc_preset']
            first=hardest_reference(report,settings['encoder']) if adaptive else 0
            trial = dict(id=trial_id, source_id=source_hash, codec=settings['codec'], encoder=settings['encoder'],
                         settings=settings, runtime_supported=True, playback_compatible=True, samples=[])
            blocked = previous_structural_failure(report['trials'], settings['encoder'])
            report['trials'].append(trial)
            if blocked:
                trial.update(structural_failure=blocked['structural_failure'],
                             skipped_redundant=True, blocked_by_trial=blocked['id'],
                             screened_out='Same encoder layout/signaling failure; CQ/preset retry cannot resolve it')
                save(directory/'trials.json', report)
                return
            order=[first]+[i for i in range(len(references)) if i!=first]
            for i in order:
                reference, probe, frames, count = references[i]
                label = trial_id+'-'+str(i)
                output = directory/(label+'.mkv')
                sample = dict(reference_id=str(i), bytes=0, quality_pass=False, preservation_pass=False,
                              decode_pass=False, quality_method='VMAF mean and fifth percentile' if not workflow.hdr_mode else 'VMAF on common HDR-to-SDR render plus native HDR preservation')
                trial['samples'].append(sample)
                try:
                    started = time.monotonic()
                    workflow.encode_preserving_color(reference,output,settings,info,probe,label,float(probe['format']['duration']))
                    sample.update(bytes=output.stat().st_size, encode_completed=True,
                                  encode_seconds=time.monotonic()-started)
                except (ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                    guard()  # Changed source/low disk aborts the run, not just this candidate.
                    sample['error'] = str(exc)
                    code=structural_failure_code(str(exc))
                    if code:trial['structural_failure']=code
                save(directory/'trials.json', report)
                if sample.get('error'):
                    trial['screened_out']='Encoding failed; evaluation incomplete'
                    save(directory/'trials.json',report)
                    return
                bound=impossible_size_bound(report['references'],trial['samples'],args.minimum_savings_percent)
                if bound and len(trial['samples'])<len(references):
                    trial['size_screen']=dict(rejected=True,early_bound=True,minimum=args.minimum_savings_percent,**bound)
                    trial['screened_out']='Encoded clips already exceed total sample size budget; remaining encodes skipped'
                    progress('Skipping candidate: sample size budget exceeded',directory=directory,
                             detail=f"{len(trial['samples'])} of {len(references)} clips already exceed the whole candidate budget. Quality not evaluated.")
                    save(directory/'trials.json',report)
                    return
            # Rejection only: size alone can never approve an output. All three
            # identical sample windows must be encoded before comparing totals.
            reference_bytes=sum(r['bytes'] for r in report['references'])
            savings=100*(1-sum(s['bytes'] for s in trial['samples'])/reference_bytes)
            trial['size_screen'] = dict(savings_percent=savings, minimum=args.minimum_savings_percent)
            if savings <= 0 or savings < args.minimum_savings_percent:
                trial['size_screen']['rejected']=True
                trial['screened_out']='Insufficient sample savings; quality not evaluated'
                progress('Keeping original size: candidate cannot save enough space',directory=directory,
                         detail=f'{savings:.1f}% sample reduction; {args.minimum_savings_percent:g}% required. Skipping costly quality checks.')
                save(directory/'trials.json',report)
                return
            for sample in trial['samples']:
                i=int(sample['reference_id'])
                reference, probe, frames, count=references[i]
                label=trial_id+'-'+str(i)
                output=directory/(label+'.mkv')
                ref_report=report['references'][i]
                if 'metric_self_check' not in ref_report:
                    calibration=workflow.quality(reference,reference,'self-'+str(i),count,float(probe['format']['duration']))
                    # Identical videos need not score 100 (or even 98). Do not
                    # normalize scores or loosen the user's conversion floors.
                    if calibration['mean'] < args.vmaf_mean or calibration['p5'] < args.vmaf_p5:
                        raise RuntimeError('Reference quality baseline is below configured thresholds; evaluation inconclusive, source retained')
                    ref_report['metric_self_check']=calibration
                try:
                    workflow.validate(reference,output,probe,settings['codec'],label,frames)
                    quality=workflow.quality(reference,output,label,count,float(probe['format']['duration']))
                    sample.update(preservation_pass=True,decode_pass=True,quality_pass=quality['passed'],quality=quality)
                    if workflow.hdr_mode:sample['hdr_preservation_pass']=True
                except (ValueError,RuntimeError,subprocess.SubprocessError) as exc:
                    guard()
                    sample['error']=str(exc)
                    code=structural_failure_code(str(exc))
                    if code:trial['structural_failure']=code
                save(directory/'trials.json',report)
                if not all(sample[k] for k in ('quality_pass','preservation_pass','decode_pass')):
                    trial['screened_out']='Scene '+str(i)+' failed; remaining quality checks skipped'
                    save(directory/'trials.json',report)
                    return
        for index, settings in enumerate(candidates):
            trial_candidate(settings)
            progress('Candidate completed', index+1, len(candidates), directory=directory, unit='candidates')
        decision = select_candidate(report, args.minimum_savings_percent)
        if getattr(args,'adaptive',False) and decision['action']=='keep_original':
            extra=adaptive_candidates(report,args.max_extra_trials)
            tested=0
            for settings in extra:
                guard()
                trial_candidate(settings,adaptive=True)
                tested+=1
                progress('Adaptive candidate checked',tested,len(extra),directory=directory,unit='candidates')
                decision=select_candidate(report,args.minimum_savings_percent)
                if decision['action']=='encode_copy':break
            save(directory/'adaptive-search.json',dict(extra_trials=tested,budget=len(extra),
                result=decision['action'],stop_reason='eligible_candidate' if decision['action']=='encode_copy' else 'bounded_search_exhausted',
                cpu_fallback='not_run_requires_explicit_opt_in',quality_thresholds_unchanged=True))
        save(directory/'selection.json', decision)
        if args.encode_best and decision['action'] == 'encode_copy':
            settings = decision['selected']['settings']
            from validated_replace import readable_destination
            readable=readable_destination(source)
            output = directory/(readable.name if readable.stem!=source.stem else 'full-'+settings['codec']+'.mkv')
            workflow_stage('encode')
            workflow.encode_preserving_color(source,output,settings,info,data,'full-encode',duration)
            # Rejection needs no expensive full-picture validation. Encoding has
            # completed successfully, but this file already cannot meet the size
            # requirement. This path never approves or publishes an output.
            actual_savings = 100*(1-output.stat().st_size/baseline['size'])
            if output.stat().st_size >= baseline['size'] or actual_savings < args.minimum_savings_percent:
                guard()
                if digest(source, guard) != source_hash:
                    raise RuntimeError('Source hash changed; size decision not reusable')
                state.update(state='full-output-rejected-insufficient-savings', candidate=str(output),
                             saved_percent=actual_savings, source_bytes=baseline['size'],
                             output_bytes=output.stat().st_size, minimum_savings_percent=args.minimum_savings_percent,
                             full_validation_performed=False, source_sha256=source_hash)
                save(directory/'status.json', state)
                progress('Keeping original: full output did not meet savings target',directory=directory,
                         detail=f'{actual_savings:.2f}% smaller; {args.minimum_savings_percent:g}% required. Full validation not needed for rejection.')
                print(json.dumps(state, indent=2))
                return 0
            workflow_stage('validate')
            frames = workflow.frame_cache.get(str(source.resolve())) if workflow.hdr_mode else None
            if frames is None:frames = workflow.frame_file(source, 'full-source', data['format'])
            workflow.validate(source, output, data, settings['codec'], 'full', frames)
            actual_savings = 100*(1-output.stat().st_size/baseline['size'])
            guard()
            if digest(source, guard) != source_hash:
                raise RuntimeError('Source hash changed; output not approved')
            if output.stat().st_size >= baseline['size'] or actual_savings < args.minimum_savings_percent:
                state.update(state='full-output-rejected-insufficient-savings', candidate=str(output), saved_percent=actual_savings)
            else:
                state.update(state='validated-copy-awaiting-playback', output=str(output), saved_percent=actual_savings,
                             source_sha256=source_hash, output_sha256=digest(output, guard))
        else:
            guard()
            if digest(source, guard) != source_hash:
                raise RuntimeError('Source hash changed')
            state.update(state='trials-completed', decision=decision)
        save(directory/'status.json', state)
        print(json.dumps(state, indent=2))
        return 0
    except BaseException as exc:
        state.update(state='stopped-original-retained', error=str(exc))
        save(directory/'status.json', state)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--capability-cache-dir', type=Path, help='Shared positive GPU-probe cache; unknown or multiple GPUs are always reprobed')
    parser.add_argument('--hardware', choices=('auto', 'nvidia', 'amd', 'intel'), default='auto')
    parser.add_argument('--execute', action='store_true', help='Run trials; default only probes and prints plan')
    parser.add_argument('--encode-best', action='store_true', help='After trials, encode and validate a full copy')
    parser.add_argument('--legacy-color',choices=('inspect','bt709-limited'),default='inspect',
                        help='Inspect missing color tags; optional BT.709 limited-range assumption is sample-only')
    parser.add_argument('--playback-verified-codecs', nargs='+', choices=('hevc', 'av1'), default=[])
    parser.add_argument('--qualities', nargs='+', choices=('transparent', 'balanced', 'compact'), default=['balanced', 'compact'])
    parser.add_argument('--hevc-nvenc-cq', nargs='+', type=int, choices=range(18,33),
                        help='HEVC-only measured trials using balanced preset and explicit CQ values; quality/savings checks still apply')
    parser.add_argument('--adaptive', action='store_true', help='If baseline fails, refine runtime-tested NVENC settings using hardest-scene screening')
    parser.add_argument('--max-extra-trials', type=int, choices=range(1,13), default=8)
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--vmaf-mean', type=float, default=90,
                        help='Minimum mean VMAF score (default: 90; not a percentage of retained quality)')
    parser.add_argument('--vmaf-p5', type=float, default=90)
    parser.add_argument('--minimum-savings-percent', type=float, default=0,
                        help='Minimum reduction; 0 accepts any strictly smaller validated output')
    parser.add_argument('--min-free-gib', type=float, default=4)
    parser.add_argument('--timeout', type=float, default=7200)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--ffprobe', default='ffprobe')
    args = parser.parse_args(argv)
    for name, low, high in [('vmaf_mean', 0, 100), ('vmaf_p5', 0, 100), ('minimum_savings_percent', 0, 99.9),
                            ('min_free_gib', 1, 100000), ('timeout', 1, 86400), ('seconds', 1, 60)]:
        value = getattr(args, name)
        if not math.isfinite(value) or not low <= value <= high:
            parser.error('Invalid '+name)
    args.qualities = list(dict.fromkeys(args.qualities))
    if args.hevc_nvenc_cq:
        args.hevc_nvenc_cq = list(dict.fromkeys(args.hevc_nvenc_cq))
        if args.hardware not in ('auto', 'nvidia') or 'hevc' not in args.playback_verified_codecs:
            parser.error('Intermediate CQ trials require NVIDIA and HEVC playback verification')
    # Validate separation BEFORE tracked_call creates dashboard artifacts.
    args.source, args.output_dir = disjoint(args.source, args.output_dir)
    return tracked_call(lambda: run(args), 'Measured codec selection', folder=args.output_dir) if args.execute else run(args)


if __name__ == '__main__':
    raise SystemExit(main())
