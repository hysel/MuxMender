#!/bin/bash
set -euo pipefail
stage=/mnt/FR4G/Apps/muxmender/output/ffmpeg-full-qualification-20261010-r5
container=muxmender-ffmpeg9-full-qualification-r5
image=muxmender-ffmpeg9-full-qualification:20261010-r5
[[ $EUID -eq 0 ]] || { echo 'Run with sudo'; exit 1; }
cd "$stage"
sha256sum -c context.sha256
docker inspect "$container" >/dev/null 2>&1 && { echo 'Test container exists; inspect it first'; exit 1; }
[[ ! -e "$stage/work/results" ]] || { echo 'Results exist; refusing to overwrite'; exit 1; }
base=$(docker inspect --format '{{.Image}}' ix-muxmender-muxmender-1)
alias=muxmender-ffmpeg9-full-base:20261010-r5
docker image tag "$base" "$alias"
trap 'docker image rm "$alias" >/dev/null 2>&1 || true' EXIT
mapfile -t devices < <(nvidia-smi --query-gpu=uuid --format=csv,noheader)
[[ ${#devices[@]} -eq 1 && ${devices[0]} == GPU-* ]] || { echo 'Multiple GPUs require an explicit test assignment'; exit 1; }
mkdir -p "$stage/work"
chown 3005:3005 "$stage/work"
chmod 750 "$stage/work"
docker build --pull=false --build-arg "BASE_IMAGE=$alias" -f Dockerfile.ffmpeg-full-qualification -t "$image" .
docker run -d --name "$container" --read-only --cap-drop ALL --security-opt no-new-privileges --memory 8g --cpus 2 \
  --gpus "device=${devices[0]}" --env NVIDIA_DRIVER_CAPABILITIES=compute,video,utility \
  --env TMPDIR=/work --mount "type=bind,src=$stage/work,dst=/work" \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m "$image" --output /work/results
echo 'Generated qualification started. No media mounts, app changes or driver changes.'
