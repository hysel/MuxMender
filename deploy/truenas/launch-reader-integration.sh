#!/usr/bin/env bash
set -euo pipefail
stage="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd -- "$stage"
sha256sum -c context.sha256
# Wait for serial research to finish; do not add GPU work during its timings.
# Docker needs PID to map host processes to the container.
processes="$(docker top muxmender-research -eo pid,comm)"
if grep -Eq '^[[:space:]]*[0-9]+[[:space:]]+(ffprobe|ffprobe-cuda|ffmpeg)[[:space:]]*$' <<< "$processes"; then
  echo 'A research media reader is active. Wait for the HDR10+ comparison to finish.' >&2
  exit 1
fi
# A reader-free gap between CPU and GPU passes is not completion.
dependency="$(python3 -c 'import json; print(json.load(open("research-dependency.json"))["research_root"])')"
[[ "$dependency" =~ ^/work/hdr-gpu-reader-[0-9a-f]{32}$ ]] || { echo 'Research dependency is invalid' >&2; exit 1; }
docker exec --user 3005:3005 muxmender-research python3 -B -c '
import json,pathlib,sys
jobs=list(pathlib.Path(sys.argv[1]).glob("qualification/reports/*/job.json"))
if len(jobs)!=1:raise SystemExit("Research completion evidence is unavailable")
state=json.loads(jobs[0].read_text())
if state.get("state")!="completed":raise SystemExit("Wait until the complete HDR10+ comparison passes")
' "$dependency"
base="$(docker inspect --format '{{.Image}}' ix-muxmender-muxmender-1)"
[[ "$base" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo 'Installed app image identity is invalid' >&2; exit 1; }
alias='muxmender-reader-integration-base:20261002-r3'
image='muxmender-reader-integration:20261003-r7'
name='muxmender-reader-integration-20261003-r7'
if docker container inspect "$name" >/dev/null 2>&1 || [[ -e "$stage/work" ]]; then
  echo 'This qualification already has a container or work directory; inspect it first.' >&2
  exit 1
fi
if docker image inspect "$alias" >/dev/null 2>&1; then
  [[ "$(docker image inspect --format '{{.Id}}' "$alias")" == "$base" ]] || { echo 'Existing base alias identifies a different image' >&2; exit 1; }
else
  # A named local alias avoids BuildKit treating a bare sha256 ID as a registry.
  docker tag "$base" "$alias"
fi
uuid="$(python3 -c 'import json; print(json.load(open("qualified-reader/qualification.json"))["adapter"]["uuid"])')"
[[ "$uuid" =~ ^GPU-[0-9a-fA-F-]{36}$ ]] || { echo 'Qualified GPU UUID is invalid' >&2; exit 1; }
docker build --pull=false --network=none --build-arg "BASE_IMAGE=$alias" -f Dockerfile.reader-integration -t "$image" .
mkdir -- "$stage/work"
chown 3005:3005 "$stage/work"
chmod 0755 "$stage/work"
docker run -d --name "$name" --read-only --network none --pid=container:muxmender-research --pids-limit 256 --memory 2g --cpus 4 \
  --gpus "device=$uuid" --env "NVIDIA_VISIBLE_DEVICES=$uuid" \
  --env NVIDIA_DRIVER_CAPABILITIES=compute,video,utility,graphics \
  --tmpfs /tmp:rw,nosuid,nodev,size=512m \
  --mount "type=bind,src=$stage/work,dst=/work" "$image"
echo "Detached test started. Monitor: sudo docker logs --follow $name"
echo 'No media/library mounts, production queue changes or original replacements.'
