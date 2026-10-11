#!/usr/bin/env bash
set -euo pipefail
version=${1:?Release version required}
checksum=${2:?Archive SHA256 required}
[[ "$version" =~ ^[0-9]{8}-v[0-9]+$ && "$checksum" =~ ^[a-f0-9]{64}$ ]] || exit 2
stage=/mnt/FR4G/Apps/muxmender/release-stage-$version
build=/mnt/FR4G/Apps/muxmender/app-build-$version-${checksum:0:12}
image=muxmender-app:$version
archive=$stage/muxmender-app-$version.tar
script=$stage/stage-release.sh
[[ $(id -u) = 0 ]] || { echo 'Run this staging script with sudo.' >&2; exit 1; }
printf '%s  %s\n' "$checksum" "$archive" | sha256sum -c -
if [[ ${3:-} != --run ]]; then
  unit=muxmender-build-$version
  systemd-run --unit="$unit" --collect --no-block /usr/bin/bash "$script" "$version" "$checksum" --run
  echo "Build started independently of this shell. Status: $stage/result.txt"
  echo "Logs: sudo journalctl -u $unit -f"
  exit 0
fi
trap 'code=$?; if [[ "$code" != 0 ]]; then printf "status=failed\nexit_code=%s\narchive_sha256=%s\n" "$code" "$checksum" > "$stage/result.txt"; fi' EXIT
printf 'status=building\nphase=Preparing build context\narchive_sha256=%s\n' "$checksum" > "$stage/result.txt"
if [[ -e "$build" ]]; then
  [[ -f "$build/.source-sha256" && $(cat "$build/.source-sha256") = "$checksum" ]] || {
    echo 'Existing build context does not match this archive; retained for inspection.' >&2; exit 1;
  }
else
  mkdir -m 755 "$build"
  tar --no-same-owner -xf "$archive" -C "$build"
  printf '%s\n' "$checksum" > "$build/.source-sha256"
fi
test "$(tr -d '\r' < "$build/python/app_version.py" | sed -n "s/^VERSION = '\(.*\)'$/\1/p")" = "$version"
container=muxmender-$version-smoke-$$
started=false
cleanup() {
  if [[ "$started" = true ]]; then docker rm -f "$container" >/dev/null 2>&1 || true; fi
}
finish() {
  code=$?
  cleanup
  if [[ "$code" != 0 ]]; then printf 'status=failed\nexit_code=%s\narchive_sha256=%s\n' "$code" "$checksum" > "$stage/result.txt"; fi
}
trap finish EXIT
phase() { printf 'status=running\nphase=%s\narchive_sha256=%s\n' "$1" "$checksum" > "$stage/result.txt"; }
cd "$build"
phase 'Building Docker image'
docker build -f deploy/truenas/Dockerfile.app -t "$image" . 2>&1 | tee "$stage/build.log"
docker image inspect --format '{{.Id}}' "$image" > "$stage/image-id.txt"
phase 'Packaged runtime and regressions'
for mode in runtime reaper; do
  docker run --rm --network none --tmpfs /work:rw,uid=568,gid=568,mode=700 \
    --mount "type=bind,src=$build,dst=/qualification,readonly" \
    --entrypoint /usr/bin/tini "$image" -- python3 -B /qualification/tools/smoke_app_release.py "$mode" --version "$version"
done
phase 'Dashboard, API and graceful shutdown'
smoke_root=$(mktemp -d "$stage/service-smoke-XXXXXX")
mkdir -m 755 "$smoke_root/media" "$smoke_root/output"
chmod 755 "$smoke_root"
chown 568:568 "$smoke_root/output"
docker run -d --name "$container" --network none \
  --mount "type=bind,src=$smoke_root/media,dst=/media,readonly" \
  --mount "type=bind,src=$smoke_root/output,dst=/output" \
  --env MUXMENDER_BIND=127.0.0.1 --env MUXMENDER_CONTROLS_ENABLED=true \
  --env MUXMENDER_PLAYBACK_CODECS=hevc,av1,h264 "$image" >/dev/null
started=true
docker exec "$container" python3 -B -c \
  'import json,time,urllib.request; u="http://127.0.0.1:8765/"; deadline=time.monotonic()+25
while True:
 try:
  assert b"MuxMender" in urllib.request.urlopen(u,timeout=2).read()
  assert isinstance(json.load(urllib.request.urlopen(u+"api/jobs",timeout=2))["jobs"],list)
  assert urllib.request.urlopen(u+"api/controls",timeout=2).status==200
  print("Dashboard and controls passed"); break
 except Exception:
  if time.monotonic()>deadline:raise
  time.sleep(.25)'
docker stop --timeout 30 "$container" >/dev/null
test "$(docker inspect --format '{{.State.ExitCode}}' "$container")" = 0
cleanup
started=false
phase 'NVIDIA encoding, reader and generated preset validation'
docker run --rm --network none --gpus all --memory 8g --cpus 4 \
  --tmpfs /work:rw,uid=568,gid=568,mode=700 \
  --mount "type=bind,src=$build,dst=/qualification,readonly" \
  --entrypoint /usr/bin/tini "$image" -- python3 -B /qualification/tools/smoke_app_release.py gpu --version "$version"
printf 'image=%s\nid=%s\nstatus=passed\nphase=Image qualification completed\narchive_sha256=%s\n' \
  "$image" "$(cat "$stage/image-id.txt")" "$checksum" > "$stage/result.txt"
trap - EXIT
echo "Built and smoke-tested $image. Production app, queue and media were not changed."
