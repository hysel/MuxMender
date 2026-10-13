#!/bin/bash
# Isolated candidate only. Never deploy, publish, mount media, or alter the queue.
set -euo pipefail
stage=/mnt/FR4G/Apps/muxmender/ffmpeg9-native-20261012-r1
checksum=${1:?Context checksum required}
[[ "$checksum" =~ ^[a-f0-9]{64}$ ]] || exit 2
[[ $(id -u) = 0 ]] || { echo 'Run with sudo'; exit 1; }
cd "$stage"
printf '%s  candidate.tar\n' "$checksum" | sha256sum -c -
if [[ ${2:-} != --run ]]; then
  systemd-run --unit=muxmender-ffmpeg9-native-r1 --collect --no-block /bin/bash "$stage/qualify-ffmpeg9-native.sh" "$checksum" --run
  echo "Build and tests launched. Status: $stage/result.txt"
  exit 0
fi
exec >> "$stage/build.log" 2>&1
trap 'code=$?; if [[ $code != 0 ]]; then printf "status=failed\nexit_code=%s\narchive_sha256=%s\n" "$code" "$checksum" > "$stage/result.txt"; fi' EXIT
phase() { printf 'status=running\nphase=%s\narchive_sha256=%s\n' "$1" "$checksum" > "$stage/result.txt"; }
build=$(mktemp -d "$stage/context-XXXXXXXX")
chmod 755 "$build"
tar --no-same-owner -xf candidate.tar -C "$build"
image=muxmender-ffmpeg9-native:20261012-r1
phase 'Building complete FFmpeg 9 candidate'
docker build -f "$build/deploy/truenas/Dockerfile.public" -t "$image" "$build"
docker image inspect "$image" --format '{{.Id}}' > "$stage/image-id.txt"
phase 'Auditing executable and PyAV library versions'
docker run --rm --network none --mount "type=bind,src=$build,dst=/qualification,readonly" --entrypoint python3 "$image" -B /qualification/tools/audit_image_runtime.py --require-redistributable --require-ffmpeg9 > "$stage/runtime-inventory.json"
for mode in runtime reaper; do
  phase "Image checks: $mode"
  docker run --rm --network none --cpus 4 --memory 12g --tmpfs /work:rw,uid=568,gid=568,mode=700 --mount "type=bind,src=$build,dst=/qualification,readonly" --entrypoint /usr/bin/tini "$image" -- python3 -B /qualification/tools/smoke_app_release.py "$mode" --version 20261012-v61 --public-runtime
done
idle() {
python3 - <<'PY'
import json,urllib.request
d=json.load(urllib.request.urlopen('http://truenas:8767/api/controls',timeout=15))
assert isinstance(d.get('jobs'),list) and not d.get('snapshot_stale') and not d.get('snapshot_error'), 'Cannot verify production queue'
assert not any(j.get('state') in ('running','pending','queued') for j in d['jobs']), 'Production queue is not idle'
PY
}
phase 'Checking production is idle before GPU tests'
idle
phase 'Generated GPU encoding tests'
docker run --rm --network none --gpus all --cpus 4 --memory 12g --tmpfs /work:rw,uid=568,gid=568,mode=700 --mount "type=bind,src=$build,dst=/qualification,readonly" --entrypoint /usr/bin/tini "$image" -- python3 -B /qualification/tools/smoke_app_release.py gpu --version 20261012-v61 --public-runtime
for kind in copy cancel; do
  idle
  work=$(mktemp -d "$stage/lifecycle-$kind-XXXXXXXX")
  chown 568:568 "$work"
  chmod 750 "$work"
  for step in initialize upgrade; do
    phase "Generated $kind lifecycle: $step"
    docker run --rm --network none --gpus all --cpus 2 --memory 12g --mount "type=bind,src=$build,dst=/qualification,readonly" --mount "type=bind,src=$work,dst=/work" --entrypoint /usr/bin/tini "$image" -- python3 -B /qualification/tools/check_public_installation.py "$step-$kind" --work /work
  done
done
printf 'status=passed\nphase=Native FFmpeg 9 image and generated lifecycle checks passed\narchive_sha256=%s\nimage=%s\n' "$checksum" "$image" > "$stage/result.txt"
echo 'Private candidate qualified. Source notices and release review remain required. Production unchanged.'
