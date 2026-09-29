"""Read-only NVIDIA process telemetry and application-independent yield policy.

The host collector never signals processes or accesses Docker. Only process
identity and utilization are exported, never command arguments/media paths.
"""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time


def proc_identity(pid, root=Path('/proc')):
    path = root/str(pid)
    fields = (path/'stat').read_text().rsplit(')', 1)[1].split()
    status = (path/'status').read_text()
    ids = next(line.split()[1:] for line in status.splitlines() if line.startswith('NSpid:'))
    return dict(namespace=os.readlink(path/'ns/pid'), pid=int(ids[-1]),
                start_ticks=int(fields[19]), parent=int(fields[1]))


def parse_pmon(text, gpu_ids):
    header = None
    rows = []
    for line in text.splitlines():
        words = line.split()
        if words[:2] == ['#', 'gpu'] and 'pid' in words:
            header = words[1:]
            continue
        if not words or words[0] == '#':
            continue
        if not header or len(words) < len(header):
            raise ValueError('Unrecognized NVIDIA process telemetry')
        row = dict(zip(header, words))
        if row.get('pid') == '-':
            continue
        usage = {}
        for key in ('sm', 'enc', 'dec'):
            value = row.get(key, '-')
            if value == '-':
                usage[key] = None
            else:
                number = float(value)
                if not math.isfinite(number) or not 0 <= number <= 100:
                    raise ValueError('Invalid utilization')
                usage[key] = number
        rows.append(dict(gpu=gpu_ids[int(row['gpu'])], host_pid=int(row['pid']),
                         name=row.get('command', 'GPU application')[:80], usage=usage))
    if header is None:
        raise ValueError('Missing NVIDIA process telemetry header')
    return rows


def collect():
    if not sys.platform.startswith('linux'):
        raise RuntimeError('GPU process collector requires Linux')
    def query(args):
        return subprocess.run(['nvidia-smi', *args], check=True, capture_output=True,
                              text=True, timeout=10).stdout
    ids = {int(index.strip()): uuid.strip() for index, uuid in
           (line.split(',', 1) for line in query(['--query-gpu=index,uuid', '--format=csv,noheader']).splitlines())}
    rows = parse_pmon(query(['pmon', '-s', 'um', '-c', '1']), ids)
    complete = True
    for row in rows:
        try:
            row.update(proc_identity(row['host_pid']))
        except (OSError, ValueError, StopIteration, IndexError):
            complete = False
            row['identity_unavailable'] = True
    return dict(schema=1, updated=time.time(), complete=complete,
                gpus=list(ids.values()), processes=rows)


def belongs_to_owner(row, owner_pid, namespace, identity=proc_identity):
    if row.get('namespace') != namespace:
        return False if row.get('namespace') else None
    pid = row.get('pid')
    try:
        current = identity(pid)
        if current['start_ticks'] != row.get('start_ticks'):
            return None  # PID reused since the sample, not proof of outside work.
        seen = set()
        while pid and pid not in seen:
            if pid == owner_pid:
                return True
            seen.add(pid)
            pid = current['parent']
            if pid:
                current = identity(pid)
        return False
    except (OSError, ValueError, KeyError, StopIteration):
        return None


class YieldPolicy:
    def __init__(self, cooldown=60, sustained=5):
        self.cooldown, self.sustained = cooldown, sustained
        self.busy_since = None
        self.last_busy = None
        self.yielding = False

    def decide(self, snapshot, gpu_ids, owner_pid, namespace, now=None, identity=proc_identity):
        now = time.time() if now is None else now
        unknown = dict(state='unavailable', pause=False, block_admission=True,
                       reason='GPU ownership telemetry unavailable; active work continues, new starts wait')
        try:
            age = now-float(snapshot['updated'])
            if (snapshot.get('schema') != 1 or snapshot.get('complete') is not True
                    or not math.isfinite(age) or not 0 <= age <= 15 or not gpu_ids
                    or not set(gpu_ids).issubset(snapshot['gpus'])):
                return unknown
            external = []
            for row in snapshot['processes']:
                if row['gpu'] not in gpu_ids:
                    continue
                owned = belongs_to_owner(row, owner_pid, namespace, identity)
                if owned is None:
                    return unknown
                if owned:
                    continue
                values = [v for v in row['usage'].values() if v is not None]
                if not values or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 100 for v in values):
                    return unknown
                if max(values) >= 3:
                    external.append(row.get('name', 'GPU application'))
            if external:
                if self.busy_since is None:
                    self.busy_since = now
                self.last_busy = now
                self.yielding = self.yielding or now-self.busy_since >= self.sustained
                return dict(state='yielding' if self.yielding else 'busy', pause=self.yielding,
                            block_admission=True, reason='Other GPU activity: '+', '.join(sorted(set(external))))
            self.busy_since = None
            if self.yielding and now-self.last_busy < self.cooldown:
                return dict(state='cooldown', pause=True, block_admission=True,
                            reason='Waiting for sustained GPU quiet before resuming')
            self.yielding = False
            return dict(state='available', pause=False, block_admission=False, reason='No competing GPU activity')
        except (KeyError, TypeError, ValueError, AttributeError):
            return unknown


class YieldController:
    """Shared controller: read trusted host telemetry, lease only owned stages."""
    def __init__(self, lease, telemetry=None):
        self.lease = Path(lease)
        self.telemetry = telemetry or os.environ.get('MUXMENDER_GPU_TELEMETRY')
        self.policy = YieldPolicy()
        self.status = dict(state='off', pause=False, block_admission=False, reason='Automatic GPU yielding is off')
        self.gpus = []
        self.last_gpu_query = 0

    def tick(self, enabled):
        if not enabled:
            self.policy = YieldPolicy()
            self.status = dict(state='off', pause=False, block_admission=False, reason='Automatic GPU yielding is off')
        else:
            snapshot = {}
            try:
                if time.monotonic()-self.last_gpu_query > 60 or not self.gpus:
                    response = subprocess.run(['nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader'],
                                              check=True, capture_output=True, text=True, timeout=5)
                    self.gpus = [line.strip() for line in response.stdout.splitlines() if line.strip()]
                    self.last_gpu_query = time.monotonic()
                if self.telemetry:
                    with Path(self.telemetry).open(encoding='utf-8') as source:
                        snapshot = json.loads(source.read(1024*1024))
                namespace = os.readlink('/proc/self/ns/pid')
                self.status = self.policy.decide(snapshot, self.gpus, os.getpid(), namespace)
            except (OSError, ValueError, subprocess.SubprocessError):
                self.status = dict(state='unavailable', pause=False, block_admission=True,
                                   reason='GPU ownership telemetry unavailable; active work continues, new starts wait')
        # A lost controller releases pauses after 15 seconds. It cannot strand
        # a worker merely because a telemetry refresh failed.
        data = dict(pause=self.status['pause'], expires_at=time.time()+15, reason=self.status['reason'])
        temporary = self.lease.with_suffix('.tmp')
        temporary.write_text(json.dumps(data), encoding='utf-8')
        temporary.replace(self.lease)
        return self.status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if not args.output.is_absolute():
        parser.error('Use an absolute telemetry output path')
    while True:
        try:
            data = collect()
        except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as exc:
            data = dict(schema=1, updated=time.time(), complete=False, error=type(exc).__name__)
        temporary = args.output.with_suffix('.tmp')
        temporary.write_text(json.dumps(data), encoding='utf-8')
        temporary.replace(args.output)
        if args.once:
            return
        time.sleep(2)


if __name__ == '__main__':
    main()
