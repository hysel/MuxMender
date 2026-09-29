"""Process-scoped hardware renderer discovery; no driver installation or edits."""
import ctypes.util
import json
import os
from pathlib import Path
import re
import sys
from native_pipeline import stage


def selected_device(lines):
    selected=[]
    for line in lines:
        match=re.search(r'Device (\d+) selected: (.+)',line)
        if match:selected.append((int(match[1]),match[2].strip()))
    if len(set(selected))!=1:return None
    index,name=selected[0]
    software=any(word in name.lower() for word in ('llvmpipe','lavapipe','software','swiftshader','(cpu)'))
    hardware=not software and any(kind in name.lower() for kind in ('(discrete)','(integrated)','(virtual)'))
    return dict(index=index,name=name,hardware=hardware,software=software)


def discover(ffmpeg, directory, guard, *, device=None):
    """Try visible devices; require actual GPU rendering, not encoder labels.

    User-provided Vulkan loader settings are respected. A missing Linux NVIDIA
    ICD manifest can be supplied only to the probe/render child using an
    already-installed vendor library. Global environment and host files stay
    untouched; actual filter execution must still succeed.
    """
    if device is not None and (type(device) is not int or device<0):raise ValueError('Invalid Vulkan device index')
    directory=Path(directory);attempts=[]
    environments=[{}]
    explicit=any(os.environ.get(k) for k in ('VK_ICD_FILENAMES','VK_DRIVER_FILES'))
    if sys.platform=='linux' and not explicit:
        library=ctypes.util.find_library('EGL_nvidia')
        if library:
            manifest=directory/'renderer-nvidia-icd.json'
            with manifest.open('x',encoding='utf-8') as handle:
                json.dump(dict(file_format_version='1.0.0',ICD=dict(library_path=library,api_version='1.3.0')),handle)
            environments.append(dict(VK_ICD_FILENAMES=str(manifest.resolve())))
    for overrides in environments:
        pending=[0 if device is None else device];seen=set()
        while pending:
            guard();index=pending.pop(0)
            if index in seen:continue
            seen.add(index);lines=[]
            command=[ffmpeg,'-hide_banner','-v','verbose','-nostdin','-init_hw_device',f'vulkan=gpu:{index}',
                '-filter_hw_device','gpu','-f','lavfi','-i','color=black:size=16x16:rate=1',
                '-vf','libplacebo=format=yuv420p10le','-frames:v','1','-f','null','-']
            error=None
            with (directory/f'renderer-probe-{len(attempts)}.log').open('x',encoding='utf-8') as log:
                log.write(json.dumps(command)+'\n')
                def observe(line):
                    log.write(line)
                    # Retain discovery records only, not a growing filter log.
                    if 'selected:' in line or re.search(r'\d+: .*\((discrete|integrated|virtual)\)',line):lines.append(line)
                    return False
                try:
                    stage(command,1,timeout=30,stall=20,guard=guard,observe=observe,cwd=directory,
                          env=dict(os.environ,**overrides))
                except RuntimeError as exc:
                    guard();error=str(exc)[-1000:]
            selected=selected_device(lines)
            attempts.append(dict(requested=index,device=selected,error=error,environment=overrides))
            if not error and selected and selected['hardware']:
                result=dict(device=selected,environment=overrides,attempts=attempts,hardware_confirmed=True)
                with (directory/'renderer.json').open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2)
                return result
            if device is None:
                for line in lines:
                    match=re.search(r'\b(\d+): .*\((?:discrete|integrated|virtual)\)',line)
                    if match and int(match[1]) not in seen:pending.append(int(match[1]))
    with (directory/'renderer.json').open('x',encoding='utf-8') as handle:
        json.dump(dict(hardware_confirmed=False,attempts=attempts),handle,indent=2)
    raise RuntimeError('No working hardware Vulkan renderer; native DV quality evaluation incomplete. See renderer.json')
