"""Bounded job-local HDR metric references, verified against rendered pixels.

The lossless reference is never delivered as output. Full-file comparisons and
unverified entries retain the ordinary two-input render path.
"""
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import uuid

ENTRY_BYTES=256*1024**2
TOTAL_BYTES=1024**3


def pixels(path, expected):
    """Compare complete raw-frame payloads; muxed timestamps are not pixel data."""
    rows=[]
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            if line.startswith('#') or not line.strip():continue
            parts=[p.strip() for p in line.split(',')]
            if len(parts)!=6 or len(rows)>=expected:raise ValueError('Invalid rendered pixel evidence')
            size=int(parts[4]);digest=parts[5]
            if size<=0 or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('Incomplete rendered pixel evidence')
            rows.append((size,digest))
    if len(rows)!=expected:raise ValueError('Incomplete rendered frame coverage')
    return rows


class ReferenceCache:
    def __init__(self,workflow):self.workflow=workflow;self.entries={};self.failures=set();self.bytes=0

    def get(self,reference,count,duration):
        from hdr_auto import RENDER_FILTER
        from auto_optimize import digest
        from artifact_manifest import registered_outputs
        from replacement_cleanup import safe_path
        from runtime_support import comparison_filter_options
        work=self.workflow;reference=Path(reference);root=work.directory.resolve()
        if (type(count) is not int or not 0<count<=6000 or type(duration) not in (int,float)
                or not math.isfinite(duration) or not 0<duration<=60):return None
        safe_path(reference)
        # Reuse only private generated clips in this job, never an arbitrary
        # original, a persistent cross-job cache, or a stat-only identity.
        if reference.resolve().parent!=root or not reference.name.startswith('reference-'):return None
        if reference not in registered_outputs(root) or reference.stat().st_size>ENTRY_BYTES:return None
        work.guard();source_hash=digest(reference,work.guard)
        key=hashlib.sha256(json.dumps([source_hash,count,RENDER_FILTER,comparison_filter_options(),str(work.args.ffmpeg)]).encode()).hexdigest()
        if key in self.failures:return None
        entry=self.entries.get(key)
        if entry:
            path=entry['path'];safe_path(path)
            if path.is_file() and digest(path,work.guard)==entry['sha256']:return path
            self.failures.add(key);return None
        limit=min(ENTRY_BYTES,TOTAL_BYTES-self.bytes)
        if limit<64*1024**2 or shutil.disk_usage(root).free<limit+2*1024**3:return None
        name='metric-reference-'+uuid.uuid4().hex
        cached=root/(name+'.mkv');before=root/(name+'-render.framehash');after=root/(name+'-decode.framehash')
        owned=(cached,before,after)
        try:
            command=[work.args.ffmpeg,'-hide_banner','-v','error','-nostdin','-n','-xerror',
                     *comparison_filter_options(),
                     '-noautorotate','-threads','2','-i',str(reference),'-filter_complex',
                     '[0:V:0]'+RENDER_FILTER+',split[cached][proof]',
                     '-map','[cached]','-an','-sn','-c:v','ffv1','-level','3','-coder','1','-context','1',
                     '-threads','2','-pix_fmt','yuv420p10le','-fps_mode','passthrough','-fs',str(limit),str(cached),
                     '-map','[proof]','-an','-sn','-c:v','rawvideo','-threads','2','-pix_fmt','yuv420p10le',
                     '-fps_mode','passthrough','-f','framehash','-hash','sha256',str(before)]
            work.execute(command,'Preparing HDR comparison reference',duration)
            if not cached.is_file() or not 0<cached.stat().st_size<=limit:raise ValueError('Metric cache size limit')
            work.execute([work.args.ffmpeg,'-hide_banner','-v','error','-nostdin','-n','-xerror',
                          *comparison_filter_options(),
                          '-threads','2','-i',str(cached),'-map','0:V:0','-an','-sn','-c:v','rawvideo','-threads','2',
                          '-pix_fmt','yuv420p10le','-fps_mode','passthrough','-f','framehash','-hash','sha256',str(after)],
                         'Verifying HDR reference pixels',duration)
            raw_pixels=pixels(before,count)
            if raw_pixels!=pixels(after,count):raise ValueError('Cached reference pixels differ')
            if digest(reference,work.guard)!=source_hash:raise ValueError('Reference changed while rendering')
            entry=dict(path=cached,sha256=digest(cached,work.guard),frames=count)
            from auto_optimize import save
            save(root/(name+'-proof.json'),dict(source_sha256=source_hash,cache_sha256=entry['sha256'],
                frames=count,render_filter=RENDER_FILTER,comparison_filter_options=comparison_filter_options(),
                pixels_sha256=hashlib.sha256(json.dumps(raw_pixels).encode()).hexdigest(),
                all_rendered_pixels_equal=True,scope='job-local HDR metric reference only'))
            self.entries[key]=entry;self.bytes+=cached.stat().st_size
            return cached
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
            work.guard()  # Source changes and cancellation must still propagate.
            self.failures.add(key)
            from auto_optimize import save
            save(root/(name+'-fallback.json'),dict(used=False,reason=str(exc),ordinary_quality_checks_required=True))
            return None
        finally:
            # Failed entries and temporary frame hashes never accumulate. The
            # registered successful entry joins ordinary terminal cleanup.
            for path in owned:
                if path==cached and key in self.entries:continue
                if path.is_file() and not path.is_symlink():path.unlink()
