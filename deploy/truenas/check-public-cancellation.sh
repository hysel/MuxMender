#!/usr/bin/env bash
set -euo pipefail
stage=/mnt/FR4G/Apps/muxmender/public-cancellation-20261012-r1
image=sha256:48a3b7a7b3f516225a9c98f7f025d5746ea23579ff4f57aa99864d833fe64b03
[[ $(id -u) = 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
if [[ ${1:-} != --run ]]; then
  systemd-run --unit=muxmender-public-cancellation-20261012-r1 --collect --no-block \
    /usr/bin/bash "$stage/check-public-cancellation.sh" --run
  echo "Generated-media cancellation check started. Status: $stage/result.txt"
  exit 0
fi
exec > >(tee -a "$stage/checks.log") 2>&1
trap 'code=$?; if [[ "$code" != 0 ]]; then printf "status=failed\nexit_code=%s\n" "$code" > "$stage/result.txt"; fi' EXIT
phase() { printf 'status=running\nphase=%s\n' "$1" > "$stage/result.txt"; }
phase 'Checking production is idle before generated GPU work'
python3 - <<'PY'
import json,subprocess,urllib.error,urllib.request
try:
    data=json.load(urllib.request.urlopen('http://truenas:8767/api/controls',timeout=15))
except urllib.error.URLError:
    running=subprocess.check_output(['docker','inspect','--format','{{.State.Running}}',
                                     'ix-muxmender-muxmender-1'],text=True,timeout=15).strip()
    assert running=='false', 'Cannot verify production is idle; no GPU work started'
else:
    assert isinstance(data.get('jobs'),list) and not data.get('snapshot_stale') and not data.get('snapshot_error')
    assert not any(j.get('state') in ('running','queued','pending') for j in data['jobs']), 'Production work is present'
PY
work=$(mktemp -d "$stage/work-XXXXXX")
chmod 755 "$work"
mkdir -m 755 "$work/install"
chown 568:568 "$work/install"
phase 'Cancelling an observed active native stage through normal app controls'
docker run --rm --network none --gpus all --cpus 2 --memory 12g \
  --mount "type=bind,src=$stage,dst=/release-tools,readonly" \
  --mount "type=bind,src=$work/install,dst=/work" --entrypoint /usr/bin/tini \
  "$image" -- python3 -B /release-tools/check_public_installation.py initialize-cancel --work /work
phase 'Checking cancelled history survives container recreation'
docker run --rm --network none --cpus 2 --memory 12g \
  --mount "type=bind,src=$stage,dst=/release-tools,readonly" \
  --mount "type=bind,src=$work/install,dst=/work" --entrypoint /usr/bin/tini \
  "$image" -- python3 -B /release-tools/check_public_installation.py upgrade-cancel --work /work
printf 'status=passed\nphase=Generated cancellation checks passed\nwork=%s\n' "$work" > "$stage/result.txt"
echo 'Generated inputs only. Production and library remain unchanged.'
