#!/usr/bin/env bash
set -euo pipefail
stage=$(cd -- "$(dirname -- "$0")" && pwd -P)
test "$stage" = /mnt/FR4G/Apps/muxmender/release-stage-20261012-v61
test "$(id -u)" = 0
checksum=${1:?Archive checksum required}
[[ "$checksum" =~ ^[a-f0-9]{64}$ ]]
printf '%s  %s\n' "$checksum" "$stage/public-candidate.tar" | sha256sum -c -
if [[ ${2:-} != --run && ${2:-} != --run-finish ]]; then
  mode=--run
  if [[ ${2:-} == --finish ]]; then mode=--run-finish; fi
  systemd-run --unit=muxmender-build-20261012-v61 --collect --no-block \
    /usr/bin/bash "$stage/check-v61.sh" "$checksum" "$mode"
  echo "Detached build started. Results: $stage/result.txt"
  exit 0
fi
exec > >(tee -a "$stage/build.log") 2>&1
trap 'code=$?; if [[ $code != 0 ]]; then printf "status=failed\nexit_code=%s\narchive_sha256=%s\n" "$code" "$checksum" > "$stage/result.txt"; fi' EXIT
phase() { printf 'status=running\nphase=%s\narchive_sha256=%s\n' "$1" "$checksum" > "$stage/result.txt"; }
image=muxmender-app:20261012-v61
if [[ ${2:-} == --run-finish ]]; then
  test "$(docker image inspect --format '{{.Id}}' "$image")" = sha256:a2cd06a2d83e3a32ed0557edcb3b787cde832c4d8e0dc4e360df69ed848c255c
  build=$stage/context-VqTkCfi7
  test -d "$build"
else
if docker image inspect "$image" >/dev/null 2>&1; then
  echo 'Candidate tag already exists; review before retrying. Nothing overwritten.'; exit 1
fi
phase 'Building code-only update on pinned public runtime'
build=$(mktemp -d "$stage/context-XXXXXXXX")
chmod 755 "$build"
tar --no-same-owner -xf "$stage/public-candidate.tar" -C "$build"
docker build -f "$build/deploy/truenas/Dockerfile.update" -t "$image" "$build"
phase 'Packaged runtime and regression checks'
for mode in runtime reaper; do
  docker run --rm --network none --tmpfs /work:rw,uid=568,gid=568,mode=700 \
    --mount "type=bind,src=$build,dst=/qualification,readonly" --entrypoint /usr/bin/tini \
    "$image" -- python3 -B /qualification/tools/smoke_app_release.py "$mode" --version 20261012-v61 --public-runtime
done
fi
phase 'Checking production is paused before generated GPU tests'
python3 - <<'PY'
import json, urllib.request
with urllib.request.urlopen('http://192.168.1.232:8767/api/controls',timeout=15) as response:
    state=json.load(response)
assert state.get('ready') and state.get('paused'), 'Keep production ready and paused'
assert not state.get('snapshot_stale') and not state.get('snapshot_error')
assert isinstance(state.get('jobs'),list)
assert not any(j.get('state') in ('running','queued','pending') for j in state['jobs']), 'Production work remains'
PY
phase 'Generated NVIDIA encoding checks'
docker run --rm --network none --gpus all --memory 8g --cpus 4 \
  --tmpfs /work:rw,uid=568,gid=568,mode=700 --mount "type=bind,src=$build,dst=/qualification,readonly" \
  --entrypoint /usr/bin/tini "$image" -- python3 -B /qualification/tools/smoke_app_release.py gpu --version 20261012-v61 --public-runtime
phase 'Exact image host-receipt dispatch and shared workflow'
mkdir "$build/results"
chown 3005:3005 "$build/results"
docker run --rm --network none --gpus all --memory 8g --cpus 4 --user 3005:3005 \
  --read-only --cap-drop ALL --security-opt no-new-privileges:true --tmpfs /tmp:rw,size=256m \
  --mount "type=bind,src=$build/tools,dst=/release-tools,readonly" \
  --mount 'type=bind,src=/var/lib/muxmender-reader-qualification,dst=/opt/muxmender-host-qualification,readonly' \
  --mount "type=bind,src=$build/results,dst=/work" --entrypoint /usr/bin/tini \
  "$image" -- python3 -B /release-tools/benchmark_shared_sdr_reader.py \
  --binary /opt/muxmender-readers/ffprobe-cuda --output /work/check --codec av1 \
  --pixel-format yuv420p --ffprobe /opt/ffmpeg9/bin/ffprobe --installed-profile
docker image inspect --format '{{.Id}}' "$image" > "$stage/image-id.txt"
printf 'status=passed\nphase=Exact image checks passed\narchive_sha256=%s\nimage=%s\n' "$checksum" "$image" > "$stage/result.txt"
echo 'Candidate checked only. No publication, production deployment or media changes.'
