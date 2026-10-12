#!/usr/bin/env bash
set -euo pipefail
checksum=${1:?Candidate archive SHA256 required}
[[ "$checksum" =~ ^[a-f0-9]{64}$ ]] || exit 2
stage=$(cd -- "$(dirname -- "$0")" && pwd)
case "$stage" in
  /mnt/FR4G/Apps/muxmender/public-image-20261011-r1|/mnt/FR4G/Apps/muxmender/public-image-20261011-r2|/mnt/FR4G/Apps/muxmender/public-image-20261012-r1) ;;
  *) exit 2 ;;
esac
revision=${stage##*/public-image-}
archive=$stage/public-candidate.tar
image=muxmender-public-candidate:$revision
version=20261010-v60
[[ $(id -u) = 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
printf '%s  %s\n' "$checksum" "$archive" | sha256sum -c -
if [[ ${2:-} != --run ]]; then
  systemd-run --unit=muxmender-public-build-$revision --collect --no-block \
    /usr/bin/bash "$stage/launch-public-candidate.sh" "$checksum" --run
  echo "Isolated build launched. Status: $stage/result.txt"
  exit 0
fi
trap 'code=$?; if [[ "$code" != 0 ]]; then printf "status=failed\nexit_code=%s\narchive_sha256=%s\n" "$code" "$checksum" > "$stage/result.txt"; fi' EXIT
phase() { printf 'status=running\nphase=%s\narchive_sha256=%s\n' "$1" "$checksum" > "$stage/result.txt"; }
exec > >(tee -a "$stage/build.log") 2>&1
phase 'Preparing separate public image context'
build=$(mktemp -d "$stage/context-${checksum:0:12}-XXXXXX")
chmod 755 "$build"
tar --no-same-owner -xf "$archive" -C "$build"
phase 'Building clean Ubuntu image'
docker build -f "$build/deploy/truenas/Dockerfile.public" -t "$image" "$build"
phase 'Runtime license inventory'
docker run --rm --network none --mount "type=bind,src=$build/tools,dst=/release-tools,readonly" \
  --entrypoint python3 "$image" -B /release-tools/audit_image_runtime.py --require-redistributable \
  | tee "$stage/runtime-inventory.json"
phase 'Packaged runtime and regressions'
for mode in runtime reaper; do
  docker run --rm --network none --tmpfs /work:rw,uid=568,gid=568,mode=700 \
    --mount "type=bind,src=$build,dst=/qualification,readonly" --entrypoint /usr/bin/tini \
    "$image" -- python3 -B /qualification/tools/smoke_app_release.py "$mode" --version "$version" --public-runtime
done
phase 'Waiting for idle production queue before GPU checks'
python3 - <<'PY'
import json,subprocess,urllib.error,urllib.request
try:
    data=json.load(urllib.request.urlopen('http://truenas:8767/api/controls',timeout=15))
except urllib.error.URLError:
    # Missing API is not evidence of an idle queue. Only an explicitly stopped
    # installed container permits the isolated checks without a queue snapshot.
    state=subprocess.check_output(['docker','inspect','--format','{{.State.Running}}',
                                   'ix-muxmender-muxmender-1'],text=True,timeout=15).strip()
    assert state=='false', 'Installed app is running but its queue cannot be verified; no GPU tests started'
    print('Installed app is stopped; it will not be restarted or changed')
else:
    assert isinstance(data.get('jobs'),list), 'Queue snapshot malformed'
    assert not data.get('snapshot_stale') and not data.get('snapshot_error'), 'Queue snapshot unavailable'
    assert not any(j.get('state') in ('running','queued','pending') for j in data['jobs']), 'Production work present: finish or pause it before isolated GPU checks'
PY
phase 'Generated NVIDIA encoding and reader checks'
docker run --rm --network none --gpus all --memory 8g --cpus 4 \
  --tmpfs /work:rw,uid=568,gid=568,mode=700 --mount "type=bind,src=$build,dst=/qualification,readonly" \
  --entrypoint /usr/bin/tini "$image" -- python3 -B /qualification/tools/smoke_app_release.py gpu --version "$version" --public-runtime
printf 'status=passed\nphase=Candidate runtime and GPU checks passed\nimage=%s\narchive_sha256=%s\n' \
  "$image" "$checksum" > "$stage/result.txt"
echo 'Research candidate only: no registry publication, production update or media mounts.'
