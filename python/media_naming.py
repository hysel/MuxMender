"""Shared CLI/app media naming and reviewed rename transactions."""
import json
import os
import re
import time
import uuid
from pathlib import Path

MEDIA_EXTENSIONS = {
    ".3gp", ".avi", ".flv", ".m2ts", ".m4v", ".mkv", ".mov",
    ".mp4", ".mpeg", ".mpg", ".mts", ".ts", ".webm", ".wmv",
}

def readable_destination(original, *, preserve_companions=True):
    """Infer a title only for a cryptic release name in a single-movie folder.

    Folder labels are local naming hints, not verified film identities. Never
    collapse episode identifiers or distinguishable versions into one title.
    """
    original=Path(original)
    fallback=original if original.suffix.lower()=='.mkv' else original.with_suffix('.mkv')
    if re.search(r's\d+e\d+|\d+x\d+',original.stem,re.I):return fallback
    if not re.fullmatch(r'[a-z0-9]{2,12}-[a-z0-9]{2,12}[._-](?:480|576|720|1080|2160)p',original.stem,re.I):
        return fallback
    title=re.sub(r'[<>:"/\\|?*\x00-\x1f]',' ',original.parent.name)
    title=' '.join(title.split()).strip(' .')
    if len(title.encode('utf-8'))>180 or len(title.split())<2 or re.search(r'\b(?:season|extras|samples|test|output)\b',title,re.I):
        return fallback
    media=MEDIA_EXTENSIONS | {'.vob'}
    siblings=[p for p in original.parent.iterdir() if p.suffix.lower() in media and p.is_file()]
    if len(siblings)!=1 or siblings[0]!=original:return fallback
    # External subtitles/artwork depend on the basename. Leave these sets intact
    # until companion-file renaming has its own transactional publication path.
    companions={'.srt','.ass','.ssa','.sub','.idx','.vtt','.nfo','.jpg','.png'}
    if preserve_companions and any(p.suffix.lower() in companions and p.name.casefold().startswith(original.stem.casefold()+'.')
           for p in original.parent.iterdir()):return fallback
    return original.with_name(title+'.mkv')

def clean_media_name(source: Path) -> str:
    """Remove release suffixes without guessing titles from an online service."""
    name = re.sub(r'[._]+', ' ', source.stem).strip()
    # A release boundary requires a distinct token, not a substring of a title.
    boundary = re.search(r'(?i)(?:^|[\s\[(-])(?:480[pi]|576[pi]|720p|1080[pi]|2160p|4320p|'
                         r'WEB[ -]?DL|WEBRip|Blu[ -]?Ray|BDRip|HDTV|REMUX|'
                         r'x26[45]|H[ .]?26[45]|HEVC|AV1|AMZN|DDP)(?=$|[\s\].)-])', name)
    if boundary:
        name = name[:boundary.start()].strip(' -([.')
    episode = re.search(r'(?i)\bS\d{1,3}E\d{1,3}(?:E\d{1,3})*\b', name)
    if episode:
        title = name[:episode.start()].strip(' -')
        suffix = name[episode.end():].strip(' -')
        name = title + ' - ' + episode.group().upper() + (' - ' + suffix if suffix else '')
    else:
        year = re.search(r'\(((?:19|20)\d{2})\)$', name)
        if not year:
            year = re.search(r'(?<!\d)((?:19|20)\d{2})$', name)
            if year and int(year.group(1)) > time.localtime().tm_year + 1:
                year = None
        if year and name[:year.start()].strip(' ('):
            name = name[:year.start()].strip(' (') + ' (' + year.group(1) + ')'
    name = re.sub(r'[<>:"/\\|?*]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip(' .-')
    if not name or name.upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(n) for n in range(1,10)), *('LPT'+str(n) for n in range(1,10))}:
        raise RuntimeError('Cannot determine a safe media title; clean up the input name first')
    return name + '.mkv'


def output_path(source: Path, root: Path, output_dir: Path | None) -> Path:
    if output_dir:
        relative = source.relative_to(root)
        candidate = output_dir / relative
        return candidate.with_name(readable_destination(source).name)
    return source.parent / 'MuxMender' / readable_destination(source).name


def rename_identity(path):
    value = path.stat()
    return dict(size=value.st_size, mtime_ns=value.st_mtime_ns,
                device=value.st_dev, inode=value.st_ino)


def check_rename_path(path):
    """Do not follow links/junctions while planning or applying renames."""
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError(f'Rename does not follow links or junctions: {part}')


def rename_release_suffix(source, title):
    """Keep the original release tail verbatim; retain uncertain abbreviations whole."""
    stem = source.stem
    if stem.startswith(title + ' - '):
        return stem[len(title) + 3:]
    prefix = re.match(r'(?i)^([a-z0-9]{2,9})-', stem)
    if prefix and not re.match(re.escape(prefix.group(1)) + r'(?:\b|_)', title, re.I):
        return stem
    match = re.search(r'(?i)(?<![a-z0-9])(?:480[pi]?|576[pi]?|720p?|1080[pi]?|2160p?|4320p?|'
                      r'REPACK|PROPER|WEB[ .-]?DL|WEBRip|Blu[ .-]?Ray|BDRip|HDTV|REMUX|'
                      r'x26[45]|H[ .]?26[45]|HEVC|AV1|AMZN|DDP)(?![a-z0-9])', stem)
    year = re.search(r'(?<!\d)(?:19|20)\d{2}(?!\d)\)?', stem)
    if year and (not match or year.end() <= match.start()) and re.search(r'\((?:19|20)\d{2}\)$', title):
        return stem[year.end():].lstrip(' ._-')
    if match:
        return stem[match.start():]
    # Keep an unclassified suffix after an explicit year instead of discarding it.
    return stem[year.end():].lstrip(' ._-') if year else ''


def create_rename_plan(target, title=None, sidecars=False):
    target = Path(os.path.abspath(target))
    check_rename_path(target)
    if not target.exists():
        raise ValueError('Rename target does not exist')
    if title and not target.is_file():
        raise ValueError('--rename-title requires a single video file')
    root = target.parent if target.is_file() else target
    files = []
    if target.is_file():
        files = [target]
    else:
        for directory, folders, names in os.walk(root, followlinks=False):
            folders[:] = [n for n in folders if not (Path(directory)/n).is_symlink()
                          and not getattr((Path(directory)/n).lstat(), 'st_file_attributes', 0) & 0x400]
            files.extend(Path(directory)/n for n in names if Path(n).suffix.lower() in MEDIA_EXTENSIONS)
    entries = []
    for source in sorted(files):
        if source.suffix.lower() not in MEDIA_EXTENSIONS:
            raise ValueError('Rename target must be a supported video file')
        check_rename_path(source)
        siblings = [p for p in source.parent.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS]
        filename = Path(clean_media_name(source)).stem
        folder = Path(clean_media_name(Path(source.parent.name + '.mkv'))).stem
        dated = lambda value: bool(re.search(r'\((?:19|20)\d{2}\)$', value))
        episode = bool(re.search(r'(?i)\bS\d{1,3}E\d{1,3}', filename))
        reason, name = 'Identity is ambiguous; supply --rename-title for this single file', None
        if title:
            name, reason = Path(clean_media_name(Path(title + '.mkv'))).stem, 'Explicit user-provided title'
        elif episode:
            name, reason = filename, 'Episode identity from filename'
        elif len(siblings) == 1 and dated(folder):
            if dated(filename) and filename[-6:] != folder[-6:]:
                reason = 'Folder and filename years disagree; review required'
            else:
                name, reason = folder, 'Single-video folder title/year; verify identity in preview'
        elif readable_destination(source, preserve_companions=False).stem != source.stem:
            name, reason = readable_destination(source, preserve_companions=False).stem, 'Single-video folder title for cryptic filename; verify identity in preview'
        elif dated(filename) and not re.match(r'(?i)^[a-z0-9]{2,9}-', source.stem):
            name, reason = filename, 'Title/year from filename'
        release = rename_release_suffix(source, name) if name else ''
        destination = source.with_name(name + (' - ' + release if release else '') + source.suffix) if name else None
        entry = dict(source=str(source), destination=str(destination) if destination else None,
                     identity=rename_identity(source), reason=reason, release_suffix=release,
                     status='ready' if destination and destination != source else 'unchanged' if destination else 'needs-review')
        entries.append(entry)
        if sidecars and destination and destination != source:
            for companion in sorted(source.parent.iterdir()):
                if (companion.is_file() and companion.suffix.lower() in {'.srt','.ass','.ssa','.vtt','.sub','.idx','.jpg','.jpeg','.png','.webp'}
                        and companion.name.startswith(source.stem + '.')):
                    check_rename_path(companion)
                    entries.append(dict(source=str(companion), destination=str(companion.with_name(destination.stem + companion.name[len(source.stem):])),
                        identity=rename_identity(companion), parent_source=str(source), reason='Same-basename subtitle/artwork companion', status='ready'))
    destinations = {}
    for entry in entries:
        if entry['status'] != 'ready':
            continue
        destination = Path(entry['destination'])
        key = str(destination).casefold()
        destinations.setdefault(key, []).append(entry)
        if destination.exists():
            entry.update(status='blocked', reason='Destination already exists; no overwrite')
    for group in destinations.values():
        if len(group) > 1:
            for entry in group:
                entry.update(status='blocked', reason='Multiple files would use the same destination')
    states = {e['source']: e['status'] for e in entries}
    for entry in entries:
        if entry.get('parent_source') and states[entry['parent_source']] != 'ready':
            entry.update(status='blocked', reason='Companion video rename is blocked')
    return dict(schema='muxmender-rename-v1', root=str(root), entries=entries,
                note='Preview only. No online identity lookup. Review every ready entry before explicit apply. No folder renames.')


def apply_rename_plan(plan_path):
    plan_path = plan_path.resolve()
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    if plan.get('schema') != 'muxmender-rename-v1':
        raise ValueError('Unsupported rename plan')
    root = Path(plan['root'])
    check_rename_path(root)
    if not root.is_absolute() or not root.is_dir():
        raise ValueError('Rename root must be an existing absolute directory')
    ready = [e for e in plan['entries'] if e['status'] == 'ready']
    ready_sources = {e['source'] for e in ready}
    seen_sources, seen_targets = set(), set()
    for entry in ready:
        source, destination = Path(entry['source']), Path(entry['destination'])
        if entry.get('parent_source') and entry['parent_source'] not in ready_sources:
            raise ValueError('Companion rename requires its video rename in the same plan')
        check_rename_path(source)
        if not source.is_absolute() or not destination.is_absolute() or source.parent != destination.parent:
            raise ValueError('Rename must stay in the same directory')
        source.resolve().relative_to(root.resolve())
        if not source.is_file() or rename_identity(source) != entry['identity']:
            raise ValueError(f'Source changed since preview: {source}')
        if source.suffix != destination.suffix or destination.name.rstrip(' .') != destination.name or re.search(r'[<>:"|?*]', destination.name):
            raise ValueError('Invalid destination or changed file extension')
        if destination.name.split('.')[0].upper() in {'CON','PRN','AUX','NUL', *('COM'+str(n) for n in range(1,10)), *('LPT'+str(n) for n in range(1,10))}:
            raise ValueError('Reserved destination filename')
        if str(source).casefold() in seen_sources or str(destination).casefold() in seen_targets or destination.exists():
            raise ValueError('Duplicate action or destination collision; nothing renamed')
        seen_sources.add(str(source).casefold()); seen_targets.add(str(destination).casefold())
    # Create the durable result journal before any mutation; partial failures are explicit.
    journal = plan_path.with_name(plan_path.stem + '.applied-' + uuid.uuid4().hex[:8] + '.jsonl')
    with journal.open('x', encoding='utf-8') as log:
        for entry in ready:
            source, destination = Path(entry['source']), Path(entry['destination'])
            log.write(json.dumps({'status':'starting','source':str(source),'destination':str(destination)})+'\n')
            log.flush(); os.fsync(log.fileno())
            try:
                check_rename_path(source)
                if rename_identity(source) != entry['identity']:
                    raise ValueError('Source changed after preflight')
                if os.name == 'nt':
                    os.rename(source, destination)  # Windows rejects existing destinations.
                else:
                    os.link(source, destination)  # Exclusive creation; never replaces a target.
                    source.unlink()
                log.write(json.dumps({'status':'renamed','source':str(source),'destination':str(destination)})+'\n')
                log.flush(); os.fsync(log.fileno())
            except Exception as exc:
                log.write(json.dumps({'status':'failed','source':str(source),'destination':str(destination),'error':str(exc)})+'\n')
                raise RuntimeError(f'Rename stopped; review journal {journal}: {exc}') from exc
    return len(ready), journal
