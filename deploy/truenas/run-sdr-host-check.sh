#!/usr/bin/env bash
set -euo pipefail
stage=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
cd -- "$stage"
test "$(id -u)" = 0 || { echo 'Run this one-time check with sudo.'; exit 1; }
sha256sum -c SHA256SUMS
python3 - <<'PY'
import json,urllib.request
with urllib.request.urlopen('http://192.168.1.232:8767/api/controls',timeout=15) as response:
    state=json.load(response)
if not state.get('ready') or not state.get('paused') or any(state.get('counts',{}).get(k,0) for k in ('running','pending')):
    raise SystemExit('Keep production ready, paused and empty for this isolated comparison.')
PY
image=sha256:20bceb9acd80f3bcf9e6a81312f4eede6d576b06fab978ab48e5da48f10c8c04
test "$(docker inspect --format '{{.Image}}' ix-muxmender-muxmender-1)" = "$image" || {
  echo 'Production image changed; review the qualification runtime before proceeding.'; exit 1;
}
docker image inspect "$image" >/dev/null
if docker container inspect muxmender-sdr-host-check-20261012-r1 >/dev/null 2>&1; then
  echo 'Test container already exists. Inspect it; this script never restarts or deletes it.'; exit 1
fi
python3 -B deploy/truenas/install_reader_qualification.py --bundle private-reader
gpu=$(python3 -c 'import json; print(json.load(open("private-reader/qualification.json"))["adapter"]["uuid"])')
[[ "$gpu" =~ ^GPU-[0-9a-fA-F-]+$ ]] || { echo 'Invalid GPU identity'; exit 1; }
test -d "$stage/results"
docker run -d --pull never --name muxmender-sdr-host-check-20261012-r1 \
  --user 3005:3005 --init --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --tmpfs /tmp:rw,nosuid,size=256m \
  --gpus "device=$gpu" --workdir /work \
  --mount "type=bind,src=$stage/python,dst=/opt/muxmender,readonly" \
  --mount "type=bind,src=$stage/tools,dst=/opt/muxmender-tools,readonly" \
  --mount 'type=bind,src=/var/lib/muxmender-reader-qualification,dst=/opt/muxmender-host-qualification,readonly' \
  --mount "type=bind,src=$stage/results,dst=/work" \
  --entrypoint /usr/bin/python3 "$image" \
  -B /opt/muxmender-tools/benchmark_shared_sdr_reader.py \
  --binary /opt/muxmender-readers/ffprobe-cuda --output /work/check \
  --codec av1 --pixel-format yuv420p --ffprobe /opt/ffmpeg9/bin/ffprobe --installed-profile
echo 'Detached isolated test started. It survives shell logout. Production and media mounts are unchanged.'
